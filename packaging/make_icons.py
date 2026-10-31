"""Render kai's icon (the same one the app draws) to PNG and ICO for the installers.

Usage: python packaging/make_icons.py OUT_DIR
"""

import sys
from pathlib import Path

from PIL import Image
from PySide6.QtGui import QGuiApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from kai.ui.tray import app_icon  # noqa: E402


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication(["make_icons", "-platform", "offscreen"])  # noqa: F841
    png = out / "kai.png"
    app_icon(256).pixmap(256, 256).save(str(png))
    Image.open(png).save(out / "kai.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    print(f"Icons written to {out}")


if __name__ == "__main__":
    main()
