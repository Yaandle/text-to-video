from elevenlabs.client import ElevenLabs
import os
from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.video.VideoClip import VideoClip, ColorClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from PIL import Image, ImageDraw, ImageFont
import textwrap
import numpy as np
import config

# ----------------------
# Configuration
# ----------------------

# Import from config module to ensure single source of truth
VIDEO_WIDTH = config.VIDEO_WIDTH
VIDEO_HEIGHT = config.VIDEO_HEIGHT
FPS = config.FPS

BACKGROUND_COLOR = (255, 255, 255)
TEXT_COLOR = (0, 0, 0)
FONT_SIZE = 50
TEXT_WRAP_WIDTH = 40
MAX_DISPLAY_LINES = 2

# Font path from config (platform-aware)
FONT_PATH = config.FONT_PATH_ARIAL


def main():
    """Main function to generate text-to-video with narration."""
    # ----------------------
    # Initialize ElevenLabs Client
    # ----------------------
    client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)

    # ----------------------
    # Get User Input
    # ----------------------
    prompt = input("Enter the text you want to speak: ").strip()

    if not prompt:
        print("❌ Error: No text provided.")
        return 1

    # ----------------------
    # Generate Audio
    # ----------------------
    print("🎙️ Generating audio...")
    audio_generator = client.text_to_speech.convert(
        text=prompt,
        voice_id=config.VOICE_ID,
        model_id=config.MODEL_ID,
        output_format="mp3_44100_128",
    )

    audio_path = "output_audio.mp3"
    with open(audio_path, "wb") as f:
        for chunk in audio_generator:
            f.write(chunk)

    print("✅ Audio saved as output_audio.mp3")

    # Load audio clip
    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration

    # ----------------------
    # Create Base Video Clip
    # ----------------------
    video_clip = ColorClip(
        size=(VIDEO_WIDTH, VIDEO_HEIGHT),
        color=BACKGROUND_COLOR,
        duration=duration
    )

    # ----------------------
    # Setup Font and Text
    # ----------------------
    try:
        font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    except OSError as e:
        print(f"❌ Error: Font not found. {e}")
        return 1

    # ----------------------
    # Create Typewriter Animation
    # ----------------------
    def make_frame(t):
        """Generate a frame with typewriter animation effect."""
        img = Image.new('RGB', (VIDEO_WIDTH, VIDEO_HEIGHT), color=BACKGROUND_COLOR)
        draw = ImageDraw.Draw(img)

        # Calculate how many characters to display based on time
        chars_to_display = int(len(prompt) * (t / duration))
        display_text = prompt[:chars_to_display]
        
        # Wrap text and limit to max lines
        current_lines = textwrap.wrap(display_text, width=TEXT_WRAP_WIDTH)
        if len(current_lines) > MAX_DISPLAY_LINES:
            current_lines = current_lines[-MAX_DISPLAY_LINES:]
        
        final_text = "\n".join(current_lines)

        # Calculate text position (centered in bottom third)
        bbox = draw.multiline_textbbox((0, 0), final_text, font=font, align='center')
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        x = (VIDEO_WIDTH - text_width) / 2
        y = (VIDEO_HEIGHT * 2 / 3) - (text_height / 2)

        # Draw text
        draw.multiline_text(
            (x, y),
            final_text,
            font=font,
            fill=TEXT_COLOR,
            align='center'
        )
        
        return np.array(img)

    # ----------------------
    # Create Text Animation Clip
    # ----------------------
    print("🎬 Creating video with typewriter animation...")
    text_clip = VideoClip(make_frame, duration=duration)

    # ----------------------
    # Composite Final Video
    # ----------------------
    final_clip = CompositeVideoClip([video_clip, text_clip])
    final_clip = final_clip.with_audio(audio_clip)

    # ----------------------
    # Export Video
    # ----------------------
    output_path = "output_video.mp4"
    print(f"💾 Exporting video to {output_path}...")
    final_clip.write_videofile(output_path, fps=FPS)

    print("✅ Video saved successfully!")
    print(f"📹 Video: {output_path}")
    print(f"🎵 Audio: {audio_path}")

    # ----------------------
    # Cleanup
    # ----------------------
    audio_clip.close()
    final_clip.close()
    
    return 0


if __name__ == "__main__":
    exit(main())