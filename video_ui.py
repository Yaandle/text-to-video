"""
Video Generation UI - Desktop application for text-to-video creation
"""

import sys
import os
import json
from typing import Optional
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox, QTextEdit,
    QTabWidget, QGroupBox, QSplitter, QFileDialog, QMessageBox,
    QScrollArea, QFrame, QGridLayout, QSpinBox
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QFont, QIcon, QColor, QTextCursor, QSyntaxHighlighter, QTextDocument
from PyQt5.QtCore import pyqtSignal, QObject

import config


class MarkerHighlighter(QSyntaxHighlighter):
    """Syntax highlighting for video markers"""

    def __init__(self, document: QTextDocument):
        super().__init__(document)

    def highlightBlock(self, text: str):
        from PyQt5.QtGui import QTextCharFormat
        
        marker_patterns = [
            (r'\[VisualiseCode.*?\]', QColor(70, 130, 180)),      # Steel blue
            (r'\[VisualiseGraph.*?\]', QColor(144, 238, 144)),    # Light green
            (r'\[/VisualiseCode\]', QColor(70, 130, 180)),
            (r'\[/VisualiseGraph\]', QColor(144, 238, 144)),
        ]

        import re
        fmt = QTextCharFormat()
        for pattern, color in marker_patterns:
            for match in re.finditer(pattern, text):
                fmt.setForeground(color)
                fmt.setFontWeight(700)
                self.setFormat(match.start(), match.end() - match.start(), fmt)


