"""
Shared configuration for video generation system
"""
import os
import sys
import warnings
from dotenv import load_dotenv

load_dotenv()

# Video Settings
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 720
FPS = 15
BACKGROUND_COLOR = (255, 255, 255)
TEXT_COLOR = (0, 0, 0)               # RGB tuple

# Text rendering
FONT_SIZE = 50
TEXT_WRAP_WIDTH = 40
MAX_DISPLAY_LINES = 2


# ElevenLabs Settings
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
if not ELEVENLABS_API_KEY:
    raise RuntimeError(
        "ELEVENLABS_API_KEY not set in environment. "
        "Please set it in .env file or as an environment variable. "
        "NEVER hard-code secrets in source code."
    )

VOICE_ID = "HOzOzWXzUCwAHOzOzWfwAHHWXf7"
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

        #  else:  # Linux
        #    font_dirs = [
        #        os.path.expanduser("~/.fonts"),
        #        "/usr/share/fonts",
        #        "/usr/local/share/fonts",
        #    ]
        #    for font_dir in font_dirs:
        #        font_path = os.path.join(font_dir, font_name)
        #        if os.path.exists(font_path):
        #            return font_path
    
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
FONT_PATH_ATKINSON = _get_font_path("Atkinson-Hyperlegible-Regular.ttf", fallback="Arial.ttf")


# Output Paths
OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# =====================
# Video Generator Settings
# =====================
SAVE_MP3_PROMPT = True  # Ask user about saving MP3 at startup
USE_CODE_VISUALIZER_DEFAULT = True
USE_GRAPH_VISUALIZER_DEFAULT = False

# =====================
# Code Visualizer Settings
# =====================
USE_CODE_VISUALIZER_DEFAULT = True
CODE_VIS_DURATION = 8.0  
CODE_VIS_FONT_SIZE = 18
CODE_VIS_LINE_HEIGHT = 26
CODE_VIS_DEFAULT_THEME = "heaven"
CODE_VIS_DEFAULT_MODE = "typewriter"
CODE_VIS_THEMES = ["heaven", "dark", "matrix"]
CODE_VIS_MODES = ["typewriter", "static"]

# =====================
# Graph Visualizer Settings
# =====================
USE_GRAPH_VISUALIZER_DEFAULT = True
GRAPH_VIS_PADDING = 80
GRAPH_VIS_FONT_SIZE = 24
GRAPH_VIS_TITLE_FONT_SIZE = 48