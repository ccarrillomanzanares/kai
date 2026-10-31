"""Screenshots, mouse coordinates, accessibility listing and image tool results."""

import pytest

from kai import tools
from kai.tools import browser, screen, uia


def test_image_results_carry_the_jpeg_apart(monkeypatch):
    fake = screen.Image(b"\xff\xd8jpeg", "Screenshot attached.")
    tool = tools.TOOLS["look_at_screen"]
    monkeypatch.setitem(tools.TOOLS, "look_at_screen",
                        tools.Tool(tool.name, tool.description, tool.parameters,
                                   lambda window=None: fake, tools.Risk.READ))
    result = tools.call("look_at_screen", {})
    assert result == {"result": "Screenshot attached.", tools.IMAGE_KEY: b"\xff\xd8jpeg"}


def test_click_needs_a_screenshot_first(monkeypatch):
    monkeypatch.setattr(screen, "_last_region", None)
    with pytest.raises(RuntimeError):
        screen._to_screen(500, 500)


def test_click_maps_normalized_points_to_the_captured_region(monkeypatch):
    monkeypatch.setattr(screen, "_last_region", (1920, 0, 1001, 501))  # second monitor
    assert screen._to_screen(0, 0) == (1920, 0)
    assert screen._to_screen(1000, 1000) == (2920, 500)
    assert screen._to_screen(500, 500) == (2420, 250)
    with pytest.raises(ValueError):
        screen._to_screen(1200, 10)


def test_to_jpeg_downscales():
    from PIL import Image

    jpeg = screen.to_jpeg(Image.new("RGB", (3840, 2160), "white"))
    assert jpeg[:2] == b"\xff\xd8"
    assert max(Image.open(__import__("io").BytesIO(jpeg)).size) == screen.MAX_SIDE


def test_click_element_uses_the_element_center(monkeypatch):
    clicks = []
    monkeypatch.setattr(uia, "_last", {1: uia.Element("button", "Guardar", (100, 200, 80, 30))})
    monkeypatch.setattr(uia, "_last_window", "Bloc de notas")
    monkeypatch.setattr(uia.desktop, "focus_window", lambda title: f"Focused '{title}'")
    monkeypatch.setattr(screen, "click_point", lambda x, y, b="left", d=False: clicks.append((x, y)))
    assert "Guardar" in uia.click_element(1)
    assert clicks == [(140, 215)]
    assert uia.describe(1) == "button \"Guardar\" in 'Bloc de notas'"
    with pytest.raises(LookupError):
        uia.click_element(7)


def test_element_description():
    e = uia.Element("field", "Search", (0, 0, 10, 10), value="otters", enabled=False)
    assert e.describe() == "field \"Search\" = 'otters' [disabled]"


def test_browser_describe_falls_back_to_number(monkeypatch):
    monkeypatch.setattr(browser, "_described", {3: 'link "News"'})
    assert browser.describe(3) == 'link "News"'
    assert browser.describe(9) == "element 9"


def test_reading_tools_never_ask(monkeypatch):
    for name in ("read_window", "browser_read", "browser_scroll", "browser_screenshot"):
        tool = tools.TOOLS[name]
        assert not tools.needs_confirmation(tool, {}, tools.Permission.STRICT)
    # Screenshots go to Google: "Ask for everything" asks first.
    assert tools.needs_confirmation(tools.TOOLS["look_at_screen"], {}, tools.Permission.STRICT)
    assert not tools.needs_confirmation(tools.TOOLS["look_at_screen"], {},
                                        tools.Permission.BALANCED)
