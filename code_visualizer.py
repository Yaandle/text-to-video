"""
Code block visualizer with syntax highlighting
Generates video of code appearing line-by-line with Carbon-style design
"""

from elevenlabs.client import ElevenLabs
import os
from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.video.VideoClip import VideoClip, ColorClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import ImageFormatter
from pygments.styles import get_style_by_name
import config

# Code Display Settings
BACKGROUND_COLOR = (40, 44, 52)  # Dark background (Atom One Dark style)
PADDING = 60
CODE_FONT_SIZE = 28
TITLE_FONT_SIZE = 32

# Font paths - monospace for code
CODE_FONT_PATH = config.FONT_PATH_CONSOLAS
TITLE_FONT_PATH = config.FONT_PATH_ARIAL


def generate_code_video(code: str, language: str, narration: str, output_name: str = "code_video"):
    """
    Generate a video with syntax-highlighted code appearing line-by-line.
    
    Args:
        code: The code snippet to display
        language: Programming language (python, javascript, java, etc.)
        narration: Text for audio narration
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
    
    # Split code into lines
    code_lines = code.strip().split('\n')
    total_lines = len(code_lines)
    
    # Load fonts
    try:
        code_font = ImageFont.truetype(CODE_FONT_PATH, CODE_FONT_SIZE)
        title_font = ImageFont.truetype(TITLE_FONT_PATH, TITLE_FONT_SIZE)
    except OSError as e:
        print(f"❌ Font error: {e}")
        raise
    
    # Define syntax colors (Atom One Dark theme)
    SYNTAX_COLORS = {
        'keyword': (198, 120, 221),      # Purple
        'string': (152, 195, 121),       # Green
        'comment': (92, 99, 112),        # Gray
        'function': (97, 175, 239),      # Blue
        'number': (209, 154, 102),       # Orange
        'default': (171, 178, 191),      # Light gray
    }
    
    def get_syntax_color(token_type):
        """Simple syntax coloring based on token type"""
        token_str = str(token_type).lower()
        
        if 'keyword' in token_str:
            return SYNTAX_COLORS['keyword']
        elif 'string' in token_str:
            return SYNTAX_COLORS['string']
        elif 'comment' in token_str:
            return SYNTAX_COLORS['comment']
        elif 'name.function' in token_str or 'name.builtin' in token_str:
            return SYNTAX_COLORS['function']
        elif 'number' in token_str:
            return SYNTAX_COLORS['number']
        else:
            return SYNTAX_COLORS['default']
    
    def make_frame(t):
        """Generate frame with code appearing line-by-line"""
        img = Image.new('RGB', (config.VIDEO_WIDTH, config.VIDEO_HEIGHT), color=BACKGROUND_COLOR)
        draw = ImageDraw.Draw(img)
        
        # Calculate how many lines to show
        lines_to_show = int(total_lines * (t / duration))
        lines_to_show = min(lines_to_show, total_lines)
        
        # Draw title bar (Carbon-style)
        title_height = 50
        draw.rectangle([(0, 0), (config.VIDEO_WIDTH, title_height)], fill=(50, 54, 62))
        
        # Draw dots (macOS style)
        dot_colors = [(255, 95, 86), (255, 189, 46), (39, 201, 63)]
        dot_y = title_height // 2
        for i, color in enumerate(dot_colors):
            dot_x = 20 + (i * 25)
            draw.ellipse([(dot_x, dot_y - 6), (dot_x + 12, dot_y + 6)], fill=color)
        
        # Draw language label
        lang_text = f"  {language}"
        draw.text((config.VIDEO_WIDTH // 2 - 30, dot_y - 8), lang_text, 
                 font=title_font, fill=(171, 178, 191))
        
        # Get lexer for syntax highlighting
        try:
            from pygments.lexers import get_lexer_by_name
            from pygments.token import Token
            lexer = get_lexer_by_name(language, stripall=True)
        except Exception:
            lexer = None
        
        # Draw code lines
        y_offset = title_height + PADDING
        line_height = CODE_FONT_SIZE + 10
        
        current_code = '\n'.join(code_lines[:lines_to_show])
        
        if lexer:
            # Tokenize for syntax highlighting
            tokens = list(lexer.get_tokens(current_code))
            
            x = PADDING
            y = y_offset
            
            for token_type, token_value in tokens:
                if token_value == '\n':
                    y += line_height
                    x = PADDING
                    continue
                
                color = get_syntax_color(token_type)
                draw.text((x, y), token_value, font=code_font, fill=color)
                
                # Move x position
                bbox = draw.textbbox((x, y), token_value, font=code_font)
                x = bbox[2]
        else:
            # Fallback without syntax highlighting
            draw.multiline_text(
                (PADDING, y_offset),
                current_code,
                font=code_font,
                fill=SYNTAX_COLORS['default'],
                spacing=10
            )
        
        return np.array(img)
    
    # Create video clip
    print("🎬 Creating code visualization...")
    video_clip = VideoClip(make_frame, duration=duration)
    video_clip = video_clip.with_audio(audio_clip)
    
    # Export
    video_path = os.path.join(config.OUTPUT_DIR, f"{output_name}.mp4")
    print(f"💾 Exporting video to {video_path}...")
    video_clip.write_videofile(video_path, fps=config.FPS)
    
    print("✅ Code video generated successfully!")
    
    # Cleanup
    audio_clip.close()
    video_clip.close()
    
    return video_path, audio_path


# Example usage
if __name__ == "__main__":
    sample_code = """def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

# Generate first 10 numbers
for i in range(10):
    print(f"F({i}) = {fibonacci(i)}")"""
    
    narration = """
    Here's a simple recursive Fibonacci function in Python. 
    It checks if n is less than or equal to 1, and if so, returns n. 
    Otherwise, it recursively calls itself with n minus 1 and n minus 2, 
    then adds the results together. Finally, we loop through the first 10 
    Fibonacci numbers and print them out.
    """
    
    generate_code_video(
        code=sample_code,
        language="python",
        narration=narration,
        output_name="fibonacci_example"
    )