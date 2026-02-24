"""
code_visualiser.py -
Terminal Preview Generator - Focused HTML Output
Clean, properly aligned terminal animations for browser preview
"""

import json
import config
import tempfile
import os
from moviepy.video.io.VideoFileClip import VideoFileClip
from playwright.sync_api import sync_playwright

VIDEO_WIDTH  = config.VIDEO_WIDTH
VIDEO_HEIGHT = config.VIDEO_HEIGHT


def create_code_video_clip(code: str, theme: str, mode: str, duration: float, pw_browser=None):
    """
    Create a video clip of the code animation using Playwright and MoviePy.

    Args:
        code:       Python source code to display.
        theme:      Terminal theme (heaven, dark, matrix).
        mode:       Animation mode ("typewriter" or "static").
        duration:   Duration in seconds for the typewriter animation.
        pw_browser: An already-running Playwright Browser instance.  When
                    provided the function opens a new context on that browser
                    instead of launching its own Playwright instance, which
                    avoids the "sync API inside asyncio loop" crash.

    Returns:
        MoviePy VideoFileClip with the animated code.
    """
    css_path     = os.path.abspath(os.path.join(os.path.dirname(__file__), "static", "master.css"))
    css_file_url = f"file:///{css_path.replace(os.sep, '/')}"

    html_temp = os.path.join(tempfile.gettempdir(), f"temp_preview_{theme}.html")
    gen       = TerminalPreviewGenerator(theme=theme)
    html_content = gen._create_html(code, language="python", mode=mode, duration=duration)
    html_content = html_content.replace('./static/master.css', css_file_url)

    with open(html_temp, 'w', encoding='utf-8') as f:
        f.write(html_content)

    try:
        _owned_pw      = None   # only set when we launch our own instance
        _owned_browser = None

        if pw_browser is not None:
            # Reuse the caller's browser — no new sync_playwright() call needed
            browser = pw_browser
        else:
            _owned_pw      = sync_playwright().start()
            _owned_browser = _owned_pw.chromium.launch(headless=True)
            browser        = _owned_browser

        context = browser.new_context(
            viewport={"width": VIDEO_WIDTH, "height": VIDEO_HEIGHT},
            record_video_dir=tempfile.gettempdir(),
            record_video_size={"width": VIDEO_WIDTH, "height": VIDEO_HEIGHT},
        )
        page = context.new_page()
        page.goto(f"file:///{os.path.abspath(html_temp)}")
        page.wait_for_load_state("networkidle")

        if mode.lower() == "typewriter":
            wait_time = int((duration * 1000) + 2000)
            print(f"  ⏱️  Waiting {wait_time/1000:.1f}s for typewriter animation...")
            page.wait_for_timeout(wait_time)
        else:
            page.wait_for_timeout(2000)

        page.wait_for_timeout(500)
        video_path = page.video.path()

        context.close()

        # Only shut down the browser/playwright if we own them
        if _owned_browser is not None:
            _owned_browser.close()
        if _owned_pw is not None:
            _owned_pw.stop()

        return VideoFileClip(video_path)

    finally:
        if os.path.exists(html_temp):
            os.unlink(html_temp)


class TerminalPreviewGenerator:
    """Generate standalone HTML previews with professional formatting."""

    def __init__(self, theme: str = None):
        if theme is None:
            theme = config.CODE_VIS_DEFAULT_THEME
        self.theme  = theme
        self.themes = ["heaven", "dark", "matrix"]

    def generate(
        self,
        code: str,
        language: str = "python",
        mode: str     = None,
        duration: float = None,
        output_path: str = "preview.html",
    ):
        if mode is None:
            mode = config.CODE_VIS_DEFAULT_MODE
        if duration is None:
            duration = config.CODE_VIS_DURATION

        html = self._create_html(code, language, mode, duration)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"✓ {output_path}")

    def _create_html(self, code: str, language: str, mode: str, duration: float) -> str:
        code_json = json.dumps(code)

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{language} - {self.theme}</title>
    <link rel="stylesheet" href="./static/master.css">
