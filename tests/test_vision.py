"""Screenshots, mouse coordinates, accessibility listing and image tool results."""

import sys
import types
from types import SimpleNamespace as NS

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


class Node:
    """An accessible object as AT-SPI hands them out, for a made-up window."""

    def __init__(self, role, name="", children=(), showing=True, text=None):
        self.role, self.name, self.children, self.showing = role, name, list(children), showing
        self.text = text  # None: it has no text of its own to hand over

    def get_role_name(self):
        return self.role

    def get_name(self):
        return self.name

    def get_child_count(self):
        return len(self.children)

    def get_child_at_index(self, index):
        return self.children[index]

    def get_state_set(self):
        return NS(contains=lambda state: self.showing or state != "showing")

    def get_extents(self, coords):
        return NS(x=10, y=20, width=640, height=480)


def linux_desktop(monkeypatch, *windows):
    """Make uia read these windows as if AT-SPI listed them on a Linux desktop."""
    desktop = Node("desktop frame", children=[Node("application", "app", windows)])
    monkeypatch.setattr(uia.sys, "platform", "linux")
    monkeypatch.setattr(uia, "_last", {})
    monkeypatch.setattr(uia, "_last_window", "")
    monkeypatch.setattr(uia, "_atspi", lambda: NS(
        get_desktop=lambda index: desktop, CoordType=NS(SCREEN="screen"),
        StateType=NS(SHOWING="showing", SENSITIVE="sensitive"),
        Text=NS(get_character_count=lambda node: len(node.text),
                get_text=lambda node, start, end: node.text[start:end])))


@pytest.mark.parametrize("terminal_first", [True, False])  # AT-SPI lists them in either order
def test_linux_window_titles_match_exactly_before_ignoring_case(monkeypatch, terminal_first):
    windows = [Node("frame", "claude", [Node("menu", "Terminal")]),
               Node("frame", "Claude", [Node("push button", "New chat")])]
    linux_desktop(monkeypatch, *(windows if terminal_first else reversed(windows)))

    assert uia.read_window("claude").splitlines()[1:] == ['1 menu "Terminal"']
    assert uia.describe(1) == "menu \"Terminal\" in 'claude'"
    assert uia.read_window("Claude").splitlines()[1:] == ['1 button "New chat"']
    assert uia.read_window("CLAUDE").startswith("Elements of ")  # no such title: either one
    with pytest.raises(LookupError, match="Accessible windows: "):
        uia.read_window("Notes")


def test_linux_read_window_takes_a_title_as_list_windows_gives_it(monkeypatch):
    linux_desktop(monkeypatch, Node("frame", "claude", [Node("menu", "Terminal")]),
                  Node("frame", "Claude", [Node("push button", "New chat")]))

    # list_windows marks a minimized window; the mark is not part of its title.
    assert uia.read_window("claude (minimized)").splitlines() == [
        "Elements of 'claude'; use their numbers with click_element:", '1 menu "Terminal"']
    with pytest.raises(LookupError, match="No accessible window matches 'Notes'"):
        uia.read_window("Notes (minimized)")


def test_linux_read_window_gives_the_text_a_terminal_shows(monkeypatch):
    menu = ("Accessing workspace:\n\n/home/ana/project    \n\n> No, exit\n"
            "  Yes, I trust this folder\n\nEnter to confirm\n" + "\n" * 18)  # a blank rest
    terminal = Node("terminal", "Terminal", text=menu)
    linux_desktop(monkeypatch, Node("frame", "claude", [
        Node("menu", "File"), Node("scroll pane", children=[terminal])]))

    assert uia.read_window("claude") == (
        "Elements of 'claude'; use their numbers with click_element:\n"
        '1 menu "File"\n'
        '2 terminal "Terminal", showing:\n'
        "    Accessing workspace:\n"
        "\n"
        "    /home/ana/project\n"
        "\n"
        "    > No, exit\n"
        "      Yes, I trust this folder\n"
        "\n"
        "    Enter to confirm")
    assert uia.describe(2) == "terminal \"Terminal\" in 'claude'"

    terminal.text = "scrolled away\n" * 20000 + "$ make\ndone"
    lines = uia.read_window("claude").splitlines()
    assert lines[2:4] == ['2 terminal "Terminal", showing:', "    (earlier text left out)"]
    assert lines[-2:] == ["    $ make", "    done"] and len(lines) == 4 + uia.TERMINAL_LINES

    terminal.text = None  # one that hands over no text is still listed
    assert uia.read_window("claude").splitlines()[2:] == ['2 terminal "Terminal"']


