import io
import os
import re
import sys
import json
import textwrap
import tempfile

import numpy as np
from PIL import Image

from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.video.VideoClip import VideoClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip

from elevenlabs.client import ElevenLabs
import config
from code_visualiser import create_code_video_clip
from graph_visualiser import create_bar_chart_clip, create_line_graph_clip

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

_SCRIPT_DIR             = os.path.dirname(os.path.abspath(__file__))
NARRATIVE_TEMPLATE_PATH = os.path.join(_SCRIPT_DIR, "static", "narrative_visualiser.html")

# ── Animation timing constants ─────────────────────────────────────────────────
_TW_GLYPH_MS        = 220
_TW_H1_MS           = 1400
_TW_H2_MS           = 900
_TW_BODY_MS         = 600
_WB_WORD_STAGGER_MS = 55
_WB_LINE_BASE_MS    = 80
_WB_H1_ANIM_MS      = 520
_WB_H2_ANIM_MS      = 440
_WB_BODY_ANIM_MS    = 360
_WB_GLYPH_MS        = 180
_LS_GLYPH_MS        = 160
_LS_H1_MS           = 750
_LS_H2_MS           = 580
_LS_BODY_MS         = 440
_CODE_CLIP_LEAD_IN_S = 1.5

# ms per line for deterministic timeline (HTML renderAtTime uses this too)
LINE_DURATION_MS = 1200

ANIM_STYLES = ["typewriter", "wordblurin", "linescan"]


# ── Semantic helpers ───────────────────────────────────────────────────────────

def _hierarchy_class(text: str, bold: bool) -> str:
    wc = len(text.strip().split())
    if bold and wc <= 5: return "h1"
    if bold or  wc <= 4: return "h2"
    return "body"


def _text_sections_to_narrative_lines(text_sections: list) -> list:
    lines, global_i = [], 0
    wrap_w = 32 if config.VIDEO_WIDTH < config.VIDEO_HEIGHT else config.TEXT_WRAP_WIDTH

    for sec in text_sections:
        for para in [p.strip() for p in sec['content'].strip().splitlines() if p.strip()]:
            for wline in textwrap.wrap(para, width=wrap_w) or [para]:
                bold = len(wline) < 28 and global_i % 5 == 0
                lines.append({
                    "text":      wline,
                    "bold":      bool(bold),
                    "hierarchy": _hierarchy_class(wline, bold),
                })
                global_i += 1
    return lines


# ── Prompt parsing ─────────────────────────────────────────────────────────────

def parse_prompt_with_markers(prompt: str) -> dict:
    sections, current_pos, clean_text = [], 0, ""

    combined_pattern = (
        r'(\[VisualiseCode(?::[^\]]+)?\].*?\[/VisualiseCode\]'
        r'|\[VisualiseGraph:[^\]]+\].*?\[/VisualiseGraph\])'
    )
    graph_pattern = r'\[VisualiseGraph:([^\]]+)\](.*?)\[/VisualiseGraph\]'
    code_pattern  = r'\[VisualiseCode(?::([^\]]+))?\](.*?)\[/VisualiseCode\]'

    for match in re.finditer(combined_pattern, prompt, re.DOTALL):
        text_before = prompt[current_pos:match.start()]
        if text_before:
            sections.append({'type': 'text', 'content': text_before})
            clean_text += text_before

        marker_text = match.group(0)
        if marker_text.startswith('[VisualiseCode'):
            m = re.search(code_pattern, marker_text, re.DOTALL)
            if m:
                mode_spec     = (m.group(1) or "").strip().lower()
                resolved_mode = (
                    "typewriter" if mode_spec in ("1", "typewriter") else
                    "static"     if mode_spec in ("0", "static")     else None
                )
                sections.append({'type': 'code', 'content': m.group(2).strip(), 'mode': resolved_mode})

        elif marker_text.startswith('[VisualiseGraph:'):
            m = re.search(graph_pattern, marker_text, re.DOTALL)
            if m:
                parts      = m.group(1).lower().split('|')
                graph_type = parts[0].strip()
                theme      = parts[1].strip() if len(parts) > 1 else None
                sections.append({'type': 'graph', 'graph_type': graph_type, 'theme': theme, 'content': m.group(2).strip()})

        current_pos = match.end()

    remaining = prompt[current_pos:]
    if remaining:
        sections.append({'type': 'text', 'content': remaining})
        clean_text += remaining

    return {
        'clean_text':      re.sub(r'\s+', ' ', clean_text).strip(),
        'sections':        sections,
        'original_prompt': prompt,
    }


