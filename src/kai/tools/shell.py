"""Shell commands and process control. Always confirmed by the user first."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import psutil

TIMEOUT = 60
MAX_OUTPUT = 6000

if sys.platform == "win32":
    SHELL_NAME = "PowerShell"
elif sys.platform == "darwin":
    SHELL_NAME = "zsh"
else:
    SHELL_NAME = "bash"


def _shell_cmd(command: str) -> list[str]:
    if sys.platform == "win32":
        # Windows PowerShell writes redirected output in the legacy console code page,
        # which garbles accents; force UTF-8 so non-English output survives.
        command = "[Console]::OutputEncoding = [Text.Encoding]::UTF8; " + command
        return ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]
    return ["/bin/zsh" if sys.platform == "darwin" else "/bin/bash", "-c", command]


def _trim(text: str) -> str:
    if len(text) <= MAX_OUTPUT:
        return text
    return text[: MAX_OUTPUT // 2] + "\n…[output truncated]…\n" + text[-MAX_OUTPUT // 2 :]


def run_command(command: str, reason: str = "") -> dict:
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    try:
        proc = subprocess.run(_shell_cmd(command), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=TIMEOUT,
                              stdin=subprocess.DEVNULL, cwd=Path.home(), **kwargs)
    except subprocess.TimeoutExpired:
        return {"exit_code": None, "error": f"Timed out after {TIMEOUT} s"}
    return {"exit_code": proc.returncode, "stdout": _trim(proc.stdout), "stderr": _trim(proc.stderr)}


def list_processes(sort_by: str = "memory", limit: int = 15) -> list[dict]:
    # cpu_percent needs two samples: the first call always returns 0.
    running = list(psutil.process_iter(["pid", "name", "memory_info"]))
    for p in running:
        try:
            p.cpu_percent(None)
        except psutil.Error:
            pass
    time.sleep(0.5)
    procs = []
    for p in running:
        try:
            cpu = p.cpu_percent(None)
        except psutil.Error:
            continue
        mem = p.info["memory_info"]
        procs.append({
            "pid": p.info["pid"],
            "name": p.info["name"],
            "memory_mb": round(mem.rss / 1e6) if mem else 0,
            "cpu_percent": cpu,
        })
    key = "cpu_percent" if sort_by == "cpu" else "memory_mb"
    return sorted(procs, key=lambda p: p[key], reverse=True)[: max(1, min(int(limit), 50))]


def kill_process(pid: int) -> str:
    proc = psutil.Process(int(pid))
    name = proc.name()
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except psutil.TimeoutExpired:
        proc.kill()
    return f"Closed {name} (pid {pid})"


def describe_kill(pid: int) -> str:
    try:
        return f"{psutil.Process(int(pid)).name()} (pid {pid})"
    except psutil.Error:
        return f"pid {pid}"
