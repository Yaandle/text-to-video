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
from code_visualiser import TerminalPreviewGenerator
from graph_visualiser import generate_bar_chart_video, generate_line_graph_video
from concurrent.futures import ThreadPoolExecutor
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

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
FPS = config.FPS

BACKGROUND_COLOR = (255, 255, 255)
TEXT_COLOR = (0, 0, 0)
FONT_SIZE = 50
TEXT_WRAP_WIDTH = 40
MAX_DISPLAY_LINES = 2

FONT_PATH = config.FONT_PATH_ARIAL


# ----------------------
# OPTIMIZATION 4: Managed Clip Context Manager
# ----------------------
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
        [VisualiseCode]code here[/VisualiseCode] - for code visualization
        [VisualiseGraph:type|theme]label1:value1,label2:value2[/VisualiseGraph] - for graph
            where type is 'bar' or 'line' and theme is 'heaven', 'dark', or 'matrix' (optional)
    
    Returns:
        Dictionary with clean_text and sections list
    """
    sections = []
    current_pos = 0
    
    combined_pattern = r'(\[VisualiseCode\].*?\[/VisualiseCode\]|\[VisualiseGraph:[^\]]+\].*?\[/VisualiseGraph\])'
    graph_pattern = r'\[VisualiseGraph:([^\]]+)\](.*?)\[/VisualiseGraph\]'
    
    clean_text = ""
    
    for match in re.finditer(combined_pattern, prompt, re.DOTALL):
        marker_start = match.start()
        marker_text = match.group(0)
        
        # Add text before this marker
        text_before = prompt[current_pos:marker_start]
        if text_before:
            sections.append({'type': 'text', 'content': text_before})
            clean_text += text_before
        
        # Parse and add the marker
        if marker_text.startswith('[VisualiseCode]'):
            code_content = re.search(r'\[VisualiseCode\](.*?)\[/VisualiseCode\]', marker_text, re.DOTALL)
            if code_content:
                sections.append({'type': 'code', 'content': code_content.group(1).strip()})
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


def create_code_video_clip(code: str, theme: str, mode: str, duration: float):
    """Create a video clip of the code animation by recording the browser.
    
    OPTIMIZATION 3: Close browser immediately after animation completes.
    """
    if not HAS_PLAYWRIGHT:
        raise RuntimeError("Playwright is required for code visualization.")
    
    gen = TerminalPreviewGenerator(theme=theme)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
        html_path = f.name

    gen.generate(
        code=code,
        language="python",
        mode=mode,
        duration=duration,
        output_path=html_path
    )

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(
                viewport={"width": VIDEO_WIDTH, "height": VIDEO_HEIGHT},
                record_video_dir=tempfile.gettempdir(),
                record_video_size={"width": VIDEO_WIDTH, "height": VIDEO_HEIGHT}
            )
            
            page = context.new_page()
            page.goto(f"file://{os.path.abspath(html_path)}")
            page.wait_for_load_state("networkidle")
            
            # Wait for animation to complete
            if mode.lower() == "typewriter":
                wait_time = int((duration * 1000) + 2000)  # Add 2 second buffer
                print(f"  ⏱️  Waiting {wait_time/1000:.1f}s for typewriter animation...")
                page.wait_for_timeout(wait_time)
            else:
                page.wait_for_timeout(2000)
            
            # OPTIMIZATION 3: Get video path and close immediately
            page.wait_for_timeout(500)  # Brief buffer for encoder
            video_path = page.video.path()
            
            # Close browser ASAP to free resources
            context.close()
            browser.close()
            
            # Load as MoviePy clip
            clip = VideoFileClip(video_path)
            
            return clip

    finally:
        if os.path.exists(html_path):
            os.unlink(html_path)


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


# ----------------------
# OPTIMIZATION 1: Direct graph clip generation (no file I/O)
# ----------------------
def create_graph_clip_direct(data: dict, graph_type: str, theme: str, duration: float, title: str = "Data Visualization"):
    """Generate graph clip directly as VideoClip without intermediate file I/O.
    
    Args:
        data: Dictionary of {label: value}
        graph_type: 'bar' or 'line'
        theme: 'heaven', 'dark', or 'matrix'
        duration: Clip duration in seconds
        title: Graph title
    
    Returns:
        VideoClip with graph visualization
    """
    # Theme colors
    themes = {
        'heaven': {
            'bg': '#FFFFFF',
            'text': '#000000',
            'primary': '#4A90E2',
            'grid': '#E0E0E0'
        },
        'dark': {
            'bg': '#1E1E1E',
            'text': '#FFFFFF',
            'primary': '#61DAFB',
            'grid': '#333333'
        },
        'matrix': {
            'bg': '#000000',
            'text': '#00FF00',
            'primary': '#00FF00',
            'grid': '#003300'
        }
    }
    
    theme_colors = themes.get(theme, themes['heaven'])
    
    # Create figure
    fig, ax = plt.subplots(figsize=(VIDEO_WIDTH/100, VIDEO_HEIGHT/100), dpi=100)
    fig.patch.set_facecolor(theme_colors['bg'])
    ax.set_facecolor(theme_colors['bg'])
    
    labels = list(data.keys())
    values = list(data.values())
    
    if graph_type == 'bar':
        bars = ax.bar(labels, values, color=theme_colors['primary'], alpha=0.8)
        ax.set_ylabel('Value', color=theme_colors['text'], fontsize=14)
    else:  # line
        ax.plot(labels, values, color=theme_colors['primary'], linewidth=3, marker='o', markersize=8)
        ax.set_ylabel('Value', color=theme_colors['text'], fontsize=14)
    
    ax.set_title(title, color=theme_colors['text'], fontsize=20, pad=20)
    ax.set_xlabel('Category', color=theme_colors['text'], fontsize=14)
    ax.tick_params(colors=theme_colors['text'], labelsize=12)
    ax.grid(True, alpha=0.3, color=theme_colors['grid'])
    
    # Tight layout
    plt.tight_layout()
    
    # Convert figure to numpy array
    fig.canvas.draw()
    frame = np.frombuffer(fig.canvas.tostring_argb(), dtype=np.uint8)
    frame = frame.reshape(fig.canvas.get_width_height()[::-1] + (4,))  # ARGB format
    frame = frame[:, :, 1:]  # Remove alpha channel to get RGB
    
    plt.close(fig)
    
    # Create VideoClip with static frame
    def make_frame(t):
        return frame
    
    clip = VideoClip(make_frame, duration=duration)
    return clip


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


def get_startup_preferences() -> dict:
    """Get user preferences at startup.
    
    OPTIMIZATION 6: Add test FPS option for faster preview rendering.
    """
    display_header()
    
    prefs = {
        "generate_audio": prompt_yes_no("Generate audio? (N to skip for testing)", default=True),
        "save_mp3": prompt_yes_no("Save MP3 audio file?", default=True),
        "use_code_visualizer": prompt_yes_no("Generate code visualisation?", default=config.USE_CODE_VISUALIZER_DEFAULT),
        "use_graph_visualizer": prompt_yes_no("Generate graph visualisation?", default=config.USE_GRAPH_VISUALIZER_DEFAULT),
    }
    
    # OPTIMIZATION 6: Lower FPS for test mode
    if not prefs["generate_audio"]:
        prefs["test_fps"] = 5  # Fast preview rendering
        print("ℹ️  Test mode: Using 5 FPS for faster rendering")
    else:
        prefs["test_fps"] = FPS
    
    # Only show code options if code visualizer is enabled
    if prefs["use_code_visualizer"]:
        prefs["code_theme"] = select_from_list(config.CODE_VIS_THEMES, "Select code visualiser theme")
        prefs["code_mode"] = select_from_list(config.CODE_VIS_MODES, "Select code animation mode")
    
    # Only show graph options if graph visualizer is enabled
    if prefs["use_graph_visualizer"]:
        prefs["graph_theme"] = select_from_list(["heaven", "dark", "matrix"], "Select graph theme")
    
    return prefs


# ----------------------
# OPTIMIZATION 5: Optimized silent audio generation with chunked streaming
# ----------------------
def create_silent_audio(duration: float) -> AudioFileClip:
    """Create silent audio clip efficiently using chunked writing.
    
    Args:
        duration: Duration in seconds
    
    Returns:
        AudioFileClip with silent audio
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


