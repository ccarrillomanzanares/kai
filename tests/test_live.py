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
