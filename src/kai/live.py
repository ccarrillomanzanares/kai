"""The Gemini Live session: streams audio in and out, handles tool calls,
and reconnects transparently using session resumption.

The session runs on its own asyncio loop in a background thread and talks to
the UI only through Qt signals.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import time
import threading
from dataclasses import dataclass

from google import genai
from google.genai import errors, types
from PySide6.QtCore import QObject, Signal

from kai import tools, transcript
from kai.tools import screen
from kai import audio
from kai.audio import IN_RATE, Microphone, Speaker
from kai.config import MODEL

log = logging.getLogger(__name__)

def _is_key_problem(code: int | None, detail: str) -> bool:
    """Only these errors mean the API key itself is wrong; others are worth a reconnect."""
    text = detail.lower()
    if code in (401, 403):
        return True
    return code in (1008, 400) and any(
        w in text for w in ("api key", "api_key", "permission", "unauthenticated", "invalid key"))


LONG_RUN = 8  # tool calls without speaking before kai is nudged to check in with the user
MAX_SILENT_RUN = 16  # ...and before further tool calls are refused until it speaks

SYSTEM_PROMPT = """\
You are kai, a calm and concise voice assistant that helps the user manage their computer.
- Always answer in the language the user speaks to you.
- Keep spoken answers short; offer details only if asked.
- Use your tools to inspect or act on the computer instead of guessing.
- Never claim you did something on the computer unless you checked it. "Clicked", "Typed"
  or "Pressed" only mean the input was sent: before saying a video plays, a file was saved
  or a message was sent, read the page or window again, or look at the screen. If it
  didn't work, say so plainly and try another way.
- You can do much more than your specific tools: for anything they don't cover
  (settings, network, installed software, moving or renaming files, etc.) use run_command
  with a command for the user's operating system. Don't tell the user you can't do
  something on the computer before considering run_command.
- Web tasks (search, read a page, use a site, fill a form): use your own browser with
  browser_open, browser_read, browser_click, browser_type, browser_scroll and browser_back.
  They show the page text and numbered elements, so you know what is there. For a search,
  open the search URL directly. Use open_url only when the user wants a page opened in
  their usual browser for themselves.
  Inside your browser ALWAYS act through the element numbers. Never use look_at_screen,
  click, scroll, press_keys or type_text on it: they are slower and miss. If an element
  isn't listed, scroll or read the next part; use browser_screenshot only to look at
  images.
