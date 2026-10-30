# kai

A minimalist voice assistant that helps you manage your computer, powered by
Google's **Gemini 3.8 Live**. Runs on Linux, Windows and macOS.

Website: https://ccmai.org/kai/

## Run from source

Requires Python 3.11+ and a free Gemini API key from
[Google AI Studio](https://aistudio.google.com/apikey) (kai asks for it on first launch).

```sh
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
kai
```

On Linux, audio needs PortAudio: `sudo apt install libportaudio2`.
Without an audio device kai still works as a text chat.

You can also set the key with the `GEMINI_API_KEY` environment variable.

## Diagnostics

If something goes wrong, use **⋯ → Send diagnostics…** (or `kai --send-diagnostics`).
It uploads kai's recent logs, versions, OS and audio devices to `ccmai.org/kai-diag`
and gives you a short reference. You can review the full report before sending.
It never includes your conversations or your API key: kai does not log what is said,
and keys are redacted. Logs live in kai's config folder under `logs/`.

## Project layout

```
src/kai/
  app.py          entry point, wires UI and agent
  live.py         Gemini Live session: audio streaming, tool calls, reconnection
  audio.py        microphone and speaker
  config.py       API key storage (OS keychain) and constants
  logs.py         log file setup and secret redaction
  diag.py         diagnostics report (no conversations, no keys)
  tools/          functions the model can call on the computer
  ui/             Qt window, orb, onboarding dialog, theme
website/          static site, deployed to ccmai.org/kai
server/           diagnostics receiver that runs on the VPS
scripts/          maintenance scripts (deploy-web.sh)
docs/             design notes (ANALYSIS.md)
```

## Development

```sh
pytest                      # tests
scripts/deploy-web.sh       # publish website/ (on the VPS)
```

The whole project (code, docs, website) is in English; kai itself answers in
whatever language you speak to it.