def parse_graph_data(content: str) -> dict:
    data = {}
    for pair in content.split(','):
        parts = pair.strip().split(':')
        if len(parts) == 2:
            try:
                data[parts[0].strip()] = float(parts[1].strip())
            except ValueError:
                pass
    return data


# ── Section timing ─────────────────────────────────────────────────────────────

def calculate_section_timings(clean_text, sections, total_duration, prefs):
    filtered = [
        s for s in sections
        if not (s['type'] == 'code'  and not prefs.get('use_code_visualizer',  True))
        and not (s['type'] == 'graph' and not prefs.get('use_graph_visualizer', True))
    ]
    if not filtered:
        return []

    text_chars   = sum(len(s['content']) for s in filtered if s['type'] == 'text')
    min_required = sum(8.0 if s['type'] == 'code' else 6.0 if s['type'] == 'graph' else 0 for s in filtered)

    if text_chars == 0:
        dur = total_duration / len(filtered)
        return [{**s, 'start_time': i * dur, 'end_time': (i + 1) * dur} for i, s in enumerate(filtered)]

    actual_duration = max(total_duration, min_required + text_chars * 0.05)
    time_per_char   = (actual_duration - min_required) / text_chars

    timed, current = [], 0.0
    for s in filtered:
        dur = len(s['content']) * time_per_char if s['type'] == 'text' else 10.0 if s['type'] == 'code' else 6.0
        timed.append({**s, 'start_time': current, 'end_time': current + dur})
        current += dur
    return timed


# ── UI helpers ─────────────────────────────────────────────────────────────────

def prompt_yes_no(question: str, default: bool = True) -> bool:
    suffix = " (Y/n): " if default else " (y/N): "
    while True:
        r = input(question + suffix).strip().lower()
        if r == "":          return default
        if r in ("y","yes"): return True
        if r in ("n","no"):  return False
        print("❌ Please enter 'y' or 'n'.")


def select_from_list(items, prompt="Select an option"):
    print(f"\n{prompt}:")
    for i, item in enumerate(items, 1):
        print(f"  {i}. {item}")
    while True:
        try:
            choice = int(input("Enter number: ").strip()) - 1
            if 0 <= choice < len(items):
                return items[choice]
            print(f"❌ Enter 1–{len(items)}.")
        except ValueError:
            print("❌ Enter a valid number.")


