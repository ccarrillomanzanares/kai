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

## Project layout

```
src/kai/
  app.py          entry point, wires UI and agent
  live.py         Gemini Live session: audio streaming, tool calls, reconnection
  audio.py        microphone and speaker
  config.py       API key storage (OS keychain) and constants
  tools/          functions the model can call on the computer
  ui/             Qt window, orb, onboarding dialog, theme
website/          static site, deployed to ccmai.org/kai
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
