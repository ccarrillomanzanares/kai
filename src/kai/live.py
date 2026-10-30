"""The Gemini Live session: streams audio in and out, handles tool calls,
and reconnects transparently using session resumption.

The session runs on its own asyncio loop in a background thread and talks to
the UI only through Qt signals.
"""

from __future__ import annotations

import asyncio
import logging
import threading

from google import genai
from google.genai import errors, types
from PySide6.QtCore import QObject, Signal

from kai import tools
from kai.audio import IN_RATE, Microphone, Speaker
from kai.config import MODEL

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are kai, a calm and concise voice assistant that helps the user manage their computer.
- Always answer in the language the user speaks to you.
- Keep spoken answers short; offer details only if asked.
- Use your tools to inspect or act on the computer instead of guessing.
- Never claim you did something on the computer unless a tool confirmed it.
"""

MAX_BACKOFF = 30


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

    def __init__(self, api_key: str, full_duplex: bool = False):
        super().__init__()
        self._api_key = api_key
        self._full_duplex = full_duplex  # True when the user wears headphones
        self._mic_enabled = True
        self._loop: asyncio.AbstractEventLoop | None = None
        self._main: asyncio.Task | None = None
        self._thread: threading.Thread | None = None
        self._audio_q: asyncio.Queue[bytes] | None = None
        self._session = None
        self._stopping = False
        self._state = State.OFFLINE
        self._speaker = Speaker(on_level=self._on_speaker_level)
        self._mic = Microphone(on_chunk=self._on_mic_chunk)

    # ---- public API (call from the UI thread) ----

    def start(self) -> None:
        self._stopping = False
        self._thread = threading.Thread(target=self._thread_main, name="kai-live", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopping = True
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

    # ---- audio callbacks (audio threads) ----

    def _on_mic_chunk(self, pcm: bytes, level: float) -> None:
        if not self._mic_enabled or self._audio_q is None or self._loop is None:
            return
        # Without headphones the speaker leaks into the mic and kai would
        # interrupt itself, so we only listen while it is quiet.
        if not self._full_duplex and self._speaker.is_playing:
            return
        if self._state == State.LISTENING:
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
            system_instruction=SYSTEM_PROMPT,
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
        try:
            self._speaker.start()
            self._mic.start()
        except Exception as e:  # no PortAudio or no devices: keep working as text chat
            log.warning("Audio unavailable: %s", e)
            self.error.emit("No audio device found, text only.")
        try:
            await self._reconnect_loop(client)
        finally:
            await client.aio.aclose()

    async def _reconnect_loop(self, client: genai.Client) -> None:
        handle: str | None = None
        backoff = 1
        while not self._stopping:
            self._set_state(State.CONNECTING)
            try:
                async with client.aio.live.connect(model=MODEL, config=self._config(handle)) as s:
                    self._session = s
                    self._set_state(State.LISTENING)
                    backoff = 1
                    handle = await self._serve(s, handle)
            except errors.APIError as e:
                detail = e.message or str(e)
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
        try:
            while True:
                async for msg in s.receive():
                    if msg.session_resumption_update and msg.session_resumption_update.new_handle:
                        handle = msg.session_resumption_update.new_handle
                    if msg.go_away:
                        log.info("Server asked to reconnect (time left: %s)", msg.go_away.time_left)
                        return handle
                    if msg.tool_call:
                        await self._handle_tool_call(s, msg.tool_call)
                    if msg.server_content:
                        self._handle_content(msg.server_content)
        finally:
            sender.cancel()

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
            result = await asyncio.to_thread(tools.call, fc.name, args)
            responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response=result))
        if responses:
            await s.send_tool_response(function_responses=responses)
