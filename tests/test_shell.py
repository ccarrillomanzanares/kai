import re

import psutil


def test_long_command_is_left_running():
    from kai.tools import shell

    # The default wait leaves room for the shell to start: PowerShell alone takes about a second.
    r = shell.run_command("echo started; sleep 30", background=True)
    try:
        assert r["exit_code"] is None
        assert "started" in r["stdout"] and "left running" in r["note"]
    finally:  # don't leave it running after the test
        for pid in re.findall(r"process (\d+)", r.get("note", "")):
            try:
                shell_proc = psutil.Process(int(pid))
                for p in [*shell_proc.children(recursive=True), shell_proc]:
                    p.kill()
            except psutil.Error:
                pass