</head>
<body data-theme="{self.theme}">
    <div class="terminal">
        <div class="header">
            <div class="dots">
                <div class="dot" id="dot1"></div>
                <div class="dot" id="dot2"></div>
                <div class="dot" id="dot3"></div>
            </div>
            <div class="title">~/{language}</div>
        </div>
        <div class="container">
            <div class="line-numbers" id="lineNumbers"></div>
            <div class="code-wrapper">
                <div class="code" id="code"></div>
            </div>
        </div>
    </div>

    <script>
        const CODE = {code_json};
        const MODE = "{mode}";
        const DURATION = {duration};

        function highlight(code) {{
            code = code.replace(/&/g, '&amp;')
                       .replace(/</g, '&lt;')
                       .replace(/>/g, '&gt;');

            const keywords  = /\b(def|class|import|from|return|if|else|elif|for|while|try|except|with|as|in|and|or|not|lambda|async|await|function|const|let|var|switch|case|break)\b/g;
            const strings   = /(["'`])(?:(?=(\\?))\2.)*?\1/g;
            const comments  = /(#.*$|\/\/.*$|\/\*[\s\S]*?\*\/)/gm;
            const numbers   = /\b(\d+\.?\d*|0x[0-9a-fA-F]+)\b/g;
            const functions = /\b([a-zA-Z_][a-zA-Z0-9_]*)(?=\s*\()/g;

            return code
                .replace(comments,  '<span class="comment">$1</span>')
                .replace(strings,   '<span class="string">$1</span>')
                .replace(keywords,  '<span class="keyword">$1</span>')
                .replace(numbers,   '<span class="number">$1</span>')
                .replace(functions, '<span class="function">$1</span>');
        }}

        function updateLineNumbers(count) {{
            document.getElementById('lineNumbers').textContent =
                Array.from({{length: count}}, (_, i) => i + 1).join('\\n');
        }}

        function typewriter() {{
            const codeEl      = document.getElementById('code');
            const totalChars  = CODE.length;
            const totalFrames = DURATION * 60;
            let frame = 0;

            setTimeout(() => document.getElementById('dot1').classList.add('active'), 0);
            setTimeout(() => document.getElementById('dot2').classList.add('active'), 150);
            setTimeout(() => document.getElementById('dot3').classList.add('active'), 300);

            function animate() {{
                const chars = Math.floor(totalChars * easeInOut(frame / totalFrames));
                const text  = CODE.substring(0, chars);

                codeEl.innerHTML = highlight(text);
                if (frame < totalFrames - 10)
                    codeEl.innerHTML += '<span class="cursor"></span>';

                updateLineNumbers(text.split('\\n').length);
                frame++;
                if (frame <= totalFrames) requestAnimationFrame(animate);
                else document.querySelectorAll('.dot').forEach(d => d.classList.remove('active'));
            }}
            animate();
        }}

        function staticDisplay() {{
            const codeEl = document.getElementById('code');
            codeEl.innerHTML = highlight(CODE);
            codeEl.classList.add('static-reveal');
            updateLineNumbers(CODE.split('\\n').length);
        }}

        function easeInOut(t) {{
            return t < 0.5 ? 4*t*t*t : 1 - Math.pow(-2*t + 2, 3) / 2;
        }}

        window.addEventListener("load", () => {{
            document.querySelector(".terminal").classList.add("reveal");
            if (MODE === 'typewriter') typewriter();
            else staticDisplay();
        }});
    </script>
</body>
</html>'''


# Quick test
if __name__ == "__main__":
    sample = '''def fibonacci(n):
    """Calculate nth Fibonacci number."""
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

for i in range(10):
    print(f"F({i}) = {fibonacci(i)}")'''

    print("Generating previews...\n")
    for theme in ["heaven", "dark", "matrix"]:
        gen = TerminalPreviewGenerator(theme=theme)
        gen.generate(sample, "python", "typewriter", 6.0, f"preview_{theme}.html")
    print("\n✓ Done! Open preview_*.html in your browser")