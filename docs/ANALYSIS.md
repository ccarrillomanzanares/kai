# kai — Initial analysis

A voice AI agent that helps manage the computer (Linux, Windows, macOS), using
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
| Google Search grounding | ✅ | Up-to-date answers |
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

### Vision
- **Look at the screen on demand**: the model calls `capture_screen()` and receives a JPEG.
  Saves quota and respects privacy.
- Optional **screen sharing mode**: ≤1 fps frames while active, with a visible indicator.
- Optional webcam (later).

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

**Python + PySide6 (Qt)**, packaged with PyInstaller for all three OSes.

| Need | Library |
|---|---|
| Gemini Live | `google-genai` (official SDK) |
| Audio | `sounddevice` |
| Screenshots | `mss` + `Pillow` |
| System info / processes | `psutil` |
| Mouse and keyboard | `pynput` / `pyautogui` |
| Secure API key | `keyring` |
| UI | `PySide6` |

Platform notes: macOS needs _Accessibility_, _Screen Recording_ and _Microphone_ permissions.
On Linux under Wayland, input control and screenshots are limited (best on X11 or via portals).

## 5. Roadmap

1. **MVP**: minimal window, API key management, voice and text conversation with
   Gemini 3.8 Live, robust reconnection. ✅
2. Read-only and safe tools, plus on-demand screen capture.
3. Sensitive actions with confirmation, action log.
4. Mouse/keyboard control and screen sharing mode.
5. Packaging and installers for Linux, Windows and macOS.
