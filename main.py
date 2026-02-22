import os
import re
import sys
import json
import bisect
import textwrap
import tempfile
import math

import numpy as np
from PIL import Image

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
VIDEO_WIDTH       = config.VIDEO_WIDTH
VIDEO_HEIGHT      = config.VIDEO_HEIGHT
BACKGROUND_COLOR  = config.BACKGROUND_COLOR
FPS               = config.FPS
TEXT_COLOR        = config.TEXT_COLOR
FONT_SIZE         = config.FONT_SIZE
FONT_PATH         = config.FONT_PATH_ATKINSON
TEXT_WRAP_WIDTH   = config.TEXT_WRAP_WIDTH
MAX_DISPLAY_LINES = config.MAX_DISPLAY_LINES

_SCRIPT_DIR             = os.path.dirname(os.path.abspath(__file__))
NARRATIVE_TEMPLATE_PATH = os.path.join(_SCRIPT_DIR, "static", "narrative_visualiser.html")

# ── Animation timing constants (must match narrative_visualiser.html) ──────────
#
# Typewriter timing: glyph types in, then text types in per-char
_TW_GLYPH_MS   = 220    # ms to type in the glyph prefix
_TW_H1_MS      = 1400   # text typewriter duration for h1
_TW_H2_MS      = 900    # text typewriter duration for h2
_TW_BODY_MS    = 600    # text typewriter duration for body

# Word blur-in timing
_WB_WORD_STAGGER_MS = 55
_WB_LINE_BASE_MS    = 80
_WB_H1_ANIM_MS      = 820
_WB_H2_ANIM_MS      = 770
_WB_BODY_ANIM_MS    = 680
_WB_GLYPH_MS        = 180   # glyph types in before words

# Line scan timing
_LS_GLYPH_MS    = 160
_LS_H1_MS       = 750
_LS_H2_MS       = 580
_LS_BODY_MS     = 440

_BURST_FRAMES   = 8     # screenshots captured per line reveal
_BURST_BUFFER   = 150   # ms safety buffer after animation

ANIM_STYLES = ["typewriter", "wordblurin", "linescan"]

# ── Glyph + semantic type mapping ─────────────────────────────────────────────
GLYPH_PREFIXES = {
    "process":"→","function":"ƒ","invoke":"⟼","return":"↩","flow":"⇒",
    "chain":"⋯","depth":"⋮","stack":"⟨⟩","thread":"⤷","call":"→",
    "recursion":"∞","reflection":"⟲","meta":"◊","self":"◉","witness":"◎",
    "evolution":"Δ","emerge":"⇡","loop":"⊚",
    "negation":"¬","void":"∅","therefore":"∴","structure":"{}","break":"⟂",
    "success":"✓","singular":"✦","threshold":"⟁","operator":"⊕","query":"?",
    "memory":"mem","exception":"!",
    "past":"←","future":"⇢","now":"●","change":"⇄",
    "lambda":"λ","xor":"⊕","tensor":"⊗","sum":"∑","product":"∏",
    "integral":"∫","gradient":"∇","approx":"≈","identity":"≡","similar":"⌁",
    "entail":"⊢","models":"⊨","element":"∈","subset":"⊂","union":"∪",
    "intersect":"∩","command":"⌘","hash":"⌗","transform":"⌬","id":"#",
    "angle":"𝜃","velocity":"𝜔","accel":"𝛼","torque":"τ","control":"⟳",
    "boundary":"⎔","layer":"⧉","target":"⌖","stable":"⎊","delay":"⧖",
    "energy":"E","flux":"Φ","resist":"Ω","variance":"σ","density":"ρ",
    "wave":"ψ","planck":"ℏ","discharge":"⚡",
    "source":"☉","cycle":"☽","balance":"⚖","portal":"⟡","eye":"𓂀",
    "duality":"☯","star":"✶","oppose":"☍",
    "wait":"⧗","timeout":"⧖","parallel":"⧑","sync":"⧓","aggregate":"⊞",
    "subtract":"⊟","block":"⊠","inactive":"◌","cancel":"⊘",
    "comment":"//","constant":"const","variable":"var","keyword":"kw",
    "class":"◻","type":"T","string":'"',"interface":"⌘","method":"m",
    "property":"prop","analogy":"~","logic":"∴","continue":"…",
}

