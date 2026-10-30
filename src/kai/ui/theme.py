"""Colors and stylesheet. One dark palette, one accent, generous spacing."""

BG = "#0d0d0f"
SURFACE = "#17171a"
BORDER = "#26262b"
TEXT = "#ececf0"
MUTED = "#8a8a94"
ACCENT = "#7dd3c0"
DANGER = "#f08a8a"

STATE_COLORS = {
    "offline": "#4a4a52",
    "connecting": "#8a8a94",
    "listening": "#ececf0",
    "thinking": "#b8a4f0",
    "speaking": ACCENT,
}

# state -> (lit color, unlit color) for the scanner LEDs
SCANNER_COLORS = {
    "offline": ("#5a5a62", "#1c1c20"),
    "connecting": ("#ff2d2d", "#2a1010"),
    "listening": ("#ff2d2d", "#2a1010"),
    "thinking": ("#ffb02e", "#2a1f0c"),
    "speaking": ("#ff2d2d", "#2a1010"),
    "muted": ("#8a8a94", "#1c1c20"),
}

STYLESHEET = f"""
* {{
    font-family: "Inter", "Segoe UI", "SF Pro Text", "Helvetica Neue", sans-serif;
    font-size: 14px;
    color: {TEXT};
}}
QWidget#root, QDialog {{
    background: {BG};
}}
QLabel#muted {{ color: {MUTED}; }}
QLabel#title {{ font-size: 22px; font-weight: 600; }}
QLabel#error {{ color: {DANGER}; }}
QLabel a {{ color: {ACCENT}; }}
QLineEdit {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 10px 12px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus {{ border-color: {MUTED}; }}
QComboBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 8px 12px;
}}
QComboBox:hover, QComboBox:focus {{ border-color: {MUTED}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    selection-background-color: {BORDER};
    outline: none;
    padding: 4px;
}}
QMenu {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{
    padding: 8px 18px;
    border-radius: 6px;
    color: {TEXT};
}}
QMenu::item:selected {{ background: {BORDER}; }}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 6px 8px;
}}
QToolTip {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 8px;
}}
QPushButton {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 9px 16px;
}}
QPushButton:hover {{ border-color: {MUTED}; }}
QPushButton:disabled {{ color: {MUTED}; }}
QPushButton#primary {{
    background: {TEXT};
    color: {BG};
    border: none;
    font-weight: 600;
}}
QPushButton#primary:disabled {{ background: {BORDER}; color: {MUTED}; }}
QToolButton {{
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 6px;
    color: {MUTED};
    font-size: 16px;
}}
QToolButton:hover {{ background: {SURFACE}; color: {TEXT}; }}
QToolButton:checked {{ color: {TEXT}; }}
QToolButton::menu-indicator {{ image: none; }}
QPlainTextEdit {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 8px;
    color: {TEXT};
    selection-background-color: {BORDER};
}}
QTextBrowser {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{ width: 0; }}
"""
