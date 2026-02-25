"""
graph_visualiser.py (depreciated)
Graph Visualiser - Minimalist Animated Charts with HTML Preview
Matches the terminal aesthetic and theme system of code_visualiser.py

Supports: bar charts, line graphs
Themes: heaven, dark, matrix
Output: HTML preview (standalone) + VideoClip (via main.py)
"""

import json
import os
import tempfile
import wave
import numpy as np

from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.video.VideoClip import VideoClip
from PIL import Image, ImageDraw, ImageFont

import config

# ─── Layout constants ────────────────────────────────────────────────────────
PADDING         = config.GRAPH_VIS_PADDING
FONT_SIZE       = config.GRAPH_VIS_FONT_SIZE
TITLE_FONT_SIZE = config.GRAPH_VIS_TITLE_FONT_SIZE
FONT_PATH       = config.FONT_PATH_ARIAL

VIDEO_WIDTH  = config.VIDEO_WIDTH
VIDEO_HEIGHT = config.VIDEO_HEIGHT

# ─── Theme definitions ────────────────────────────────────────────────────────
THEMES = {
    "heaven": {
        "bg":      "#F9FAFB",
        "surface": "#FFFFFF",
        "header":  "#F5F5F7",
        "border":  "#D1D1D6",
        "graph":   "#3B82F6",
        "accent":  "#F59E0B",
        "grid":    "#F3F4F6",
        "text":    "#1D1D1F",
        "subtext": "#6B7280",
        "line":    "#3B82F6",
        "area":    "rgba(59,130,246,0.08)",
        # PIL dot colour (outline, no fill — matches hollow CSS dots)
        "dot_outline": "#B0B0B5",
    },
    "dark": {
        "bg":      "#141414",
        "surface": "#1E1E1E",
        "header":  "#2D2D30",
        "border":  "#3E3E42",
        "graph":   "#60A5FA",
        "accent":  "#FBBF24",
        "grid":    "#262626",
        "text":    "#D4D4D4",
        "subtext": "#9CA3AF",
        "line":    "#60A5FA",
        "area":    "rgba(96,165,250,0.08)",
        "dot_outline": "#858585",
    },
    "matrix": {
        "bg":      "#0D0208",
        "surface": "#001400",
        "header":  "#002800",
        "border":  "#003B00",
        "graph":   "#00FF41",
        "accent":  "#39FF14",
        "grid":    "#001400",
        "text":    "#00FF41",
        "subtext": "#008F11",
        "line":    "#00FF41",
        "area":    "rgba(0,255,65,0.06)",
        "dot_outline": "#005020",
    },
}


# ─── HTML Preview Generator ───────────────────────────────────────────────────