# ----------------------
# OPTIMIZATION 2: Cached text frame generation
# ----------------------
def create_text_clip_optimized(sections: list, duration: float, font: ImageFont.FreeTypeFont):
    """Create text clip with frame caching to reduce PIL overhead.
    
    Args:
        sections: List of timed sections
        duration: Total clip duration
        font: PIL font object
    
    Returns:
        VideoClip with optimized text rendering
    """
    frame_cache = {}
    cache_interval = 0.1  # Cache every 100ms
    
    def generate_text_frame(t):
        """Generate a single text frame."""
        img = Image.new('RGB', (VIDEO_WIDTH, VIDEO_HEIGHT), color=BACKGROUND_COLOR)
        draw = ImageDraw.Draw(img)

        # Find which section we're in
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
            section_progress = (t - current_section['start_time']) / section_duration if section_duration > 0 else 1.0
            
            chars_to_display = int(len(content) * section_progress)
            display_text = content[:chars_to_display]
            
            current_lines = textwrap.wrap(display_text, width=TEXT_WRAP_WIDTH)
            if len(current_lines) > MAX_DISPLAY_LINES:
                current_lines = current_lines[-MAX_DISPLAY_LINES:]
            
            final_text = "\n".join(current_lines)

            bbox = draw.multiline_textbbox((0, 0), final_text, font=font, align='center')
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            x = (VIDEO_WIDTH - text_width) / 2
            y = (VIDEO_HEIGHT * 2 / 3) - (text_height / 2)

            draw.multiline_text((x, y), final_text, font=font, fill=TEXT_COLOR, align='center')
        
        return np.array(img)
    
    def make_frame(t):
        """Make frame with caching."""
        cache_key = int(t / cache_interval)
        
        if cache_key not in frame_cache:
            frame_cache[cache_key] = generate_text_frame(t)
        
        return frame_cache[cache_key]
    
    return VideoClip(make_frame, duration=duration)


