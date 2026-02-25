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
from animation_visualiser import generate_animation_clip
from playwright.sync_api import sync_playwright

_SCRIPT_DIR             = os.path.dirname(os.path.abspath(__file__))
NARRATIVE_TEMPLATE_PATH = os.path.join(_SCRIPT_DIR, "static", "narrative_visualiser.html")

# ── Animation timing constants ─────────────────────────────────────────────────
LINE_DURATION_MS  = 1200
_VIS_MIN_DURATION = 10.0   # seconds of display time given to each code/graph section
ANIM_STYLES          = ["typewriter", "wordblurin", "linescan"]


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
        r'(?:'
        r'\[VisualiseCode(?::[^\]]+)?\].*?\[/VisualiseCode\]'
        r'|\[VisualiseGraph:[^\]]+\].*?\[/VisualiseGraph\]'
        r'|\[VisualiseAnimation:[^\]]+\].*?\[/VisualiseAnimation\]'
        r')'
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

        elif marker_text.startswith('[VisualiseAnimation:'):
            m = re.search(r'\[VisualiseAnimation:([^\]]+)\](.*?)\[/VisualiseAnimation\]', marker_text, re.DOTALL)
            if m:
                sections.append({
                    'type':         'animation',
                    'component_id': m.group(1).strip(),
                    'content':      m.group(2).strip(),
                })        

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
    has_animation = any(s['type'] == 'animation' for s in parsed_sections)

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
        "use_animation_visualizer": has_animation,
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

def _build_narrative_html(sections: list, theme: str, anim_style: str) -> tuple[list, str]:
    with open(os.path.abspath(NARRATIVE_TEMPLATE_PATH), "r", encoding="utf-8") as f:
        template = f.read()

    text_sections = [s for s in sections if s['type'] == 'text']
    all_lines     = _text_sections_to_narrative_lines(text_sections)

    css_abs = os.path.abspath(os.path.join(_SCRIPT_DIR, "static", "master.css"))
    css_url = f"file:///{css_abs.replace(os.sep, '/')}"

    html = template
    html = html.replace('href="master.css"',        f'href="{css_url}"')
    html = html.replace("THEME_PLACEHOLDER",         theme)
    html = html.replace("NARRATIVE_JSON",            json.dumps(all_lines))
    html = html.replace("ACTIVE_LINE_IDX",           "0")
    html = html.replace("SHOW_BOOT_PLACEHOLDER",     "false")
    html = html.replace("FOOTER_TEXT_PLACEHOLDER",   '""')
    html = html.replace("LINE_DELAY_PLACEHOLDER",    "0")
    html = html.replace("ANIM_STYLE_PLACEHOLDER",    anim_style)
    html = html.replace("LINE_DURATION_PLACEHOLDER", str(LINE_DURATION_MS))

    return all_lines, html


def create_text_clip_optimized(
    sections: list,
    duration: float,
    theme: str = "dark",
    anim_style: str = "wordblurin",
    playwright_page=None,
) -> VideoClip:
    """Render narrative text via Playwright with pause/resume across vis sections.

    During code/graph windows the text animation is frozen at the last frame
    it reached, then resumes from exactly that point when text comes back.
    This is done by remapping real video time t -> text-only time, skipping
    over every non-text window.
    """
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

    # ── Build remap table ──────────────────────────────────────────────────────
    # For each section we record: (real_start, real_end, kind, value)
    #   kind='text'   → text_ms = (real_t - value) * 1000   where value = accumulated vis seconds before this section
    #   kind='freeze' → text_ms = value (ms) held constant for the whole window
    remap: list = []
    accumulated_vis_s = 0.0

    for s in sections:
        rs  = s['start_time']
        re_ = s['end_time']
        if s['type'] == 'text':
            remap.append((rs, re_, 'text', accumulated_vis_s))
        else:
            frozen_text_s = rs - accumulated_vis_s
            remap.append((rs, re_, 'freeze', frozen_text_s))
            accumulated_vis_s += re_ - rs

    text_total_s = sum(s['end_time'] - s['start_time'] for s in sections if s['type'] == 'text')

    def real_to_text_ms(t: float) -> int:
        for (rs, re_, kind, val) in remap:
            if rs <= t <= re_:
                if kind == 'text':
                    return int((t - val) * 1000)
                else:
                    return int(val * 1000)
        return int(text_total_s * 1000)

    def make_frame(t: float) -> np.ndarray:
        vid_ms = real_to_text_ms(t)
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

