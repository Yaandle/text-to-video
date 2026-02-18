from elevenlabs.client import ElevenLabs
import os
import re
import sys
import tempfile
from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.video.VideoClip import VideoClip, ColorClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from moviepy.video.io.VideoFileClip import VideoFileClip
import moviepy.video.fx as vfx
from PIL import Image, ImageDraw, ImageFont
import textwrap
import numpy as np
import config
from code_visualiser import TerminalPreviewGenerator, create_code_video_clip
from graph_visualiser import create_bar_chart_clip, create_line_graph_clip
from concurrent.futures import ThreadPoolExecutor

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


# ----------------------
# Configuration
# ----------------------

VIDEO_WIDTH = config.VIDEO_WIDTH
VIDEO_HEIGHT = config.VIDEO_HEIGHT

BACKGROUND_COLOR = config.BACKGROUND_COLOR
FPS = config.FPS
TEXT_COLOR = config.TEXT_COLOR
FONT_SIZE = config.FONT_SIZE
FONT_PATH = config.FONT_PATH_ATKINSON
TEXT_WRAP_WIDTH = config.TEXT_WRAP_WIDTH
MAX_DISPLAY_LINES = config.MAX_DISPLAY_LINES


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


def parse_prompt_with_markers(prompt: str) -> dict:
    """Parse prompt for visualization markers and track their positions.

    Markers:
        [VisualiseCode]code[/VisualiseCode]
        [VisualiseCode:0]code[/VisualiseCode]        -> static
        [VisualiseCode:1]code[/VisualiseCode]        -> typewriter
        [VisualiseCode:typewriter]code[/VisualiseCode]
        [VisualiseCode:static]code[/VisualiseCode]

        [VisualiseGraph:type|theme]data[/VisualiseGraph]

    Returns:
        Dictionary with clean_text and sections list
    """

    sections = []
    current_pos = 0

    combined_pattern = (
        r'(\[VisualiseCode(?::[^\]]+)?\].*?\[/VisualiseCode\]'
        r'|\[VisualiseGraph:[^\]]+\].*?\[/VisualiseGraph\])'
    )

    graph_pattern = r'\[VisualiseGraph:([^\]]+)\](.*?)\[/VisualiseGraph\]'
    code_pattern = r'\[VisualiseCode(?::([^\]]+))?\](.*?)\[/VisualiseCode\]'

    clean_text = ""

    for match in re.finditer(combined_pattern, prompt, re.DOTALL):
        marker_start = match.start()
        marker_text = match.group(0)

        # Add text before marker
        text_before = prompt[current_pos:marker_start]
        if text_before:
            sections.append({'type': 'text', 'content': text_before})
            clean_text += text_before

        # ----------------------
        # CODE
        # ----------------------
        if marker_text.startswith('[VisualiseCode'):
            code_match = re.search(code_pattern, marker_text, re.DOTALL)
            if code_match:
                mode_spec = code_match.group(1)
                code_content = code_match.group(2).strip()

                resolved_mode = None
                if mode_spec:
                    mode_spec = mode_spec.strip().lower()
                    if mode_spec in ("1", "typewriter"):
                        resolved_mode = "typewriter"
                    elif mode_spec in ("0", "static"):
                        resolved_mode = "static"

                sections.append({
                    'type': 'code',
                    'content': code_content,
                    'mode': resolved_mode  # None = fallback to startup preference
                })

        # ----------------------
        # GRAPH
        # ----------------------
        elif marker_text.startswith('[VisualiseGraph:'):
            graph_match = re.search(graph_pattern, marker_text, re.DOTALL)
            if graph_match:
                graph_spec = graph_match.group(1).lower()
                graph_data = graph_match.group(2).strip()

                parts = graph_spec.split('|')
                graph_type = parts[0].strip()
                theme = parts[1].strip() if len(parts) > 1 else None

                sections.append({
                    'type': 'graph',
                    'graph_type': graph_type,
                    'theme': theme,
                    'content': graph_data
                })

        current_pos = match.end()

    # Add remaining text
    remaining = prompt[current_pos:]
    if remaining:
        sections.append({'type': 'text', 'content': remaining})
        clean_text += remaining

    clean_text = re.sub(r'\s+', ' ', clean_text).strip()

    return {
        'clean_text': clean_text,
        'sections': sections,
        'original_prompt': prompt
    }