def get_startup_preferences(parsed_sections: list, file_mode: bool) -> dict:
    print("\n" + "="*60)
    print("TEXT TO VIDEO GENERATOR WITH VISUALIZERS")
    print("="*60 + "\n")

    has_code  = any(s['type'] == 'code'  for s in parsed_sections)
    has_graph = any(s['type'] == 'graph' for s in parsed_sections)

    prefs = {
        "generate_audio":       prompt_yes_no("Generate audio? (N to skip for testing)", default=True),
        "save_mp3":             prompt_yes_no("Save MP3 audio file?", default=True),
        "use_code_visualizer":  has_code,
        "use_graph_visualizer": has_graph,
        "code_theme":           config.CODE_VIS_DEFAULT_THEME,
        "code_mode":            config.CODE_VIS_DEFAULT_MODE,
        "graph_theme":          getattr(config, 'GRAPH_VIS_DEFAULT_THEME', 'dark'),
        "narrative_theme":      getattr(config, 'NARRATIVE_THEME', 'dark'),
        "narrative_style":      getattr(config, 'NARRATIVE_STYLE', 'wordblurin'),
    }

    prefs["test_fps"] = config.FPS if prefs["generate_audio"] else 5
    if not prefs["generate_audio"]:
        print("ℹ️  Test mode: 5 FPS")

    if not file_mode:
        if has_code:
            prefs["code_theme"] = select_from_list(config.CODE_VIS_THEMES, "Code visualiser theme")
        if has_graph:
            prefs["graph_theme"] = select_from_list(["heaven","dark","matrix"], "Graph theme")
        prefs["narrative_theme"] = select_from_list(["dark","heaven","matrix"], "Narrative text theme")
        prefs["narrative_style"] = select_from_list(ANIM_STYLES, "Narrative animation style")

    print(f"\n  ✓ Narrative: theme={prefs['narrative_theme']}, style={prefs['narrative_style']}")
    return prefs


# ── Audio helpers ──────────────────────────────────────────────────────────────

def create_silent_audio(duration: float) -> AudioFileClip:
    import wave
    tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    tmp.close()
    with wave.open(tmp.name, 'w') as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        chunk = b'\x00\x00' * 44100
        for _ in range(int(duration)):
            wav.writeframes(chunk)
        rem = int((duration % 1) * 44100)
        if rem:
            wav.writeframes(b'\x00\x00' * rem)
    return AudioFileClip(tmp.name)


# ── Narrative text → HTML clip (Playwright, deterministic timeline) ────────────

def _build_narrative_html(
    sections: list,
    theme: str,
    anim_style: str,
) -> tuple[list, str]:
    """Prepare narrative lines and rendered HTML string. Returns (all_lines, html_str)."""
    with open(os.path.abspath(NARRATIVE_TEMPLATE_PATH), "r", encoding="utf-8") as f:
        template = f.read()

    text_sections = [s for s in sections if s['type'] == 'text']
    all_lines     = _text_sections_to_narrative_lines(text_sections)

    css_abs = os.path.abspath(os.path.join(_SCRIPT_DIR, "static", "master.css"))
    css_url = f"file:///{css_abs.replace(os.sep, '/')}"

    html = template
    html = html.replace('href="master.css"',      f'href="{css_url}"')
    html = html.replace("THEME_PLACEHOLDER",       theme)
    html = html.replace("NARRATIVE_JSON",          json.dumps(all_lines))
    html = html.replace("ACTIVE_LINE_IDX",         "0")
    html = html.replace("SHOW_BOOT_PLACEHOLDER",   "false")
    html = html.replace("FOOTER_TEXT_PLACEHOLDER", '""')
    html = html.replace("LINE_DELAY_PLACEHOLDER",  "0")
    html = html.replace("ANIM_STYLE_PLACEHOLDER",  anim_style)
    html = html.replace("LINE_DURATION_PLACEHOLDER", str(LINE_DURATION_MS))

    return all_lines, html


