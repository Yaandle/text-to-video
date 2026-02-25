"""
animation_visualiser.py
-----------------------
Generates animated chart clips using the TypeScript/React animation pipeline.

Mirrors the interface of code_visualiser.py and graph_visualiser.py so
main.py can call it identically.

Flow:
  1.  agent_context.resolve_animation() selects component + parses data.
  2.  Serialise parsed data to JSON, write to a temp file.
  3.  Call Node.js render script (animations/render.js) via subprocess —
      Puppeteer renders the React component to PNG frames.
  4.  ffmpeg stitches frames into an MP4 clip and returns the path.

Marker syntax (in prompt.txt):
  [VisualiseAnimation:auto] title:Revenue,x:Jan|Feb|Mar,series1:2024:4|6|9 [/VisualiseAnimation]
  [VisualiseAnimation:pie_animated] title:Share,variant:donut,data:A:40,B:35,C:25 [/VisualiseAnimation]
"""

import glob
import json
import os
import subprocess
import tempfile
from typing import Optional

import config
from agent_context import resolve_animation

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_ANIMATIONS_DIR = os.path.join(os.path.dirname(__file__), "animations")
_RENDER_SCRIPT  = os.path.join(_ANIMATIONS_DIR, "render.js")
_FRAMES_DIR     = os.path.abspath(os.path.join(config.OUTPUT_DIR, "animation_frames"))


# ---------------------------------------------------------------------------
# Public interface (called by main.py / generate_main_video)
# ---------------------------------------------------------------------------

def generate_animation_clip(
    section_text: str,
    data_string: str,
    explicit_component_id: Optional[str] = "auto",
    output_path: Optional[str] = None,
    width: int = 1280,
    height: int = 720,
) -> Optional[str]:
    """
    Generate an animated chart MP4 clip.

    Parameters
    ----------
    section_text            : Narrative text surrounding the marker (used for
                              auto-selection context).
    data_string             : Raw data string from inside the marker tags.
    explicit_component_id   : Component to use, or 'auto' to let the agent decide.
    output_path             : Where to write the final MP4. Defaults to
                              OUTPUT_DIR/animation_<component_id>.mp4.
    width / height          : Frame dimensions (default 1280×720).

    Returns
    -------
    Path to the generated MP4, or None on failure.
    """
    print(f"\n[AnimationVisualiser] Resolving component...")

    try:
        component_id, component_meta, parsed_data = resolve_animation(
            section_text, data_string, explicit_component_id
        )
    except ValueError as e:
        print(f"❌ Agent context error: {e}")
        return None

    print(f"  ✓ Selected: {component_meta['display_name']} ({component_id})")
    print(f"  ✓ Parsed data keys: {list(parsed_data.keys())}")

    # -----------------------------------------------------------------------
    # Clear any stale frames from a previous run so the frame count check
    # below is accurate and ffmpeg doesn't pick up old frames.
    # -----------------------------------------------------------------------
    os.makedirs(_FRAMES_DIR, exist_ok=True)
    stale = glob.glob(os.path.join(_FRAMES_DIR, "frame_*.png"))
    if stale:
        print(f"  🧹 Clearing {len(stale)} stale frame(s) from previous run")
        for f in stale:
            try:
                os.remove(f)
            except OSError:
                pass

    # -----------------------------------------------------------------------
    # Write render payload to a temp JSON file
    # -----------------------------------------------------------------------
    render_params = component_meta.get("render_params", {})
    payload = {
        "componentId":     component_id,
        "data":            parsed_data,
        "width":           width or render_params.get("width", 1280),
        "height":          height or render_params.get("height", 720),
        "durationSeconds": render_params.get("duration_seconds", 4),
        # Always pass the absolute path so Node/Puppeteer writes frames
        # to the right location regardless of its working directory.
        "framesDir":       _FRAMES_DIR,
    }

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(payload, tmp, indent=2)
        payload_path = tmp.name

    print(f"  ✓ Render payload written: {payload_path}")
    print(f"  ✓ Frames will be written to: {_FRAMES_DIR}")

    # -----------------------------------------------------------------------
    # Call Node render script
    # -----------------------------------------------------------------------
    if not os.path.exists(_RENDER_SCRIPT):
        print(f"❌ Render script not found: {_RENDER_SCRIPT}")
        print("   Run: cd animations && npm install")
        os.unlink(payload_path)
        return None

    node_cmd = ["node", _RENDER_SCRIPT, payload_path]
    print(f"  → Running: {' '.join(node_cmd)}")

    result = subprocess.run(
        node_cmd,
        capture_output=True,
        text=True,
        cwd=_ANIMATIONS_DIR,
    )

    os.unlink(payload_path)

    # Print stdout/stderr regardless of exit code — helps diagnose silent failures
    if result.stdout.strip():
        print(f"  [node stdout]\n{result.stdout.strip()}")
    if result.stderr.strip():
        print(f"  [node stderr]\n{result.stderr.strip()}")

    if result.returncode != 0:
        print(f"❌ Node render failed (exit {result.returncode})")
        return None

    # -----------------------------------------------------------------------
    # Validate that frames were actually written
    # -----------------------------------------------------------------------
    written_frames = sorted(glob.glob(os.path.join(_FRAMES_DIR, "frame_*.png")))
    frame_count    = len(written_frames)

    if frame_count == 0:
        print(f"❌ Node exited 0 but wrote no frames to: {_FRAMES_DIR}")
        print("   Check that render.js uses the 'framesDir' field from the payload,")
        print("   and that Puppeteer has write access to that directory.")
        return None

    print(f"  ✓ {frame_count} frame(s) rendered to {_FRAMES_DIR}")

    # Detect the starting index (0-based or 1-based) so ffmpeg uses the right
    # pattern.  Puppeteer scripts sometimes start at frame_0000.png, sometimes
    # frame_0001.png.
    first_name   = os.path.basename(written_frames[0])   # e.g. "frame_0000.png"
    first_index  = int(first_name.replace("frame_", "").replace(".png", ""))
    start_number = first_index  # pass to ffmpeg via -start_number

    # -----------------------------------------------------------------------
    # Stitch frames to MP4 with ffmpeg
    # -----------------------------------------------------------------------
    if output_path is None:
        output_path = os.path.abspath(
            os.path.join(config.OUTPUT_DIR, f"animation_{component_id}.mp4")
        )

    frames_pattern = os.path.abspath(os.path.join(_FRAMES_DIR, "frame_%04d.png"))

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-framerate",    "30",
        "-start_number", str(start_number),
        "-i",            frames_pattern,
        "-c:v",          "libx264",
        "-pix_fmt",      "yuv420p",
        "-crf",          "18",
        output_path,
    ]

    print(f"  → Stitching {frame_count} frames → {output_path}")
    ff_result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)

    if ff_result.returncode != 0:
        print(f"❌ ffmpeg failed:")
        print(ff_result.stderr)
        return None

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        print(f"❌ ffmpeg exited 0 but output file is missing or empty: {output_path}")
        return None

    print(f"  ✓ Animation clip: {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Marker parsing helper (mirrors graph_visualiser pattern)
# ---------------------------------------------------------------------------

def parse_animation_marker(marker_content: str) -> tuple[str, str]:
    """
    Given the full content of a [VisualiseAnimation:X] ... [/VisualiseAnimation]
    block, extract the component_id and data_string.

    Returns (component_id, data_string).
    """
    parts = marker_content.strip().split(None, 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return "auto", marker_content.strip()