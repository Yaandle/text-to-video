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
VIDEO_HEIGHT = 1920
FPS = 30


# Text rendering
FONT_SIZE = int(VIDEO_HEIGHT * 0.065)
TEXT_WRAP_WIDTH = 34


# ElevenLabs Settings
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
if not ELEVENLABS_API_KEY:
    raise RuntimeError(
        "ELEVENLABS_API_KEY not set in environment. "
        "Please set it in .env file or as an environment variable."
    )

VOICE_ID = ""
MODEL_ID = "eleven_multilingual_v2"

# Font Paths (Platform-aware)
def _get_font_path(font_name: str, fallback: str = "Arial.ttf") -> str:
    if sys.platform == "win32":
        font_path = os.path.join("C:\\Windows\\Fonts", font_name)
        if os.path.exists(font_path):
            return font_path
        fallback_path = os.path.join("C:\\Windows\\Fonts", fallback)
        if os.path.exists(fallback_path):
            return fallback_path
    warnings.warn(
        f"Font '{font_name}' not found. Falling back to '{fallback}'.",
        RuntimeWarning
    )
    return fallback

FONT_PATH_ARIAL     = _get_font_path("Arial.ttf")
FONT_PATH_CONSOLAS  = _get_font_path("consola.ttf", fallback="Arial.ttf")
FONT_PATH_ATKINSON  = _get_font_path("Atkinson-Hyperlegible-Regular.ttf", fallback="Arial.ttf")

# Output
OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Video Generator ────────────────────────────────────────────────────────────

USE_CODE_VISUALIZER_DEFAULT  = True
USE_GRAPH_VISUALIZER_DEFAULT = False

# ── Narrative ─────────────────────────────────────────────────────────────────
NARRATIVE_THEME = "dark"  
# Animation style for narrative text clip.
# Options: "typewriter" | "wordblurin" | "linescan"
# - typewriter : characters type in left-to-right (like code clips), glyph first
# - wordblurin : words spring+blur in with stagger (smoothed from original)
# - linescan   : line slides in from left with a light sweep highlight
NARRATIVE_STYLE = "wordblurin"

# ── Code Visualizer ───────────────────────────────────────────────────────────
CODE_VIS_DURATION      = 8.0
CODE_VIS_FONT_SIZE     = 18
CODE_VIS_LINE_HEIGHT   = 26
CODE_VIS_DEFAULT_THEME = "dark"
CODE_VIS_DEFAULT_MODE  = "linescan"
CODE_VIS_THEMES        = ["heaven", "dark", "matrix"]
CODE_VIS_MODES         = ["typewriter", "static"]

# ── Graph Visualizer ──────────────────────────────────────────────────────────
USE_GRAPH_VISUALIZER_DEFAULT = True
GRAPH_VIS_PADDING            = 80
GRAPH_VIS_FONT_SIZE          = 24
GRAPH_VIS_TITLE_FONT_SIZE    = 48