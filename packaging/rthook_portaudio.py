# PyInstaller runtime hook (Linux): sounddevice looks for PortAudio with
# ctypes.util.find_library. Use the system's copy when there is one, otherwise
# the copy bundled with kai.
import ctypes.util
import os
import sys

_find_library = ctypes.util.find_library


def _find_with_bundled(name):
    found = _find_library(name)
    if found is None and name == "portaudio":
        bundled = os.path.join(sys._MEIPASS, "libportaudio.so.2")
        if os.path.exists(bundled):
            return bundled
    return found


ctypes.util.find_library = _find_with_bundled