# ----------------------
# OPTIMIZATION 7: Parallel pre-rendering
# ----------------------
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
            mode = prefs.get('code_mode', config.CODE_VIS_DEFAULT_MODE)
            code_duration = config.CODE_VIS_DURATION  # 8 seconds for animation
            
            try:
                clip = create_code_video_clip(code_content, theme, mode, code_duration)
                
                section_duration = section['end_time'] - section['start_time']
                
                clip = clip.resized((VIDEO_WIDTH, VIDEO_HEIGHT))
                clip = clip.with_duration(min(section_duration, clip.duration))
                clip = clip.with_start(section['start_time'])
                
                code_clips[i] = clip
                print(f"✅ Rendered code clip for section {i+1} (duration: {section_duration:.2f}s)")
            except Exception as e:
                print(f"❌ Error rendering code clip: {e}")
                import traceback
                traceback.print_exc()
    
    return code_clips


def render_graph_clips_parallel(timed_sections: list, prefs: dict) -> dict:
    """Render all graph clips using direct generation (OPTIMIZATION 1)."""
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
                    
                    # OPTIMIZATION 1: Direct clip generation (no file I/O)
                    print(f"  → Generating {graph_type} graph directly...")
                    clip = create_graph_clip_direct(
                        data=graph_data,
                        graph_type=graph_type,
                        theme=theme,
                        duration=section_duration,
                        title="Data Visualization"
                    )
                    
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
    
    Includes all optimizations:
    - OPTIMIZATION 1: Direct graph generation (no file I/O)
    - OPTIMIZATION 2: Cached text frames
    - OPTIMIZATION 3: Fast browser close
    - OPTIMIZATION 4: Managed clips
    - OPTIMIZATION 5: Chunked silent audio
    - OPTIMIZATION 6: Test FPS
    - OPTIMIZATION 7: Parallel rendering (where safe)
    - OPTIMIZATION 8: Fast codec preset
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
        # OPTIMIZATION 5: Chunked silent audio generation
        print("\n⏭️  Skipping audio generation (testing mode)")
        test_duration = 30.0  # Fixed duration for testing
        audio_clip = create_silent_audio(test_duration)
        print(f"⏭️  Using silent {test_duration}-second placeholder")

    duration = audio_clip.duration

    # ----------------------
    # Calculate Section Timings (AFTER determining audio duration)
    # ----------------------
    timed_sections = calculate_section_timings(clean_text, sections, duration, prefs)
    
    # If calculated sections exceed audio duration, extend the audio
    if timed_sections and timed_sections[-1]['end_time'] > duration:
        actual_duration = timed_sections[-1]['end_time']
        print(f"⏱️  Extending duration from {duration:.1f}s to {actual_duration:.1f}s to fit visualizations")
        
        if not prefs.get("generate_audio", True):
            audio_clip.close()
            audio_clip = create_silent_audio(actual_duration)
        
        duration = actual_duration

    # ----------------------
    # Setup Font
    # ----------------------
    try:
        font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    except OSError as e:
        print(f"❌ Error: Font not found. {e}")
        audio_clip.close()
        return None

    # ----------------------
    # OPTIMIZATION 7: Parallel Pre-rendering (where thread-safe)
    # ----------------------
    # Note: Playwright isn't thread-safe, so code clips must be serial
    # Graphs could be parallelized but gains are minimal for 2-3 graphs
    
    code_clips_cache = render_code_clips_parallel(timed_sections, prefs)
    graph_clips_cache = render_graph_clips_parallel(timed_sections, prefs)

    # ----------------------
    # OPTIMIZATION 2: Create optimized text clip with caching
    # ----------------------
    print("\n🎬 Creating main video with visualizations...")
    
    text_clip = create_text_clip_optimized(timed_sections, duration, font)
    
    bg_clip = ColorClip(
        size=(VIDEO_WIDTH, VIDEO_HEIGHT),
        color=BACKGROUND_COLOR,
        duration=duration
    )
    
    # Combine all clips
    clips = [bg_clip, text_clip]
    
    # Add code clips
    for clip in code_clips_cache.values():
        clips.append(clip)
    
    # Add graph clips
    for clip in graph_clips_cache.values():
        clips.append(clip)
    
    final_clip = CompositeVideoClip(clips)
    final_clip = final_clip.with_audio(audio_clip)

    # ----------------------
    # OPTIMIZATION 6 & 8: Export with optimal settings
    # ----------------------
    video_path = os.path.join(config.OUTPUT_DIR, "output_video.mp4")
    print(f"💾 Exporting main video to {video_path}...")
    
    # OPTIMIZATION 6: Use test FPS if in test mode
    export_fps = prefs.get("test_fps", FPS)
    
    # OPTIMIZATION 8: Fast codec preset for testing, medium for production
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
    
    # ----------------------
    # OPTIMIZATION 4: Cleanup with managed resources
    # ----------------------
    audio_clip.close()
    final_clip.close()
    
    # Close all cached clips
    for clip in code_clips_cache.values():
        clip.close()
    for clip in graph_clips_cache.values():
        clip.close()
    
    return video_path