def test_terminal_text_is_cut_to_its_last_lines_and_characters():
    assert uia._screen_text("\r\n  $ ls  \r\nnotes.txt\r\n\r\n") == "  $ ls\nnotes.txt"
    assert uia._screen_text(None) == uia._screen_text(" \n \n") == ""

    long = uia._screen_text("\n".join(f"line {n}" for n in range(1, 201))).split("\n")
    assert long[:2] == ["(earlier text left out)", "line 151"] and long[-1] == "line 200"
    wide = uia._screen_text("\n".join(f"{n:02}" + "x" * 298 for n in range(30))).split("\n")
    assert wide[0] == "(earlier text left out)" and wide[1].startswith("17") and len(wide) == 14
    assert len("\n".join(wide[1:])) <= uia.TERMINAL_CHARS
    endless = uia._screen_text("y" * 9000 + "END")
    assert endless == "(earlier text left out)\n" + "y" * (uia.TERMINAL_CHARS - 3) + "END"


class Control:
    """A UI Automation control as the uiautomation package hands them out."""

    def __init__(self, kind, name="", class_name="", text=None, value=None):
        self.ControlTypeName, self.Name, self.ClassName = kind + "Control", name, class_name
        self.IsOffscreen, self.IsEnabled = False, True
        self.BoundingRectangle = NS(left=0, top=30, width=lambda: 800, height=lambda: 500)
        self.text, self.value = text, value  # None: it has no such pattern

    def GetPattern(self, pattern):
        assert pattern == "the text pattern"
        if self.text is not None:  # one range for each piece of text in view
            return NS(GetVisibleRanges=lambda: [
                NS(GetText=lambda limit, piece=piece: piece) for piece in self.text])

    def GetValuePattern(self):
        return None if self.value is None else NS(Value=self.value)


def windows_desktop(monkeypatch, window, *controls):
    """Make uia read this window as if UI Automation walked it on Windows."""
    fake = types.ModuleType("uiautomation")
    fake.ControlFromHandle = lambda handle: window
    fake.WalkControl = lambda top, includeTop, maxDepth: [(control, 1) for control in controls]
    fake.PatternId = NS(TextPattern="the text pattern")
    monkeypatch.setitem(sys.modules, "uiautomation", fake)
    monkeypatch.setattr(uia.sys, "platform", "win32")
    monkeypatch.setattr(uia, "_uia_init", lambda: None)
    monkeypatch.setattr(uia, "_uia_executor", None)
    monkeypatch.setattr(uia, "_last", {})
    monkeypatch.setattr(uia, "_last_window", "")
    monkeypatch.setattr(uia.desktop, "_find_window",
                        lambda title: NS(title=title, getHandle=lambda: 7))


def test_windows_read_window_gives_the_text_a_terminal_shows(monkeypatch):
    shown = "PS C:\\Users\\ana> claude\r\n\r\n> No, exit\r\n  Yes, I trust this folder\r\n\r\n\r\n"
    windows_desktop(monkeypatch, Control("Window", "claude", "CASCADIA_HOSTING_WINDOW_CLASS"),
                    Control("TabItem", "claude"),
                    Control("Text", "PowerShell", "TermControl", text=[shown]),
                    Control("Text", "Ready", "TextBlock", text=["a label stays a label"]))

    assert uia.read_window("claude") == (
        "Elements of 'claude'; use their numbers with click_element:\n"
        '1 tab "claude"\n'
        '2 terminal "PowerShell", showing:\n'
        "    PS C:\\Users\\ana> claude\n"
        "\n"
        "    > No, exit\n"
        "      Yes, I trust this folder\n"
        '3 text "Ready"')
    assert uia.describe(2) == "terminal \"PowerShell\" in 'claude'"


def test_windows_console_window_is_read_as_a_terminal_too(monkeypatch):
    rows = ["C:\\>dir\r\n", " Volume in drive C has no label.\r\n"]  # handed over row by row
    windows_desktop(monkeypatch, Control("Window", "Command Prompt", "ConsoleWindowClass"),
                    Control("Document", "Text Area", text=rows))

    assert uia.read_window("Command Prompt").splitlines()[1:] == [
        '1 terminal "Text Area", showing:', "    C:\\>dir",
        "     Volume in drive C has no label."]


def test_windows_documents_are_not_taken_for_terminals(monkeypatch):
    windows_desktop(monkeypatch, Control("Window", "Notes", "Notepad"),
                    Control("Document", "Text editor", "RichEditD2DPT",
                            text=["dear diary"], value="dear diary"),
                    Control("Text", "", "TermControl"))  # a terminal that hands over no text

    assert uia.read_window("Notes").splitlines()[1:] == [
        "1 document \"Text editor\" = 'dear diary'", "2 terminal"]


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