_KEYWORD_TYPE_MAP = [
    (["run","execute","call","trigger","start","launch"],          "invoke"),
    (["return","output","result","yield","emit","produce"],        "return"),
    (["flow","pipeline","stream","pipe","chain","sequence"],       "flow"),
    (["depth","layer","level","nested","deep","stack"],            "depth"),
    (["thread","async","parallel","concurrent","worker"],          "thread"),
    (["learn","adapt","evolve","improve","grow","train"],          "evolution"),
    (["loop","cycle","repeat","iterate","again","recurse"],        "recursion"),
    (["self","itself","own","internal","intrinsic"],               "self"),
    (["reflect","observe","monitor","watch","inspect"],            "reflection"),
    (["emerge","arise","surface","appear","birth"],                "emerge"),
    (["not","never","no","without","absence","lack"],              "negation"),
    (["if","when","condition","whether","unless","decide"],        "query"),
    (["break","halt","stop","end","terminate","exit"],             "break"),
    (["success","done","complete","achieve","accomplish","win"],   "success"),
    (["structure","pattern","framework","system","architecture"],  "structure"),
    (["memory","store","cache","remember","retain","persist"],     "memory"),
    (["before","past","history","prior","previous","old"],         "past"),
    (["future","next","ahead","coming","tomorrow","soon"],         "future"),
    (["now","current","present","today","immediate","live"],       "now"),
    (["change","shift","transform","transition","update","alter"], "change"),
    (["data","dataset","record","row","table","database"],         "models"),
    (["model","train","predict","infer","classify","detect"],      "models"),
    (["hash","key","index","id","identifier","lookup"],            "hash"),
    (["merge","join","combine","union","aggregate","group"],       "union"),
    (["sum","total","count","add","accumulate","tally"],           "sum"),
    (["gradient","descent","loss","optimize","minimize","backprop"],"gradient"),
    (["tensor","matrix","vector","array","dimension","shape"],     "tensor"),
    (["integral","area","continuous","converge","limit"],          "integral"),
    (["power","energy","strength","force","capacity","resource"],  "energy"),
    (["wave","signal","frequency","pulse","oscillate","resonate"], "wave"),
    (["balance","stable","equilibrium","steady","constant","maintain"],"balance"),
    (["source","origin","root","begin","genesis","initial"],       "source"),
    (["portal","gateway","bridge","connect","link","path"],        "portal"),
    (["star","highlight","notable","key","important","critical"],  "star"),
    (["dual","both","two","pair","either","or"],                   "duality"),
    (["fast","speed","quick","rapid","instant","accelerate"],      "invoke"),
    (["build","create","make","construct","generate","produce"],   "structure"),
    (["think","idea","concept","vision","imagine","insight"],      "meta"),
    (["question","ask","why","how","what"],                        "query"),
    (["time","moment","second","minute","hour","day"],             "now"),
]

_POSITIONAL_TYPES = [
    "flow","depth","recursion","structure","memory","evolution","now",
    "invoke","return","emerge","gradient","source","change","balance",
    "wave","negation","success","query","portal","star","thread",
    "reflection","union","sum","identity","threshold","singular",
    "void","therefore","loop",
]

_ACCENT_SEQUENCE = [
    "c-blue-300","c-teal-300","c-purple-300","c-emerald-300",
    "c-yellow-300","c-amber-300","c-rose-300","c-fuchsia-300",
    "c-indigo-300","c-lime-300","c-cyan-400","c-violet-400",
    "c-pink-300","c-cyan-300","c-green-400","c-orange-300",
    "c-fuchsia-400","c-sky-400","c-teal-400","c-amber-200",
]

_PORTRAIT_WRAP_WIDTH = 32


# ── Semantic helpers ───────────────────────────────────────────────────────────

def _assign_line_type(text: str, position: int) -> str:
    lower = text.lower()
    for keywords, ltype in _KEYWORD_TYPE_MAP:
        if any(kw in lower for kw in keywords):
            return ltype
    return _POSITIONAL_TYPES[position % len(_POSITIONAL_TYPES)]


def _hierarchy_class(text: str, bold: bool) -> str:
    wc = len(text.strip().split())
    if bold and wc <= 5:  return "h1"
    if bold or  wc <= 4:  return "h2"
    return "body"


