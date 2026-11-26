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


QUOTA_NOTICE = "Free-tier quota reached. Retrying shortly…"


def _quota_error():
    from google.genai import errors
    return errors.APIError(1011, "Resource has been exhausted (e.g. check quota).")


def _internal_error():
    from google.genai import errors
    return errors.APIError(1011, "Internal error")


def _run_reconnects(monkeypatch, connections, handle="handle"):
    """Drive the reconnect loop through one connection per item and stop at the last one.

    Each item says how that connection ends: ("open", error) fails to connect;
    ("serve", seconds, error) connects, lasts that long and then fails, or with None
    as the error ends well, resumed on a new connection. Time is a fake clock that the
    connections and the waits move forward.
    Returns the agent, the waits between attempts, the notices shown and the handle
    each connection was opened with.
    """
    agent = live.LiveAgent("key", full_duplex=True)
    agent._handle = handle
    clock = [1000.0]
    waits, shown, handles = [], [], []
    agent.error.connect(shown.append)
    plan = iter(connections)
    current = []

    class Connect:
        async def __aenter__(self):
            handles.append(agent._handle)
            current[:] = [next(plan)]
            if len(handles) == len(connections):
                agent._stopping = True
            if current[0][0] == "open":
                raise current[0][1]
            return object()

        async def __aexit__(self, *exc):
            return False

    class Client:
        class aio:
            class live:
                connect = staticmethod(lambda **kw: Connect())

    async def serve(session):
        _, seconds, error = current[0]
        clock[0] += seconds
        if error:
            raise error
        return True

    async def no_sleep(seconds):
        waits.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(live.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(live.transcript, "note", lambda text: None)
    monkeypatch.setattr(agent, "_serve_until_reconnect", serve)
    monkeypatch.setattr(live.asyncio, "sleep", no_sleep)

    async def bounded():  # a loop that waits some other way fails here instead of hanging
        await asyncio.wait_for(agent._reconnect_loop(Client()), timeout=10)

    asyncio.run(bounded())
    return agent, waits, shown, handles


def test_quota_errors_keep_the_session_and_stay_quiet_at_first(monkeypatch):
    agent, waits, shown, _ = _run_reconnects(
        monkeypatch, [("open", _quota_error())] * 3)
    assert agent._handle == "handle"  # the conversation can still be resumed
    assert waits == [live.QUOTA_FIRST_RETRY, live.MAX_BACKOFF]
    assert shown == [QUOTA_NOTICE] * 2  # for the second and third errors, not the first


def test_quota_errors_after_connecting_are_announced_too(monkeypatch):
    # Google accepts the connection and closes it at once: still the same quota problem.
    agent, waits, shown, _ = _run_reconnects(
        monkeypatch, [("serve", 1, _quota_error())] * 3)
    assert agent._handle == "handle"
    assert waits == [live.QUOTA_FIRST_RETRY, live.MAX_BACKOFF]
    assert shown == [QUOTA_NOTICE] * 2


def test_a_connection_that_held_starts_the_quota_count_again(monkeypatch):
    _, waits, shown, _ = _run_reconnects(
        monkeypatch, [("open", _quota_error()), ("serve", 300, _quota_error()),
                      ("open", _quota_error())])
    assert waits == [live.QUOTA_FIRST_RETRY, live.QUOTA_FIRST_RETRY]
    assert shown == [QUOTA_NOTICE]  # only for the last one, the second in a row


def test_a_connection_refused_with_http_429_is_a_quota_error(monkeypatch):
    from websockets.datastructures import Headers
    from websockets.exceptions import InvalidStatus
    from websockets.http11 import Response

    def refused():
        return InvalidStatus(Response(429, "Too Many Requests", Headers()))

    agent, waits, shown, _ = _run_reconnects(monkeypatch, [("open", refused())] * 3)
    assert agent._handle == "handle"
    assert waits == [live.QUOTA_FIRST_RETRY, live.MAX_BACKOFF]
    assert shown == [QUOTA_NOTICE] * 2


def test_a_session_that_only_gets_quota_errors_is_given_up_in_the_end(monkeypatch):
    tries = live.QUOTA_HANDLE_TRIES
    agent, _, _, handles = _run_reconnects(
        monkeypatch, [("open", _quota_error())] * (tries + 1))
    assert handles == ["handle"] * tries + [None]


def test_two_quick_errors_drop_the_old_session(monkeypatch):
    _, _, _, handles = _run_reconnects(
        monkeypatch, [("serve", 100, _internal_error()), ("open", _internal_error()),
                      ("open", _internal_error())])
    assert handles == ["handle", "handle", None]


def test_an_error_from_long_ago_does_not_count_against_the_session(monkeypatch):
    agent, _, _, _ = _run_reconnects(
        monkeypatch, [("serve", 100, _internal_error()), ("serve", 3600, None),
                      ("serve", 3600, None), ("open", _internal_error())])
    assert agent._handle == "handle"
