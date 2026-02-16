"""
code_visualiser.py -
Terminal Preview Generator - Focused HTML Output
Clean, properly aligned terminal animations for browser preview
"""

import json
import config


class TerminalPreviewGenerator:
    """Generate standalone HTML previews with professional formatting."""
    
    def __init__(self, theme: str = None):
        if theme is None:
            theme = config.CODE_VIS_DEFAULT_THEME
        self.theme = theme
        self.themes = {
            "heaven": {
                "bg": "#FFFFFF",
                "terminal": "#FFFFFF",
                "header": "#F5F5F7",
                "border": "#D1D1D6",
                "text": "#1D1D1F",
                "keyword": "#AD3DA4",
                "comment": "#8E8E93",
                "string": "#D12F1B",
                "number": "#272AD8",
                "function": "#3E8087",
                "line_num": "#B0B0B5",
            },
            "dark": {
                "bg": "#1E1E1E",
                "terminal": "#252526",
                "header": "#2D2D30",
                "border": "#3E3E42",
                "text": "#D4D4D4",
                "keyword": "#569CD6",
                "comment": "#6A9955",
                "string": "#CE9178",
                "number": "#B5CEA8",
                "function": "#DCDCAA",
                "line_num": "#858585",
            },
            "matrix": {
                "bg": "#0D0208",
                "terminal": "#001400",
                "header": "#002800",
                "border": "#00FF41",
                "text": "#00FF41",
                "keyword": "#39FF14",
                "comment": "#008F11",
                "string": "#00DD3A",
                "number": "#00FF66",
                "function": "#00CC33",
                "line_num": "#005020",
            }
        }
    
    def generate(
        self,
        code: str,
        language: str = "python",
        mode: str = None,
        duration: float = None,
        output_path: str = "preview.html"
    ):
        """Generate HTML preview file.
        
        Args:
            code: Source code to display
            language: Programming language for syntax highlighting
            mode: Animation mode - "typewriter" or "static" (uses config default if None)
            duration: Duration for typewriter animation in seconds (uses config default if None)
            output_path: Output file path
        """
        if mode is None:
            mode = config.CODE_VIS_DEFAULT_MODE
        if duration is None:
            duration = config.CODE_VIS_DURATION
            
        html = self._create_html(code, language, mode, duration)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"✓ {output_path}")
    
    def _create_html(self, code: str, language: str, mode: str, duration: float) -> str:
        """Create complete HTML with optimal formatting and alignment."""
        
        theme = self.themes[self.theme]
        code_json = json.dumps(code)
        
        # Calculate precise vertical alignment
        header_height = 56
        padding_top = 32
        padding_bottom = 32
        font_size = config.CODE_VIS_FONT_SIZE
        line_height = config.CODE_VIS_LINE_HEIGHT
        
        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{language} - {self.theme}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            min-height: 100vh;
            background: {theme['bg']};
            font-family: 'SF Mono', 'Consolas', 'Monaco', 'Courier New', monospace;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 40px;
            -webkit-font-smoothing: antialiased;
        }}
        
        .terminal {{
            width: 100%;
            max-width: 1200px;
            background: {theme['terminal']};
            border: 1px solid {theme['border']};
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
        }}
        
        /* Header */
        .header {{
            height: {header_height}px;
            background: {theme['header']};
            border-bottom: 1px solid {theme['border']};
            display: flex;
            align-items: center;
            padding: 0 20px;
            gap: 12px;
        }}
        
        .dots {{
            display: flex;
            gap: 8px;
        }}
        
        .dot {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
            border: 1.5px solid {theme['line_num']};
            opacity: 0.6;
        }}
        
        .dot.active {{
            animation: pulse 1.5s ease-in-out infinite;
        }}
        
        @keyframes pulse {{
            0%, 100% {{ opacity: 0.6; transform: scale(1); }}
            50% {{ opacity: 1; transform: scale(1.1); }}
        }}
        
        .title {{
            color: {theme['line_num']};
            font-size: 13px;
            margin-left: 8px;
        }}
        
        /* Code Container */
        .container {{
            display: flex;
            min-height: 400px;
        }}
        
        /* Line Numbers - Perfect Alignment */
        .line-numbers {{
            background: {theme['header']};
            border-right: 1px solid {theme['border']};
            padding: {padding_top}px 16px {padding_bottom}px 20px;
            color: {theme['line_num']};
            font-size: {font_size}px;
            line-height: {line_height}px;
            text-align: right;
            user-select: none;
            min-width: 56px;
            font-variant-numeric: tabular-nums;
            white-space: pre;
        }}
        
        /* Code Area - Aligned with Line Numbers */
        .code-wrapper {{
            flex: 1;
            padding: {padding_top}px 32px {padding_bottom}px 20px;
            overflow-x: auto;
        }}
        
        .code {{
            color: {theme['text']};
            font-size: {font_size}px;
            line-height: {line_height}px;
            white-space: pre;
            font-family: inherit;
            tab-size: 4;
        }}
        
        /* Syntax Colors */
        .keyword {{ color: {theme['keyword']}; font-weight: 600; }}
        .comment {{ color: {theme['comment']}; font-style: italic; }}
        .string {{ color: {theme['string']}; }}
        .number {{ color: {theme['number']}; }}
        .function {{ color: {theme['function']}; }}
        
        /* Cursor */
        .cursor {{
            display: inline-block;
            width: 8px;
            height: {line_height}px;
            background: {theme['keyword']};
            margin-left: 2px;
            vertical-align: text-top;
            animation: blink 1s step-end infinite;
        }}
        
        @keyframes blink {{
            50% {{ opacity: 0; }}
        }}
        
        /* Static Fade */
        .fade-in {{
            animation: fadeIn 1.5s ease-out;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; }}
            to {{ opacity: 1; }}
        }}
        
        /* Scrollbar */
        .code-wrapper::-webkit-scrollbar {{
            width: 8px;
            height: 8px;
        }}
        
        .code-wrapper::-webkit-scrollbar-track {{
            background: transparent;
        }}
        
        .code-wrapper::-webkit-scrollbar-thumb {{
            background: {theme['border']};
            border-radius: 4px;
        }}
    </style>
