"""Measure the Claude executor on desktop tasks kai's voice model failed at.

Run through bench/run.sh, which provides a virtual display. Each task opens real
terminal windows, hands the executor a goal as the voice model would, and checks
the outcome from a marker file the stand-in program writes; the executor's own
report is never trusted for the verdict.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

import anthropic

from kai import executor, tools
from kai.tools import desktop

HERE = Path(__file__).parent
WORK = Path(os.environ.get("BENCH_WORK", "/tmp/kai-bench"))
PROJECT = WORK / "ClaudeMaxProject"
MARKER = WORK / "marker"


def terminal(title: str = "Terminal", autostart: bool = False) -> subprocess.Popen:
    env = dict(os.environ, PATH=f"{HERE / 'bin'}:{os.environ['PATH']}",
               BENCH_MARKER=str(MARKER), BENCH_DIR=str(PROJECT), HOME=str(WORK))
    if title != "Terminal":
        env["BENCH_TITLE"] = title
    if autostart:
        env["BENCH_AUTOSTART"] = "1"
    return subprocess.Popen(
        ["xfce4-terminal", "--disable-server", "--dynamic-title-mode=replace",
         "--initial-title", title, "--geometry", "100x30", "--working-directory", str(WORK),
         "-x", "bash", "--rcfile", str(HERE / "bashrc"), "-i"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wait_for_window(title: str, timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if title in [w.title for w in desktop._windows()]:
            return
        time.sleep(0.3)
    raise RuntimeError(f"Window '{title}' did not appear")


def setup_menu() -> list[subprocess.Popen]:
    procs = [terminal(autostart=True)]
    wait_for_window("claude")
    return procs


def setup_launch() -> list[subprocess.Popen]:
    procs = [terminal()]
    wait_for_window("Terminal")
    return procs


def setup_minimized() -> list[subprocess.Popen]:
    procs = [terminal(autostart=True)]
    wait_for_window("claude")
    next(w for w in desktop._windows() if w.title == "claude").minimize()
    procs.append(terminal(title="Claude"))  # a decoy whose title differs only in case
    wait_for_window("Claude")
    return procs


def trusted_in_project() -> bool:
    return MARKER.exists() and MARKER.read_text().strip() == f"trusted {PROJECT}"


TASKS = {
    "menu": (setup_menu,
             "In the terminal on screen, Claude Code has just started and is asking whether "
             "to trust the folder. Accept it so that Claude Code starts."),
    "launch": (setup_launch,
               "In the terminal window that is open on screen, change to the folder "
               "~/ClaudeMaxProject and run claude inside that terminal, so I can see it. "
               "Get it started: accept whatever it asks about the folder."),
    "minimized": (setup_minimized,
                  "I started Claude Code in a terminal a while ago and it is waiting for me "
                  "to answer something about trusting the folder, but I can't see that "
                  "window now. Find it, show it and accept."),
}


def run_one(client: anthropic.Anthropic, model: str, task: str, effort: str) -> dict:
    setup, goal = TASKS[task]
    MARKER.unlink(missing_ok=True)
    desktop._last_used = None
    procs = setup()
    time.sleep(1.0)
    try:
        result = executor.run_task(goal, client=client, model=model, effort=effort,
                                   level=tools.Permission.TRUSTED)
        time.sleep(0.5)
        passed = trusted_in_project()
        marker = MARKER.read_text().strip() if MARKER.exists() else None
    finally:
        for p in procs:
            p.terminate()
        time.sleep(1.0)
    return {
        "model": model, "task": task, "effort": effort, "passed": passed, "marker": marker,
        "finished": result.finished, "seconds": round(result.seconds, 1),
        "steps": len(result.steps), "requests": result.requests, "usage": result.usage,
        "cost": round(result.cost or 0, 4), "report": result.report,
        "trace": [f"{s.tool}({json.dumps(s.args, ensure_ascii=False)}) -> {s.result[:160]}"
                  for s in result.steps],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", default="claude-haiku-5-5,claude-sonnet-5-5,claude-opus-5-5")
    parser.add_argument("--tasks", default=",".join(TASKS))
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--effort", default="medium")
    parser.add_argument("--out", default=str(HERE / "results.json"))
    opts = parser.parse_args()

    PROJECT.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(["xfwm4", "--compositor=off"], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    client = anthropic.Anthropic()
    rows = []
    for task in opts.tasks.split(","):
        for model in opts.models.split(","):
            for _ in range(opts.runs):
                row = run_one(client, model, task, opts.effort)
                rows.append(row)
                print(f"{task:10} {model:18} {'PASS' if row['passed'] else 'FAIL'}  "
                      f"{row['seconds']:5.1f}s  {row['steps']:2} steps  ${row['cost']:.4f}  "
                      f"marker={row['marker']}", flush=True)
                Path(opts.out).write_text(json.dumps(rows, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
