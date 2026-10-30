from kai import config, voices


def test_accent_instruction():
    assert voices.accent_instruction("auto") == ""
    assert "Argentina" in voices.accent_instruction("es-AR")
    assert voices.accent_instruction("custom", "  soft Galician  ").endswith("soft Galician")
    assert voices.accent_instruction("custom", "") == ""


def test_voices_are_unique():
    names = [n for n, _ in voices.VOICES]
    assert len(names) == len(set(names)) == 30


def test_settings_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path)
    assert config.load_settings() == config.DEFAULT_SETTINGS
    config.save_settings({**config.DEFAULT_SETTINGS, "voice": "Kore", "accent": "es-ES"})
    assert config.load_settings()["voice"] == "Kore"