def _text_sections_to_narrative_lines(text_sections: list) -> list:
    lines    = []
    global_i = 0
    wrap_w   = _PORTRAIT_WRAP_WIDTH if VIDEO_WIDTH < VIDEO_HEIGHT else TEXT_WRAP_WIDTH

    for sec in text_sections:
        raw        = sec['content'].strip()
        paragraphs = [p.strip() for p in raw.splitlines() if p.strip()]
        for para in paragraphs:
            wrapped = textwrap.wrap(para, width=wrap_w) or [para]
            for wline in wrapped:
                colour    = _ACCENT_SEQUENCE[global_i % len(_ACCENT_SEQUENCE)]
                bold      = len(wline) < 28 and global_i % 5 == 0
                ltype     = _assign_line_type(wline, global_i)
                hierarchy = _hierarchy_class(wline, bold)
                lines.append({
                    "text":      wline,
                    "color":     colour,
                    "type":      ltype,
                    "bold":      bool(bold),
                    "hierarchy": hierarchy,
                })
                global_i += 1
    return lines


# ── Per-style animation duration calculator ────────────────────────────────────

def _line_animation_ms(text: str, bold: bool, anim_style: str) -> int:
    """Total ms for one line's full animation (glyph + text) for the given style."""
    hclass = _hierarchy_class(text, bold)
    wc     = len(text.strip().split())

    if anim_style == "typewriter":
        text_ms = _TW_H1_MS if hclass == "h1" else _TW_H2_MS if hclass == "h2" else _TW_BODY_MS
        return _TW_GLYPH_MS + text_ms + _BURST_BUFFER

    elif anim_style == "linescan":
        scan_ms = _LS_H1_MS if hclass == "h1" else _LS_H2_MS if hclass == "h2" else _LS_BODY_MS
        return _LS_GLYPH_MS + scan_ms + _BURST_BUFFER

    else:  # wordblurin
        anim_ms = _WB_H1_ANIM_MS if hclass == "h1" else _WB_H2_ANIM_MS if hclass == "h2" else _WB_BODY_ANIM_MS
        last_delay = _WB_LINE_BASE_MS + max(0, wc - 1) * _WB_WORD_STAGGER_MS
        return _WB_GLYPH_MS + last_delay + anim_ms + _BURST_BUFFER


def _burst_timestamps_ms(total_ms: int) -> list[int]:
    """N burst-capture timestamps within [0, total_ms], non-linearly distributed
    (denser at start where motion is highest)."""
    if _BURST_FRAMES <= 1:
        return [total_ms]
    pts = []
    for i in range(_BURST_FRAMES):
        t = (i / (_BURST_FRAMES - 1)) ** 0.55   # slight ease — denser early
        pts.append(int(t * total_ms))
    return pts


# ── Prompt parsing ─────────────────────────────────────────────────────────────

