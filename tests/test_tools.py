import pytest

from kai import config, tools
from kai.tools import system


def test_declarations_cover_all_tools():
    names = {d.name for d in tools.declarations()[0].function_declarations}
    assert names == set(tools.TOOLS)


def test_call_unknown_tool():
    assert "error" in tools.call("nope", {})


def test_call_wraps_errors():
    assert "error" in tools.call("open_url", {"url": "file:///etc/passwd"})


def test_get_datetime():
    assert "iso" in tools.call("get_datetime", None)["result"]


def test_get_system_info():
    info = system.get_system_info()
    assert info["cpu_count"] >= 1
    assert 0 <= info["memory_percent"] <= 100


@pytest.mark.parametrize(
    "key, ok",
    [("", False), ("short", False), ("A" * 39, True), ("has a space " + "A" * 30, False)],
)
def test_looks_like_api_key(key, ok):
    assert config.looks_like_api_key(key) is ok
