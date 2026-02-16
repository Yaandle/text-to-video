"""
Graph visualizer with animated charts and theme support
Generates minimalist data visualization videos with heaven, dark, and matrix themes
"""

from elevenlabs.client import ElevenLabs
import os
from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.video.VideoClip import VideoClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import config
import tempfile
import wave

PADDING = config.GRAPH_VIS_PADDING
FONT_SIZE = config.GRAPH_VIS_FONT_SIZE
TITLE_FONT_SIZE = config.GRAPH_VIS_TITLE_FONT_SIZE

FONT_PATH = config.FONT_PATH_ARIAL

# Theme definitions matching code_visualizer.py
THEMES = {
    "heaven": {
        "bg": "#FFFFFF",
        "graph": "#3B82F6",
        "accent": "#F59E0B",
        "grid": "#E5E7EB",
        "text": "#1F2937",
        "subtitle": "#6B7280",
        "line": "#3B82F6",
        "area": "#DBEAFE",
    },
    "dark": {
        "bg": "#1E1E1E",
        "graph": "#60A5FA",
        "accent": "#FBBF24",
        "grid": "#374151",
        "text": "#F3F4F6",
        "subtitle": "#9CA3AF",
        "line": "#60A5FA",
        "area": "#1E3A8A",
    },
    "matrix": {
        "bg": "#0D0208",
        "graph": "#00FF41",
        "accent": "#39FF14",
        "grid": "#003D00",
        "text": "#00FF41",
        "subtitle": "#008F11",
        "line": "#00FF41",
        "area": "#001400",
    }
}