def render_code_clips(timed_sections: list, prefs: dict, pw_browser) -> dict:
    """Render code clips by opening a fresh page on the *existing* browser.

    Passing `pw_browser` avoids launching a second Playwright instance (which
    would crash with "sync API inside asyncio loop" because the outer
    sync_playwright context is already running).
    """
    code_clips = {}
    if not prefs.get('use_code_visualizer', True):
        return code_clips
    if not any(s['type'] == 'code' for s in timed_sections):
        return code_clips

    print("\n🎨 Pre-rendering code visualizations...")
    for i, section in enumerate(timed_sections):
        if section['type'] != 'code':
            continue
        theme   = prefs.get('code_theme', config.CODE_VIS_DEFAULT_THEME)
        mode    = section.get('mode') or prefs.get('code_mode', config.CODE_VIS_DEFAULT_MODE)
        sec_dur = section['end_time'] - section['start_time']

        try:
            clip = create_code_video_clip(
                section['content'], theme, mode, config.CODE_VIS_DURATION,
                pw_browser=pw_browser,
            )
            clip = clip.resized((config.VIDEO_WIDTH, config.VIDEO_HEIGHT))
            clip = clip.with_duration(min(sec_dur, clip.duration))
            clip = clip.with_start(section['start_time'])
            code_clips[i] = clip
            print(f"  ✅ Code clip {i+1} (mode: {mode}, start: {section['start_time']:.2f}s, dur: {clip.duration:.2f}s)")
        except Exception as e:
            print(f"  ❌ Code clip {i+1}: {e}")
            import traceback; traceback.print_exc()
    return code_clips


def render_graph_clips(timed_sections: list, prefs: dict) -> dict:
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

