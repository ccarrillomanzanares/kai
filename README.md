# kai

A minimalist voice assistant that helps you manage your computer, powered by
Google's **Gemini 3.8 Live**. Runs on Windows and Linux (macOS is not supported for now).

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

On Linux, audio needs PortAudio and window management needs `xrandr`:
`sudo apt install libportaudio2 x11-xserver-utils`. Use an X11 session:
Wayland blocks screenshots and mouse/keyboard control. To let kai read app windows,
install AT-SPI and give the virtual environment access to it:

```sh
sudo apt install python3-gi gir1.2-atspi-2.0
python -m venv --system-site-packages .venv
```

## How kai sees and acts

- **Web**: kai opens its own browser window (Edge or Chrome if installed, otherwise it
  downloads Chromium on first use). It reads each page as text plus a numbered list of
  links, buttons and fields, and clicks or types by number. Logins you make in that window
  are kept in kai's own profile.
- **Apps**: kai reads a window's buttons, fields and menus through the system
  accessibility tree (UI Automation on Windows, AT-SPI on Linux) and clicks them exactly.
- **Screenshots**: when that isn't enough, kai takes a screenshot (only when needed,
  never in the background) and clicks by position. Screenshots are sent to Google like
  the rest of the conversation. With "Ask for everything" kai asks before each one.
- **Out of the way**: while kai works in another app it folds its conversation panel
  (it comes back when kai speaks), leaves itself out of screenshots and moves its bar if
  a click would land on it.
- **Downloads** from kai's browser are saved to your Downloads folder.
- **Headset button**: in Settings you can make the play/pause button of a headset or
  keyboard mute and unmute the microphone.

Without an audio device kai still works as a text chat.

You can also set the key with the `GEMINI_API_KEY` environment variable.

## Diagnostics

If something goes wrong, use **⋯ → Send diagnostics…** (or `kai --send-diagnostics`).
It uploads kai's recent logs, versions, OS and audio devices to `ccmai.org/kai-diag`
and gives you a short reference. You can review the full report before sending.
It never includes your API key, and keys are redacted. Logs live in kai's config
folder under `logs/`; kai does not log what is said.

The report also carries the conversation since kai started (what you and kai said or
typed, every action it took and its last 12 screenshots with its clicks marked) while
**Include the conversation** is ticked; untick it to leave it out. kai keeps that
conversation in memory only, and it is gone when kai closes.

To also keep earlier runs, turn on **Settings → Record conversations for diagnostics**.
kai then saves the same things in `logs/conversation.log` on your computer, and the
report carries that recording instead. Turning the option off deletes the recording.
To record a single run without changing Settings, start kai with `kai --record`, and
send it later from the terminal with `kai --send-diagnostics --include-conversation`.

## Project layout

```
src/kai/
  app.py          entry point, wires UI and agent
  live.py         Gemini Live session: audio streaming, tool calls, reconnection
  audio.py        microphone and speaker
  config.py       API key storage (OS keychain) and constants
  logs.py         log file setup and secret redaction
  diag.py         diagnostics report (no conversations unless opted in, no keys)
  transcript.py   opt-in conversation recording for diagnostics
  tools/          functions the model can call on the computer
    browser.py    kai's own browser (Playwright)
    uia.py        app windows through the accessibility tree
    screen.py     screenshots and mouse
  ui/             scanner bar, tray icon, dialogs, theme
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
