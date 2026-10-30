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


def test_open_diagnostics_is_a_ui_action():
    assert tools.is_ui_action("open_diagnostics")
    assert not tools.is_ui_action("open_url")
    assert "Send" in tools.call("open_diagnostics", {})["result"]


def test_list_directory_and_search(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "Report-2026.pdf").write_text("x")
    listing = tools.call("list_directory", {"path": str(tmp_path)})["result"]
    assert [e["name"] for e in listing["entries"]] == ["sub", "Report-2026.pdf"]
    found = tools.call("search_files", {"pattern": "report", "folder": str(tmp_path)})["result"]
    assert found["complete"] and found["matches"][0].endswith("Report-2026.pdf")
    found = tools.call("search_files", {"pattern": "*.pdf", "folder": str(tmp_path)})["result"]
    assert len(found["matches"]) == 1


def test_sensitive_tools_need_confirmation():
    asked = []
    approve = lambda title, detail: asked.append((title, detail)) or True  # noqa: E731
    out = tools.call("run_command", {"command": "echo kai", "reason": "Test"}, approve)
    assert asked == [("Test", "echo kai")]
    assert out["result"]["exit_code"] == 0 and "kai" in out["result"]["stdout"]

    assert tools.call("run_command", {"command": "echo kai", "reason": "x"}, lambda *_: False) == {
        "error": "The user declined this action."
    }
    assert "error" in tools.call("run_command", {"command": "echo kai", "reason": "x"})


def test_list_processes():
    procs = tools.call("list_processes", {"sort_by": "cpu", "limit": 3})["result"]
    assert 1 <= len(procs) <= 3 and {"pid", "name", "memory_mb", "cpu_percent"} <= procs[0].keys()
