"""Cross-platform system tools."""

from __future__ import annotations

import datetime
import platform
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

import psutil


def get_datetime() -> dict:
    now = datetime.datetime.now().astimezone()
    return {
        "iso": now.isoformat(timespec="seconds"),
        "weekday": now.strftime("%A"),
        "timezone": now.tzname(),
    }


def get_system_info() -> dict:
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(str(Path.home().anchor or "/"))
    info = {
        "os": f"{platform.system()} {platform.release()}",
        "machine": platform.machine(),
        "cpu_count": psutil.cpu_count(),
        "cpu_percent": psutil.cpu_percent(interval=0.3),
        "memory_total_gb": round(mem.total / 1e9, 1),
        "memory_percent": mem.percent,
        "disk_total_gb": round(disk.total / 1e9, 1),
        "disk_percent": disk.percent,
    }
    battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    if battery is not None:
        info["battery_percent"] = round(battery.percent)
        info["battery_plugged"] = battery.power_plugged
    return info


def open_url(url: str) -> str:
    if urlparse(url).scheme not in ("http", "https"):
        raise ValueError("Only http and https URLs can be opened.")
    if not webbrowser.open(url):
        raise RuntimeError("No browser available.")
    return f"Opened {url}"
