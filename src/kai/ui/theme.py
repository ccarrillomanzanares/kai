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

# state -> (glow color, highlight color) for the light line
LINE_COLORS = {
    "offline": ("#5a5a64", "#8a8a94"),
    "connecting": ("#ff5a5f", "#ff8a80"),
    "listening": ("#ff5a5f", "#ffd1cc"),
    "thinking": ("#8b5cf6", "#d8c8ff"),
    "speaking": ("#ff5a5f", "#ffb347"),
    "muted": ("#6a6a74", "#a0a0aa"),
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
QCheckBox {{ spacing: 8px; color: {MUTED}; }}
QCheckBox::indicator {{
    width: 14px; height: 14px; border-radius: 4px;
    border: 1px solid {BORDER}; background: {SURFACE};
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
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
QToolButton#barButton {{ font-size: 11px; padding: 4px 6px; color: {MUTED}; }}
QToolButton#barButton:hover {{ color: {TEXT}; background: transparent; }}
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
