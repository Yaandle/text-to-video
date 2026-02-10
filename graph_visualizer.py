"""
Graph visualizer with animated charts
Generates video of data visualization building up over time
"""

from elevenlabs.client import ElevenLabs
import os
from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.video.VideoClip import VideoClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import config

# Graph Settings
BACKGROUND_COLOR = (255, 255, 255)
GRAPH_COLOR = (59, 130, 246)  # Blue
GRID_COLOR = (229, 231, 235)  # Light gray
TEXT_COLOR = (31, 41, 55)     # Dark gray
ACCENT_COLOR = (239, 68, 68)  # Red for highlights

PADDING = 80
FONT_SIZE = 24
TITLE_FONT_SIZE = 36

FONT_PATH = config.FONT_PATH_ARIAL


def generate_bar_chart_video(data: dict, title: str, narration: str, 
                             output_name: str = "chart_video"):
    """
    Generate an animated bar chart video.
    
    Args:
        data: Dictionary of {label: value}
        title: Chart title
        narration: Audio narration text
        output_name: Output filename (without extension)
    
    Returns:
        tuple: (video_path, audio_path)
    """
    
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
    
    # Load audio
    audio_clip = AudioFileClip(audio_path)
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
    
    def make_frame(t):
        """Generate frame with animated bar chart"""
        img = Image.new('RGB', (config.VIDEO_WIDTH, config.VIDEO_HEIGHT), 
                       color=BACKGROUND_COLOR)
        draw = ImageDraw.Draw(img)
        
        # Draw title
        title_bbox = draw.textbbox((0, 0), title, font=title_font)
        title_width = title_bbox[2] - title_bbox[0]
        title_x = (config.VIDEO_WIDTH - title_width) // 2
        draw.text((title_x, PADDING // 2), title, font=title_font, fill=TEXT_COLOR)
        
        # Calculate animation progress
        progress = min(t / duration, 1.0)
        
        # Chart origin
        chart_x = PADDING
        chart_y = config.VIDEO_HEIGHT - PADDING - 50  # Bottom of chart
        
        # Draw horizontal grid lines
        for i in range(5):
            y = chart_y - (i * chart_height // 4)
            draw.line([(chart_x, y), (chart_x + chart_width, y)], 
                     fill=GRID_COLOR, width=1)
            
            # Draw value labels
            value_label = f"{int(max_value * i / 4)}"
            draw.text((chart_x - 50, y - 10), value_label, font=font, fill=TEXT_COLOR)
        
        # Draw bars
        for i, (label, value) in enumerate(zip(labels, values)):
            # Calculate bar position
            bar_x = chart_x + (i * (bar_width + bar_spacing)) + bar_spacing
            
            # Animated bar height
            bar_height = (value / max_value) * chart_height * progress
            bar_y = chart_y - bar_height
            
            # Draw bar
            draw.rectangle(
                [(bar_x, bar_y), (bar_x + bar_width, chart_y)],
                fill=GRAPH_COLOR,
                outline=GRAPH_COLOR
            )
            
            # Draw value on top of bar if visible
            if bar_height > 30:
                value_text = str(int(value * progress))
                value_bbox = draw.textbbox((0, 0), value_text, font=font)
                value_width = value_bbox[2] - value_bbox[0]
                value_x = bar_x + (bar_width - value_width) // 2
                draw.text((value_x, bar_y - 30), value_text, font=font, fill=TEXT_COLOR)
            
            # Draw label
            label_bbox = draw.textbbox((0, 0), label, font=font)
            label_width = label_bbox[2] - label_bbox[0]
            label_x = bar_x + (bar_width - label_width) // 2
            draw.text((label_x, chart_y + 10), label, font=font, fill=TEXT_COLOR)
        
        return np.array(img)
    
    # Create video clip
    print("📊 Creating graph visualization...")
    video_clip = VideoClip(make_frame, duration=duration)
    video_clip = video_clip.with_audio(audio_clip)
    
    # Export
    video_path = os.path.join(config.OUTPUT_DIR, f"{output_name}.mp4")
    print(f"💾 Exporting video to {video_path}...")
    video_clip.write_videofile(video_path, fps=config.FPS)
    
    print("✅ Graph video generated successfully!")
    
    # Cleanup
    audio_clip.close()
    video_clip.close()
    
    return video_path, audio_path


def generate_line_graph_video(data: dict, title: str, narration: str,
                              output_name: str = "line_graph_video"):
    """
    Generate an animated line graph video.
    
    Args:
        data: Dictionary of {x_label: y_value}
        title: Graph title
        narration: Audio narration text
        output_name: Output filename (without extension)
    
    Returns:
        tuple: (video_path, audio_path)
    """
    
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
    
    # Load audio
    audio_clip = AudioFileClip(audio_path)
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
    
    def make_frame(t):
        """Generate frame with animated line graph"""
        img = Image.new('RGB', (config.VIDEO_WIDTH, config.VIDEO_HEIGHT), 
                       color=BACKGROUND_COLOR)
        draw = ImageDraw.Draw(img)
        
        # Draw title
        title_bbox = draw.textbbox((0, 0), title, font=title_font)
        title_width = title_bbox[2] - title_bbox[0]
        title_x = (config.VIDEO_WIDTH - title_width) // 2
        draw.text((title_x, PADDING // 2), title, font=title_font, fill=TEXT_COLOR)
        
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
                     fill=GRID_COLOR, width=2)
            
            # Value labels
            value_range = max_value - min_value
            value_label = f"{int(min_value + (value_range * i / 4))}"
            draw.text((chart_x - 50, y - 10), value_label, font=font, fill=TEXT_COLOR)
        
        # Calculate point positions
        x_step = chart_width / (num_points - 1) if num_points > 1 else chart_width
        
        points = []
        for i in range(min(points_to_show, num_points)):
            x = chart_x + (i * x_step)
            normalized_value = (values[i] - min_value) / (max_value - min_value) if max_value != min_value else 0.5
            y = chart_y - (normalized_value * chart_height)
            points.append((x, y))
        
        # Draw line
        if len(points) >= 2:
            draw.line(points, fill=GRAPH_COLOR, width=4)
        
        # Draw points and labels
        for i, (x, y) in enumerate(points):
            # Draw point
            radius = 6
            draw.ellipse([(x - radius, y - radius), (x + radius, y + radius)], 
                        fill=ACCENT_COLOR, outline=ACCENT_COLOR)
            
            # Draw x-axis label
            label = labels[i]
            label_bbox = draw.textbbox((0, 0), label, font=font)
            label_width = label_bbox[2] - label_bbox[0]
            draw.text((x - label_width // 2, chart_y + 10), label, 
                     font=font, fill=TEXT_COLOR)
        
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