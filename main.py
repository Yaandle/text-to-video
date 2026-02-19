import os
import re
import sys
import json
import textwrap
import tempfile
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.video.VideoClip import VideoClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip

from elevenlabs.client import ElevenLabs
import config
from code_visualiser import TerminalPreviewGenerator, create_code_video_clip
from graph_visualiser import create_bar_chart_clip, create_line_graph_clip

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

# ── Configuration ──────────────────────────────────────────────────────────────
VIDEO_WIDTH      = config.VIDEO_WIDTH
VIDEO_HEIGHT     = config.VIDEO_HEIGHT
BACKGROUND_COLOR = config.BACKGROUND_COLOR
FPS              = config.FPS
TEXT_COLOR       = config.TEXT_COLOR
FONT_SIZE        = config.FONT_SIZE
FONT_PATH        = config.FONT_PATH_ATKINSON
TEXT_WRAP_WIDTH  = config.TEXT_WRAP_WIDTH
MAX_DISPLAY_LINES = config.MAX_DISPLAY_LINES

# Path to the narrative HTML template (same directory as main.py)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
NARRATIVE_TEMPLATE_PATH = os.path.join(_SCRIPT_DIR, "static", "narrative_visualiser.html")


class ManagedClip:
    """Context manager for automatic clip cleanup."""
    def __init__(self, clip):
        self.clip = clip
    def __enter__(self):
        return self.clip
    def __exit__(self, *args):
        if self.clip:
            self.clip.close()
        return False


# ── Prompt parsing ─────────────────────────────────────────────────────────────

def parse_prompt_with_markers(prompt: str) -> dict:
    """Parse prompt for visualization markers.

    Markers:
        [VisualiseCode]code[/VisualiseCode]
        [VisualiseCode:0]  → static
        [VisualiseCode:1]  → typewriter
        [VisualiseGraph:type|theme]data[/VisualiseGraph]
    """
    sections    = []
    current_pos = 0
    clean_text  = ""

    combined_pattern = (
        r'(\[VisualiseCode(?::[^\]]+)?\].*?\[/VisualiseCode\]'
        r'|\[VisualiseGraph:[^\]]+\].*?\[/VisualiseGraph\])'
    )
    graph_pattern = r'\[VisualiseGraph:([^\]]+)\](.*?)\[/VisualiseGraph\]'
    code_pattern  = r'\[VisualiseCode(?::([^\]]+))?\](.*?)\[/VisualiseCode\]'

    for match in re.finditer(combined_pattern, prompt, re.DOTALL):
        marker_start = match.start()
        marker_text  = match.group(0)

        text_before = prompt[current_pos:marker_start]
        if text_before:
            sections.append({'type': 'text', 'content': text_before})
            clean_text += text_before

        if marker_text.startswith('[VisualiseCode'):
            m = re.search(code_pattern, marker_text, re.DOTALL)
            if m:
                mode_spec = (m.group(1) or "").strip().lower()
                resolved_mode = (
                    "typewriter" if mode_spec in ("1", "typewriter") else
                    "static"     if mode_spec in ("0", "static")     else
                    None
                )
                sections.append({
                    'type':    'code',
                    'content': m.group(2).strip(),
                    'mode':    resolved_mode,
                })

        elif marker_text.startswith('[VisualiseGraph:'):
            m = re.search(graph_pattern, marker_text, re.DOTALL)
            if m:
                parts      = m.group(1).lower().split('|')
                graph_type = parts[0].strip()
                theme      = parts[1].strip() if len(parts) > 1 else None
                sections.append({
                    'type':       'graph',
                    'graph_type': graph_type,
                    'theme':      theme,
                    'content':    m.group(2).strip(),
                })

        current_pos = match.end()

    remaining = prompt[current_pos:]
    if remaining:
        sections.append({'type': 'text', 'content': remaining})
        clean_text += remaining

    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    return {'clean_text': clean_text, 'sections': sections, 'original_prompt': prompt}


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

    text_chars = sum(len(s['content']) for s in filtered if s['type'] == 'text')

    if text_chars == 0:
        dur = total_duration / len(filtered)
        return [{**s, 'start_time': i*dur, 'end_time': (i+1)*dur}
                for i, s in enumerate(filtered)]

    min_required = sum(
        8.0 if s['type'] == 'code' else
        6.0 if s['type'] == 'graph' else 0
        for s in filtered
    )
    actual_duration = max(total_duration, min_required + text_chars * 0.05)
    time_per_char   = (actual_duration - min_required) / text_chars if text_chars else 0

    timed, current = [], 0.0
    for s in filtered:
        dur = (
            len(s['content']) * time_per_char if s['type'] == 'text' else
            10.0 if s['type'] == 'code' else
            6.0
        )
        timed.append({**s, 'start_time': current, 'end_time': current + dur})
        current += dur
    return timed