- Apps on the desktop: open them with open_app, then call read_window and act on the
  numbers it lists: click_element for buttons, menus and links, fill_field for text
  fields. A [disabled] button usually needs something first (e.g. text in a field).
  Only if read_window finds nothing useful, use look_at_screen and click with coordinates
  from the image; for small icons, look closely and aim at their center. If a click
  landed somewhere else, aim differently: never repeat the same point. Shortcuts go
  through press_keys, passing the window title (list_windows shows them). Some apps
  (Blender, games, editors with panels) send keys to the area under the mouse: click
  inside that area first (e.g. Blender's 3D view) so the shortcut reaches it.
- Downloads from your browser are saved to the user's Downloads folder; the browser
  tells you when one starts and finishes. A big one keeps your browser busy until done.
- When the user asks to open "the browser" to do something, use your own (browser_open).
- To close a program, use close_window. Use kill_process only if it hangs or the user asks;
  never kill every process of an app (e.g. all msedge.exe): that loses the user's work.
  After acting, check the result (read again or take a new screenshot) instead of assuming.
  If list_windows doesn't show the window you need, try read_window or look_at_screen
  before telling the user you can't find it.
- Never act blindly: don't chain keystrokes hoping they work. If you can't see how to do
  something after a few tries, tell the user what you see and ask.
  Never simulate the keyboard through run_command: those commands run hidden and can't
  reach the user's windows.
- Depending on the user's permission level, some actions show a confirmation window.
  If a tool result says the user declined, accept it and don't insist.
- You only act when the user talks to you: you can't watch the screen or wait in the
  background. If asked to keep an eye on something, say so and suggest they ask you to
  check whenever they want.
- Prefer read-only commands to look before changing anything. Never run destructive
  commands (deleting, formatting, uninstalling) unless the user explicitly asked for it.

About the kai app itself, so you can help the user with it:
- kai is a desktop app for Windows and Linux: a slim floating bar above the taskbar
  with a thin line of light: a coral glow glides along it while listening (and swells with
  the user's voice), two violet glows cross while thinking, and it becomes a waveform
  while speaking. Clicking the line opens the conversation and a text field to type. The bar can be dragged anywhere. A tray icon shows or hides kai.
- The ● button on the left of the bar mutes or unmutes the microphone.
- Without headphones kai does not listen while it speaks; with headphones works best.
- The ⋯ menu (right end of the bar) has "Settings…", "Change API key…", "Send diagnostics…" and
  "Quit". In Settings the user picks one of 30 voices, an accent (e.g. Spanish from Spain,
  Mexico or Argentina; changing voice or accent restarts the conversation) and a permission
  level: "Ask for everything", "Ask before risky actions" (default: commands, closing
  programs, typing in terminals) or "Only ask before destructive commands". Commands that
  delete, uninstall or shut down always ask.
  The window can be moved by dragging it. While kai works in other apps it folds its
  conversation panel (it comes back when kai talks), is left out of screenshots and
  moves away if a click would land on it.
- Settings also has an option for the headset or keyboard play/pause button to mute
  and unmute the microphone.
- kai uses Google's Gemini 3.8 Live with the user's own free API key from Google AI Studio,
  stored in the system keychain. On the free tier Google may use conversations to improve
  its products; enabling billing on the key opts out.
- kai does not store conversations by default: its log files only contain technical events.
  For debugging, the user can turn on "Record conversations for diagnostics" in Settings; the
  recording stays on the computer and is only sent if the user ticks it in the diagnostics
  window. Turning the option off deletes it.
- If the user reports a problem with kai, offer to open the diagnostics window with the
  open_diagnostics tool. It shows the report and only uploads it if the user clicks Send.
  The user then gets a short reference to share with the developer.
- Website: ccmai.org/kai. Source code: github.com/ccarrillomanzanares/kai.
"""

MAX_BACKOFF = 30
CONFIRM_TIMEOUT = 120  # seconds before an unanswered confirmation counts as declined
HEARTBEAT_SECONDS = 60  # how often the log records the health of the session
VOICED_LEVEL = 0.05  # mic chunks louder than this probably contain speech
# If the user has spoken this many voiced chunks (50 ms each) and the server has been
# silent this long, the session is assumed stuck and resumed on a new connection.
STUCK_VOICED_CHUNKS = 40
STUCK_SILENCE_SECONDS = 15


class State:
    OFFLINE = "offline"
    CONNECTING = "connecting"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"


@dataclass
class _Turn:
    """Content-free facts about the current conversation turn, for the log."""

    user_first: float | None = None
    user_last: float | None = None
    reply_started: float | None = None
    user_chars: int = 0
    kai_chars: int = 0
    audio_seconds: float = 0.0


class LiveAgent(QObject):
    state_changed = Signal(str)
    user_said = Signal(str)  # transcription chunk of the user's speech
    kai_said = Signal(str)  # transcription chunk of kai's speech
    turn_done = Signal()
    level = Signal(float)  # 0..1, current mic or speaker level
    error = Signal(str)
    fatal_error = Signal(str)  # e.g. invalid API key; the agent has stopped
    tool_used = Signal(str, dict)
    ui_action = Signal(str)  # a tool asked the app to do something in the UI
    confirm_requested = Signal(int, str, str)  # (request id, title, detail)

    def __init__(self, api_key: str, full_duplex: bool | None = None, voice: str | None = None,
                 accent_instruction: str = "", microphone: str | None = None):
        super().__init__()
        self._api_key = api_key
        self._voice = voice
        self._system_prompt = SYSTEM_PROMPT + (f"\n{accent_instruction}\n" if accent_instruction else "")
        # True when the user wears headphones; None = detect from the output device.
        self._full_duplex = full_duplex
        self._auto_duplex = full_duplex is None
        self._mic_enabled = True
        self._permission = tools.Permission.BALANCED
        self._loop: asyncio.AbstractEventLoop | None = None
        self._main: asyncio.Task | None = None
        self._thread: threading.Thread | None = None
        self._audio_q: asyncio.Queue[bytes] | None = None
        self._session = None
        self._stopping = False
        self._state = State.OFFLINE
        self._confirmations: dict[int, tuple[threading.Event, list[bool]]] = {}
        self._confirm_ids = itertools.count(1)
        self._speaker = Speaker(on_level=self._on_speaker_level)
        self._mic = Microphone(on_chunk=self._on_mic_chunk, device=microphone)
        self._audio_ok = False
        # Content-free counters for the heartbeat log line.
        self._stats = {"sent": 0, "voiced": 0, "gated": 0, "muted": 0, "peak": 0.0, "msgs": 0,
                       "heard": 0, "vad": 0}
        self._last_server_msg = time.monotonic()
        self._voiced_since_msg = 0
        self._handle: str | None = None  # latest session resumption handle
        self._reconnect_now: asyncio.Event | None = None
        self._turn = _Turn()
        self._user_spoke_at: float | None = None  # last user words, across tool turns
        self._silent_tools = 0  # tool calls since kai or the user last spoke

    # ---- public API (call from the UI thread) ----

    def start(self) -> None:
        self._stopping = False
        self._thread = threading.Thread(target=self._thread_main, name="kai-live", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopping = True
        for event, _ in list(self._confirmations.values()):
            event.set()  # unblock pending confirmations as declined
        if self._loop and self._main:
            self._loop.call_soon_threadsafe(self._main.cancel)
        if self._thread:
            self._thread.join(timeout=3)
        self._mic.stop()
        self._speaker.stop()

    def send_text(self, text: str) -> None:
        log.info("User typed a message (%d chars)%s", len(text),
                 "" if self._session else " but there is no session")
        if self._loop and self._session:
            asyncio.run_coroutine_threadsafe(
                self._session.send_realtime_input(text=text), self._loop
            )
            transcript.typed(text)
            self._turn.user_chars += len(text)
            self._user_spoke_at = time.monotonic()

    def set_mic_enabled(self, enabled: bool) -> None:
        if enabled != self._mic_enabled:
            log.info("Microphone %s by the user", "unmuted" if enabled else "muted")
        self._mic_enabled = enabled

    def set_permission_level(self, level: tools.Permission) -> None:
        log.info("Permission level: %s", level.value)
        self._permission = level

    def resolve_confirmation(self, request_id: int, approved: bool) -> None:
        if entry := self._confirmations.get(request_id):
            entry[1].append(approved)
            entry[0].set()

    # ---- confirmations (tool worker threads) ----

    def _confirm(self, title: str, detail: str) -> bool:
        """Ask the UI to approve a sensitive action and wait for the answer."""
        request_id = next(self._confirm_ids)
        event, answer = threading.Event(), []
        self._confirmations[request_id] = (event, answer)
        started = time.monotonic()
        log.info("Confirmation #%d requested", request_id)
        try:
            self.confirm_requested.emit(request_id, title, detail)
            answered = event.wait(CONFIRM_TIMEOUT)
            approved = answered and bool(answer) and answer[0] and not self._stopping
            log.info("Confirmation #%d %s after %.1fs", request_id,
                     "approved" if approved else ("declined" if answered else "timed out"),
                     time.monotonic() - started)
            return bool(approved)
        finally:
            del self._confirmations[request_id]

    # ---- audio callbacks (audio threads) ----

    def _on_mic_chunk(self, pcm: bytes, level: float) -> None:
        if self._audio_q is None or self._loop is None:
            return
        if not self._mic_enabled:
            self._stats["muted"] += 1
            return
        # Without headphones the speaker leaks into the mic and kai would
        # interrupt itself, so we only listen while it is quiet.
        if not self._full_duplex and self._speaker.is_playing:
            self._stats["gated"] += 1
            return
        self._stats["sent"] += 1
        if level > VOICED_LEVEL:
            self._stats["voiced"] += 1
            self._voiced_since_msg += 1
        self._stats["peak"] = max(self._stats["peak"], level)
        if self._state in (State.LISTENING, State.THINKING):
            self.level.emit(level)
        self._loop.call_soon_threadsafe(self._enqueue_audio, pcm)

    def _enqueue_audio(self, pcm: bytes) -> None:
        assert self._audio_q is not None
        if self._audio_q.full():  # not connected: drop the oldest audio
            self._audio_q.get_nowait()
        self._audio_q.put_nowait(pcm)

    def _on_speaker_level(self, level: float) -> None:
        if self._speaker.is_playing:
            self._set_state(State.SPEAKING)
            self.level.emit(level)
        elif self._state == State.SPEAKING:
            self._set_state(State.LISTENING)

    # ---- session ----

    def _set_state(self, state: str) -> None:
        if state != self._state:
            log.debug("State %s -> %s", self._state, state)
            self._state = state
            self.state_changed.emit(state)

    def _thread_main(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._audio_q = asyncio.Queue(maxsize=200)
        self._reconnect_now = asyncio.Event()
        self._main = self._loop.create_task(self._run())
        try:
            self._loop.run_until_complete(self._main)
        except asyncio.CancelledError:
            pass  # stopped by stop()
        finally:
            self._loop.close()
            self._set_state(State.OFFLINE)

    def _config(self, handle: str | None) -> types.LiveConnectConfig:
        return types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            system_instruction=self._system_prompt,
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self._voice)
                )
            ) if self._voice else None,
            # Google Search grounding is not included in the free tier.
            tools=tools.declarations(),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            context_window_compression=types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow()
            ),
            session_resumption=types.SessionResumptionConfig(handle=handle),
            # Catch quieter or farther voices than the default detector does.
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
                    prefix_padding_ms=200,
                )
            ),
        )

    async def _run(self) -> None:
        client = genai.Client(api_key=self._api_key)
        self._start_audio()
        watchdog = asyncio.create_task(self._watchdog())
        try:
            await self._reconnect_loop(client)
        finally:
            watchdog.cancel()
            await client.aio.aclose()

    def _start_audio(self) -> None:
        try:
            mic_name, out_name = audio.default_devices()
            if self._full_duplex is None:
                self._full_duplex = audio.is_headphones(out_name)
            log.info("Audio: mic '%s', output '%s', headphones mode: %s",
                     self._mic.device or mic_name, out_name, self._full_duplex)
            self._speaker.start()
            self._mic.start()
            self._audio_ok = True
        except Exception as e:  # no PortAudio or no devices: keep working as text chat
            log.warning("Audio unavailable: %s", e)
            self.error.emit("No audio device found, text only.")

    def _restart_audio(self) -> None:
        """Reopen both streams on the current default devices."""
        import sounddevice as sd

        self._mic.stop()
        self._speaker.stop()
        try:
            # PortAudio caches the device list; refresh it to pick up new defaults.
            sd._terminate()
            sd._initialize()
        except Exception as e:
            log.warning("PortAudio reinit failed: %s", e)
        self._audio_ok = False
        self._full_duplex = None if self._auto_duplex else self._full_duplex
        self._start_audio()

    async def _watchdog(self) -> None:
        """Restart audio streams the OS stopped, and log a heartbeat now and then."""
        last_beat = time.monotonic()
        while True:
            await asyncio.sleep(1)
            stalled = [type(st).__name__ for st in (self._mic, self._speaker) if st.stalled()]
            if self._audio_ok and stalled:
                log.warning("Audio stalled (%s), restarting audio", ", ".join(stalled))
                await asyncio.to_thread(self._restart_audio)
            now = time.monotonic()
            silent = now - self._last_server_msg
            if (self._session is not None and silent > STUCK_SILENCE_SECONDS
                    and self._voiced_since_msg >= STUCK_VOICED_CHUNKS):
                log.warning("Server silent for %.0fs while the user spoke (%d voiced chunks); "
                            "resuming on a new connection", silent, self._voiced_since_msg)
                self._voiced_since_msg = 0
                self._reconnect_now.set()
            if now - last_beat >= HEARTBEAT_SECONDS:
                st = self._stats
                log.info(
                    "Heartbeat: state=%s connected=%s mic_sent=%d mic_voiced=%d mic_gated=%d "
                    "mic_muted=%d mic_peak=%.2f speaker_buffer=%.1fs "
                    "server_msgs=%d server_vad=%d speech_heard=%d last_server_msg=%.0fs ago",
                    self._state, self._session is not None, st["sent"], st["voiced"],
                    st["gated"], st["muted"], st["peak"],
                    self._speaker.buffered_seconds, st["msgs"], st["vad"], st["heard"],
                    now - self._last_server_msg)
                self._stats = dict.fromkeys(st, 0) | {"peak": 0.0}
                last_beat = now

    async def _reconnect_loop(self, client: genai.Client) -> None:
        backoff = 1
        stale_resumes = 0  # "already exists" errors in a row
        while not self._stopping:
            self._set_state(State.CONNECTING)
            resumed = False
            connected_at = None
            try:
                config = self._config(self._handle)
                async with client.aio.live.connect(model=MODEL, config=config) as s:
                    self._session = s
                    connected_at = time.monotonic()
                    self._last_server_msg = time.monotonic()
                    self._voiced_since_msg = 0
                    log.info("Connected to %s (resumed: %s)", MODEL, self._handle is not None)
                    transcript.note("connected" + (" (resumed)" if self._handle else ""))
                    self._set_state(State.LISTENING)
                    backoff = 1
                    opened = time.monotonic()
                    try:
                        resumed = await self._serve_until_reconnect(s)
                    finally:
                        log.info("Connection closed after %.0fs", time.monotonic() - opened)
            except errors.APIError as e:
                detail = e.message or str(e)
                log.warning("Live API error %s: %s", e.code, detail)
                if _is_key_problem(e.code, detail):
                    self.fatal_error.emit(detail or "Google rejected the API key.")
                    return
                if self._handle and ("not found" in detail.lower()
                                     or "expired" in detail.lower()):
                    # The old session is gone (e.g. after a server error): start a fresh one.
                    log.info("Session can't be resumed; starting a new one")
                    self._handle = None
                    stale_resumes = 0
                    self.error.emit("Reconnected with a fresh conversation: kai lost "
                                    "what was said before.")
                    backoff = 1
                    continue
                if self._handle:
                    # Resuming keeps the context, but if the old session fails twice in a
                    # row within a minute (e.g. "already exists" after a long idle), start a
                    # fresh one rather than retrying it forever.
                    lived = time.monotonic() - connected_at if connected_at else 0
                    stale_resumes = stale_resumes + 1 if lived < 60 else 1
                    if stale_resumes >= 2:
                        log.info("Dropping the resumption handle after repeated errors")
                        self._handle = None
                        stale_resumes = 0
                if e.code == 429 or "quota" in detail.lower():
                    self.error.emit("Free-tier quota reached. Retrying shortly…")
                    backoff = MAX_BACKOFF
                else:
                    self.error.emit(f"Connection lost: {detail}")
            except Exception as e:
                log.exception("Live session failed")
                self.error.emit(f"Connection lost: {e}")
            finally:
                self._session = None
            if not self._stopping and not resumed:
                self._set_state(State.CONNECTING)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)

    async def _serve_until_reconnect(self, s) -> bool:
        """Serve the connection until it ends. True if the watchdog asked to reconnect."""
        assert self._reconnect_now is not None
        self._reconnect_now.clear()
        serve = asyncio.create_task(self._serve(s))
        wake = asyncio.create_task(self._reconnect_now.wait())
        try:
            done, _ = await asyncio.wait({serve, wake}, return_when=asyncio.FIRST_COMPLETED)
        except asyncio.CancelledError:  # kai is quitting
            serve.cancel()
            await asyncio.gather(serve, return_exceptions=True)
            raise
        finally:
            wake.cancel()
        if serve in done:
            serve.result()  # re-raise connection errors
            return True  # GoAway: reconnect right away
        serve.cancel()
        await asyncio.gather(serve, return_exceptions=True)  # the watchdog's reconnect wins
        return True

    async def _serve(self, s) -> None:
        """Run one connection until it closes or the server asks to reconnect."""
        sender = asyncio.create_task(self._pump_audio(s))
        tool_tasks: set[asyncio.Task] = set()
        try:
            while True:
                async for msg in s.receive():
                    self._stats["msgs"] += 1
                    self._stats["vad"] += bool(msg.voice_activity_detection_signal
                                               or msg.voice_activity)
                    self._last_server_msg = time.monotonic()
                    self._voiced_since_msg = 0
                    if msg.session_resumption_update and msg.session_resumption_update.new_handle:
                        self._handle = msg.session_resumption_update.new_handle
                    if msg.voice_activity_detection_signal:
                        log.debug("Server VAD signal: %s",
                                  msg.voice_activity_detection_signal.vad_signal_type)
                    if msg.voice_activity:
                        log.debug("Server voice activity: %s",
                                  msg.voice_activity.voice_activity_type)
                    if msg.usage_metadata and msg.usage_metadata.total_token_count:
                        log.debug("Usage: %s tokens", msg.usage_metadata.total_token_count)
                    if msg.tool_call_cancellation:
                        log.info("Server cancelled %d tool call(s)",
                                 len(msg.tool_call_cancellation.ids or []))
                    if msg.go_away:
                        log.info("Server asked to reconnect (time left: %s)", msg.go_away.time_left)
                        return
                    if msg.tool_call:
                        # Run tools in the background: a confirmation can take a while
                        # and audio must keep flowing meanwhile.
                        task = asyncio.create_task(self._handle_tool_call(s, msg.tool_call))
                        tool_tasks.add(task)
                        task.add_done_callback(tool_tasks.discard)
                    if msg.server_content:
                        self._handle_content(msg.server_content)
        finally:
            sender.cancel()
            for task in tool_tasks:
                task.cancel()

    async def _pump_audio(self, s) -> None:
        assert self._audio_q is not None
        mime = f"audio/pcm;rate={IN_RATE}"
        while True:
            pcm = await self._audio_q.get()
            await s.send_realtime_input(audio=types.Blob(data=pcm, mime_type=mime))

    def _handle_content(self, sc: types.LiveServerContent) -> None:
        turn = self._turn
        now = time.monotonic()
        if sc.interrupted:
            log.info("kai interrupted after %.1fs of reply audio (%.1fs still queued)",
                     turn.audio_seconds, self._speaker.buffered_seconds)
            self._speaker.clear()
        if sc.model_turn:
            for part in sc.model_turn.parts or []:
                if part.inline_data and part.inline_data.data:
                    if turn.reply_started is None:
                        turn.reply_started = now
                        if self._user_spoke_at is not None:
                            log.info("kai started replying %.2fs after the user's last words",
                                     now - self._user_spoke_at)
                            self._user_spoke_at = None
                        else:
                            log.info("kai started speaking on its own")
                    turn.audio_seconds += len(part.inline_data.data) / (audio.OUT_RATE * 2)
                    self._speaker.play(part.inline_data.data)
        if sc.input_transcription and sc.input_transcription.text:
            self._stats["heard"] += 1
            if turn.user_first is None:
                turn.user_first = now
                log.info("Server is hearing the user")
            turn.user_last = self._user_spoke_at = now
            turn.user_chars += len(sc.input_transcription.text)
            self.user_said.emit(sc.input_transcription.text)
            transcript.said("user", sc.input_transcription.text)
            self._silent_tools = 0
            self._set_state(State.THINKING)
        if sc.output_transcription and sc.output_transcription.text:
            turn.kai_chars += len(sc.output_transcription.text)
            self.kai_said.emit(sc.output_transcription.text)
            transcript.said("kai", sc.output_transcription.text)
            self._silent_tools = 0
        if sc.generation_complete:
            log.debug("Generation complete")
        if sc.waiting_for_input:
            log.debug("Server waiting for input")
        if sc.turn_complete:
            log.info("Turn complete (reason: %s): user %d chars, kai %d chars, %.1fs of audio",
                     sc.turn_complete_reason or "-", turn.user_chars, turn.kai_chars,
                     turn.audio_seconds)
            self._turn = _Turn()
            transcript.turn_done()
            self.turn_done.emit()
            if not self._speaker.is_playing:
                self._set_state(State.LISTENING)

    async def _handle_tool_call(self, s, tool_call: types.LiveServerToolCall) -> None:
        self._set_state(State.THINKING)
        responses = []
        for fc in tool_call.function_calls or []:
            args = dict(fc.args or {})
            if self._silent_tools >= MAX_SILENT_RUN:
                log.info("Tool %s refused: %d tool calls without speaking", fc.name,
                         self._silent_tools)
                result = {"error": "Stopped: you have taken too many actions without talking. "
                                   "Tell the user what you see and what is blocking you, and "
                                   "ask how to go on. No more tools until you have spoken."}
                transcript.tool(fc.name, args, result)
                responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response=result))
                continue
            self.tool_used.emit(fc.name, args)
            started = time.monotonic()
            log.debug("Tool %s started", fc.name)
            result = await asyncio.to_thread(tools.call, fc.name, args, self._confirm,
                                             self._permission)
            if tools.is_ui_action(fc.name):
                self.ui_action.emit(fc.name)
            log.info("Tool %s: %s in %.2fs", fc.name, "error" if "error" in result else "ok",
                     time.monotonic() - started)
            image = result.pop(tools.IMAGE_KEY, None)
            self._silent_tools += 1
            if self._silent_tools == LONG_RUN:
                log.info("%d tool calls in a row without speaking", self._silent_tools)
                result["note"] = (f"You have used {self._silent_tools} tools in a row without "
                                  "speaking. Briefly tell the user what you are doing or what "
                                  "is blocking you, and ask before going on if it isn't working.")
            transcript.tool(fc.name, args, result)
            if fc.name == "click" and "error" not in result:
                transcript.shot(screen.last_jpeg(), "click", (args.get("x", 0), args.get("y", 0)))
            elif image:
                transcript.shot(image, fc.name)
            parts = None
            if image:
                parts = [types.FunctionResponsePart(inline_data=types.FunctionResponseBlob(
                    data=image, mime_type="image/jpeg"))]
                log.debug("Tool %s attached a %d KB image", fc.name, len(image) // 1024)
            responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response=result,
                                                    parts=parts))
        if responses:
            await s.send_tool_response(function_responses=responses)