</head>
<body>
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
        
        // Simple syntax highlighter
        function highlight(code, lang) {{
            const keywords = /\\b(def|class|import|from|return|if|else|elif|for|while|try|except|with|as|in|and|or|not|lambda|async|await|function|const|let|var|return|if|else|for|while|switch|case|break)\\b/g;
            const strings = /(["'`])(?:(?=(\\\\?))\\2.)*?\\1/g;
            const comments = /(#.*$|\\/\\/.*$|\\/\\*[\\s\\S]*?\\*\\/)/gm;
            const numbers = /\\b(\\d+\\.?\\d*|0x[0-9a-fA-F]+)\\b/g;
            const functions = /\\b([a-zA-Z_][a-zA-Z0-9_]*)(?=\\s*\\()/g;
            
            return code
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(comments, '<span class="comment">$1</span>')
                .replace(strings, '<span class="string">$1</span>')
                .replace(keywords, '<span class="keyword">$1</span>')
                .replace(numbers, '<span class="number">$1</span>')
                .replace(functions, '<span class="function">$1</span>');
        }}
        
        // Update line numbers
        function updateLineNumbers(count) {{
            const el = document.getElementById('lineNumbers');
            el.textContent = Array.from({{length: count}}, (_, i) => i + 1).join('\\n');
        }}
        
        // Typewriter animation
        function typewriter() {{
            const codeEl = document.getElementById('code');
            const totalChars = CODE.length;
            const fps = 60;
            const totalFrames = DURATION * fps;
            let frame = 0;
            
            // Activate dots with staggered delay
            setTimeout(() => document.getElementById('dot1').classList.add('active'), 0);
            setTimeout(() => document.getElementById('dot2').classList.add('active'), 150);
            setTimeout(() => document.getElementById('dot3').classList.add('active'), 300);
            
            function animate() {{
                const progress = frame / totalFrames;
                const chars = Math.floor(totalChars * easeInOut(progress));
                const text = CODE.substring(0, chars);
                
                codeEl.innerHTML = highlight(text, "{language}");
                
                if (frame < totalFrames - 10) {{
                    codeEl.innerHTML += '<span class="cursor"></span>';
                }}
                
                updateLineNumbers(text.split('\\n').length);
                
                frame++;
                if (frame <= totalFrames) {{
                    requestAnimationFrame(animate);
                }} else {{
                    document.querySelectorAll('.dot').forEach(d => d.classList.remove('active'));
                }}
            }}
            
            animate();
        }}
        
        // Static fade
        function staticDisplay() {{
            const codeEl = document.getElementById('code');
            codeEl.innerHTML = highlight(CODE, "{language}");
            codeEl.classList.add('fade-in');
            updateLineNumbers(CODE.split('\\n').length);
        }}
        
        // Easing
        function easeInOut(t) {{
            return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
        }}
        
        // Initialize
        if (MODE === 'typewriter') {{
            typewriter();
        }} else {{
            staticDisplay();
        }}
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

# Example usage
for i in range(10):
    print(f"F({i}) = {fibonacci(i)}")'''
    
    print("Generating previews...\n")
    
    for theme in ["heaven", "dark", "matrix"]:
        gen = TerminalPreviewGenerator(theme=theme)
        gen.generate(sample, "python", "typewriter", 6.0, f"preview_{theme}.html")
    
    print("\n✓ Done! Open preview_*.html in your browser")