def generate_bar_chart_video(data: dict, title: str, narration: str, 
                             output_name: str = "chart_video",
                             theme: str = "heaven"):
    """
    Generate an animated bar chart video with theme support.
    
    Args:
        data: Dictionary of {label: value}
        title: Chart title
        narration: Audio narration text (empty string to skip audio)
        output_name: Output filename (without extension)
        theme: Color theme - "heaven", "dark", or "matrix"
    
    Returns:
        tuple: (video_path, audio_path or None)
    """
    
    if theme not in THEMES:
        theme = "heaven"
    
    colors = THEMES[theme]
    
    # CRITICAL FIX: Handle empty narration (when embedded in main video)
    audio_path = None
    if narration and narration.strip():
        print(f"🎙️ Generating audio narration...")
        
        # Initialize ElevenLabs client
        client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)
        
        # Generate audio
        audio_generator = client.text_to_speech.convert(
            text=narration,
            voice_id=config.VOICE_ID,
            model_id=config.MODEL_ID,
            output_format="mp3_44100_128",
        )
        
        audio_path = os.path.join(config.OUTPUT_DIR, f"{output_name}_audio.mp3")
        with open(audio_path, "wb") as f:
            for chunk in audio_generator:
                f.write(chunk)
        
        print("✅ Audio generated")
        audio_clip = AudioFileClip(audio_path)
    else:
        # Create silent audio for fixed duration
        print("⏭️  Using silent audio (embedded mode)")
        test_duration = 6.0  # Minimum for graph visualization
        sample_rate = 44100
        num_samples = int(sample_rate * test_duration)
        
        wav_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        with wave.open(wav_file.name, 'w') as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(b'\x00\x00' * num_samples)
        
        audio_clip = AudioFileClip(wav_file.name)
    
    duration = audio_clip.duration
    
    # Load fonts
    try:
        font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
        title_font = ImageFont.truetype(FONT_PATH, TITLE_FONT_SIZE)
    except OSError as e:
        print(f"❌ Font error: {e}")
        raise
    
    # Prepare data
    labels = list(data.keys())
    values = list(data.values())
    max_value = max(values)
    num_bars = len(labels)
    
    # Chart dimensions
    chart_width = config.VIDEO_WIDTH - (2 * PADDING)
    chart_height = config.VIDEO_HEIGHT - (3 * PADDING) - 100  # Space for title and labels
    
    bar_width = chart_width // (num_bars * 2)
    bar_spacing = bar_width
    
    # Convert hex to RGB tuple
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    bg_color = hex_to_rgb(colors["bg"])
    graph_color = hex_to_rgb(colors["graph"])
    grid_color = hex_to_rgb(colors["grid"])
    text_color = hex_to_rgb(colors["text"])
    
    def make_frame(t):
        """Generate frame with animated bar chart"""
        img = Image.new('RGB', (config.VIDEO_WIDTH, config.VIDEO_HEIGHT), 
                       color=bg_color)
        draw = ImageDraw.Draw(img)
        
        # Draw title
        title_bbox = draw.textbbox((0, 0), title, font=title_font)
        title_width = title_bbox[2] - title_bbox[0]
        title_x = (config.VIDEO_WIDTH - title_width) // 2
        draw.text((title_x, PADDING), title, font=title_font, fill=text_color)
        
        # Calculate animation progress
        progress = min(t / duration, 1.0)
        
        # Chart origin
        chart_x = PADDING
        chart_y = config.VIDEO_HEIGHT - PADDING - 50  # Bottom of chart
        
        # Draw subtle horizontal grid lines
        for i in range(5):
            y = chart_y - (i * chart_height // 4)
            draw.line([(chart_x, y), (chart_x + chart_width, y)], 
                     fill=grid_color, width=1)
            
            # Draw value labels (right-aligned)
            value_label = f"{int(max_value * i / 4)}"
            value_bbox = draw.textbbox((0, 0), value_label, font=font)
            value_width = value_bbox[2] - value_bbox[0]
            draw.text((chart_x - value_width - 20, y - 10), value_label, font=font, fill=text_color)
        
        # Draw bars with smooth animation
        for i, (label, value) in enumerate(zip(labels, values)):
            # Calculate bar position
            bar_x = chart_x + (i * (bar_width + bar_spacing)) + bar_spacing
            
            # Animated bar height
            bar_height = (value / max_value) * chart_height * progress
            bar_y = chart_y - bar_height
            
            # Draw bar
            draw.rectangle(
                [(bar_x, bar_y), (bar_x + bar_width, chart_y)],
                fill=graph_color
            )
            
            # Draw value on top of bar if visible
            if bar_height > 30 and progress > 0:
                value_text = str(int(value * progress))
                value_bbox = draw.textbbox((0, 0), value_text, font=font)
                value_width = value_bbox[2] - value_bbox[0]
                value_x = bar_x + (bar_width - value_width) // 2
                draw.text((value_x, bar_y - 25), value_text, font=font, fill=text_color)
            
            # Draw label
            label_bbox = draw.textbbox((0, 0), label, font=font)
            label_width = label_bbox[2] - label_bbox[0]
            label_x = bar_x + (bar_width - label_width) // 2
            draw.text((label_x, chart_y + 15), label, font=font, fill=text_color)
        
        return np.array(img)
    
    # Create video clip
    print("📊 Creating bar chart visualization...")
    video_clip = VideoClip(make_frame, duration=duration)
    video_clip = video_clip.with_audio(audio_clip)
    
    # Export
    video_path = os.path.join(config.OUTPUT_DIR, f"{output_name}.mp4")
    print(f"💾 Exporting video to {video_path}...")
    video_clip.write_videofile(video_path, fps=config.FPS)
    
    print("✅ Bar chart video generated successfully!")
    
    # Cleanup
    audio_clip.close()
    video_clip.close()
    
    return video_path, audio_path


def generate_line_graph_video(data: dict, title: str, narration: str,
                              output_name: str = "line_graph_video",
                              theme: str = "heaven"):
    """
    Generate an animated line graph video with theme support.
    
    Args:
        data: Dictionary of {x_label: y_value}
        title: Graph title
        narration: Audio narration text (empty string to skip audio)
        output_name: Output filename (without extension)
        theme: Color theme - "heaven", "dark", or "matrix"
    
    Returns:
        tuple: (video_path, audio_path or None)
    """
    
    if theme not in THEMES:
        theme = "heaven"
    
    colors = THEMES[theme]
    
    # CRITICAL FIX: Handle empty narration (when embedded in main video)
    audio_path = None
    if narration and narration.strip():
        print(f"🎙️ Generating audio narration...")
        
        # Initialize ElevenLabs client
        client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)
        
        # Generate audio
        audio_generator = client.text_to_speech.convert(
            text=narration,
            voice_id=config.VOICE_ID,
            model_id=config.MODEL_ID,
            output_format="mp3_44100_128",
        )
        
        audio_path = os.path.join(config.OUTPUT_DIR, f"{output_name}_audio.mp3")
        with open(audio_path, "wb") as f:
            for chunk in audio_generator:
                f.write(chunk)
        
        print("✅ Audio generated")
        audio_clip = AudioFileClip(audio_path)
    else:
        # Create silent audio for fixed duration
        print("⏭️  Using silent audio (embedded mode)")
        test_duration = 6.0  # Minimum for graph visualization
        sample_rate = 44100
        num_samples = int(sample_rate * test_duration)
        
        wav_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        with wave.open(wav_file.name, 'w') as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(b'\x00\x00' * num_samples)
        
        audio_clip = AudioFileClip(wav_file.name)
    
    duration = audio_clip.duration
    
    # Load fonts
    try:
        font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
        title_font = ImageFont.truetype(FONT_PATH, TITLE_FONT_SIZE)
    except OSError as e:
        print(f"❌ Font error: {e}")
        raise
    
    # Prepare data
    labels = list(data.keys())
    values = list(data.values())
    max_value = max(values)
    min_value = min(values)
    num_points = len(labels)
    
    # Chart dimensions
    chart_width = config.VIDEO_WIDTH - (2 * PADDING)
    chart_height = config.VIDEO_HEIGHT - (3 * PADDING) - 100
    
    # Convert hex to RGB tuple
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    bg_color = hex_to_rgb(colors["bg"])
    line_color = hex_to_rgb(colors["line"])
    accent_color = hex_to_rgb(colors["accent"])
    grid_color = hex_to_rgb(colors["grid"])
    text_color = hex_to_rgb(colors["text"])
    
    def make_frame(t):
        """Generate frame with animated line graph"""
        img = Image.new('RGB', (config.VIDEO_WIDTH, config.VIDEO_HEIGHT), 
                       color=bg_color)
        draw = ImageDraw.Draw(img)
        
        # Draw title
        title_bbox = draw.textbbox((0, 0), title, font=title_font)
        title_width = title_bbox[2] - title_bbox[0]
        title_x = (config.VIDEO_WIDTH - title_width) // 2
        draw.text((title_x, PADDING), title, font=title_font, fill=text_color)
        
        # Calculate animation progress
        progress = min(t / duration, 1.0)
        points_to_show = int(num_points * progress)
        points_to_show = max(2, points_to_show)  # Show at least 2 points
        
        # Chart origin
        chart_x = PADDING
        chart_y = config.VIDEO_HEIGHT - PADDING - 50
        
        # Draw grid
        for i in range(5):
            y = chart_y - (i * chart_height // 4)
            draw.line([(chart_x, y), (chart_x + chart_width, y)], 
                     fill=grid_color, width=1)
            
            # Value labels (right-aligned)
            value_range = max_value - min_value
            value_label = f"{int(min_value + (value_range * i / 4))}"
            value_bbox = draw.textbbox((0, 0), value_label, font=font)
            value_width = value_bbox[2] - value_bbox[0]
            draw.text((chart_x - value_width - 20, y - 10), value_label, font=font, fill=text_color)
        
        # Calculate point positions
        x_step = chart_width / (num_points - 1) if num_points > 1 else chart_width
        
        points = []
        for i in range(min(points_to_show, num_points)):
            x = chart_x + (i * x_step)
            normalized_value = (values[i] - min_value) / (max_value - min_value) if max_value != min_value else 0.5
            y = chart_y - (normalized_value * chart_height)
            points.append((x, y))
        
        # Draw line with smooth animation
        if len(points) >= 2:
            draw.line(points, fill=line_color, width=3)
        
        # Draw points and labels
        for i, (x, y) in enumerate(points):
            # Draw point
            radius = 5
            draw.ellipse([(x - radius, y - radius), (x + radius, y + radius)], 
                        fill=accent_color, outline=accent_color)
            
            # Draw x-axis label
            label = labels[i]
            label_bbox = draw.textbbox((0, 0), label, font=font)
            label_width = label_bbox[2] - label_bbox[0]
            draw.text((x - label_width // 2, chart_y + 15), label, 
                     font=font, fill=text_color)
        
        return np.array(img)
    
    # Create video clip
    print("📈 Creating line graph visualization...")
    video_clip = VideoClip(make_frame, duration=duration)
    video_clip = video_clip.with_audio(audio_clip)
    
    # Export
    video_path = os.path.join(config.OUTPUT_DIR, f"{output_name}.mp4")
    print(f"💾 Exporting video to {video_path}...")
    video_clip.write_videofile(video_path, fps=config.FPS)
    
    print("✅ Line graph video generated successfully!")
    
    # Cleanup
    audio_clip.close()
    video_clip.close()
    
    return video_path, audio_path


# Example usage
if __name__ == "__main__":
    # Bar chart example
    performance_data = {
        "Mon": 45,
        "Tue": 62,
        "Wed": 58,
        "Thu": 71,
        "Fri": 89
    }
    
    narration_bar = """
    This chart shows our performance throughout the week. 
    Monday started slow at 45 points, but we saw steady improvement. 
    Tuesday jumped to 62, Wednesday dipped slightly to 58, 
    Thursday reached 71, and Friday we crushed it with 89 points!
    """
    
    generate_bar_chart_video(
        data=performance_data,
        title="Weekly Performance",
        narration=narration_bar,
        output_name="weekly_performance"
    )
    
    # Line graph example
    growth_data = {
        "Jan": 1000,
        "Feb": 1200,
        "Mar": 1800,
        "Apr": 2400,
        "May": 3200
    }
    
    narration_line = """
    Our user growth has been exceptional over the past five months.
    We started January with 1000 users, grew to 1200 in February,
    then saw accelerated growth reaching 1800 in March,
    2400 in April, and breaking through 3200 users in May.
    """
    
    generate_line_graph_video(
        data=growth_data,
        title="User Growth Trend",
        narration=narration_line,
        output_name="user_growth"
    )