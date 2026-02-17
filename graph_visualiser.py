"""
Graph visualizer with animated charts and theme support
Generates minimalist data visualization videos with heaven, dark, and matrix themes

OPTIMIZED: Returns VideoClips directly instead of writing/reading files
"""

from elevenlabs.client import ElevenLabs
import os
from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.video.VideoClip import VideoClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import config
import tempfile
import wave

PADDING = config.GRAPH_VIS_PADDING
FONT_SIZE = config.GRAPH_VIS_FONT_SIZE
TITLE_FONT_SIZE = config.GRAPH_VIS_TITLE_FONT_SIZE
FONT_PATH = config.FONT_PATH_ARIAL

# Theme definitions
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


def create_silent_audio_clip(duration: float) -> AudioFileClip:
    """Create silent audio efficiently using chunked writing."""
    sample_rate = 44100
    temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    temp_path = temp_file.name
    temp_file.close()
    
    with wave.open(temp_path, 'w') as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        
        chunk_size = sample_rate
        silent_chunk = b'\x00\x00' * chunk_size
        
        for _ in range(int(duration)):
            wav.writeframes(silent_chunk)
        
        remaining_samples = int((duration - int(duration)) * sample_rate)
        if remaining_samples > 0:
            wav.writeframes(b'\x00\x00' * remaining_samples)
    
    return AudioFileClip(temp_path)


