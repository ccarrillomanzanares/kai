# kai — Initial analysis

A voice AI agent that helps manage the computer (Windows and Linux), using
**Gemini 3.8 Live** as its conversational model, with a minimalist look.

_Analysis date: 2026-10-30. Sources: official Google AI for Developers documentation._

## 1. Is Gemini 3.8 Live free?

**Yes.** On the official pricing page, `gemini-3.8-live` and `gemini-3.8-live-extended-thinking`
are listed as _"Free of charge"_ for input and output on the **Free Tier**.

Caveats:
- On the free tier Google **may use the data** (audio, screenshots) to improve its products.
  On the paid tier it does not. The app tells the user about this.
- Google does not publish concrete rate limits for this model; they are shown in AI Studio.
  The app must handle quota errors (429) gracefully.
- Paid prices (if the user enables billing): audio $3/M input tokens, $12/M output;
  image/video $1/M input; text $0.75/M input, $4.50/M output.

## 2. What the model offers (and what it doesn't)

| Capability | Status | Use in kai |
|---|---|---|
| Real-time audio in/out (PCM 16 kHz in / 24 kHz out) | ✅ | Voice conversation with barge-in |
| Text in/out | ✅ | Typed chat as an alternative |
| Images / video frames (JPEG, ≤1 fps) | ✅ | **Screen vision** and webcam |
| Function calling (async by default, `NON_BLOCKING`) | ✅ | **Core of computer control** |
| Google Search grounding | ⚠️ | Not in the free tier ("exceeded your current quota"); disabled |
| Input and output transcription | ✅ | Captions and history |
| ~70 languages | ✅ | Speaks the user's language |
| Proactive audio (always on) | ✅ | The model decides when to speak |
| Reasoning variant (`-extended-thinking`) | ✅ | "Think" mode for complex tasks |
| Code execution | ❌ | Replaced by our own local tools |
| Structured output, caching, URL context | ❌ | — |

Session limits that shape the design:
- Without compression: **15 min** audio-only, **2 min** audio+video. Each connection lasts ~10 min.
- With **context window compression** and **session resumption** (handles valid for 2 h) a session
  can run indefinitely. The app listens for `GoAway` to reconnect seamlessly.

## 3. Planned features

### Vision: how kai sees (implemented 2026-10-31)
Field tests showed that without vision kai chained dozens of blind keystrokes (one request:
~60 tool calls and 54 s of silence). kai now has three ways to see, from most to least exact:

1. **Its own browser** (`tools/browser.py`, Playwright): a separate Edge/Chrome window
   (Playwright's Chromium if neither is installed) with its own profile. Every read
   returns the page title, URL, text and a numbered list of the links, buttons and fields
   in view; kai clicks and types by number. Best for anything on the web.
2. **Accessibility tree** (`tools/uia.py`): the same data screen readers use. Windows: UI
   Automation (`uiautomation`). Linux: AT-SPI through PyGObject. Lists a window's buttons,
   fields, menus and texts with exact positions; kai clicks their centres.
3. **Screenshots** (`tools/screen.py`, `mss` + `Pillow`): on demand only, of the screen or
   one window, at most 1280 px. kai clicks with coordinates normalized to 0-1000 over the
   image, which Gemini handles well (3/3 hits in tests).

Findings about Gemini 3.8 Live:
- An image must travel **inside the function response** (`FunctionResponse.parts`). Sent
  as a realtime video frame during a tool call, the model ignored it and made up the screen.
- kai is nudged to talk to the user after 8 tool calls in a row without speaking.

### Computer control (via function calling)
By risk level:

1. **Read-only**: system info (CPU, RAM, disk, battery, network), processes, file search,
   clipboard, open windows.
2. **Safe actions**: open apps, files and URLs; volume and brightness; notifications;
   write clipboard; focus/minimise windows.
3. **Sensitive actions** (always **ask for confirmation**): move, rename or delete files,
   kill processes, run shell commands, install packages.
4. **Desktop control** (mouse and keyboard): clicks, typing and shortcuts guided by vision.
   Powerful but fragile; off by default, with confirmation and an emergency stop key.

### User experience
- Small minimalist window: an orb that reacts to the voice, optional captions and a text field.
- Global push-to-talk shortcut or continuous listening.
- System tray icon.
- **API key setup** on first launch, with a guide to get one at
  [Google AI Studio](https://aistudio.google.com/apikey). Stored in the **OS secret store**
  (Keychain, Credential Manager, Secret Service), never in plain text when one is available.
- A visible log of the actions the agent performed.

## 4. Stack

**Python + PySide6 (Qt)**, to be packaged with PyInstaller for Windows and Linux.
macOS is not supported for now (no test machine); some code paths exist but are untested.

| Need | Library |
|---|---|
| Gemini Live | `google-genai` (official SDK) |
| Audio | `sounddevice` |
| Screenshots | `mss` + `Pillow` |
| Browser control | `playwright` |
| Accessibility | `uiautomation` (Windows), AT-SPI via PyGObject (Linux) |
| System info / processes | `psutil` |
| Mouse and keyboard | `pynput` |
| Secure API key | `keyring` |
| UI | `PySide6` |

Platform notes: on Linux under Wayland, input control and screenshots are blocked (use an
X11 session). Reading windows on Linux needs AT-SPI (`python3-gi`, `gir1.2-atspi-2.0`).

## 5. Roadmap

1. **MVP**: minimal window, API key management, voice and text conversation with
   Gemini 3.8 Live, robust reconnection. ✅
2. Read-only and safe tools, plus on-demand screen capture. ✅
3. Sensitive actions with confirmation, three permission levels, diagnostics. ✅
4. Mouse/keyboard control, own browser and accessibility tree. ✅
5. Packaging and installers for Windows and Linux.