# ── UI helpers ─────────────────────────────────────────────────────────────────

def display_header():
    print("\n" + "="*60)
    print("TEXT TO VIDEO GENERATOR WITH VISUALIZERS")
    print("="*60 + "\n")


def prompt_yes_no(question: str, default: bool = True) -> bool:
    suffix = " (Y/n): " if default else " (y/N): "
    while True:
        r = input(question + suffix).strip().lower()
        if r == "":            return default
        if r in ("y", "yes"): return True
        if r in ("n", "no"):  return False
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
    """Minimal startup — auto-detects code/graph from sections, skips theme
    questions in file mode."""
    display_header()

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
    }

    if not prefs["generate_audio"]:
        prefs["test_fps"] = 5
        print("ℹ️  Test mode: 5 FPS")
    else:
        prefs["test_fps"] = FPS

    if not file_mode:
        if has_code:
            prefs["code_theme"] = select_from_list(config.CODE_VIS_THEMES, "Code visualiser theme")
        if has_graph:
            prefs["graph_theme"] = select_from_list(["heaven", "dark", "matrix"], "Graph theme")
        prefs["narrative_theme"] = select_from_list(["dark", "heaven", "matrix"], "Narrative text theme")

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


# ── Narrative text → structured line list ─────────────────────────────────────

# Colour sequence cycling across lines (matches Console Narratives palette)
_ACCENT_SEQUENCE = [
    "c-blue-300", "c-teal-300", "c-purple-300", "c-emerald-300",
    "c-yellow-300", "c-amber-300", "c-rose-300", "c-fuchsia-300",
    "c-indigo-300", "c-lime-300", "c-cyan-400", "c-violet-400",
    "c-pink-300", "c-cyan-300", "c-green-400", "c-orange-300",
    "c-fuchsia-400", "c-sky-400", "c-teal-400", "c-amber-200",
]

_TYPE_SEQUENCE = [
    "flow", "recursion", "memory", "structure", "constant",
    "break", "return", "reflection", "meta", "self",
    "evolution", "success", "continue", "invoke", "negation",
    "call", "logic", "question", "depth", "emerge",
]


_PORTRAIT_WRAP_WIDTH = 32   # shorter wrap for tall portrait viewport


def _text_sections_to_narrative_lines(text_sections: list) -> list:
    """Convert text section content to narrative line dicts for the HTML renderer.

    Lines split on newlines first (preserving short punchy lines), then wrapped.
    Bold heuristic: short lines (< 28 chars) every ~5 entries for visual rhythm.
    """
    lines    = []
    global_i = 0
    wrap_w   = _PORTRAIT_WRAP_WIDTH if VIDEO_WIDTH < VIDEO_HEIGHT else TEXT_WRAP_WIDTH

    for sec in text_sections:
        raw = sec['content'].strip()
        paragraphs = [p.strip() for p in raw.splitlines() if p.strip()]
        for para in paragraphs:
            wrapped = textwrap.wrap(para, width=wrap_w) or [para]
            for wline in wrapped:
                colour = _ACCENT_SEQUENCE[global_i % len(_ACCENT_SEQUENCE)]
                ltype  = _TYPE_SEQUENCE[global_i % len(_TYPE_SEQUENCE)]
                bold   = len(wline) < 28 and global_i % 5 == 0
                lines.append({
                    "text":  wline,
                    "color": colour,
                    "type":  ltype,
                    "bold":  bool(bold),
                })
                global_i += 1
    return lines


# ── HTML narrative text clip (Playwright) ─────────────────────────────────────