def create_text_clip_optimized(
    sections: list,
    duration: float,
    theme: str = "dark",
    anim_style: str = "wordblurin",
    playwright_page=None,
) -> VideoClip:
    """Render narrative text via narrative_visualiser.html + Playwright.

    Uses a deterministic time-driven approach: MoviePy calls make_frame(t),
    which pushes window.__videoTime into the page. The HTML renderAtTime()
    function advances the narrative based on that value.

    IMPORTANT: `playwright_page` must be a live Playwright Page object whose
    browser/context will remain open for the entire duration of write_videofile().
    The caller (generate_main_video) owns the Playwright lifecycle.

    LINE_DURATION_MS in this file must match LINE_DURATION in the HTML.
    """
    if not HAS_PLAYWRIGHT:
        raise RuntimeError(
            "Playwright required.\n"
            "Install: pip install playwright && playwright install chromium"
        )

    if playwright_page is None:
        raise RuntimeError(
            "create_text_clip_optimized requires a live `playwright_page` argument.\n"
            "Playwright must be started in the caller and kept alive until after "
            "write_videofile() completes."
        )

    if anim_style not in ANIM_STYLES:
        print(f"  ⚠️  Unknown style '{anim_style}', falling back to 'wordblurin'")
        anim_style = "wordblurin"

    all_lines, html_str = _build_narrative_html(sections, theme, anim_style)

    if not all_lines:
        black = np.zeros((config.VIDEO_HEIGHT, config.VIDEO_WIDTH, 3), dtype=np.uint8)
        return VideoClip(lambda t: black, duration=duration)

    tmp_path = os.path.join(tempfile.gettempdir(), "narrative_full.html")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(html_str)

    print(
        f"  🖼  Deterministic render: {len(all_lines)} lines  "
        f"[{anim_style} / {theme}]  LINE_DURATION={LINE_DURATION_MS}ms"
    )

    page = playwright_page
    page.goto(f"file:///{os.path.abspath(tmp_path)}")
    page.wait_for_timeout(300)

    try:
        os.unlink(tmp_path)
    except OSError:
        pass

    # Work out which portion of the video timeline is text
    text_section_timing = [s for s in sections if s['type'] == 'text']
    text_start = text_section_timing[0]['start_time']  if text_section_timing else 0.0
    text_end   = text_section_timing[-1]['end_time']   if text_section_timing else duration

    # Capture the initial frame (used for t < text_start)
    first_png   = page.screenshot(full_page=False)
    first_frame = np.array(Image.open(io.BytesIO(first_png)).convert("RGB"))

    def make_frame(t: float) -> np.ndarray:
        if t < text_start:
            return first_frame

        rel_t  = min(t - text_start, text_end - text_start)
        vid_ms = int(rel_t * 1000)

        page.evaluate(f"window.__videoTime = {vid_ms}")

        png   = page.screenshot(full_page=False)
        frame = np.array(Image.open(io.BytesIO(png)).convert("RGB"))

        if frame.shape[:2] != (config.VIDEO_HEIGHT, config.VIDEO_WIDTH):
            frame = np.array(
                Image.fromarray(frame).resize(
                    (config.VIDEO_WIDTH, config.VIDEO_HEIGHT), Image.LANCZOS
                )
            )
        return frame

    return VideoClip(make_frame, duration=duration)


# ── Visualiser clip renderers ─────────────────────────────────────────────────

def _extract_code_title(code: str) -> str:
    for line in code.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        for kw in ('async def ', 'def ', 'class '):
            if line.startswith(kw):
                name = line[len(kw):].split('(')[0].split(':')[0].strip()
                return f"{kw.strip()} {name}"
        if '=' in line and not line.startswith(('if ', 'while ', 'for ', 'return')):
            var = line.split('=')[0].strip()
            if var.isidentifier():
                return var
        return line[:40] + ('...' if len(line) > 40 else '')
    return "script.py"


def render_code_clips_parallel(timed_sections: list, prefs: dict) -> dict:
    code_clips = {}
    if not prefs.get('use_code_visualizer', True):
        return code_clips
    if not any(s['type'] == 'code' for s in timed_sections):
        return code_clips
    if not HAS_PLAYWRIGHT:
        print("\n❌ Playwright required for code visualization.")
        return code_clips

    print("\n🎨 Pre-rendering code visualizations...")
    for i, section in enumerate(timed_sections):
        if section['type'] != 'code':
            continue
        theme   = prefs.get('code_theme', config.CODE_VIS_DEFAULT_THEME)
        mode    = section.get('mode') or prefs.get('code_mode', config.CODE_VIS_DEFAULT_MODE)
        sec_dur = section['end_time'] - section['start_time']
        lead_in = min(_CODE_CLIP_LEAD_IN_S, sec_dur * 0.5)

        try:
            clip = create_code_video_clip(section['content'], theme, mode, config.CODE_VIS_DURATION)
            clip = clip.resized((config.VIDEO_WIDTH, config.VIDEO_HEIGHT))
            clip = clip.with_duration(min(sec_dur - lead_in, clip.duration))
            clip = clip.with_start(section['start_time'] + lead_in)
            code_clips[i] = clip
            print(f"  ✅ Code clip {i+1} (mode: {mode}, lead-in: {lead_in:.2f}s)")
        except Exception as e:
            print(f"  ❌ Code clip {i+1}: {e}")
            import traceback; traceback.print_exc()
    return code_clips