def render_animation_clips(timed_sections: list, prefs: dict) -> dict:
    
    animation_clips = {}
    print("\n✨ Pre-rendering animation visualizations...")
    for i, section in enumerate(timed_sections):
        if section['type'] != 'animation':
            continue
        sec_dur = section['end_time'] - section['start_time']
        try:
            clip_path = generate_animation_clip(
                section_text=section.get('content', ''),
                data_string=section['content'],
                explicit_component_id=section.get('component_id', 'auto'),
                width=config.VIDEO_WIDTH,
                height=config.VIDEO_HEIGHT,
            )
            if clip_path:
                from moviepy.video.io.VideoFileClip import VideoFileClip
                clip = VideoFileClip(clip_path)
                clip = clip.resized((config.VIDEO_WIDTH, config.VIDEO_HEIGHT))
                clip = clip.with_duration(min(sec_dur, clip.duration))
                clip = clip.with_start(section['start_time'])
                animation_clips[i] = clip
                print(f"  ✅ Animation clip {i+1} ({section['component_id']}, {sec_dur:.1f}s)")
        except Exception as e:
            print(f"  ❌ Animation clip {i+1}: {e}")
            import traceback; traceback.print_exc()
    return animation_clips





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
    # Each text section is spoken separately so we can insert exact silence gaps
    # where visualiser sections appear.  The final audio is the sections spliced
    # together: spoken_1 | silence_for_vis | spoken_2 | ...
    #
    # This gives us ground-truth start/end times for every section that are
    # locked to the actual audio waveform.

    text_sections = [s for s in sections if s['type'] == 'text']

    # ── Pre-calculate animation duration for each text section ────────────────
    # Each line animates at LINE_DURATION_MS. Audio is time-stretched to match
    # so speech stays exactly in sync with the text appearing on screen.
    wrap_w = 32 if config.VIDEO_WIDTH < config.VIDEO_HEIGHT else config.TEXT_WRAP_WIDTH

    def _anim_duration_for_section(ts: dict) -> float:
        line_count = 0
        for para in [p.strip() for p in ts['content'].strip().splitlines() if p.strip()]:
            line_count += len(textwrap.wrap(para, width=wrap_w) or [para])
        # Add a half-line buffer so audio trails slightly behind text appearance,
        # ensuring words are visible before they are spoken.
        return ((line_count + 0.5) * LINE_DURATION_MS) / 1000.0

    anim_durations = [_anim_duration_for_section(ts) for ts in text_sections]
    print(f"\n📐 Animation durations per text section: {[f'{d:.2f}s' for d in anim_durations]}")

    if prefs.get("generate_audio", True):
        print("\n🎙️  Generating audio (one request per text section)...")
        client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)

        spoken_clips: list[AudioFileClip] = []
        for idx, ts in enumerate(text_sections):
            spoken_text = re.sub(r'\s+', ' ', ts['content']).strip()
            gen = client.text_to_speech.convert(
                text=spoken_text, voice_id=config.VOICE_ID,
                model_id=config.MODEL_ID, output_format="mp3_44100_128",
            )
            part_path = os.path.join(config.OUTPUT_DIR, f"audio_part_{idx}.mp3")
            with open(part_path, "wb") as f:
                for chunk in gen:
                    f.write(chunk)

            raw_clip   = AudioFileClip(part_path)
            target_dur = anim_durations[idx]
            print(f"  ✅ Part {idx+1}: raw={raw_clip.duration:.2f}s  target={target_dur:.2f}s")

            if abs(raw_clip.duration - target_dur) > 0.05:
                speed = max(0.5, min(2.0, raw_clip.duration / target_dur))
                stretched_path = os.path.join(config.OUTPUT_DIR, f"audio_part_{idx}_s.mp3")
                raw_clip.close()
                os.system(
                    f'ffmpeg -y -i "{part_path}" '
                    f'-filter:a "atempo={speed:.6f}" '
                    f'-q:a 2 "{stretched_path}" -loglevel error'
                )
                os.remove(part_path)
                spoken_clips.append(AudioFileClip(stretched_path))
                print(f"     → stretched {speed:.3f}x → {spoken_clips[-1].duration:.2f}s")
            else:
                spoken_clips.append(raw_clip)
    else:
        print("\n⏭️  Skipping audio (test mode)")
        spoken_clips = [create_silent_audio(d) for d in anim_durations]

    # ── Build timeline by walking sections in order ────────────────────────────
    # Interleave spoken clips (for text) and silence gaps (for vis sections).
    timed_sections: list[dict] = []
    spoken_iter    = iter(spoken_clips)
    cursor         = 0.0

    for s in sections:
        if s['type'] not in ('code', 'graph', 'animation'):
            ac  = next(spoken_iter)
            dur = ac.duration
        else:
            dur = _VIS_MIN_DURATION

        # Skip disabled visualiser types but still consume the spoken_iter slot
        if s['type'] == 'code'  and not prefs.get('use_code_visualizer',  True):
            cursor += dur
            continue
        if s['type'] == 'graph' and not prefs.get('use_graph_visualizer', True):
            cursor += dur
            continue

        timed_sections.append({**s, 'start_time': cursor, 'end_time': cursor + dur})
        cursor += dur

    total_duration = cursor

    print("\n⏱️  Section timings:")
    for s in timed_sections:
        label = s['content'][:50].replace('\n', ' ').strip() if s['type'] == 'text' else f"[{s['type'].upper()}]"
        print(f"  {s['type']:5s}  {s['start_time']:6.2f}s → {s['end_time']:6.2f}s  {label!r}")

    # ── Splice audio: spoken parts + silence gaps ──────────────────────────────
    if prefs.get("generate_audio", True):
        from moviepy.audio.AudioClip import concatenate_audioclips

        audio_segments: list[AudioFileClip] = []
        spoken_iter2 = iter(spoken_clips)

        for s in sections:
            if s['type'] not in ('code', 'graph'):
                audio_segments.append(next(spoken_iter2))
            else:
                # Find the timed entry for this vis section to get exact duration
                vis_dur = next(
                    (t['end_time'] - t['start_time'] for t in timed_sections
                     if t['type'] == s['type'] and t['content'] == s['content']),
                    _VIS_MIN_DURATION,
                )
                audio_segments.append(create_silent_audio(vis_dur))

        combined = concatenate_audioclips(audio_segments)
        audio_path = os.path.join(config.OUTPUT_DIR, "output_audio.mp3")
        combined.write_audiofile(audio_path, fps=44100, bitrate="192k", logger=None)
        audio_clip = AudioFileClip(audio_path)
        print(f"  🔊 Final audio: {audio_clip.duration:.2f}s")

        # Clean up part files (both raw and stretched variants)
        for idx in range(len(spoken_clips)):
            for suffix in ["", "_s"]:
                p = os.path.join(config.OUTPUT_DIR, f"audio_part_{idx}{suffix}.mp3")
                if os.path.exists(p):
                    os.remove(p)
    else:
        audio_path = None
        audio_clip = create_silent_audio(total_duration)

    duration = total_duration

    theme      = prefs.get("narrative_theme", getattr(config, 'NARRATIVE_THEME', 'dark'))
    anim_style = prefs.get("narrative_style",  getattr(config, 'NARRATIVE_STYLE', 'wordblurin'))
    print(f"\n🖼  Building narrative text clip  [{anim_style} / {theme}]...")

    # One Playwright instance shared across narrative + code clips
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

        # Pass pw_browser so code_visualiser opens pages on the existing instance
        code_clips  = render_code_clips(timed_sections, prefs, pw_browser)
        graph_clips = render_graph_clips(timed_sections, prefs)
        animation_clips = render_animation_clips(timed_sections, prefs) 
         
        print("\n🎬 Compositing final video...")
        final_clip = CompositeVideoClip(
            [text_clip]
            + list(code_clips.values())
            + list(graph_clips.values())
            + list(animation_clips.values())   
        )

        final_clip.write_videofile(
            video_path,
            fps=prefs.get("test_fps", config.FPS),
            codec='libx264',
            preset='ultrafast' if not prefs.get("generate_audio", True) else 'medium',
            audio=audio_path,
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

    audio_clip.close()
    final_clip.close()
    for c in list(code_clips.values()) + list(graph_clips.values()):
        c.close()

    if prefs.get("generate_audio", True):
        if not save_mp3 and audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
            print("🗑️  MP3 deleted.")
        elif audio_path:
            print(f"🎵 Audio: {audio_path}")

    return video_path



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
        print("\n" + "="*30)
        print("TEXT TO VIDEO ")
        print("="*60)
        print("\nMarker syntax:")
        print("  [VisualiseCode:1] ... [/VisualiseCode]   (typewriter)")
        print("  [VisualiseCode:0] ... [/VisualiseCode]   (static)")
        print("  [VisualiseGraph:bar|dark] k:v,k:v [/VisualiseGraph]")
        print("  [VisualiseAnimation:auto] <data> [/VisualiseAnimation]  (agent selects)")
        print("  [VisualiseAnimation:pie_animated] <data> [/VisualiseAnimation]")
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