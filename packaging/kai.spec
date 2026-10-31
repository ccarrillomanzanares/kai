# PyInstaller spec for kai. Build from the repository root:
#   python packaging/make_icons.py build/icons
#   pyinstaller packaging/kai.spec
# The result is a folder, dist/kai/, that the Windows installer and the Linux
# AppImage wrap.

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent
ICONS = ROOT / "build" / "icons"

hiddenimports = []
binaries = []
datas = []

# Modules imported lazily or chosen per platform at run time.
for pkg in ("kai", "pynput", "pywinctl", "pymonctl", "pywinbox", "keyring.backends"):
    hiddenimports += collect_submodules(pkg)

# diagnostics report the versions of these packages
for dist in ("google-genai", "PySide6", "sounddevice", "numpy", "keyring", "psutil",
             "pynput", "PyWinCtl", "playwright", "mss", "Pillow"):
    datas += copy_metadata(dist)

if sys.platform == "win32":
    hiddenimports += collect_submodules("uiautomation") + ["comtypes.stream"]
    datas += copy_metadata("uiautomation")
runtime_hooks = []
if sys.platform != "win32":
    # Bundle PortAudio so audio works without installing libportaudio2.
    import ctypes.util

    if lib := ctypes.util.find_library("portaudio"):
        for d in ("/usr/lib/x86_64-linux-gnu", "/usr/lib64", "/usr/lib"):
            if os.path.exists(os.path.join(d, lib)):
                binaries.append((os.path.join(d, lib), "."))
                break
        runtime_hooks.append(str(ROOT / "packaging" / "rthook_portaudio.py"))
    else:
        print("WARNING: PortAudio not found; the build will have no audio without libportaudio2")

if sys.platform != "win32":
    # Reading app windows on Linux goes through AT-SPI (PyGObject + typelib).
    try:
        from PyInstaller.utils.hooks.gi import GiModuleInfo

        info = GiModuleInfo("Atspi", "2.0")
        if info.available:
            b, d, h = info.collect_typelib_data()
            binaries += b
            datas += d
            hiddenimports += h + ["gi", "gi.repository.Atspi"]
        else:
            print("WARNING: AT-SPI typelib not found; the build cannot read app windows")
    except ImportError:
        print("WARNING: PyGObject not installed; the build cannot read app windows")

a = Analysis(
    [str(ROOT / "src" / "kai" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    runtime_hooks=runtime_hooks,
    excludes=["tkinter", "pytest", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.Qt3DCore", "PySide6.QtQuick3D", "PySide6.QtCharts",
              "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtMultimedia"],
    noarchive=False,
)
pyz = PYZ(a.pure)

icon = ICONS / ("kai.ico" if sys.platform == "win32" else "kai.png")
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="kai",
    console=False,  # a GUI app: no console window on Windows
    icon=str(icon) if icon.exists() else None,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="kai", upx=False)