def create_bar_chart_clip(data: dict, title: str, audio_clip: AudioFileClip, theme: str = "heaven") -> VideoClip:
    """Generate bar chart VideoClip with caching and theme support."""
    colors = THEMES.get(theme, THEMES["heaven"])
    duration = audio_clip.duration
    
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    title_font = ImageFont.truetype(FONT_PATH, TITLE_FONT_SIZE)
    
    labels = list(data.keys())
    values = list(data.values())
    max_value = max(values)
    
    chart_width = config.VIDEO_WIDTH - (2 * PADDING)
    chart_height = config.VIDEO_HEIGHT - (3 * PADDING) - 100
    
    bar_width = chart_width // (len(labels) * 2)
    bar_spacing = bar_width
    
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    bg_color = hex_to_rgb(colors["bg"])
    graph_color = hex_to_rgb(colors["graph"])
    grid_color = hex_to_rgb(colors["grid"])
    text_color = hex_to_rgb(colors["text"])
    
    frame_cache = {}
    cache_interval = 0.05
    
    def generate_bar_frame(t):
        img = Image.new('RGB', (config.VIDEO_WIDTH, config.VIDEO_HEIGHT), color=bg_color)
        draw = ImageDraw.Draw(img)
        
        # Draw title
        title_bbox = draw.textbbox((0, 0), title, font=title_font)
        title_width = title_bbox[2] - title_bbox[0]
        draw.text(((config.VIDEO_WIDTH - title_width)//2, PADDING), title, font=title_font, fill=text_color)
        
        progress = min(t / duration, 1.0)
        chart_x = PADDING
        chart_y = config.VIDEO_HEIGHT - PADDING - 50
        
        # Grid lines
        for i in range(5):
            y = chart_y - (i * chart_height // 4)
            draw.line([(chart_x, y), (chart_x + chart_width, y)], fill=grid_color, width=1)
            value_label = str(int(max_value * i / 4))
            label_bbox = draw.textbbox((0, 0), value_label, font=font)
            label_width = label_bbox[2] - label_bbox[0]
            draw.text((chart_x - label_width - 20, y - 10), value_label, font=font, fill=text_color)
        
        # Bars
        for i, (label, value) in enumerate(zip(labels, values)):
            bar_x = chart_x + (i * (bar_width + bar_spacing)) + bar_spacing
            bar_height = (value / max_value) * chart_height * progress
            bar_y = chart_y - bar_height
            draw.rectangle([(bar_x, bar_y), (bar_x + bar_width, chart_y)], fill=graph_color)
            
            # Value on top
            if bar_height > 30 and progress > 0:
                value_text = str(int(value * progress))
                value_bbox = draw.textbbox((0, 0), value_text, font=font)
                value_width = value_bbox[2] - value_bbox[0]
                draw.text((bar_x + (bar_width - value_width)//2, bar_y - 25), value_text, font=font, fill=text_color)
            
            # Label
            label_bbox = draw.textbbox((0, 0), label, font=font)
            label_width = label_bbox[2] - label_bbox[0]
            draw.text((bar_x + (bar_width - label_width)//2, chart_y + 15), label, font=font, fill=text_color)
        
        return np.array(img)
    
    def make_frame(t):
        key = int(t / cache_interval)
        if key not in frame_cache:
            frame_cache[key] = generate_bar_frame(t)
        return frame_cache[key]
    
    return VideoClip(make_frame, duration=duration)


def create_line_graph_clip(data: dict, title: str, audio_clip: AudioFileClip, theme: str = "heaven") -> VideoClip:
    """Generate line graph VideoClip with caching and theme support."""
    colors = THEMES.get(theme, THEMES["heaven"])
    duration = audio_clip.duration
    
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    title_font = ImageFont.truetype(FONT_PATH, TITLE_FONT_SIZE)
    
    labels = list(data.keys())
    values = list(data.values())
    max_value, min_value = max(values), min(values)
    
    chart_width = config.VIDEO_WIDTH - (2 * PADDING)
    chart_height = config.VIDEO_HEIGHT - (3 * PADDING) - 100
    
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    bg_color = hex_to_rgb(colors["bg"])
    line_color = hex_to_rgb(colors["line"])
    accent_color = hex_to_rgb(colors["accent"])
    grid_color = hex_to_rgb(colors["grid"])
    text_color = hex_to_rgb(colors["text"])
    
    frame_cache = {}
    cache_interval = 0.05
    
    def generate_line_frame(t):
        img = Image.new('RGB', (config.VIDEO_WIDTH, config.VIDEO_HEIGHT), color=bg_color)
        draw = ImageDraw.Draw(img)
        
        title_bbox = draw.textbbox((0, 0), title, font=title_font)
        title_width = title_bbox[2] - title_bbox[0]
        draw.text(((config.VIDEO_WIDTH - title_width)//2, PADDING), title, font=title_font, fill=text_color)
        
        progress = min(t / duration, 1.0)
        points_to_show = max(2, int(len(labels) * progress))
        
        chart_x, chart_y = PADDING, config.VIDEO_HEIGHT - PADDING - 50
        
        # Grid
        for i in range(5):
            y = chart_y - (i * chart_height // 4)
            draw.line([(chart_x, y), (chart_x + chart_width, y)], fill=grid_color, width=1)
            value_range = max_value - min_value
            value_label = str(int(min_value + (value_range * i / 4)))
            value_bbox = draw.textbbox((0, 0), value_label, font=font)
            draw.text((chart_x - (value_bbox[2] - value_bbox[0]) - 20, y - 10), value_label, font=font, fill=text_color)
        
        x_step = chart_width / (len(labels) - 1) if len(labels) > 1 else chart_width
        points = []
        for i in range(min(points_to_show, len(labels))):
            x = chart_x + i * x_step
            normalized_value = (values[i] - min_value) / (max_value - min_value) if max_value != min_value else 0.5
            y = chart_y - (normalized_value * chart_height)
            points.append((x, y))
        
        if len(points) >= 2:
            draw.line(points, fill=line_color, width=3)
        
        for i, (x, y) in enumerate(points):
            r = 5
            draw.ellipse([(x - r, y - r), (x + r, y + r)], fill=accent_color, outline=accent_color)
            label_bbox = draw.textbbox((0, 0), labels[i], font=font)
            label_width = label_bbox[2] - label_bbox[0]
            draw.text((x - label_width // 2, chart_y + 15), labels[i], font=font, fill=text_color)
        
        return np.array(img)
    
    def make_frame(t):
        key = int(t / cache_interval)
        if key not in frame_cache:
            frame_cache[key] = generate_line_frame(t)
        return frame_cache[key]
    
    return VideoClip(make_frame, duration=duration)