def parse_graph_data(content: str) -> dict:
    """Parse graph data from marker content.
    
    Format: label1:value1,label2:value2
    
    Returns:
        Dictionary of {label: value}
    """
    data = {}
    pairs = content.split(',')
    for pair in pairs:
        parts = pair.strip().split(':')
        if len(parts) == 2:
            label = parts[0].strip()
            try:
                value = float(parts[1].strip())
                data[label] = value
            except ValueError:
                pass
    return data


def calculate_section_timings(clean_text: str, sections: list, total_duration: float, prefs: dict) -> list:
    """Calculate timing for each section based on text character count.
    
    CRITICAL: Accounts for whether audio is generated or skipped.
    Uses minimum durations for code (8s) and graph (6s) visualizations.
    If minimums exceed total_duration, extends the duration.
    
    Returns:
        List of sections with start/end times
    """
    if not sections:
        return []
    
    # Filter sections based on preferences
    filtered_sections = []
    for section in sections:
        if section['type'] == 'code' and not prefs.get('use_code_visualizer', True):
            continue  # Skip code visualizations if disabled
        if section['type'] == 'graph' and not prefs.get('use_graph_visualizer', True):
            continue  # Skip graph visualizations if disabled
        filtered_sections.append(section)
    
    if not filtered_sections:
        return []
    
    # Count text characters for proportional timing
    text_chars = sum(len(s['content']) for s in filtered_sections if s['type'] == 'text')
    
    if text_chars == 0:
        # No text content, divide time equally
        time_per_section = total_duration / len(filtered_sections)
        timed_sections = []
        for i, section in enumerate(filtered_sections):
            timed_sections.append({
                **section,
                'start_time': i * time_per_section,
                'end_time': (i + 1) * time_per_section
            })
        return timed_sections
    
    # First pass: Calculate minimum required duration
    minimum_required = 0.0
    text_duration_needed = 0.0
    
    for section in filtered_sections:
        if section['type'] == 'code':
            minimum_required += 8.0  # Minimum 8 seconds for code
        elif section['type'] == 'graph':
            minimum_required += 6.0  # Minimum 6 seconds for graph
        elif section['type'] == 'text':
            text_duration_needed += len(section['content'])  # We'll scale this
    
    # Calculate time remaining for text after allocating minimums for visualizations
    time_for_text = max(0, total_duration - minimum_required)
    
    # If we don't have enough time, we need to extend duration
    actual_duration = max(total_duration, minimum_required + (text_duration_needed * 0.05))
    
    # Recalculate time for text with actual duration
    time_for_text = actual_duration - minimum_required
    time_per_char = time_for_text / text_duration_needed if text_duration_needed > 0 else 0
    
    # Build timed sections with proper durations
    timed_sections = []
    current_time = 0.0
    
    for section in filtered_sections:
        if section['type'] == 'text':
            duration = len(section['content']) * time_per_char
        elif section['type'] == 'code':
            duration = 10.0  # Code gets 10 seconds total (8s animation + 2s hold)
        elif section['type'] == 'graph':
            duration = 6.0  # Fixed 6 seconds
        else:
            duration = 1.0
        
        timed_sections.append({
            **section,
            'start_time': current_time,
            'end_time': current_time + duration
        })
        
        current_time += duration
    
    return timed_sections


def display_header():
    """Display application header."""
    print("\n" + "="*60)
    print("TEXT TO VIDEO GENERATOR WITH VISUALIZERS")
    print("="*60 + "\n")


def prompt_yes_no(question: str, default: bool = True) -> bool:
    """Prompt user for yes/no answer."""
    default_text = " (Y/n): " if default else " (y/N): "
    while True:
        response = input(question + default_text).strip().lower()
        if response == "":
            return default
        elif response in ("y", "yes"):
            return True
        elif response in ("n", "no"):
            return False
        else:
            print("❌ Please enter 'y' or 'n'.")


