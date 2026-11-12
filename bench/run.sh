#!/usr/bin/env bash
# Run the executor bench on a virtual display. Needs ANTHROPIC_API_KEY, xvfb, xfwm4 and
# xfce4-terminal. Arguments go to bench/run.py (--models, --tasks, --runs, --effort).
cd "$(dirname "$0")/.."
exec dbus-run-session -- xvfb-run -a -s "-screen 0 1280x800x24" \
  env PYTHONPATH=src .venv/bin/python bench/run.py "$@"