def render_graph_clips_parallel(timed_sections: list, prefs: dict) -> dict:
    graph_clips = {}
    if not prefs.get('use_graph_visualizer', True):
        return graph_clips

    print("\n📊 Pre-rendering graph visualizations...")
    for i, section in enumerate(timed_sections):
        if section['type'] != 'graph':
            continue
        graph_type = section.get('graph_type', 'bar')
        theme      = section.get('theme') or prefs.get('graph_theme', 'dark')
        graph_data = parse_graph_data(section['content'])
        if not graph_data:
            print(f"  ⚠️  No data in graph section {i+1}")
            continue
        sec_dur = section['end_time'] - section['start_time']
        try:
            fn          = create_bar_chart_clip if graph_type == 'bar' else create_line_graph_clip
            clip        = fn(data=graph_data, title="Data Visualization",
                             audio_clip=create_silent_audio(sec_dur), theme=theme)
            graph_clips[i] = clip.with_duration(sec_dur).with_start(section['start_time'])
            print(f"  ✅ Graph clip {i+1} ({graph_type}, {sec_dur:.1f}s)")
        except Exception as e:
            print(f"  ❌ Graph clip {i+1}: {e}")
            import traceback; traceback.print_exc()
    return graph_clips


# ── Main video generator ──────────────────────────────────────────────────────