def select_from_list(items: list, prompt: str = "Select an option") -> str:
    """Allow user to select from a list."""
    print(f"\n{prompt}:")
    for i, item in enumerate(items, 1):
        print(f"  {i}. {item}")
    
    while True:
        try:
            choice = int(input("Enter number: ").strip()) - 1
            if 0 <= choice < len(items):
                return items[choice]
            else:
                print(f"❌ Please enter a number between 1 and {len(items)}.")
        except ValueError:
            print("❌ Please enter a valid number.")


def get_startup_preferences(parsed_sections: list, file_mode: bool) -> dict:
    """
    Minimal startup preferences.

    - Always ask about audio.
    - Auto-detect code/graph usage from parsed sections.
    - Skip redundant questions when using prompt file.
    """

    display_header()

    has_code = any(s['type'] == 'code' for s in parsed_sections)
    has_graph = any(s['type'] == 'graph' for s in parsed_sections)

    prefs = {
        "generate_audio": prompt_yes_no("Generate audio? (N to skip for testing)", default=True),
        "save_mp3": prompt_yes_no("Save MP3 audio file?", default=True),
        "use_code_visualizer": has_code,
        "use_graph_visualizer": has_graph,
        "code_theme": config.CODE_VIS_DEFAULT_THEME,
        "code_mode": config.CODE_VIS_DEFAULT_MODE,
        "graph_theme": "heaven"
    }

    if not prefs["generate_audio"]:
        prefs["test_fps"] = 5
        print("ℹ️  Test mode: Using 5 FPS for faster rendering")
    else:
        prefs["test_fps"] = FPS

    # Only ask for theme overrides in manual mode
    if not file_mode:
        if has_code:
            prefs["code_theme"] = select_from_list(
                config.CODE_VIS_THEMES,
                "Select code visualiser theme"
            )

        if has_graph:
            prefs["graph_theme"] = select_from_list(
                ["heaven", "dark", "matrix"],
                "Select graph theme"
            )

    return prefs


def create_silent_audio(duration: float) -> AudioFileClip:
    """Create silent audio clip efficiently using chunked writing.
    """
    import wave
    
    sample_rate = 44100
    temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    temp_path = temp_file.name
    temp_file.close()
    
    with wave.open(temp_path, 'w') as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        
        # Write in 1-second chunks to avoid large memory buffer
        chunk_size = sample_rate  # 1 second of samples
        silent_chunk = b'\x00\x00' * chunk_size
        
        for _ in range(int(duration)):
            wav.writeframes(silent_chunk)
        
        # Handle remaining fractional second
        remaining_samples = int((duration - int(duration)) * sample_rate)
        if remaining_samples > 0:
            wav.writeframes(b'\x00\x00' * remaining_samples)
    
    return AudioFileClip(temp_path)