def parse_prompt_with_markers(prompt: str) -> dict:
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
        text_before  = prompt[current_pos:marker_start]
        if text_before:
            sections.append({'type': 'text', 'content': text_before})
            clean_text += text_before

        if marker_text.startswith('[VisualiseCode'):
            m = re.search(code_pattern, marker_text, re.DOTALL)
            if m:
                mode_spec     = (m.group(1) or "").strip().lower()
                resolved_mode = (
                    "typewriter" if mode_spec in ("1","typewriter") else
                    "static"     if mode_spec in ("0","static")     else None
                )
                sections.append({'type':'code','content':m.group(2).strip(),'mode':resolved_mode})

        elif marker_text.startswith('[VisualiseGraph:'):
            m = re.search(graph_pattern, marker_text, re.DOTALL)
            if m:
                parts      = m.group(1).lower().split('|')
                graph_type = parts[0].strip()
                theme      = parts[1].strip() if len(parts) > 1 else None
                sections.append({'type':'graph','graph_type':graph_type,'theme':theme,'content':m.group(2).strip()})

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

    min_required    = sum(
        8.0 if s['type'] == 'code' else 6.0 if s['type'] == 'graph' else 0
        for s in filtered
    )
    actual_duration = max(total_duration, min_required + text_chars * 0.05)
    time_per_char   = (actual_duration - min_required) / text_chars if text_chars else 0

    timed, current = [], 0.0
    for s in filtered:
        dur = (
            len(s['content']) * time_per_char if s['type'] == 'text' else
            10.0 if s['type'] == 'code' else 6.0
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
        if r in ("y","yes"):  return True
        if r in ("n","no"):   return False
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
        "narrative_style":      getattr(config, 'NARRATIVE_STYLE', 'wordblurin'),
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
            prefs["graph_theme"] = select_from_list(["heaven","dark","matrix"], "Graph theme")
        prefs["narrative_theme"] = select_from_list(["dark","heaven","matrix"], "Narrative text theme")
        prefs["narrative_style"] = select_from_list(
            ANIM_STYLES,
            "Narrative animation style (typewriter / wordblurin / linescan)"
        )

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


# ── Narrative text → HTML clip (Playwright, multi-frame burst) ─────────────────

def create_text_clip_optimized(
    sections: list,
    duration: float,
    theme: str = "dark",
    anim_style: str = "wordblurin",
    font=None,
) -> VideoClip:
    """Render narrative text via narrative_visualiser.html + Playwright.

    Multi-frame burst per line: captures _BURST_FRAMES screenshots spread
    across each line's full animation window so the word/character motion
    is captured, not just the settled final state.
    """
    import io as _io

    if not HAS_PLAYWRIGHT:
        raise RuntimeError(
            "Playwright required.\n"
            "Install: pip install playwright && playwright install chromium"
        )

    tmpl_path = os.path.abspath(NARRATIVE_TEMPLATE_PATH)
    with open(tmpl_path, "r", encoding="utf-8") as f:
        template = f.read()

    # Validate style
    if anim_style not in ANIM_STYLES:
        print(f"  ⚠️  Unknown style '{anim_style}', falling back to 'wordblurin'")
        anim_style = "wordblurin"

    text_sections = [s for s in sections if s['type'] == 'text']
    all_lines     = _text_sections_to_narrative_lines(text_sections)

    if not all_lines:
        black = np.zeros((VIDEO_HEIGHT, VIDEO_WIDTH, 3), dtype=np.uint8)
        return VideoClip(lambda t: black, duration=duration)

    # Absolute path to master.css for file:// loading
    css_abs = os.path.abspath(os.path.join(_SCRIPT_DIR, "static", "master.css"))
    css_url = f"file:///{css_abs.replace(os.sep, '/')}"

    def _render_html(lines_so_far: list, active_idx: int) -> str:
        html = template
        # Fix CSS path for file:// protocol
        html = html.replace('href="master.css"', f'href="{css_url}"')
        html = html.replace("THEME_PLACEHOLDER",       theme)
        html = html.replace("NARRATIVE_JSON",          json.dumps(lines_so_far))
        html = html.replace("ACTIVE_LINE_IDX",         str(active_idx))
        html = html.replace("SHOW_BOOT_PLACEHOLDER",   "false")
        html = html.replace("FOOTER_TEXT_PLACEHOLDER", '""')
        html = html.replace("LINE_DELAY_PLACEHOLDER",  "0")
        html = html.replace("ANIM_STYLE_PLACEHOLDER",  anim_style)
        return html

    total_lines  = len(all_lines)
    total_frames = total_lines * _BURST_FRAMES
    print(
        f"  🖼  Pre-rendering {total_lines} lines × {_BURST_FRAMES} burst frames "
        f"= {total_frames} screenshots  [{anim_style} / {theme}]"
    )

    # (line_idx, burst_idx, frame_array)
    state_frames: list[tuple[int, int, np.ndarray]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": VIDEO_WIDTH, "height": VIDEO_HEIGHT},
            device_scale_factor=1,
        )
        page = context.new_page()

        for line_idx in range(total_lines):
            lines_so_far = all_lines[: line_idx + 1]
            html_str     = _render_html(lines_so_far, line_idx)
            html_tmp     = os.path.join(
                tempfile.gettempdir(), f"narrative_{line_idx}.html"
            )
            with open(html_tmp, "w", encoding="utf-8") as f:
                f.write(html_str)

            page.goto(f"file:///{os.path.abspath(html_tmp)}")

            # Calculate this line's animation window
            line_data  = all_lines[line_idx]
            anim_total = _line_animation_ms(line_data['text'], line_data['bold'], anim_style)
            timestamps = _burst_timestamps_ms(anim_total)

            # Brief initial render pause
            page.wait_for_timeout(60)

            for burst_i, ts_ms in enumerate(timestamps):
                wait_here = max(0, ts_ms - (60 if burst_i == 0 else timestamps[burst_i - 1]))
                if wait_here > 0:
                    page.wait_for_timeout(wait_here)

                png   = page.screenshot(full_page=False)
                img   = Image.open(_io.BytesIO(png)).convert("RGB")
                frame = np.array(img)

                if frame.shape[:2] != (VIDEO_HEIGHT, VIDEO_WIDTH):
                    frame = np.array(
                        Image.fromarray(frame).resize(
                            (VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS
                        )
                    )
                state_frames.append((line_idx, burst_i, frame))

            # Wait out remainder before moving to next line
            elapsed   = timestamps[-1] + 60
            remainder = max(0, anim_total - elapsed)
            if remainder > 0:
                page.wait_for_timeout(remainder)

            try:
                os.unlink(html_tmp)
            except OSError:
                pass

            if (line_idx + 1) % 5 == 0 or line_idx == total_lines - 1:
                print(f"    ✓ line {line_idx+1}/{total_lines}  "
                      f"({(line_idx+1)*_BURST_FRAMES}/{total_frames} frames)")

        context.close()
        browser.close()

    # ── Map frames to video timeline ───────────────────────────────────────
    text_section_timing = [s for s in sections if s['type'] == 'text']
    text_start = text_section_timing[0]['start_time']  if text_section_timing else 0.0
    text_end   = text_section_timing[-1]['end_time']   if text_section_timing else duration
    text_dur   = max(text_end - text_start, 0.1)

    secs_per_line = text_dur / total_lines
    last_frame    = state_frames[-1][2]

    timed_frames: list[tuple[float, np.ndarray]] = []
    for line_idx, burst_i, frame in state_frames:
        line_data  = all_lines[line_idx]
        anim_total = _line_animation_ms(line_data['text'], line_data['bold'], anim_style)
        timestamps = _burst_timestamps_ms(anim_total)
        rel        = timestamps[burst_i] / float(anim_total)   # 0.0 → 1.0

        line_t_start = text_start + line_idx * secs_per_line
        video_t      = line_t_start + rel * secs_per_line
        timed_frames.append((video_t, frame))

    timed_frames.sort(key=lambda x: x[0])
    frame_times  = [tf[0] for tf in timed_frames]
    frame_arrays = [tf[1] for tf in timed_frames]

    def make_frame(t: float) -> np.ndarray:
        if t < text_start:   return frame_arrays[0]
        if t >= text_end:    return last_frame
        idx = bisect.bisect_right(frame_times, t) - 1
        return frame_arrays[max(0, min(idx, len(frame_arrays) - 1))]

    return VideoClip(make_frame, duration=duration)


# ── Code clip renderer ────────────────────────────────────────────────────────

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
        theme = prefs.get('code_theme', config.CODE_VIS_DEFAULT_THEME)
        mode  = section.get('mode') or prefs.get('code_mode', config.CODE_VIS_DEFAULT_MODE)
        try:
            clip    = create_code_video_clip(section['content'], theme, mode, config.CODE_VIS_DURATION)
            sec_dur = section['end_time'] - section['start_time']
            clip    = clip.resized((VIDEO_WIDTH, VIDEO_HEIGHT))
            clip    = clip.with_duration(min(sec_dur, clip.duration))
            clip    = clip.with_start(section['start_time'])
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
            silent      = create_silent_audio(sec_dur)
            fn          = create_bar_chart_clip if graph_type == 'bar' else create_line_graph_clip
            clip        = fn(data=graph_data, title="Data Visualization",
                             audio_clip=silent, theme=theme)
            clip        = clip.with_duration(sec_dur).with_start(section['start_time'])
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

    duration       = audio_clip.duration
    timed_sections = calculate_section_timings(clean_text, sections, duration, prefs)

    if timed_sections and timed_sections[-1]['end_time'] > duration:
        actual = timed_sections[-1]['end_time']
        print(f"⏱️  Extending duration {duration:.1f}s → {actual:.1f}s")
        if not prefs.get("generate_audio", True):
            audio_clip.close()
            audio_clip = create_silent_audio(actual)
        duration = actual

    theme       = prefs.get("narrative_theme", getattr(config, 'NARRATIVE_THEME', 'dark'))
    anim_style  = prefs.get("narrative_style",  getattr(config, 'NARRATIVE_STYLE', 'wordblurin'))
    print(f"\n🖼  Building narrative text clip  [{anim_style} / {theme}]...")
    text_clip = create_text_clip_optimized(
        timed_sections, duration, theme=theme, anim_style=anim_style
    )

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

    parsed   = parse_prompt_with_markers(prompt)
    sections = parsed['sections']
    print(f"\n🔍 Detected {len(sections)} sections")

    prefs = get_startup_preferences(sections, file_mode)

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