def main():
    """Main application flow."""
    
    prefs = get_startup_preferences()
    
    print("\n" + "-"*60)
    print("📝 ENTER YOUR CONTENT")
    print("-"*60)
    print("\nYou can embed visualizations in your text using markers:")
    print("  [VisualiseCode]def hello():\\n    print('Hi')[/VisualiseCode]")
    print("  [VisualiseGraph:bar]Python:85,JavaScript:72,Go:68[/VisualiseGraph]")
    print("  [VisualiseGraph:bar|heaven]Python:85,JS:72[/VisualiseGraph]")
    print("  [VisualiseGraph:line]Jan:10,Feb:20,Mar:15[/VisualiseGraph]")
    print("  [VisualiseGraph:line|dark]Data1:5,Data2:10[/VisualiseGraph]")
    print("\nGraph themes: heaven (light), dark (dark mode), matrix (green terminal)")
    print()
    
    # Check for file argument
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            prompt = f.read().strip()
        print(f"✓ Loaded from {sys.argv[1]}")
    else:
        prompt = input("Enter your text (with optional markers): ").strip()

    if not prompt:
        print("❌ Error: No text provided.")
        return 1

    video_path = generate_main_video(prompt, save_mp3=prefs["save_mp3"], prefs=prefs)
    
    if not video_path:
        return 1
    
    print("\n" + "="*60)
    print("✅ GENERATION COMPLETE")
    print("="*60)
    print(f"\n📹 Video: {video_path}")
    print(f"📁 Output directory: {config.OUTPUT_DIR}")
    
    if prefs["save_mp3"]:
        print(f"🎵 Audio: {os.path.join(config.OUTPUT_DIR, 'output_audio.mp3')}")
    
    print()
    
    return 0


if __name__ == "__main__":
    exit(main())