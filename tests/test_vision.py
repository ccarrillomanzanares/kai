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


def test_disabled_elements_are_not_clicked(monkeypatch):
    monkeypatch.setattr(uia, "_last", {1: uia.Element("button", "Send", (0, 0, 10, 10),
                                                      enabled=False)})
    with pytest.raises(ValueError, match="disabled"):
        uia.click_element(1)


def test_buttons_are_pressed_without_the_mouse(monkeypatch):
    pressed = []

    class Handle:
        def GetInvokePattern(self):
            return type("P", (), {"Invoke": lambda s: pressed.append(True)})()

    monkeypatch.setattr(uia.sys, "platform", "win32")
    monkeypatch.setattr(uia, "_uia_init", lambda: None)
    monkeypatch.setattr(uia, "_uia_executor", None)
    monkeypatch.setattr(uia, "_last", {1: uia.Element("button", "Guardar", (0, 0, 10, 10),
                                                      handle=Handle())})
    monkeypatch.setattr(uia, "_last_window", "Guardar como")
    monkeypatch.setattr(uia.desktop, "focus_window", lambda t: "")
    monkeypatch.setattr(screen, "click_point", lambda *a: pytest.fail("used the mouse"))
    assert uia.click_element(1).startswith("Pressed")
    assert pressed == [True]


def test_a_press_that_opens_a_modal_is_not_repeated(monkeypatch):
    import threading

    release = threading.Event()

    class Handle:
        def GetInvokePattern(self):
            return type("P", (), {"Invoke": lambda s: release.wait(5)})()

    monkeypatch.setattr(uia.sys, "platform", "win32")
    monkeypatch.setattr(uia, "_uia_init", lambda: None)
    monkeypatch.setattr(uia, "_uia_executor", None)
    monkeypatch.setattr(uia, "PRESS_WAIT", 0.2)
    monkeypatch.setattr(uia, "_last", {1: uia.Element("button", "Descartar todo", (0, 0, 9, 9),
                                                      handle=Handle())})
    monkeypatch.setattr(uia, "_last_window", "Recuperación")
    monkeypatch.setattr(uia.desktop, "focus_window", lambda t: "")
    monkeypatch.setattr(screen, "click_point", lambda *a: pytest.fail("clicked again"))
    try:
        assert "waiting for an answer" in uia.click_element(1)
        assert uia._uia_executor is None and uia._last == {}  # fresh thread for what's next
    finally:
        release.set()


def test_fill_field_refuses_buttons(monkeypatch):
    monkeypatch.setattr(uia, "_last", {15: uia.Element("button", "Añadir imágenes", (0, 0, 9, 9))})
    with pytest.raises(ValueError, match="not a text field"):
        uia.fill_field(15, "hola")


def test_same_click_twice_is_refused_once(monkeypatch):
    from kai.tools import screen, uia
    monkeypatch.setattr(screen, "_last_region", (0, 0, 1000, 1000))
    monkeypatch.setattr(screen, "_last_click", None)
    monkeypatch.setattr(screen, "click_point", lambda *a, **k: None)
    monkeypatch.setattr(uia, "describe_point", lambda px, py: "TitleBar")
    assert screen.click(250, 20).startswith("Clicked")
    with pytest.raises(RuntimeError, match="Repeating"):
        screen.click(252, 22)
    assert screen.click(250, 20).startswith("Clicked")  # deliberate retry goes through
    assert screen.click(600, 500).startswith("Clicked")
