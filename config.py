"""
Shared configuration for video generation system
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Video Settings
VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
FPS = 24

# ElevenLabs Settings
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = "RF0O2wEkFIOz81sMfUPn"
MODEL_ID = "eleven_multilingual_v2"

# Output Paths
OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)