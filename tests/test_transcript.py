from kai import diag, logs, transcript

FAKE_KEY = "AIza" + "S" * 35


def _use_tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(logs, "log_file", lambda: tmp_path / "kai.log")
    transcript.clear_session()


def test_this_run_is_kept_in_memory_only(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    transcript.set_enabled(False)
    assert not diag.has_conversation()
    assert "conversation" not in diag.collect(include_conversation=True)
    transcript.typed(f"hello {FAKE_KEY}")
    transcript.said("kai", "Hi there.")
    transcript.turn_done()
    transcript.tool("open_url", {"url": "https://x"}, {"result": "ok"})
    assert not transcript.path().exists()
    assert "conversation" not in diag.collect()
    report = diag.collect(include_conversation=True)
    assert "user (typed): hello" in report["conversation"]
    assert "kai: Hi there." in report["conversation"]
    assert "tool open_url(" in report["conversation"]
    assert FAKE_KEY not in report["conversation"]
    assert report["conversation_status"]["source"] == "this run"


def test_old_recording_is_not_sent_while_recording_is_off(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    transcript.set_enabled(False)
    transcript.path().write_text("2026-01-01 00:00:00 user: something old\n", encoding="utf-8")
    assert not diag.has_conversation()
    assert "conversation" not in diag.collect(include_conversation=True)
    # From the terminal there is no run: the recording is what was asked for.
    assert "something old" in diag.collect(include_conversation=True, stored=True)["conversation"]
    transcript.said("user", "something new")
    transcript.turn_done()
    report = diag.collect(include_conversation=True)
    assert "something new" in report["conversation"]
    assert "something old" not in report["conversation"]


def test_session_is_capped(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    monkeypatch.setattr(transcript, "MAX_SESSION_CHARS", 500)
    for i in range(100):
        transcript.note(f"line {i}")
    text = transcript.read_session()
    assert len(text) < 700 and "line 99" in text and "line 0\n" not in text


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
    assert transcript.path().exists()  # stopping keeps it, e.g. to send it later
    transcript.delete()
    assert not transcript.path().exists()


def test_screenshots_are_kept_marked_and_capped(monkeypatch, tmp_path):
    import io

    from PIL import Image

    _use_tmp(monkeypatch, tmp_path)
    buf = io.BytesIO()
    Image.new("RGB", (1280, 720), "white").save(buf, "JPEG")
    transcript.set_enabled(True)
    try:
        for i in range(transcript.MAX_SHOTS + 3):
            transcript.shot(buf.getvalue(), "click", (500, 500))
        shots = transcript.read_shots()
        assert len(shots) == transcript.MAX_SHOTS
        img = Image.open(transcript.shots_dir() / sorted(shots)[-1]).convert("RGB")
        assert max(img.size) == transcript.SHOT_SIDE
        cx, cy = img.width // 2, img.height // 2
        around = [img.getpixel((cx + dx, cy + dy)) for dx in range(-10, 11) for dy in range(-10, 11)]
        assert any(r > 150 and g < 100 and b < 100 for r, g, b in around)  # the red click mark
        assert len(diag.collect(include_conversation=True)["screenshots"]) == transcript.MAX_SHOTS
    finally:
        transcript.set_enabled(False)
        transcript.delete()
    assert transcript.read_shots() == {}
    # Without recording, this run's screenshots are still there, from memory.
    assert len(diag.collect(include_conversation=True)["screenshots"]) == transcript.MAX_SHOTS