class CodePreviewWidget(QWidget):
    """Preview and input widget for code visualization"""

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        header = QLabel("Code Visualization Preview")
        header.setFont(QFont("Segoe UI", 11, QFont.Bold))
        layout.addWidget(header)

        theme_layout = QHBoxLayout()
        theme_layout.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(config.CODE_VIS_THEMES)
        self.theme_combo.currentTextChanged.connect(self.apply_theme_styling)
        theme_layout.addWidget(self.theme_combo)
        theme_layout.addStretch()
        layout.addLayout(theme_layout)

        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Animation:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["typewriter", "static"])
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)

        layout.addWidget(QLabel("Code to visualize:"))
        self.code_input = QTextEdit()
        self.code_input.setPlaceholderText(
            "Paste your Python code here...\n\n"
            "def hello():\n    print('Hello World')"
        )
        self.code_input.setFont(QFont("Consolas", 9))
        layout.addWidget(self.code_input, stretch=1)

        layout.addWidget(QLabel("Live Preview:"))
        self.preview_container = QFrame()
        self.preview_container.setFrameShape(QFrame.StyledPanel)
        self.preview_container.setFrameShadow(QFrame.Sunken)
        preview_layout = QVBoxLayout()
        preview_layout.setContentsMargins(0, 0, 0, 0)
        
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFont(QFont("Consolas", 10))
        self.preview.setPlaceholderText("[Code preview will appear here]")
        preview_layout.addWidget(self.preview)
        self.preview_container.setLayout(preview_layout)
        layout.addWidget(self.preview_container, stretch=1)

        button_layout = QHBoxLayout()
        
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.code_input.clear)
        button_layout.addWidget(clear_btn)
        
        paste_btn = QPushButton("Paste from Clipboard")
        paste_btn.clicked.connect(self.paste_from_clipboard)
        button_layout.addWidget(paste_btn)
        
        load_btn = QPushButton("Load from File")
        load_btn.clicked.connect(self.load_from_file)
        button_layout.addWidget(load_btn)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)

        self.setLayout(layout)
        self.code_input.textChanged.connect(self.on_code_changed)
        self.apply_theme_styling()

    def apply_theme_styling(self):
        """Apply current theme colors to preview"""
        theme_name = self.theme_combo.currentText()
        theme = config.THEMES.get(theme_name, config.THEMES["dark"])
        
        bg_color = theme["bg"]
        text_color = theme["text"]
        border_color = theme["border"]
        
        frame_style = f"""
            QFrame {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 4px;
                padding: 2px;
            }}
        """
        self.preview_container.setStyleSheet(frame_style)
        
        preview_style = f"""
            QTextEdit {{
                background-color: {bg_color};
                color: {text_color};
                border: none;
                padding: 12px;
                font-family: 'Consolas', monospace;
                font-size: 10pt;
            }}
            QTextEdit::selection {{
                background-color: rgba(100, 149, 237, 0.3);
            }}
        """
        self.preview.setStyleSheet(preview_style)
        
        self.on_code_changed()

    def on_code_changed(self):
        """Update preview when code changes with syntax coloring"""
        code = self.code_input.toPlainText()
        theme_name = self.theme_combo.currentText()
        theme = config.THEMES.get(theme_name, config.THEMES["dark"])
        
        html_code = self._colorize_code(code, theme)
        self.preview.setHtml(html_code)

    def _colorize_code(self, code: str, theme: dict) -> str:
        """Generate HTML with syntax coloring - matches code_visualiser.py highlighting"""
        import re
        from html import escape
        
        code = escape(code)
        
        # Apply highlighting in same order as code_visualiser.py for consistency
        
        # Comments first (# comment text)
        code = re.sub(
            r'(#[^\n]*)',
            f'<span style="color: {theme.get("comment", "#6B7280")};">\1</span>',
            code
        )
        
        # Strings - triple double-quoted
        code = re.sub(
            r'("""(?:[^"\\]|\\.|\n)*?""")',
            f'<span style="color: {theme.get("string", "#16A34A")};">\1</span>',
            code,
            flags=re.DOTALL
        )
        
        # Strings - triple single-quoted
        code = re.sub(
            r"('''(?:[^'\\]|\\.|\n)*?''')",
            f'<span style="color: {theme.get("string", "#16A34A")};">\1</span>',
            code,
            flags=re.DOTALL
        )
        
        # Strings - double-quoted (single line)
        code = re.sub(
            r'("(?:[^"\\]|\\.)*?")',
            f'<span style="color: {theme.get("string", "#16A34A")};">\1</span>',
            code
        )
        
        # Strings - single-quoted (single line)
        code = re.sub(
            r"('(?:[^'\\]|\\.)*?')",
            f'<span style="color: {theme.get("string", "#16A34A")};">\1</span>',
            code
        )
        
        # Numbers
        code = re.sub(
            r'\b(0x[0-9a-fA-F]+|0b[01]+|0o[0-7]+|\d+\.\d+|\d+)\b',
            f'<span style="color: {theme.get("number", "#DB2777")};">\\g<1></span>',
            code
        )
        
        # Keywords - Python reserved words
        keywords = ['False', 'None', 'True', 'and', 'as', 'assert', 'async', 'await',
                    'break', 'class', 'continue', 'def', 'del', 'elif', 'else', 'except',
                    'finally', 'for', 'from', 'global', 'if', 'import', 'in', 'is',
                    'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise', 'return',
                    'try', 'while', 'with', 'yield']
        keyword_pattern = r'\b(' + '|'.join(keywords) + r')\b'
        code = re.sub(
            keyword_pattern,
            f'<span style="color: {theme.get("keyword", "#D97706")}; font-weight: bold;">\\1</span>',
            code
        )
        
        # Functions - identifier followed by (
        code = re.sub(
            r'([a-zA-Z_][a-zA-Z0-9_]*)\s*(?=\()',
            f'<span style="color: {theme.get("function", "#2563EB")}; font-weight: bold;">\\1</span>',
            code
        )
        
        # Operators
        code = re.sub(
            r'([=+\-*/%<>!&|^~@]+)',
            f'<span style="color: {theme.get("operator", "#374151")};">\\1</span>',
            code
        )
        
        # Variables - other identifiers (lower priority than keywords/functions)
        code = re.sub(
            r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b',
            f'<span style="color: {theme.get("variable", "#7C3AED")};">\\1</span>',
            code
        )
        
        html = f'<pre style="margin: 0; font-family: Consolas, monospace; color: {theme.get("text", "#1F2937")}; background: {theme.get("bg", "#f9f3ef")};">{code}</pre>'
        return html

    def paste_from_clipboard(self):
        """Paste code from clipboard"""
        clipboard = QApplication.clipboard()
        self.code_input.setPlainText(clipboard.text())

    def load_from_file(self):
        """Load code from file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Code File", "", "All Files (*.*)"
        )
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    self.code_input.setPlainText(f.read())
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to load file: {e}")

    def get_marker_text(self) -> str:
        """Generate marker text for main editor"""
        code = self.code_input.toPlainText()
        if not code.strip():
            return ""
        mode = self.mode_combo.currentText()
        mode_spec = "1" if mode == "typewriter" else "0"
        return f"[VisualiseCode:{mode_spec}]\n{code}\n[/VisualiseCode]"


class GraphPreviewWidget(QWidget):
    """Preview and input widget for graph visualization"""

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        header = QLabel("Graph Visualization Preview")
        header.setFont(QFont("Segoe UI", 11, QFont.Bold))
        layout.addWidget(header)

        settings_layout = QGridLayout()

        settings_layout.addWidget(QLabel("Graph Type:"), 0, 0)
        self.graph_type_combo = QComboBox()
        self.graph_type_combo.addItems(["bar", "line"])
        self.graph_type_combo.currentTextChanged.connect(self.apply_theme_styling)
        settings_layout.addWidget(self.graph_type_combo, 0, 1)

        settings_layout.addWidget(QLabel("Theme:"), 0, 2)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(config.CODE_VIS_THEMES)
        self.theme_combo.currentTextChanged.connect(self.apply_theme_styling)
        settings_layout.addWidget(self.theme_combo, 0, 3)

        layout.addLayout(settings_layout)

        layout.addWidget(QLabel("Data (label:value pairs, comma-separated):"))
        self.data_input = QTextEdit()
        self.data_input.setPlaceholderText(
            "Python:85,JavaScript:72,TypeScript:65,Rust:55"
        )
        self.data_input.setFont(QFont("Consolas", 10))
        self.data_input.setMaximumHeight(100)
        self.data_input.textChanged.connect(self.on_data_changed)
        layout.addWidget(self.data_input)

        layout.addWidget(QLabel("Live Preview:"))
        self.preview_container = QFrame()
        self.preview_container.setFrameShape(QFrame.StyledPanel)
        self.preview_container.setFrameShadow(QFrame.Sunken)
        preview_layout = QVBoxLayout()
        preview_layout.setContentsMargins(0, 0, 0, 0)
        
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFont(QFont("Consolas", 9))
        self.preview.setPlaceholderText("[Graph preview will appear here]")
        preview_layout.addWidget(self.preview)
        self.preview_container.setLayout(preview_layout)
        layout.addWidget(self.preview_container, stretch=1)

        button_layout = QHBoxLayout()
        
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear_data)
        button_layout.addWidget(clear_btn)
        
        paste_btn = QPushButton("Paste Data")
        paste_btn.clicked.connect(self.paste_from_clipboard)
        button_layout.addWidget(paste_btn)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)

        self.setLayout(layout)
        

        self.apply_theme_styling()

    def apply_theme_styling(self):
        """Apply current theme colors to preview"""
        theme_name = self.theme_combo.currentText()
        theme = config.THEMES.get(theme_name, config.THEMES["dark"])
        
        bg_color = theme["bg"]
        text_color = theme["text"]
        border_color = theme["border"]
        
        frame_style = f"""
            QFrame {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 4px;
                padding: 2px;
            }}
        """
        self.preview_container.setStyleSheet(frame_style)
        
        preview_style = f"""
            QTextEdit {{
                background-color: {bg_color};
                color: {text_color};
                border: none;
                padding: 12px;
                font-family: 'Consolas', monospace;
                font-size: 9pt;
            }}
            QTextEdit::selection {{
                background-color: rgba(100, 149, 237, 0.3);
            }}
        """
        self.preview.setStyleSheet(preview_style)
        
        self.on_data_changed()

    def on_data_changed(self):
        """Update preview when data changes with theme colors"""
        data = self.data_input.toPlainText()
        theme_name = self.theme_combo.currentText()
        theme = config.THEMES.get(theme_name, config.THEMES["dark"])
        graph_type = self.graph_type_combo.currentText()
        
        preview_text = f"<div style='color: {theme['text']};'>"
        preview_text += f"<strong>Graph Type:</strong> {graph_type.upper()}<br/>"
        preview_text += f"<strong>Theme:</strong> {theme_name}<br/><br/>"
        preview_text += f"<strong style='color: {theme['keyword']};'>Data Points:</strong><br/>"
        
        if data.strip():
            for pair in data.split(','):
                pair = pair.strip()
                if ':' in pair:
                    label, value = pair.split(':', 1)
                    label = label.strip()
                    value = value.strip()
                    try:
                        val_num = float(value)
                        bar_width = int(val_num / 2)
                        bar = "▮" * min(bar_width, 30)
                        preview_text += f"  <span style='color: {theme['function']};'>{label}</span>: "
                        preview_text += f"<span style='color: {theme['number']};'>{bar}</span> "
                        preview_text += f"<span style='color: {theme['comment']};'>{value}</span><br/>"
                    except:
                        preview_text += f"  {label}: {value}<br/>"
        
        preview_text += "</div>"
        self.preview.setHtml(preview_text)

    def paste_from_clipboard(self):
        """Paste data from clipboard"""
        clipboard = QApplication.clipboard()
        self.data_input.setPlainText(clipboard.text())

    def clear_data(self):
        """Clear data input"""
        self.data_input.clear()

    def get_marker_text(self) -> str:
        """Generate marker text for main editor"""
        data = self.data_input.toPlainText().strip()
        if not data:
            return ""
        graph_type = self.graph_type_combo.currentText()
        theme = self.theme_combo.currentText()
        return f"[VisualiseGraph:{graph_type}|{theme}]{data}[/VisualiseGraph]"


class MainVideoUI(QMainWindow):
    """Main application window for video generation"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video Generator - Text to Video Creation Tool")
        self.setGeometry(100, 100, 1400, 900)
        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        
        main_widget = QWidget()
        main_layout = QHBoxLayout()

        # LEFT PANEL: Main input and settings
        left_panel = QWidget()
        left_layout = QVBoxLayout()

        title = QLabel("Main Video Content")
        title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        left_layout.addWidget(title)

        settings_group = QGroupBox("Narrative Settings")
        settings_layout = QGridLayout()

        settings_layout.addWidget(QLabel("Theme:"), 0, 0)
        self.narrative_theme = QComboBox()
        self.narrative_theme.addItems(["dark", "heaven", "matrix"])
        self.narrative_theme.setCurrentText(getattr(config, 'NARRATIVE_THEME', 'dark'))
        settings_layout.addWidget(self.narrative_theme, 0, 1)

        settings_layout.addWidget(QLabel("Animation:"), 0, 2)
        self.narrative_style = QComboBox()
        self.narrative_style.addItems(["typewriter", "wordblurin", "linescan"])
        self.narrative_style.setCurrentText(getattr(config, 'NARRATIVE_STYLE', 'wordblurin'))
        settings_layout.addWidget(self.narrative_style, 0, 3)

        settings_group.setLayout(settings_layout)
        left_layout.addWidget(settings_group)

        left_layout.addWidget(QLabel("Narration Text (use markers below):"))
        self.main_text = QTextEdit()
        self.main_text.setPlaceholderText(
            "Enter your narration here...\n\n"
            "You can insert code and graph markers using the buttons below or type them manually.\n\n"
            "[VisualiseCode:1]\ncode here\n[/VisualiseCode]\n\n"
            "[VisualiseGraph:bar|dark]Label:Value,Label2:Value2[/VisualiseGraph]"
        )
        self.main_text.setFont(QFont("Segoe UI", 10))
        self.highlighter = MarkerHighlighter(self.main_text.document())
        left_layout.addWidget(self.main_text, stretch=3)

        marker_layout = QHBoxLayout()
        marker_layout.addWidget(QLabel("Insert Marker:"))
        
        code_btn = QPushButton("+ Code Block")
        code_btn.clicked.connect(self.insert_code_marker)
        marker_layout.addWidget(code_btn)
        
        graph_btn = QPushButton("+ Graph Block")
        graph_btn.clicked.connect(self.insert_graph_marker)
        marker_layout.addWidget(graph_btn)
        
        marker_layout.addStretch()
        left_layout.addLayout(marker_layout)

        left_panel.setLayout(left_layout)
        main_layout.addWidget(left_panel, stretch=2)

        # RIGHT PANEL: Preview and visualization tools
        right_panel = QWidget()
        right_layout = QVBoxLayout()

        preview_title = QLabel("Visualization Tools")
        preview_title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        right_layout.addWidget(preview_title)

        self.preview_tabs = QTabWidget()

        self.code_preview = CodePreviewWidget()
        self.preview_tabs.addTab(self.code_preview, "Code")

        self.graph_preview = GraphPreviewWidget()
        self.preview_tabs.addTab(self.graph_preview, "Graph")

        right_layout.addWidget(self.preview_tabs, stretch=1)

        insert_from_preview_layout = QHBoxLayout()
        
        insert_code_btn = QPushButton("Insert Code Marker")
        insert_code_btn.clicked.connect(self.insert_code_from_preview)
        insert_from_preview_layout.addWidget(insert_code_btn)
        
        insert_graph_btn = QPushButton("Insert Graph Marker")
        insert_graph_btn.clicked.connect(self.insert_graph_from_preview)
        insert_from_preview_layout.addWidget(insert_graph_btn)
        
        right_layout.addLayout(insert_from_preview_layout)

        right_panel.setLayout(right_layout)
        main_layout.addWidget(right_panel, stretch=1)

        # BOTTOM PANEL: Generation controls
        bottom_panel = QWidget()
        bottom_layout = QVBoxLayout()

        gen_settings = QGroupBox("Generation Settings")
        gen_layout = QGridLayout()

        self.generate_audio_check = QCheckBox("Generate Audio")
        self.generate_audio_check.setChecked(True)
        self.generate_audio_check.stateChanged.connect(self.on_audio_toggle)
        gen_layout.addWidget(self.generate_audio_check, 0, 0)

        self.save_mp3_check = QCheckBox("Save MP3")
        self.save_mp3_check.setChecked(True)
        self.save_mp3_check.setEnabled(True)
        gen_layout.addWidget(self.save_mp3_check, 0, 1)

        self.use_code_check = QCheckBox("Use Code Visualizer")
        self.use_code_check.setChecked(True)
        gen_layout.addWidget(self.use_code_check, 0, 2)

        self.use_graph_check = QCheckBox("Use Graph Visualizer")
        self.use_graph_check.setChecked(True)
        gen_layout.addWidget(self.use_graph_check, 0, 3)

        gen_settings.setLayout(gen_layout)
        bottom_layout.addWidget(gen_settings)

        action_layout = QHBoxLayout()
        
        load_btn = QPushButton("Load Prompt File")
        load_btn.clicked.connect(self.load_prompt_file)
        action_layout.addWidget(load_btn)
        
        save_btn = QPushButton("Save Project")
        save_btn.clicked.connect(self.save_project)
        action_layout.addWidget(save_btn)
        
        action_layout.addStretch()
        
        generate_btn = QPushButton("🎬 Generate Video")
        generate_btn.setFont(QFont("Segoe UI", 11, QFont.Bold))
        generate_btn.setMinimumHeight(45)
        generate_btn.setStyleSheet(
            "QPushButton { background-color: #2ecc71; color: white; "
            "border-radius: 5px; padding: 10px; }"
        )
        generate_btn.clicked.connect(self.generate_video)
        action_layout.addWidget(generate_btn)

        bottom_layout.addLayout(action_layout)

        bottom_panel.setLayout(bottom_layout)

        # Assemble main layout
        main_wrapper = QWidget()
        wrapper_layout = QVBoxLayout()
        wrapper_layout.addLayout(main_layout, stretch=1)
        wrapper_layout.addWidget(bottom_panel)
        main_wrapper.setLayout(wrapper_layout)

        self.setCentralWidget(main_wrapper)

    def on_audio_toggle(self):
        """Enable/disable save MP3 checkbox based on audio generation"""
        is_enabled = self.generate_audio_check.isChecked()
        self.save_mp3_check.setEnabled(is_enabled)
        if not is_enabled:
            self.save_mp3_check.setChecked(False)

    def insert_code_marker(self):
        """Insert empty code marker template"""
        cursor = self.main_text.textCursor()
        marker = "[VisualiseCode:1]\n\n[/VisualiseCode]\n"
        cursor.insertText(marker)
        self.main_text.setTextCursor(cursor)

    def insert_graph_marker(self):
        """Insert empty graph marker template"""
        cursor = self.main_text.textCursor()
        marker = "[VisualiseGraph:bar|dark]Label:Value[/VisualiseGraph]\n"
        cursor.insertText(marker)
        self.main_text.setTextCursor(cursor)

    def insert_code_from_preview(self):
        """Insert code marker from preview panel"""
        marker = self.code_preview.get_marker_text()
        if marker:
            cursor = self.main_text.textCursor()
            cursor.insertText(marker + "\n")
            self.main_text.setTextCursor(cursor)
            QMessageBox.information(self, "Success", "Code marker inserted!")
        else:
            QMessageBox.warning(self, "Empty", "Please enter code first.")

    def insert_graph_from_preview(self):
        """Insert graph marker from preview panel"""
        marker = self.graph_preview.get_marker_text()
        if marker:
            cursor = self.main_text.textCursor()
            cursor.insertText(marker + "\n")
            self.main_text.setTextCursor(cursor)
            QMessageBox.information(self, "Success", "Graph marker inserted!")
        else:
            QMessageBox.warning(self, "Empty", "Please enter data first.")

    def load_prompt_file(self):
        """Load prompt from file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Prompt File", "", "Text Files (*.txt);;All Files (*.*)"
        )
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    self.main_text.setPlainText(f.read())
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to load file: {e}")

    def save_project(self):
        """Save project to JSON"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Project", "", "JSON Files (*.json)"
        )
        if file_path:
            try:
                project_data = {
                    "narration": self.main_text.toPlainText(),
                    "narrative_theme": self.narrative_theme.currentText(),
                    "narrative_style": self.narrative_style.currentText(),
                    "generate_audio": self.generate_audio_check.isChecked(),
                    "save_mp3": self.save_mp3_check.isChecked(),
                    "use_code_visualizer": self.use_code_check.isChecked(),
                    "use_graph_visualizer": self.use_graph_check.isChecked(),
                }
                with open(file_path, 'w') as f:
                    json.dump(project_data, f, indent=2)
                QMessageBox.information(self, "Success", f"Project saved to {file_path}")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to save: {e}")

    def generate_video(self):
        """Generate video from narration text with markers"""
        text = self.main_text.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Empty Content", "Please enter narration text.")
            return

        prefs = {
            "generate_audio": self.generate_audio_check.isChecked(),
            "save_mp3": self.save_mp3_check.isChecked(),
            "use_code_visualizer": self.use_code_check.isChecked(),
            "use_graph_visualizer": self.use_graph_check.isChecked(),
            "narrative_theme": self.narrative_theme.currentText(),
            "narrative_style": self.narrative_style.currentText(),
        }

        confirm = QMessageBox.question(
            self,
            "Generate Video",
            f"Generate video with these settings?\n\n"
            f"  Theme: {prefs['narrative_theme']}\n"
            f"  Style: {prefs['narrative_style']}\n"
            f"  Generate Audio: {'Yes' if prefs['generate_audio'] else 'No'}\n"
            f"  Save MP3: {'Yes' if prefs['save_mp3'] else 'No'}\n"
            f"  Code Visualizer: {'Yes' if prefs['use_code_visualizer'] else 'No'}\n"
            f"  Graph Visualizer: {'Yes' if prefs['use_graph_visualizer'] else 'No'}\n",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if confirm != QMessageBox.Yes:
            return

        self.setEnabled(False)
        QApplication.processEvents()

        try:
            import sys
            from pathlib import Path
            main_module_path = str(Path(__file__).parent)
            if main_module_path not in sys.path:
                sys.path.insert(0, main_module_path)
            
            from main import generate_main_video
            
            # Create a proper modal progress dialog
            progress_dialog = QMessageBox(self)
            progress_dialog.setWindowTitle("Generating Video")
            progress_dialog.setText("🎬 Video generation in progress...\n\nThis may take several minutes.\nPlease wait.")
            progress_dialog.setStandardButtons(QMessageBox.NoButton)
            progress_dialog.setModal(True)
            progress_dialog.setAttribute(1, True)  # Set WA_ShowWithoutActivating to prevent focus issues
            progress_dialog.show()
            
            # Process events multiple times to ensure dialog is fully rendered
            for _ in range(5):
                QApplication.processEvents()
            
            try:
                video_path = generate_main_video(
                    prompt=text,
                    save_mp3=prefs["save_mp3"],
                    prefs=prefs
                )
            finally:
                # Ensure dialog is closed even if generation fails
                progress_dialog.close()
                QApplication.processEvents()

            if video_path and os.path.exists(video_path):
                mp3_path = ""
                if prefs["save_mp3"] and prefs["generate_audio"]:
                    mp3_path = video_path.replace(".mp4", ".mp3")
                    if os.path.exists(mp3_path):
                        mp3_path = f"\n📻 Audio: {mp3_path}"

                msg = (
                    "✅ Video Generated Successfully!\n\n"
                    f"📹 Video: {video_path}"
                    f"{mp3_path}"
                )
                
                reply = QMessageBox.information(
                    self,
                    "Success",
                    msg,
                    QMessageBox.Ok | QMessageBox.Open,
                    QMessageBox.Ok
                )

                if reply == QMessageBox.Open:
                    import subprocess
                    try:
                        if sys.platform == "win32":
                            os.startfile(video_path)
                        elif sys.platform == "darwin":
                            subprocess.run(["open", video_path])
                        else:
                            subprocess.run(["xdg-open", video_path])
                    except Exception as e:
                        QMessageBox.warning(self, "Open Failed", f"Could not open file: {e}")
            else:
                QMessageBox.critical(
                    self,
                    "Generation Failed",
                    "Video generation did not complete successfully.\n"
                    "Please check the console output for details."
                )

        except ImportError as e:
            QMessageBox.critical(
                self,
                "Import Error",
                f"Failed to import video generation module:\n{e}\n\n"
                "Make sure main.py is in the same directory."
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Generation Error",
                f"An error occurred during video generation:\n\n{str(e)}\n\n"
                "Please check the console output for detailed error information."
            )
        finally:
            import gc
            gc.collect()  # Clean up memory
            self.setEnabled(True)
            QApplication.processEvents()  # Process any pending events


def main():
    """Entry point"""
    app = QApplication(sys.argv)
    window = MainVideoUI()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