class GraphPreviewGenerator:
    """
    Generates a standalone HTML preview of bar/line charts.
    Uses master.css for all styling — no inline CSS.
    """

    def __init__(self, theme: str = "heaven"):
        self.theme = theme if theme in THEMES else "heaven"

    def generate(
        self,
        data: dict,
        title: str,
        chart_type: str = "bar",
        output_path: str = "graph_preview.html"
    ):
        """Write a self-contained HTML preview file.

        Args:
            data:        {label: value, ...} mapping
            title:       Chart title
            chart_type:  "bar" or "line"
            output_path: Destination .html file
        """
        html = self._create_html(data, title, chart_type)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"✓ {output_path}")

    def _create_html(self, data: dict, title: str, chart_type: str) -> str:
        # Only the theme-specific JS colour values are injected — no CSS.
        t = THEMES[self.theme]
        data_json = json.dumps(data)

        chart_script = (
            self._bar_chart_script() if chart_type == "bar"
            else self._line_chart_script()
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — {self.theme}</title>
  <link rel="stylesheet" href="./static/master.css">
</head>
<body data-theme="{self.theme}">
  <div class="terminal graph-terminal" id="terminal">
    <div class="header">
      <div class="dots">
        <div class="dot" id="dot1"></div>
        <div class="dot" id="dot2"></div>
        <div class="dot" id="dot3"></div>
      </div>
      <div class="header-title">~/charts/{chart_type}</div>
    </div>
    <div class="chart-container">
      <div class="chart-title">{title}</div>
      <canvas id="chart"></canvas>
    </div>
  </div>

  <script>
    const DATA  = {data_json};
    const THEME = {{
      bg:      getComputedStyle(document.body).getPropertyValue('--bg').trim(),
      surface: getComputedStyle(document.body).getPropertyValue('--terminal').trim(),
      header:  getComputedStyle(document.body).getPropertyValue('--header').trim(),
      border:  getComputedStyle(document.body).getPropertyValue('--border').trim(),
      graph:   getComputedStyle(document.body).getPropertyValue('--graph').trim(),
      accent:  getComputedStyle(document.body).getPropertyValue('--accent').trim(),
      grid:    getComputedStyle(document.body).getPropertyValue('--grid').trim(),
      text:    getComputedStyle(document.body).getPropertyValue('--text').trim(),
      subtext: getComputedStyle(document.body).getPropertyValue('--subtext').trim(),
      area:    getComputedStyle(document.body).getPropertyValue('--area').trim(),
    }};

    {chart_script}

    window.addEventListener("load", () => {{
      document.getElementById("terminal").classList.add("reveal");
      setTimeout(() => document.getElementById("dot1").classList.add("active"), 0);
      setTimeout(() => document.getElementById("dot2").classList.add("active"), 150);
      setTimeout(() => document.getElementById("dot3").classList.add("active"), 300);
      drawChart(DATA, THEME);
    }});
  </script>
</body>
</html>"""

    # ── Bar chart canvas script ──────────────────────────────────────────────
    def _bar_chart_script(self) -> str:
        return """
    function drawChart(data, theme) {
      const canvas = document.getElementById("chart");
      const labels = Object.keys(data);
      const values = Object.values(data);
      const maxVal = Math.max(...values);

      // DPR-aware sizing — set ONCE, never touch canvas size again
      const dpr = window.devicePixelRatio || 1;
      const W   = canvas.parentElement.clientWidth - 88;
      const H   = 320;
      canvas.width        = Math.round(W * dpr);
      canvas.height       = Math.round(H * dpr);
      canvas.style.width  = W + "px";
      canvas.style.height = H + "px";

      const ctx = canvas.getContext("2d");
      ctx.scale(dpr, dpr);

      const PAD_LEFT  = 56;
      const PAD_RIGHT = 20;
      const PAD_TOP   = 12;
      const PAD_BOT   = 44;

      const chartW = W - PAD_LEFT - PAD_RIGHT;
      const chartH = H - PAD_TOP  - PAD_BOT;
      const baseY  = PAD_TOP + chartH;   // Y pixel of x-axis baseline

      const n      = labels.length;
      const groupW = chartW / n;
      const barW   = Math.min(groupW * 0.52, 56);

      function niceTick(max) {
        const rough = max / 4;
        const mag   = Math.pow(10, Math.floor(Math.log10(rough || 1)));
        const norm  = rough / mag;
        const nice  = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
        return nice * mag;
      }
      const tick      = niceTick(maxVal);
      const yMax      = Math.ceil(maxVal / tick) * tick;
      const tickCount = Math.round(yMax / tick);

      // ── Draw static elements ONCE (grid, axes, labels) ──────────────────
      ctx.font      = "11px 'SF Mono', 'Fira Code', monospace";
      ctx.textAlign = "right";

      for (let i = 0; i <= tickCount; i++) {
        const v = i * tick;
        const y = baseY - (v / yMax) * chartH;

        ctx.strokeStyle = theme.grid;
        ctx.lineWidth   = 1;
        ctx.setLineDash([3, 4]);
        ctx.beginPath();
        ctx.moveTo(PAD_LEFT, y);
        ctx.lineTo(PAD_LEFT + chartW, y);
        ctx.stroke();
        ctx.setLineDash([]);

        ctx.fillStyle = theme.subtext;
        ctx.fillText(v.toLocaleString(), PAD_LEFT - 8, y + 4);
      }

      // X baseline
      ctx.strokeStyle = theme.border;
      ctx.lineWidth   = 1;
      ctx.beginPath();
      ctx.moveTo(PAD_LEFT, baseY);
      ctx.lineTo(PAD_LEFT + chartW, baseY);
      ctx.stroke();

      // X labels (static — drawn once)
      ctx.fillStyle = theme.subtext;
      ctx.font      = "11px 'SF Mono', 'Fira Code', monospace";
      ctx.textAlign = "center";
      labels.forEach((label, i) => {
        const x = PAD_LEFT + i * groupW + (groupW - barW) / 2 + barW / 2;
        ctx.fillText(label, x, baseY + 20);
      });

      // ── Snapshot the static layer so we can restore it each frame ───────
      const staticSnapshot = ctx.getImageData(0, 0, canvas.width, canvas.height);

      // ── Animate bars on top ──────────────────────────────────────────────
      let progress = 0;
      const FRAMES = 50;

      function easeOut(t) { return 1 - Math.pow(1 - t, 3); }

      function frame() {
        // Restore static background (grid + axes + labels) — no duplication
        ctx.putImageData(staticSnapshot, 0, 0);

        const p = easeOut(progress / FRAMES);

        labels.forEach((label, i) => {
          const v  = values[i];
          const bH = (v / yMax) * chartH * p;
          const x  = PAD_LEFT + i * groupW + (groupW - barW) / 2;
          const y  = baseY - bH;

          if (bH > 0) {
            ctx.fillStyle = theme.graph;
            ctx.beginPath();
            ctx.roundRect(x, y, barW, bH, [3, 3, 0, 0]);
            ctx.fill();
          }

          // Value above bar
          if (p > 0.25 && bH > 0) {
            ctx.fillStyle = theme.text;
            ctx.font      = "11px 'SF Mono', 'Fira Code', monospace";
            ctx.textAlign = "center";
            ctx.fillText(Math.round(v * p).toLocaleString(), x + barW / 2, y - 7);
          }
        });

        progress++;
        if (progress <= FRAMES) requestAnimationFrame(frame);
      }

      frame();
    }
"""

    # ── Line chart canvas script ─────────────────────────────────────────────
    def _line_chart_script(self) -> str:
        return """
    function drawChart(data, theme) {
      const canvas = document.getElementById("chart");
      const labels = Object.keys(data);
      const values = Object.values(data);
      const maxVal = Math.max(...values);
      const minVal = Math.min(...values);

      // DPR-aware sizing — set ONCE
      const dpr = window.devicePixelRatio || 1;
      const W   = canvas.parentElement.clientWidth - 88;
      const H   = 320;
      canvas.width        = Math.round(W * dpr);
      canvas.height       = Math.round(H * dpr);
      canvas.style.width  = W + "px";
      canvas.style.height = H + "px";

      const ctx = canvas.getContext("2d");
      ctx.scale(dpr, dpr);

      const PAD_LEFT  = 56;
      const PAD_RIGHT = 20;
      const PAD_TOP   = 12;
      const PAD_BOT   = 44;

      const chartW = W - PAD_LEFT - PAD_RIGHT;
      const chartH = H - PAD_TOP  - PAD_BOT;
      const baseY  = PAD_TOP + chartH;

      function niceTick(range) {
        const rough = range / 4;
        const mag   = Math.pow(10, Math.floor(Math.log10(rough || 1)));
        const norm  = rough / mag;
        const nice  = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
        return nice * mag;
      }

      const range     = maxVal - minVal || 1;
      const tick      = niceTick(range);
      const yMin      = Math.floor(minVal / tick) * tick;
      const yMax      = Math.ceil(maxVal  / tick) * tick;
      const tickCount = Math.round((yMax - yMin) / tick);

      function toY(v) {
        return baseY - ((v - yMin) / (yMax - yMin)) * chartH;
      }
      function toX(i) {
        return PAD_LEFT + (i / (labels.length - 1)) * chartW;
      }

      // ── Draw static elements ONCE ────────────────────────────────────────
      ctx.font      = "11px 'SF Mono', 'Fira Code', monospace";
      ctx.textAlign = "right";

      for (let i = 0; i <= tickCount; i++) {
        const v = yMin + i * tick;
        const y = toY(v);

        ctx.strokeStyle = theme.grid;
        ctx.lineWidth   = 1;
        ctx.setLineDash([3, 4]);
        ctx.beginPath();
        ctx.moveTo(PAD_LEFT, y);
        ctx.lineTo(PAD_LEFT + chartW, y);
        ctx.stroke();
        ctx.setLineDash([]);

        ctx.fillStyle = theme.subtext;
        ctx.fillText(v.toLocaleString(), PAD_LEFT - 8, y + 4);
      }

      // Baseline
      ctx.strokeStyle = theme.border;
      ctx.lineWidth   = 1;
      ctx.beginPath();
      ctx.moveTo(PAD_LEFT, baseY);
      ctx.lineTo(PAD_LEFT + chartW, baseY);
      ctx.stroke();

      // X labels (static)
      ctx.fillStyle = theme.subtext;
      ctx.font      = "11px 'SF Mono', 'Fira Code', monospace";
      ctx.textAlign = "center";
      labels.forEach((label, i) => {
        ctx.fillText(label, toX(i), baseY + 20);
      });

      // ── Snapshot static layer ────────────────────────────────────────────
      const staticSnapshot = ctx.getImageData(0, 0, canvas.width, canvas.height);

      // ── Animate line on top ──────────────────────────────────────────────
      let progress = 0;
      const FRAMES = 60;

      function easeInOut(t) {
        return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      }

      function frame() {
        // Restore static layer — eliminates ghost axes / labels
        ctx.putImageData(staticSnapshot, 0, 0);

        const p      = easeInOut(progress / FRAMES);
        const nPts   = labels.length;
        const drawTo = p * (nPts - 1);

        // Build visible points
        const pts = [];
        for (let i = 0; i < nPts && i <= drawTo; i++) {
          pts.push({ x: toX(i), y: toY(values[i]) });
        }

        // Partial last segment
        if (drawTo < nPts - 1) {
          const i    = Math.floor(drawTo);
          const frac = drawTo - i;
          pts.push({
            x: toX(i) + frac * (toX(i + 1) - toX(i)),
            y: toY(values[i]) + frac * (toY(values[i + 1]) - toY(values[i]))
          });
        }

        if (pts.length < 2) {
          progress++;
          if (progress <= FRAMES) requestAnimationFrame(frame);
          return;
        }

        // Area fill
        ctx.beginPath();
        ctx.moveTo(pts[0].x, baseY);
        pts.forEach(pt => ctx.lineTo(pt.x, pt.y));
        ctx.lineTo(pts[pts.length - 1].x, baseY);
        ctx.closePath();
        ctx.fillStyle = theme.area;
        ctx.fill();

        // Line
        ctx.beginPath();
        ctx.moveTo(pts[0].x, pts[0].y);
        pts.slice(1).forEach(pt => ctx.lineTo(pt.x, pt.y));
        ctx.strokeStyle = theme.graph;
        ctx.lineWidth   = 2.5;
        ctx.lineJoin    = "round";
        ctx.lineCap     = "round";
        ctx.stroke();

        // Dots — hollow circles matching the header dot aesthetic
        const completedCount = Math.min(Math.floor(drawTo) + 1, nPts);
        for (let i = 0; i < completedCount; i++) {
          const cx = toX(i);
          const cy = toY(values[i]);

          // Outer filled circle (accent colour)
          ctx.beginPath();
          ctx.arc(cx, cy, 4.5, 0, Math.PI * 2);
          ctx.fillStyle = theme.accent;
          ctx.fill();

          // Inner cutout (surface colour) — creates ring effect
          ctx.beginPath();
          ctx.arc(cx, cy, 2.5, 0, Math.PI * 2);
          ctx.fillStyle = theme.surface || theme.bg;
          ctx.fill();
        }

        progress++;
        if (progress <= FRAMES) requestAnimationFrame(frame);
      }

      frame();
    }
"""


# ─── PIL rendering helpers ────────────────────────────────────────────────────

def _hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _load_fonts():
    try:
        font       = ImageFont.truetype(FONT_PATH, FONT_SIZE)
        title_font = ImageFont.truetype(FONT_PATH, TITLE_FONT_SIZE)
        small_font = ImageFont.truetype(FONT_PATH, max(FONT_SIZE - 4, 10))
    except Exception:
        font = title_font = small_font = ImageFont.load_default()
    return font, title_font, small_font


def _draw_terminal_chrome(draw: ImageDraw, colors: dict, width: int):
    """Draw the top chrome bar (hollow dots + separator) matching master.css aesthetic."""
    header_h  = 56
    chrome_bg = _hex_to_rgb(colors["header"])
    border    = _hex_to_rgb(colors["border"])
    draw.rectangle([(0, 0), (width, header_h)], fill=chrome_bg)
    draw.line([(0, header_h), (width, header_h)], fill=border, width=1)

    # Hollow dots — outline only, matching CSS .dot { border: 1.5px solid; background: transparent }
    outline_col = _hex_to_rgb(colors["dot_outline"])
    dot_r, dot_x, dot_y = 5, 16, header_h // 2
    for i in range(3):
        cx = dot_x + i * 18
        draw.ellipse(
            [(cx - dot_r, dot_y - dot_r), (cx + dot_r, dot_y + dot_r)],
            outline=outline_col, width=2
        )


def _nice_tick(value_range: float, divisions: int = 4) -> float:
    if value_range == 0:
        return 1.0
    import math
    rough = value_range / divisions
    mag   = 10 ** math.floor(math.log10(rough))
    norm  = rough / mag
    nice  = 1 if norm <= 1 else 2 if norm <= 2 else 5 if norm <= 5 else 10
    return nice * mag


# ─── Shared PIL axis/grid renderer ───────────────────────────────────────────

def _draw_axes_and_grid(
    draw: ImageDraw,
    small_font,
    colors: dict,
    chart_x: int, chart_y: int, chart_w: int, chart_h: int,
    y_min: float, y_max: float, tick: float,
    labels: list = None, to_x_fn=None
):
    """Render grid lines, Y-axis labels, baseline, and optionally X labels.
    Called ONCE before the animation cache is built.
    """
    sub_col  = _hex_to_rgb(colors["subtext"])
    grid_col = _hex_to_rgb(colors["grid"])
    bdr_col  = _hex_to_rgb(colors["border"])

    tick_count = round((y_max - y_min) / tick)
    for i in range(tick_count + 1):
        v  = y_min + i * tick
        gy = chart_y - int((v - y_min) / max(y_max - y_min, 1) * chart_h)
        # Dashed grid line
        for dx in range(0, chart_w, 8):
            draw.line([(chart_x + dx, gy), (chart_x + dx + 4, gy)], fill=grid_col, width=1)
        # Y label
        label = f"{int(v):,}"
        bb = draw.textbbox((0, 0), label, font=small_font)
        lw, lh = bb[2] - bb[0], bb[3] - bb[1]
        draw.text((chart_x - lw - 8, gy - lh // 2), label, font=small_font, fill=sub_col)

    # Baseline
    draw.line([(chart_x, chart_y), (chart_x + chart_w, chart_y)], fill=bdr_col, width=1)

    # X labels (optional)
    if labels and to_x_fn:
        for i, lbl in enumerate(labels):
            bb = draw.textbbox((0, 0), lbl, font=small_font)
            lw = bb[2] - bb[0]
            draw.text((to_x_fn(i) - lw // 2, chart_y + 10), lbl, font=small_font, fill=sub_col)


# ─── Bar chart PIL renderer ───────────────────────────────────────────────────

def _build_bar_frame(
    t: float, duration: float,
    labels: list, values: list,
    colors: dict, font, title_font, small_font,
    chart_x: int, chart_y: int, chart_w: int, chart_h: int,
    y_min: float, y_max: float, tick: float,
    bar_w: int, group_w: float,
    static_bg: Image.Image   # pre-rendered static layer
) -> np.ndarray:
    """Composite animated bars on top of the pre-rendered static background."""
    img  = static_bg.copy()
    draw = ImageDraw.Draw(img)

    progress = min(t / max(duration, 0.001), 1.0)

    def ease_out(t): return 1 - (1 - t) ** 3

    p       = ease_out(progress)
    text_col = _hex_to_rgb(colors["text"])
    bar_col  = _hex_to_rgb(colors["graph"])

    for i, (label, value) in enumerate(zip(labels, values)):
        bx = chart_x + int(i * group_w) + int((group_w - bar_w) / 2)
        bh = int((value / y_max) * chart_h * p)
        by = chart_y - bh
        if bh > 0:
            draw.rounded_rectangle([(bx, by), (bx + bar_w, chart_y)], radius=3, fill=bar_col)
        if p > 0.25 and bh > 0:
            val_text = f"{int(value * p):,}"
            bb = draw.textbbox((0, 0), val_text, font=small_font)
            vw, vh = bb[2] - bb[0], bb[3] - bb[1]
            draw.text((bx + (bar_w - vw) // 2, by - vh - 5), val_text, font=small_font, fill=text_col)

    return np.array(img)


# ─── Line graph PIL renderer ──────────────────────────────────────────────────

def _build_line_frame(
    t: float, duration: float,
    labels: list, values: list,
    colors: dict, font, title_font, small_font,
    chart_x: int, chart_y: int, chart_w: int, chart_h: int,
    y_min: float, y_max: float, tick: float,
    static_bg: Image.Image   # pre-rendered static layer
) -> np.ndarray:
    """Composite animated line on top of the pre-rendered static background."""
    img  = static_bg.copy()
    draw = ImageDraw.Draw(img)

    progress = min(t / max(duration, 0.001), 1.0)

    def ease_in_out(t):
        return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2

    p = ease_in_out(progress)

    n = len(labels)

    def to_x(i): return chart_x + int(i / max(n - 1, 1) * chart_w)
    def to_y(v): return chart_y - int((v - y_min) / max(y_max - y_min, 1) * chart_h)

    line_col   = _hex_to_rgb(colors["line"])
    accent_col = _hex_to_rgb(colors["accent"])
    surface_col = _hex_to_rgb(colors["surface"])

    draw_to = p * (n - 1)
    pts = []
    for i in range(n):
        if i <= draw_to:
            pts.append((to_x(i), to_y(values[i])))

    # Partial last segment
    if draw_to < n - 1:
        i    = int(draw_to)
        frac = draw_to - i
        px   = to_x(i) + int(frac * (to_x(i + 1) - to_x(i)))
        py   = to_y(values[i]) + int(frac * (to_y(values[i + 1]) - to_y(values[i])))
        pts.append((px, py))

    if len(pts) >= 2:
        # Area fill via RGBA overlay
        area_pts = [pts[0]] + pts + [(pts[-1][0], chart_y), (pts[0][0], chart_y)]
        overlay  = Image.new("RGBA", img.size, (0, 0, 0, 0))
        od       = ImageDraw.Draw(overlay)
        r, g, b  = line_col
        od.polygon(area_pts, fill=(r, g, b, 18))
        img  = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)
        draw.line(pts, fill=line_col, width=3)

    # Hollow dots (accent ring over surface fill)
    r_dot = 5
    completed = min(int(draw_to) + 1, n)
    for i in range(completed):
        cx, cy = to_x(i), to_y(values[i])
        draw.ellipse([(cx - r_dot, cy - r_dot), (cx + r_dot, cy + r_dot)], fill=accent_col)
        draw.ellipse([(cx - r_dot + 2, cy - r_dot + 2), (cx + r_dot - 2, cy + r_dot - 2)],
                     fill=surface_col)

    return np.array(img)


# ─── Chart layout calculator ──────────────────────────────────────────────────

def _chart_area():
    """Return chart origin and dimensions for the video frame."""
    CHROME_H   = 56
    LEFT_PAD   = 80
    RIGHT_PAD  = 40
    TOP_PAD    = 80
    BOTTOM_PAD = 64
    cx = LEFT_PAD
    cy = VIDEO_HEIGHT - BOTTOM_PAD
    cw = VIDEO_WIDTH - LEFT_PAD - RIGHT_PAD
    ch = VIDEO_HEIGHT - CHROME_H - TOP_PAD - BOTTOM_PAD
    return cx, cy, cw, ch


def _draw_chart_title(draw, title: str, title_font, colors: dict):
    """Draw centred chart title below chrome bar."""
    CHROME_H = 56
    text_col = _hex_to_rgb(colors["text"])
    bb = draw.textbbox((0, 0), title, font=title_font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    draw.text(((VIDEO_WIDTH - tw) // 2, CHROME_H + 20), title, font=title_font, fill=text_col)


def _build_static_bg(colors: dict, title: str, title_font, small_font,
                     chart_x, chart_y, chart_w, chart_h,
                     y_min, y_max, tick,
                     labels=None, to_x_fn=None) -> Image.Image:
    """Render chrome + grid + axes + title into a single PIL image (drawn once)."""
    img  = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), _hex_to_rgb(colors["bg"]))
    draw = ImageDraw.Draw(img)
    _draw_terminal_chrome(draw, colors, VIDEO_WIDTH)
    _draw_chart_title(draw, title, title_font, colors)
    _draw_axes_and_grid(
        draw, small_font, colors,
        chart_x, chart_y, chart_w, chart_h,
        y_min, y_max, tick, labels, to_x_fn
    )
    return img


# ─── Public API: VideoClip factories ─────────────────────────────────────────

def create_silent_audio_clip(duration: float) -> AudioFileClip:
    """Create a silent stereo WAV AudioFileClip of the given duration."""
    sample_rate = 44100
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    with wave.open(tmp.name, "w") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        chunk = b"\x00\x00" * sample_rate
        for _ in range(int(duration)):
            wav.writeframes(chunk)
        rem = int((duration - int(duration)) * sample_rate)
        if rem:
            wav.writeframes(b"\x00\x00" * rem)
    return AudioFileClip(tmp.name)


def create_bar_chart_clip(
    data: dict,
    title: str,
    audio_clip: AudioFileClip,
    theme: str = "heaven"
) -> VideoClip:
    """
    Create an animated bar-chart VideoClip.

    Args:
        data:       {label: numeric_value, ...}
        title:      Chart heading
        audio_clip: AudioFileClip that sets the duration
        theme:      "heaven" | "dark" | "matrix"

    Returns:
        MoviePy VideoClip (no audio attached)
    """
    colors   = THEMES.get(theme, THEMES["heaven"])
    duration = audio_clip.duration

    font, title_font, small_font = _load_fonts()

    labels = list(data.keys())
    values = [float(v) for v in data.values()]
    y_max_raw = max(values)
    tick  = _nice_tick(y_max_raw)
    y_min = 0.0
    y_max = max(round((y_max_raw / tick + 1)) * tick, tick)

    cx, cy, cw, ch = _chart_area()

    n       = len(labels)
    group_w = cw / max(n, 1)
    bar_w   = max(int(min(group_w * 0.52, 64)), 8)

    # X-label positions for static bg
    def to_x_bar(i):
        return cx + int(i * group_w) + int((group_w - bar_w) / 2) + bar_w // 2

    # Build static background ONCE
    static_bg = _build_static_bg(
        colors, title, title_font, small_font,
        cx, cy, cw, ch, y_min, y_max, tick,
        labels=labels, to_x_fn=to_x_bar
    )

    frame_cache = {}
    cache_step  = 0.04

    def make_frame(t: float) -> np.ndarray:
        key = round(t / cache_step)
        if key not in frame_cache:
            frame_cache[key] = _build_bar_frame(
                t, duration, labels, values,
                colors, font, title_font, small_font,
                cx, cy, cw, ch, y_min, y_max, tick,
                bar_w, group_w, static_bg
            )
        return frame_cache[key]

    return VideoClip(make_frame, duration=duration)


def create_line_graph_clip(
    data: dict,
    title: str,
    audio_clip: AudioFileClip,
    theme: str = "heaven"
) -> VideoClip:
    """
    Create an animated line-graph VideoClip.

    Args:
        data:       {label: numeric_value, ...}
        title:      Chart heading
        audio_clip: AudioFileClip that sets the duration
        theme:      "heaven" | "dark" | "matrix"

    Returns:
        MoviePy VideoClip (no audio attached)
    """
    colors   = THEMES.get(theme, THEMES["heaven"])
    duration = audio_clip.duration

    font, title_font, small_font = _load_fonts()

    labels = list(data.keys())
    values = [float(v) for v in data.values()]
    v_min, v_max = min(values), max(values)
    tick  = _nice_tick(v_max - v_min)
    y_min = max(0.0, (v_min // tick) * tick)
    y_max = (int(v_max / tick) + 1) * tick

    cx, cy, cw, ch = _chart_area()

    n = len(labels)

    def to_x(i): return cx + int(i / max(n - 1, 1) * cw)

    # Build static background ONCE
    static_bg = _build_static_bg(
        colors, title, title_font, small_font,
        cx, cy, cw, ch, y_min, y_max, tick,
        labels=labels, to_x_fn=to_x
    )

    frame_cache = {}
    cache_step  = 0.04

    def make_frame(t: float) -> np.ndarray:
        key = round(t / cache_step)
        if key not in frame_cache:
            frame_cache[key] = _build_line_frame(
                t, duration, labels, values,
                colors, font, title_font, small_font,
                cx, cy, cw, ch, y_min, y_max, tick,
                static_bg
            )
        return frame_cache[key]

    return VideoClip(make_frame, duration=duration)


# ─── Standalone preview ───────────────────────────────────────────────────────

if __name__ == "__main__":
    sample_bar = {
        "Jan": 4200, "Feb": 5800, "Mar": 3900,
        "Apr": 7100, "May": 6300, "Jun": 8400,
    }
    sample_line = {
        "Q1": 12000, "Q2": 18500, "Q3": 15200,
        "Q4": 22800, "Q5": 19600, "Q6": 27400,
    }

    print("Generating graph previews...\n")

    for theme in ["heaven", "dark", "matrix"]:
        gen = GraphPreviewGenerator(theme=theme)

        gen.generate(
            sample_bar,
            title="Monthly Revenue",
            chart_type="bar",
            output_path=f"graph_preview_bar_{theme}.html"
        )
        gen.generate(
            sample_line,
            title="Quarterly Growth",
            chart_type="line",
            output_path=f"graph_preview_line_{theme}.html"
        )

    print("\n✓ Done! Open graph_preview_*.html in your browser")