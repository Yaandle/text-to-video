"""
Shared configuration for video generation system
"""
import os
import sys
import warnings
from dotenv import load_dotenv

load_dotenv()

# Video Settings
VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
FPS = 24

# ElevenLabs Settings
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
if not ELEVENLABS_API_KEY:
    raise RuntimeError(
        "ELEVENLABS_API_KEY not set in environment. "
        "Please set it in .env file or as an environment variable. "
        "NEVER hard-code secrets in source code."
    )

VOICE_ID = "RF0O2wEkFIOz81sMfUPn"
MODEL_ID = "eleven_multilingual_v2"

# Font Paths (Platform-aware)
def _get_font_path(font_name: str, fallback: str = "Arial.ttf") -> str:
    """Get platform-specific font path with fallback.
    
    Args:
        font_name: Font filename (e.g., 'consola.ttf', 'Arial.ttf')
        fallback: Fallback font name if primary not found
    
    Returns:
        Full path to font file
    """
    if sys.platform == "win32":
        font_path = os.path.join("C:\\Windows\\Fonts", font_name)
        if os.path.exists(font_path):
            return font_path
        fallback_path = os.path.join("C:\\Windows\\Fonts", fallback)
        if os.path.exists(fallback_path):
            return fallback_path
    elif sys.platform == "darwin":  # macOS
        font_dirs = [
            os.path.expanduser("~/Library/Fonts"),
            "/Library/Fonts",
            "/System/Library/Fonts",
        ]
        for font_dir in font_dirs:
            font_path = os.path.join(font_dir, font_name)
            if os.path.exists(font_path):
                return font_path
    else:  # Linux
        font_dirs = [
            os.path.expanduser("~/.fonts"),
            "/usr/share/fonts",
            "/usr/local/share/fonts",
        ]
        for font_dir in font_dirs:
            font_path = os.path.join(font_dir, font_name)
            if os.path.exists(font_path):
                return font_path
    
    # Fallback: return default name and let PIL handle it
    warnings.warn(
        f"Font '{font_name}' not found. Falling back to '{fallback}'. "
        "Font rendering may use default system font.",
        RuntimeWarning
    )
    return fallback

# Font configuration
FONT_PATH_ARIAL = _get_font_path("Arial.ttf")
FONT_PATH_CONSOLAS = _get_font_path("consola.ttf", fallback="Arial.ttf")

# Output Paths
OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)