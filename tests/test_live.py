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