def create_text_clip_optimized(
    sections: list,
    duration: float,
    theme: str = "dark",
    font=None,
) -> VideoClip:
    """Render narrative text via the Console Narratives HTML template + Playwright.

    Strategy: pre-render one screenshot per line reveal (rolling window of
    MAX_VISIBLE=5 lines, older lines fade out). The screenshot list is then
    mapped evenly across the text portion of the timeline.

    Args:
        sections:  Timed sections from calculate_section_timings.
        duration:  Total clip duration in seconds.
        theme:     "dark" | "heaven" | "matrix".
        font:      Ignored (call-site compatibility).
    """
    import io as _io

    if not HAS_PLAYWRIGHT:
        raise RuntimeError(
            "Playwright required for narrative rendering.\n"
            "Install: pip install playwright && playwright install chromium"
        )

    tmpl_path = os.path.abspath(NARRATIVE_TEMPLATE_PATH)
    with open(tmpl_path, "r", encoding="utf-8") as f:
        template = f.read()

    text_sections = [s for s in sections if s['type'] == 'text']
    all_lines     = _text_sections_to_narrative_lines(text_sections)

    if not all_lines:
        black = np.zeros((VIDEO_HEIGHT, VIDEO_WIDTH, 3), dtype=np.uint8)
        return VideoClip(lambda t: black, duration=duration)

    def _render_html(lines_so_far: list) -> str:
        html = template
        html = html.replace("THEME_PLACEHOLDER",       theme)
        html = html.replace("NARRATIVE_JSON",          json.dumps(lines_so_far))
        html = html.replace("SHOW_BOOT_PLACEHOLDER",   "false")
        html = html.replace("FOOTER_TEXT_PLACEHOLDER", '""'  )
        html = html.replace("LINE_DELAY_PLACEHOLDER",  "0"    )
        return html

    print(f"  🖼  Pre-rendering {len(all_lines)} narrative frames "
          f"({VIDEO_WIDTH}×{VIDEO_HEIGHT}, theme: {theme})...")

    state_frames: list[np.ndarray] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": VIDEO_WIDTH, "height": VIDEO_HEIGHT},
            device_scale_factor=1,
        )
        page = context.new_page()

        for idx in range(len(all_lines)):
            lines_so_far = all_lines[: idx + 1]
            html_str     = _render_html(lines_so_far)
            html_tmp     = os.path.join(
                tempfile.gettempdir(), f"narrative_{idx}.html"
            )
            with open(html_tmp, "w", encoding="utf-8") as f:
                f.write(html_str)

            page.goto(f"file:///{os.path.abspath(html_tmp)}")
            page.wait_for_timeout(900)   # wait for 650ms slide-in + buffer

            png   = page.screenshot(full_page=False)
            img   = Image.open(_io.BytesIO(png)).convert("RGB")
            frame = np.array(img)

            if frame.shape[:2] != (VIDEO_HEIGHT, VIDEO_WIDTH):
                frame = np.array(
                    Image.fromarray(frame).resize(
                        (VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS
                    )
                )

            state_frames.append(frame)
            try:
                os.unlink(html_tmp)
            except OSError:
                pass

            if (idx + 1) % 5 == 0 or idx == len(all_lines) - 1:
                print(f"    ✓ {idx+1}/{len(all_lines)} frames")

        context.close()
        browser.close()

    # Map frames evenly across text timeline
    text_section_timing = [s for s in sections if s['type'] == 'text']
    text_start  = text_section_timing[0]['start_time']  if text_section_timing else 0.0
    text_end    = text_section_timing[-1]['end_time']   if text_section_timing else duration
    text_dur    = max(text_end - text_start, 0.1)
    secs_per_ln = text_dur / len(all_lines)
    last_frame  = state_frames[-1]

    def make_frame(t: float) -> np.ndarray:
        if t < text_start:
            return state_frames[0]
        if t >= text_end:
            return last_frame
        idx = min(int((t - text_start) / secs_per_ln), len(state_frames) - 1)
        return state_frames[idx]

    return VideoClip(make_frame, duration=duration)



# ── Code clip renderer ────────────────────────────────────────────────────────

def render_code_clips_parallel(timed_sections: list, prefs: dict) -> dict:
    """Render code clips serially (Playwright isn't thread-safe)."""
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
        theme = prefs.get('code_theme', config.CODE_VIS_DEFAULT_THEME)
        mode  = section.get('mode') or prefs.get('code_mode', config.CODE_VIS_DEFAULT_MODE)
        try:
            clip = create_code_video_clip(section['content'], theme, mode, config.CODE_VIS_DURATION)
            sec_dur = section['end_time'] - section['start_time']
            clip = clip.resized((VIDEO_WIDTH, VIDEO_HEIGHT))
            clip = clip.with_duration(min(sec_dur, clip.duration))
            clip = clip.with_start(section['start_time'])
            code_clips[i] = clip
            print(f"  ✅ Code clip {i+1} (mode: {mode})")
        except Exception as e:
            print(f"  ❌ Code clip {i+1}: {e}")
            import traceback; traceback.print_exc()
    return code_clips


# ── Graph clip renderer ───────────────────────────────────────────────────────

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
            silent = create_silent_audio(sec_dur)
            fn     = create_bar_chart_clip if graph_type == 'bar' else create_line_graph_clip
            clip   = fn(data=graph_data, title="Data Visualization",
                        audio_clip=silent, theme=theme)
            clip   = clip.with_duration(sec_dur).with_start(section['start_time'])
            graph_clips[i] = clip
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

    # Parse
    parsed     = parse_prompt_with_markers(prompt)
    clean_text = parsed['clean_text']
    sections   = parsed['sections']
    print(f"\n🔍 Parsed {len(sections)} sections:")
    for i, s in enumerate(sections):
        print(f"  {i+1}. {s['type'].upper()}: {s['content'][:60].strip()}...")

    # Audio
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
    else:
        print("\n⏭️  Skipping audio (test mode) — 30s silent placeholder")
        audio_clip = create_silent_audio(30.0)
        audio_path = None

    duration        = audio_clip.duration
    timed_sections  = calculate_section_timings(clean_text, sections, duration, prefs)

    if timed_sections and timed_sections[-1]['end_time'] > duration:
        actual = timed_sections[-1]['end_time']
        print(f"⏱️  Extending duration {duration:.1f}s → {actual:.1f}s")
        if not prefs.get("generate_audio", True):
            audio_clip.close()
            audio_clip = create_silent_audio(actual)
        duration = actual

    # Narrative text clip (HTML/Playwright)
    theme = prefs.get("narrative_theme", getattr(config, 'NARRATIVE_THEME', 'dark'))
    print(f"\n🖼  Building narrative text clip (theme: {theme})...")
    text_clip = create_text_clip_optimized(timed_sections, duration, theme=theme)

    # Code + graph clips
    code_clips  = render_code_clips_parallel(timed_sections, prefs)
    graph_clips = render_graph_clips_parallel(timed_sections, prefs)

    print("\n🎬 Compositing final video...")
    clips      = [text_clip] + list(code_clips.values()) + list(graph_clips.values())
    final_clip = CompositeVideoClip(clips).with_audio(audio_clip)

    video_path = os.path.join(config.OUTPUT_DIR, "output_video.mp4")
    print(f"💾 Exporting → {video_path}")
    final_clip.write_videofile(
        video_path,
        fps=prefs.get("test_fps", FPS),
        codec='libx264',
        preset='ultrafast' if not prefs.get("generate_audio", True) else 'medium',
        audio_codec='aac',
    )
    print("✅ Video saved.")

    # Cleanup
    if prefs.get("generate_audio", True):
        if not save_mp3 and audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
            print("🗑️  MP3 deleted.")
        elif audio_path:
            print(f"🎵 Audio: {audio_path}")
    audio_clip.close()
    final_clip.close()
    for c in list(code_clips.values()) + list(graph_clips.values()):
        c.close()
    return video_path


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    """Main flow.

    File mode  (python main.py prompt.txt) → no theme/mode prompts.
    Interactive (python main.py)           → full prompt flow.
    """
    file_mode = len(sys.argv) > 1

    # Load prompt first so we can parse it before asking preferences
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
        display_header()
        print("Marker syntax:")
        print("  [VisualiseCode:1] ... [/VisualiseCode]   (typewriter)")
        print("  [VisualiseCode:0] ... [/VisualiseCode]   (static)")
        print("  [VisualiseGraph:bar|dark] k:v,k:v [/VisualiseGraph]")
        print()
        prompt = input("Enter text (with optional markers): ").strip()
        if not prompt:
            print("❌ No text provided.")
            return 1

    # Parse early so preferences can be auto-detected
    parsed   = parse_prompt_with_markers(prompt)
    sections = parsed['sections']
    print(f"\n🔍 Detected {len(sections)} sections")

    # Preferences
    prefs = get_startup_preferences(sections, file_mode)

    # Generate
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