from kai import diag, logs, transcript

FAKE_KEY = "AIza" + "S" * 35


def _use_tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(logs, "log_file", lambda: tmp_path / "kai.log")


def test_disabled_records_nothing(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    transcript.set_enabled(False)
    transcript.said("user", "hello")
    transcript.turn_done()
    transcript.tool("open_url", {"url": "https://x"}, {"result": "ok"})
    assert not transcript.path().exists()
    assert "conversation" not in diag.collect(include_conversation=True)


def test_records_turns_and_tools(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    transcript.set_enabled(True)
    try:
        transcript.said("user", "open ")
        transcript.said("user", "the news")
        transcript.tool("open_url", {"url": f"https://x/?key={FAKE_KEY}"}, {"result": "x" * 1000})
        transcript.said("kai", "Done.")
        transcript.turn_done()
        text = transcript.path().read_text(encoding="utf-8")
        assert "user: open the news" in text
        assert "kai: Done." in text
        assert "tool open_url(" in text and "(1014 chars)" in text
        assert FAKE_KEY not in text
        assert "conversation" not in diag.collect()
        assert "open the news" in diag.collect(include_conversation=True)["conversation"]
    finally:
        transcript.set_enabled(False)
    assert not transcript.path().exists()  # turning it off deletes the recording