def create_text_clip_optimized(sections: list, duration: float, font: ImageFont.FreeTypeFont):
    """Create a high-quality, minimal floating text clip with typewriter cursor and optional background effects.
    
    Args:
        sections: List of timed sections
        duration: Total clip duration
        font: PIL font object
    
    Returns:
        VideoClip with optimized text rendering
    """
    import math

    frame_cache = {}
    cache_interval = 0.05  # cache every 50ms for smoother cursor
    
    # Cursor config
    CURSOR_CHAR = "│"
    CURSOR_COLOR = (255, 255, 255, 180)  # subtle opacity white
    CURSOR_BLINK_SPEED = 0.6  # seconds per blink cycle

    LEFT_MARGIN = 60
    RIGHT_MARGIN = 60
    TOP_MARGIN = 80
    BOTTOM_MARGIN = 80
    LINE_SPACING = 6

    # Background gradient/shadow
    def draw_background(draw_obj):
        """Draw subtle vertical gradient for floating effect."""
        for y in range(VIDEO_HEIGHT):
            ratio = y / VIDEO_HEIGHT
            r = int(BACKGROUND_COLOR[0] * (0.95 + 0.05 * ratio))
            g = int(BACKGROUND_COLOR[1] * (0.95 + 0.05 * ratio))
            b = int(BACKGROUND_COLOR[2] * (0.95 + 0.05 * ratio))
            draw_obj.line([(0, y), (VIDEO_WIDTH, y)], fill=(r, g, b))

    def generate_text_frame(t):
        """Generate a single text frame with typewriter cursor."""
        img = Image.new('RGB', (VIDEO_WIDTH, VIDEO_HEIGHT), color=BACKGROUND_COLOR)
        draw = ImageDraw.Draw(img)

        draw_background(draw)

        # Determine current section
        current_section = None
        for section in sections:
            if section['start_time'] <= t < section['end_time']:
                current_section = section
                break
        if current_section is None and sections:
            current_section = sections[-1]

        if current_section and current_section['type'] == 'text':
            content = current_section['content']
            section_duration = current_section['end_time'] - current_section['start_time']
            progress = (t - current_section['start_time']) / section_duration if section_duration > 0 else 1.0
            chars_to_display = int(len(content) * progress)
            display_text = content[:chars_to_display]

            lines = textwrap.wrap(display_text, width=TEXT_WRAP_WIDTH)
            if len(lines) > MAX_DISPLAY_LINES:
                lines = lines[-MAX_DISPLAY_LINES:]
            final_text = "\n".join(lines)

            bbox = draw.multiline_textbbox((0, 0), final_text, font=font, spacing=LINE_SPACING, align="left")
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x = LEFT_MARGIN
            y = TOP_MARGIN + (VIDEO_HEIGHT - TOP_MARGIN - BOTTOM_MARGIN - text_height) / 2

            # Draw text
            draw.multiline_text((x, y), final_text, font=font, fill=TEXT_COLOR, spacing=LINE_SPACING, align="left")

            # Draw typewriter cursor
            if current_section['end_time'] - current_section['start_time'] > 0:
                blink_phase = (t % CURSOR_BLINK_SPEED) / CURSOR_BLINK_SPEED
                cursor_visible = blink_phase < 0.5
                if cursor_visible:
                    last_line = lines[-1] if lines else ""
                    cursor_x = x + draw.textlength(last_line, font=font)
                    line_height = font.getbbox("Ay")[3] - font.getbbox("Ay")[1]
                    cursor_y = y + (len(lines) - 1) * (line_height + LINE_SPACING)
                    draw.text((cursor_x, cursor_y), CURSOR_CHAR, font=font, fill=CURSOR_COLOR)

        return np.array(img)

    def make_frame(t):
        cache_key = int(t / cache_interval)
        if cache_key not in frame_cache:
            frame_cache[cache_key] = generate_text_frame(t)
        return frame_cache[cache_key]

    return VideoClip(make_frame, duration=duration)

def render_code_clips_parallel(timed_sections: list, prefs: dict) -> dict:
    """Render all code clips (serial since Playwright isn't thread-safe)."""

    code_clips = {}

    if not prefs.get('use_code_visualizer', True):
        return code_clips

    if not any(s['type'] == 'code' for s in timed_sections):
        return code_clips

    if not HAS_PLAYWRIGHT:
        print("\n❌ ERROR: Playwright is required for code visualization!")
        print("Install with: pip install playwright && playwright install chromium")
        return code_clips

    print("\n🎨 Pre-rendering code visualizations...")

    for i, section in enumerate(timed_sections):
        if section['type'] == 'code':
            code_content = section['content']
            theme = prefs.get('code_theme', config.CODE_VIS_DEFAULT_THEME)

            # 🔹 Prompt-level override
            mode = section.get('mode') or prefs.get(
                'code_mode',
                config.CODE_VIS_DEFAULT_MODE
            )

            code_duration = config.CODE_VIS_DURATION

            try:
                clip = create_code_video_clip(
                    code_content,
                    theme,
                    mode,
                    code_duration
                )

                section_duration = section['end_time'] - section['start_time']

                clip = clip.resized((VIDEO_WIDTH, VIDEO_HEIGHT))
                clip = clip.with_duration(min(section_duration, clip.duration))
                clip = clip.with_start(section['start_time'])

                code_clips[i] = clip
                print(f"✅ Rendered code clip for section {i+1} (mode: {mode})")

            except Exception as e:
                print(f"❌ Error rendering code clip: {e}")
                import traceback
                traceback.print_exc()

    return code_clips


