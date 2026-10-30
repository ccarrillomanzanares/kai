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
QTextBrowser {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{ width: 0; }}
"""