def generate_main_video(prompt: str, save_mp3: bool = True, prefs: dict = None) -> str:
    if prefs is None:
        prefs = {}

    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    video_path = os.path.join(config.OUTPUT_DIR, "output_video.mp4")
    parsed     = parse_prompt_with_markers(prompt)
    clean_text = parsed['clean_text']
    sections   = parsed['sections']
    print(f"\n🔍 Parsed {len(sections)} sections:")
    for i, s in enumerate(sections):
        print(f"  {i+1}. {s['type'].upper()}: {s['content'][:60].strip()}...")

    # ── Audio ──────────────────────────────────────────────────────────────────
    if prefs.get("generate_audio", True):
        print("\n🎙️  Generating audio...")
        client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)
        gen    = client.text_to_speech.convert(
            text=clean_text, voice_id=config.VOICE_ID,
            model_id=config.MODEL_ID, output_format="mp3_44100_128",
        )
        audio_path = os.path.join(config.OUTPUT_DIR, "output_audio.mp3")
        with open(audio_path, "wb") as f:
            for chunk in gen:
                f.write(chunk)
        print("  ✅ Audio generated")
        audio_clip = AudioFileClip(audio_path)
        print(f"  🔊 Audio duration: {audio_clip.duration:.2f}s, fps: {audio_clip.fps}")
    else:
        print("\n⏭️  Skipping audio (test mode) — 30s silent placeholder")
        audio_clip = create_silent_audio(30.0)
        audio_path = None

    duration       = audio_clip.duration
    timed_sections = calculate_section_timings(clean_text, sections, duration, prefs)

    if timed_sections and timed_sections[-1]['end_time'] > duration:
        duration = timed_sections[-1]['end_time']
        print(f"⏱️  Extending duration → {duration:.1f}s")
        if not prefs.get("generate_audio", True):
            audio_clip.close()
            audio_clip = create_silent_audio(duration)

    theme      = prefs.get("narrative_theme", getattr(config, 'NARRATIVE_THEME', 'dark'))
    anim_style = prefs.get("narrative_style",  getattr(config, 'NARRATIVE_STYLE', 'wordblurin'))
    print(f"\n🖼  Building narrative text clip  [{anim_style} / {theme}]...")

    pw         = sync_playwright().start()
    pw_browser = pw.chromium.launch(headless=True)
    pw_context = pw_browser.new_context(
        viewport={"width": config.VIDEO_WIDTH, "height": config.VIDEO_HEIGHT},
        device_scale_factor=1,
    )
    pw_page = pw_context.new_page()

    try:
        text_clip = create_text_clip_optimized(
            timed_sections, duration,
            theme=theme, anim_style=anim_style,
            playwright_page=pw_page,
        )

        code_clips  = render_code_clips_parallel(timed_sections, prefs)
        graph_clips = render_graph_clips_parallel(timed_sections, prefs)

        _OVERLAY_DELAY_S = 2.0
        for clips_dict in (code_clips, graph_clips):
            for key, clip in clips_dict.items():
                clips_dict[key] = clip.with_start(clip.start + _OVERLAY_DELAY_S).with_duration(
                    max(0.1, clip.duration - _OVERLAY_DELAY_S)
                )

        print("\n🎬 Compositing final video...")
        final_clip = CompositeVideoClip(
            [text_clip] + list(code_clips.values()) + list(graph_clips.values())
        )

        final_clip.write_videofile(
            video_path,
            fps=prefs.get("test_fps", config.FPS),
            codec='libx264',
            preset='ultrafast' if not prefs.get("generate_audio", True) else 'medium',
            audio=audio_path,          # ← pass the path directly
            audio_codec='aac',
            audio_fps=44100,
            audio_bitrate='192k',
        )
        print("✅ Video saved.")

    finally:
        try:
            pw_context.close()
            pw_browser.close()
            pw.stop()
        except Exception:
            pass

    # Close all clips before touching the MP3 file
    audio_clip.close()
    final_clip.close()
    for c in list(code_clips.values()) + list(graph_clips.values()):
        c.close()

    # Now safe to delete
    if prefs.get("generate_audio", True):
        if not save_mp3 and audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
            print("🗑️  MP3 deleted.")
        elif audio_path:
            print(f"🎵 Audio: {audio_path}")

    return video_path

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    file_mode = len(sys.argv) > 1

    if file_mode:
        try:
            with open(sys.argv[1], 'r', encoding='utf-8') as f:
                prompt = f.read().strip()
        except FileNotFoundError:
            print(f"❌ File not found: {sys.argv[1]}")
            return 1
        if not prompt:
            print("❌ File is empty.")
            return 1
        print(f"✓ Loaded from {sys.argv[1]}")
    else:
        print("\n" + "="*60)
        print("TEXT TO VIDEO GENERATOR WITH VISUALIZERS")
        print("="*60)
        print("\nMarker syntax:")
        print("  [VisualiseCode:1] ... [/VisualiseCode]   (typewriter)")
        print("  [VisualiseCode:0] ... [/VisualiseCode]   (static)")
        print("  [VisualiseGraph:bar|dark] k:v,k:v [/VisualiseGraph]")
        print()
        prompt = input("Enter text (with optional markers): ").strip()
        if not prompt:
            print("❌ No text provided.")
            return 1

    prefs      = get_startup_preferences(parse_prompt_with_markers(prompt)['sections'], file_mode)
    video_path = generate_main_video(prompt, save_mp3=prefs["save_mp3"], prefs=prefs)
    if not video_path:
        return 1

    print("\n" + "="*60)
    print("✅ GENERATION COMPLETE")
    print("="*60)
    print(f"\n📹 Video: {video_path}")
    if prefs.get("save_mp3") and prefs.get("generate_audio"):
        print(f"🎵 Audio: {os.path.join(config.OUTPUT_DIR, 'output_audio.mp3')}")
    print()
    return 0


if __name__ == "__main__":
    exit(main())