def render_graph_clips_parallel(timed_sections: list, prefs: dict) -> dict:
    """Render all graph clips using optimized direct clip generation.
    
    OPTIMIZATION 1: Uses return_clip=True to get clips directly without file I/O.
    """
    graph_clips = {}
    
    if not prefs.get('use_graph_visualizer', True):
        return graph_clips
    
    if not any(s['type'] == 'graph' for s in timed_sections):
        return graph_clips
    
    print("\n📊 Pre-rendering graph visualizations...")
    for i, section in enumerate(timed_sections):
        if section['type'] == 'graph':
            graph_type = section.get('graph_type', 'bar')
            theme = section.get('theme') or prefs.get('graph_theme', 'heaven')
            graph_data_str = section['content']
            
            print(f"  → Parsing graph data: {graph_data_str}")
            graph_data = parse_graph_data(graph_data_str)
            print(f"  → Parsed data: {graph_data}")
            
            if graph_data:
                try:
                    section_duration = section['end_time'] - section['start_time']
                    
                    # OPTIMIZATION 1: Get clip directly without file I/O
                    print(f"  → Generating {graph_type} graph directly in memory...")
                    if graph_type == 'bar':
                        clip = create_bar_chart_clip(
                            data=graph_data,
                            title="Data Visualization",
                            narration="",
                            output_name=f"graph_{i}",
                            theme=theme,
                            return_clip=True  # Get clip directly
                        )
                    else:  # line
                        clip = create_line_graph_clip(
                            data=graph_data,
                            title="Data Visualization",
                            narration="",
                            output_name=f"graph_{i}",
                            theme=theme,
                            return_clip=True  # Get clip directly
                        )
                    
                    # Adjust duration and start time
                    clip = clip.with_duration(section_duration)
                    clip = clip.with_start(section['start_time'])
                    
                    graph_clips[i] = clip
                    print(f"✅ Generated graph clip for section {i+1} (duration: {section_duration:.2f}s)")
                    
                except Exception as e:
                    print(f"❌ Error generating graph: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"⚠️  Warning: No valid graph data parsed from '{graph_data_str}'")
    
    return graph_clips


def generate_main_video(prompt: str, save_mp3: bool = True, prefs: dict = None) -> str:
    """Generate the main text-to-video with narration and embedded visualisations.

    """
    if prefs is None:
        prefs = {}
    
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    
    # ----------------------
    # Parse Markers
    # ----------------------
    parsed = parse_prompt_with_markers(prompt)
    clean_text = parsed['clean_text']
    sections = parsed['sections']
    
    print(f"\n🔍 Parsed {len(sections)} sections:")
    for i, section in enumerate(sections):
        print(f"  {i+1}. {section['type'].upper()}: {section['content'][:50]}...")
    
    # ----------------------
    # Generate Audio
    # ----------------------
    audio_path = None
    if prefs.get("generate_audio", True):
        print("\n🎙️ Generating audio for main video...")
        client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)
        audio_generator = client.text_to_speech.convert(
            text=clean_text,
            voice_id=config.VOICE_ID,
            model_id=config.MODEL_ID,
            output_format="mp3_44100_128",
        )

        audio_path = os.path.join(config.OUTPUT_DIR, "output_audio.mp3")
        with open(audio_path, "wb") as f:
            for chunk in audio_generator:
                f.write(chunk)

        print("✅ Audio generated")
        audio_clip = AudioFileClip(audio_path)
    else:
        print("\n⏭️  Skipping audio generation (testing mode)")
        test_duration = 30.0  # Fixed duration for testing
        audio_clip = create_silent_audio(test_duration)
        print(f"⏭️  Using silent {test_duration}-second placeholder")

    duration = audio_clip.duration
    timed_sections = calculate_section_timings(clean_text, sections, duration, prefs)
    if timed_sections and timed_sections[-1]['end_time'] > duration:
        actual_duration = timed_sections[-1]['end_time']
        print(f"⏱️  Extending duration from {duration:.1f}s to {actual_duration:.1f}s to fit visualizations")
        
        if not prefs.get("generate_audio", True):
            audio_clip.close()
            audio_clip = create_silent_audio(actual_duration)
        
        duration = actual_duration
    try:
        font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    except OSError as e:
        print(f"❌ Error: Font not found. {e}")
        audio_clip.close()
        return None

    # ----------------------
    #  Parallel Pre-rendering (where thread-safe)
    # ----------------------
    # Note: Playwright isn't thread-safe, so code clips must be serial
    # Graphs could be parallelized but gains are minimal for 2-3 graphs
    
    code_clips_cache = render_code_clips_parallel(timed_sections, prefs)
    graph_clips_cache = render_graph_clips_parallel(timed_sections, prefs)
    print("\n🎬 Creating main video with visualizations...")
    
    text_clip = create_text_clip_optimized(timed_sections, duration, font)
    
    bg_clip = ColorClip(
        size=(VIDEO_WIDTH, VIDEO_HEIGHT),
        color=BACKGROUND_COLOR,
        duration=duration
    )
    
    # Combine all clips
    clips = [bg_clip, text_clip]
    for clip in code_clips_cache.values():
        clips.append(clip)
    for clip in graph_clips_cache.values():
        clips.append(clip)
    
    final_clip = CompositeVideoClip(clips)
    final_clip = final_clip.with_audio(audio_clip)
    video_path = os.path.join(config.OUTPUT_DIR, "output_video.mp4")
    print(f"💾 Exporting main video to {video_path}...")
    export_fps = prefs.get("test_fps", FPS)
    codec_preset = 'ultrafast' if not prefs.get("generate_audio", True) else 'medium'
    
    final_clip.write_videofile(
        video_path, 
        fps=export_fps,
        codec='libx264',
        preset=codec_preset,
        audio_codec='aac'
    )

    print("✅ Main video saved successfully!")
    
    # ----------------------
    # Handle MP3 File
    # ----------------------
    if prefs.get("generate_audio", True):
        if not save_mp3:
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)
                print("🗑️  Audio file deleted.")
        else:
            print(f"🎵 Audio saved: {audio_path}")
    else:
        print("⏭️  (Audio was skipped for testing)")
    
    audio_clip.close()
    final_clip.close()
    for clip in code_clips_cache.values():
        clip.close()
    for clip in graph_clips_cache.values():
        clip.close()
    
    return video_path


