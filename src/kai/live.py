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

from google import genai
from google.genai import errors, types
from PySide6.QtCore import QObject, Signal

from kai import tools
from kai import audio
from kai.audio import IN_RATE, Microphone, Speaker
from kai.config import MODEL

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are kai, a calm and concise voice assistant that helps the user manage their computer.
- Always answer in the language the user speaks to you.
- Keep spoken answers short; offer details only if asked.
- Use your tools to inspect or act on the computer instead of guessing.
- Never claim you did something on the computer unless a tool confirmed it.
- You can do much more than your specific tools: for anything they don't cover
  (settings, network, installed software, moving or renaming files, etc.) use run_command
  with a command for the user's operating system. Don't tell the user you can't do
  something on the computer before considering run_command.
- To work inside an app (write in Notepad, open a new tab, save…): open it with open_app,
  then use type_text and press_keys passing the window title (list_windows shows them).
  Never simulate the keyboard through run_command: those commands run hidden and can't
  reach the user's windows. If a step fails, check list_windows instead of retrying blindly.
- Depending on the user's permission level, some actions show a confirmation window.
  If a tool result says the user declined, accept it and don't insist.
- Prefer read-only commands to look before changing anything. Never run destructive
  commands (deleting, formatting, uninstalling) unless the user explicitly asked for it.

About the kai app itself, so you can help the user with it:
- kai is a desktop app for Linux, Windows and macOS: a slim floating bar above the taskbar
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
  The window can be moved by dragging it.
- kai uses Google's Gemini 3.8 Live with the user's own free API key from Google AI Studio,
  stored in the system keychain. On the free tier Google may use conversations to improve
  its products; enabling billing on the key opts out.
- kai does not store conversations: its log files only contain technical events.
- If the user reports a problem with kai, offer to open the diagnostics window with the
  open_diagnostics tool. It shows the report and only uploads it if the user clicks Send.
  The user then gets a short reference to share with the developer.
- Website: ccmai.org/kai. Source code: github.com/ccarrillomanzanares/kai.
"""

MAX_BACKOFF = 30
CONFIRM_TIMEOUT = 120  # seconds before an unanswered confirmation counts as declined
HEARTBEAT_SECONDS = 60  # how often the log records the health of the session


class State:
    OFFLINE = "offline"
    CONNECTING = "connecting"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"


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
                 accent_instruction: str = ""):
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
        self._mic = Microphone(on_chunk=self._on_mic_chunk)
        self._audio_ok = False
        # Content-free counters for the heartbeat log line.
        self._stats = {"sent": 0, "gated": 0, "muted": 0, "peak": 0.0, "msgs": 0, "heard": 0}
        self._last_server_msg = time.monotonic()

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
        if self._loop and self._session:
            asyncio.run_coroutine_threadsafe(
                self._session.send_realtime_input(text=text), self._loop
            )

    def set_mic_enabled(self, enabled: bool) -> None:
        self._mic_enabled = enabled

    def set_permission_level(self, level: tools.Permission) -> None:
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
        try:
            self.confirm_requested.emit(request_id, title, detail)
            approved = event.wait(CONFIRM_TIMEOUT) and bool(answer) and answer[0]
            approved = approved and not self._stopping
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
            self._state = state
            self.state_changed.emit(state)

    def _thread_main(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._audio_q = asyncio.Queue(maxsize=200)
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
                     mic_name, out_name, self._full_duplex)
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
            if now - last_beat >= HEARTBEAT_SECONDS:
                st = self._stats
                log.info(
                    "Heartbeat: state=%s connected=%s mic_sent=%d mic_gated=%d mic_muted=%d "
                    "mic_peak=%.2f speaker_buffer=%.1fs server_msgs=%d speech_heard=%d "
                    "last_server_msg=%.0fs ago",
                    self._state, self._session is not None, st["sent"], st["gated"],
                    st["muted"], st["peak"], self._speaker.buffered_seconds, st["msgs"],
                    st["heard"], now - self._last_server_msg)
                self._stats = dict.fromkeys(st, 0) | {"peak": 0.0}
                last_beat = now

    async def _reconnect_loop(self, client: genai.Client) -> None:
        handle: str | None = None
        backoff = 1
        while not self._stopping:
            self._set_state(State.CONNECTING)
            try:
                async with client.aio.live.connect(model=MODEL, config=self._config(handle)) as s:
                    self._session = s
                    log.info("Connected to %s (resumed: %s)", MODEL, handle is not None)
                    self._set_state(State.LISTENING)
                    backoff = 1
                    handle = await self._serve(s, handle)
            except errors.APIError as e:
                detail = e.message or str(e)
                log.warning("Live API error %s: %s", e.code, detail)
                if e.code in (1008, 400, 401, 403):
                    self.fatal_error.emit(detail or "Google rejected the API key.")
                    return
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
            if not self._stopping:
                self._set_state(State.CONNECTING)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)

    async def _serve(self, s, handle: str | None) -> str | None:
        """Run one connection until it closes. Returns the latest resumption handle."""
        sender = asyncio.create_task(self._pump_audio(s))
        tool_tasks: set[asyncio.Task] = set()
        try:
            while True:
                async for msg in s.receive():
                    self._stats["msgs"] += 1
                    self._last_server_msg = time.monotonic()
                    if msg.session_resumption_update and msg.session_resumption_update.new_handle:
                        handle = msg.session_resumption_update.new_handle
                    if msg.go_away:
                        log.info("Server asked to reconnect (time left: %s)", msg.go_away.time_left)
                        return handle
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
        if sc.interrupted:
            self._speaker.clear()
        if sc.model_turn:
            for part in sc.model_turn.parts or []:
                if part.inline_data and part.inline_data.data:
                    self._speaker.play(part.inline_data.data)
        if sc.input_transcription and sc.input_transcription.text:
            self._stats["heard"] += 1
            self.user_said.emit(sc.input_transcription.text)
            self._set_state(State.THINKING)
        if sc.output_transcription and sc.output_transcription.text:
            self.kai_said.emit(sc.output_transcription.text)
        if sc.turn_complete:
            self.turn_done.emit()
            if not self._speaker.is_playing:
                self._set_state(State.LISTENING)

    async def _handle_tool_call(self, s, tool_call: types.LiveServerToolCall) -> None:
        self._set_state(State.THINKING)
        responses = []
        for fc in tool_call.function_calls or []:
            args = dict(fc.args or {})
            self.tool_used.emit(fc.name, args)
            result = await asyncio.to_thread(tools.call, fc.name, args, self._confirm,
                                             self._permission)
            if tools.is_ui_action(fc.name):
                self.ui_action.emit(fc.name)
            log.info("Tool %s: %s", fc.name, "error" if "error" in result else "ok")
            responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response=result))
        if responses:
            await s.send_tool_response(function_responses=responses)
