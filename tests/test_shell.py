

def test_long_command_is_left_running(monkeypatch):
    from kai.tools import shell
    monkeypatch.setattr(shell, "BACKGROUND_WAIT", 1)
    r = shell.run_command("echo started; sleep 20", background=True)
    assert r["exit_code"] is None and "started" in r["stdout"] and "left running" in r["note"]
