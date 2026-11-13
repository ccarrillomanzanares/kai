import asyncio
import time

from kai import live


def test_watchdog_reconnects_when_server_ignores_speech(monkeypatch):
    agent = live.LiveAgent("key", full_duplex=True)
    agent._audio_ok = False  # no audio devices in tests

    async def scenario():
        agent._reconnect_now = asyncio.Event()
        agent._session = object()
        agent._last_server_msg = time.monotonic() - live.STUCK_SILENCE_SECONDS - 1
        agent._voiced_since_msg = live.STUCK_VOICED_CHUNKS
        task = asyncio.create_task(agent._watchdog())
        await asyncio.wait_for(agent._reconnect_now.wait(), timeout=3)
        task.cancel()

    asyncio.run(scenario())
    assert agent._voiced_since_msg == 0


def test_watchdog_leaves_quiet_sessions_alone():
    agent = live.LiveAgent("key", full_duplex=True)
    agent._audio_ok = False

    async def scenario():
        agent._reconnect_now = asyncio.Event()
        agent._session = object()
        agent._last_server_msg = time.monotonic() - 120  # long silence, but nobody spoke
        agent._voiced_since_msg = 3
        task = asyncio.create_task(agent._watchdog())
        await asyncio.sleep(1.5)
        task.cancel()
        return agent._reconnect_now.is_set()

    assert asyncio.run(scenario()) is False


def test_long_silent_tool_runs_are_nudged_then_stopped(monkeypatch):
    from google.genai import types

    agent = live.LiveAgent("key", full_duplex=True)
    calls, sent = [], []
    monkeypatch.setattr(live.tools, "call",
                        lambda name, args, *a: calls.append(name) or {"result": "ok"})

    class Session:
        async def send_tool_response(self, function_responses):
            sent.extend(function_responses)

    def tool_call():
        return types.LiveServerToolCall(function_calls=[
            types.FunctionCall(id="1", name="get_datetime", args={})])

    async def scenario():
        for _ in range(live.MAX_SILENT_RUN + 2):
            await agent._handle_tool_call(Session(), tool_call())

    asyncio.run(scenario())
    assert len(calls) == live.MAX_SILENT_RUN  # the rest were refused without running
    assert "note" in sent[live.LONG_RUN - 1].response
    assert "Stopped" in sent[-1].response["error"]
    agent._silent_tools = 0  # speaking resets the count


def test_only_key_errors_are_fatal():
    assert live._is_key_problem(1008, "API key not valid. Please pass a valid API key.")
    assert live._is_key_problem(403, "")
    assert not live._is_key_problem(1008, "Requested entity already exists")
    assert not live._is_key_problem(1011, "Internal error")


def test_expired_session_is_not_a_key_problem():
    from kai.live import _is_key_problem
    assert not _is_key_problem(1008, "BidiGenerateContent session not found or expired")


def test_quota_errors_keep_the_session_and_stay_quiet_at_first(monkeypatch):
    from google.genai import errors

    agent = live.LiveAgent("key", full_duplex=True)
    agent._handle = "handle"
    shown, waits = [], []
    agent.error.connect(shown.append)

    class Connect:
        async def __aenter__(self):
            if len(waits) == 2:
                agent._stopping = True
            raise errors.APIError(1011, "Resource has been exhausted (e.g. check quota).")

        async def __aexit__(self, *exc):
            return False

    class Client:
        class aio:
            class live:
                connect = staticmethod(lambda **kw: Connect())

    async def no_sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr(live.asyncio, "sleep", no_sleep)
    asyncio.run(agent._reconnect_loop(Client()))
    assert agent._handle == "handle"  # the conversation can still be resumed
    assert waits == [live.QUOTA_FIRST_RETRY, live.MAX_BACKOFF]
    assert len(shown) == 2 and all("quota" in m for m in shown)  # none for the first error