def main():
    """Main application flow (intelligent mode)."""

    # ----------------------
    # Load Prompt First
    # ----------------------
    file_mode = len(sys.argv) > 1

    if file_mode:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            prompt = f.read().strip()
        print(f"✓ Loaded from {sys.argv[1]}")
    else:
        print("\n" + "-"*60)
        print("📝 ENTER YOUR CONTENT")
        print("-"*60)
        print("\nYou can embed visualizations using markers.")
        print()
        prompt = input("Enter your text (with optional markers): ").strip()

    if not prompt:
        print("❌ Error: No text provided.")
        return 1

    # ----------------------
    # Parse Prompt Early
    # ----------------------
    parsed = parse_prompt_with_markers(prompt)
    sections = parsed['sections']

    print(f"\n🔍 Detected {len(sections)} sections")

    # ----------------------
    # Get Preferences AFTER parsing
    # ----------------------
    prefs = get_startup_preferences(sections, file_mode)

    # ----------------------
    # Generate Video
    # ----------------------
    video_path = generate_main_video(
        prompt,
        save_mp3=prefs["save_mp3"],
        prefs=prefs
    )

    if not video_path:
        return 1

    print("\n" + "="*60)
    print("✅ GENERATION COMPLETE")
    print("="*60)
    print(f"\n📹 Video: {video_path}")
    print(f"📁 Output directory: {config.OUTPUT_DIR}")

    if prefs["save_mp3"] and prefs["generate_audio"]:
        print(f"🎵 Audio: {os.path.join(config.OUTPUT_DIR, 'output_audio.mp3')}")

    print()

    return 0


if __name__ == "__main__":
    exit(main())