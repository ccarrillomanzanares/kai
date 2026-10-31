"""Local tools the model can call through Gemini function calling.

Each tool has a risk level, and the user picks a permission level that decides
which risks need their approval in a confirmation dialog (see needs_confirmation).
"""

from __future__ import annotations

import enum
import logging
import platform
import re
from dataclasses import dataclass
from typing import Any, Callable

from google.genai import types

from kai.tools import apps, browser, desktop, files, screen, shell, system, uia

log = logging.getLogger(__name__)

# Asks the user to approve a sensitive action: (title, detail) -> approved.
# Called from a worker thread; blocks until the user answers.
Confirm = Callable[[str, str], bool]


class Risk(enum.Enum):
    READ = "read"  # only looks
    SAFE = "safe"  # opens things
    CONTROL = "control"  # types or presses keys in other apps
    SENSITIVE = "sensitive"  # runs commands or closes programs


class Permission(enum.Enum):
    STRICT = "strict"  # ask before anything that isn't read-only
    BALANCED = "balanced"  # ask before commands, closing programs and typing in terminals
    TRUSTED = "trusted"  # only ask before destructive commands


PERMISSION_LABELS = {
    Permission.STRICT: "Ask for everything",
    Permission.BALANCED: "Ask before risky actions",
    Permission.TRUSTED: "Only ask before destructive commands",
}

# Commands that delete, wipe, uninstall or power off: confirmed at every level.
_DESTRUCTIVE = re.compile(
    r"\brm\b|\brmdir\b|\brd\b|\bdel\b|\berase\b|remove-item|\bri\b|clear-content|"
    r"\bformat(\.com)?\s+[a-z]:|format-volume|mkfs|\bdd\b|diskpart|clear-disk|\bshred\b|\bwipe|"
    r"shutdown|restart-computer|stop-computer|\breboot\b|\bpoweroff\b|\bhalt\b|"
    r"reg(\.exe)?\s+delete|remove-itemproperty|uninstall|\bapt(-get)?\s+(remove|purge)|"
    r"\bbrew\s+uninstall|\bwinget\s+uninstall|\bchmod\b|\bchown\b|takeown|icacls|"
    r"\bmv\b|move-item|\bmove\b|>\s*[^&|]",
    re.IGNORECASE,
)


def is_destructive(command: str) -> bool:
    return bool(_DESTRUCTIVE.search(command))


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    func: Callable[..., Any]
    risk: Risk
    # UI tools only describe what happened; the app performs the action on the UI thread.
    ui_action: bool = False
    # For SENSITIVE tools: builds the (title, detail) shown in the confirmation dialog.
    confirm_text: Callable[..., tuple[str, str]] | None = None

    def declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name, description=self.description, parameters=self.parameters
        )


def _params(required: list[str] | None = None, **props: tuple[str, str]) -> dict[str, Any]:
    """Build a JSON schema from name=(type, description) pairs."""
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {k: {"type": t, "description": d} for k, (t, d) in props.items()},
    }
    if required:
        schema["required"] = required
    return schema


OS_NAME = f"{platform.system()} {platform.release()}"

TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        # ---- read ----
        Tool("get_datetime", "Get the current local date, time and timezone.",
             _params(), system.get_datetime, Risk.READ),
        Tool("get_system_info",
             "Get operating system, CPU, memory, disk and battery usage of this computer.",
             _params(), system.get_system_info, Risk.READ),
        Tool("list_processes",
             "List the running programs using the most memory or CPU.",
             _params(sort_by=("string", "'memory' (default) or 'cpu'."),
                     limit=("integer", "How many to return, default 15.")),
             shell.list_processes, Risk.READ),
        Tool("list_directory",
             "List the files and folders inside a folder. Accepts ~ for the home folder.",
             _params(path=("string", "Folder path, e.g. '~/Downloads'. Default: home.")),
             files.list_directory, Risk.READ),
        Tool("search_files",
             "Find files or folders by name under a folder (default: home). "
             "Plain text matches anywhere in the name; glob patterns like '*.pdf' also work.",
             _params(["pattern"], pattern=("string", "Name or glob pattern."),
                     folder=("string", "Where to search, default '~'.")),
             files.search_files, Risk.READ),
        # ---- safe ----
        Tool("open_url", "Open a web page in the user's default browser.",
             _params(["url"], url=("string", "Absolute http(s) URL.")),
             system.open_url, Risk.SAFE),
        Tool("open_app",
             "Launch an installed application by name, including Microsoft Store apps on "
             "Windows. App names are usually in the system's language (e.g. 'Calculadora').",
             _params(["name"], name=("string", "Application name, e.g. 'Spotify', 'WhatsApp'.")),
             apps.open_app, Risk.SAFE),
        Tool("open_path",
             "Open a file with its default application, or a folder in the file manager.",
             _params(["path"], path=("string", "File or folder path, ~ allowed.")),
             apps.open_path, Risk.SAFE),
        Tool("look_at_screen",
             "Take a screenshot so you can see the screen (or one window) as an image. Use it "
             "before acting in apps, when unsure what's on screen, and to check the result. "
             "kai's own bar may appear at the bottom.",
             _params(window=("string", "Optional window title to capture just that window.")),
             screen.look_at_screen, Risk.SAFE,
             confirm_text=lambda window=None: (
                 "Look at the screen", f"Send a screenshot of {window or 'the screen'} to Gemini")),
        Tool("read_window",
             "List the buttons, fields, menus, links and texts of an app window through the "
             "system accessibility tree, numbered for click_element. More exact than a "
             "screenshot; if it finds little, use look_at_screen.",
             _params(["window"], window=("string", "Window title or part of it.")),
             uia.read_window, Risk.READ),
        Tool("list_windows",
             "List the titles of the open windows on the desktop.",
             _params(), desktop.list_windows, Risk.READ),
        Tool("focus_window",
             "Bring an open window to the front, matching its title (partial names work).",
             _params(["title"], title=("string", "Window title or part of it.")),
             desktop.focus_window, Risk.SAFE),
        Tool("type_text",
             "Type text into an app as if using the keyboard, e.g. to write in Notepad or "
             "fill a field. Always pass the target window's title: kai's own window may have "
             "the focus. Newlines press Enter.",
             _params(["text", "window"], text=("string", "Text to type."),
                     window=("string", "Title (or part) of the window to type into.")),
             desktop.type_text, Risk.CONTROL,
             confirm_text=lambda text, window=None: (
                 f"Type into {window or 'the active window'}",
                 text if len(text) <= 600 else text[:600] + "…")),
        Tool("press_keys",
             "Press a key or shortcut in an app, e.g. 'ctrl+t' (new tab), 'ctrl+s', 'enter', "
             "'alt+tab', 'ctrl+shift+esc'. Always pass "
             "the target window's title.",
             _params(["keys", "window"], keys=("string", "Keys joined with '+'."),
                     window=("string", "Title (or part) of the window.")),
             desktop.press_keys, Risk.CONTROL,
             confirm_text=lambda keys, window=None: (
                 f"Press keys in {window or 'the active window'}", keys)),
        Tool("click",
             "Click at a point of the last look_at_screen image, with x and y from 0 to 1000 "
             "(0,0 = top-left of that image). Use it when read_window can't see the element.",
             _params(["x", "y"], x=("number", "0-1000 from the left edge of the screenshot."),
                     y=("number", "0-1000 from the top edge of the screenshot."),
                     button=("string", "'left' (default) or 'right'."),
                     double=("boolean", "True for a double-click.")),
             screen.click, Risk.CONTROL,
             confirm_text=lambda x, y, button="left", double=False: (
                 "Click on the screen", f"{'Double-click' if double else button + ' click'} "
                 f"at {x:g}, {y:g} of the last screenshot")),
        Tool("scroll",
             "Scroll the mouse wheel, optionally over a point of the last screenshot (0-1000).",
             _params(["direction"], direction=("string", "'down' or 'up'."),
                     amount=("integer", "Wheel steps, default 5."),
                     x=("number", "Optional point to scroll over, 0-1000."),
                     y=("number", "Optional point to scroll over, 0-1000.")),
             screen.scroll, Risk.CONTROL),
        Tool("click_element",
             "Click an element listed by read_window, by its number. To type into a field, "
             "click it, then use type_text with the window title.",
             _params(["number"], number=("integer", "Element number from read_window."),
                     double=("boolean", "True for a double-click."),
                     button=("string", "'left' (default) or 'right'.")),
             uia.click_element, Risk.CONTROL,
             confirm_text=lambda number, double=False, button="left": (
                 "Click in an app", uia.describe(number))),
        # ---- kai's browser ----
        Tool("browser_open",
             "Open a web page in kai's own browser window, which kai can read and control. "
             "Use it for any web task (searching, reading, filling forms). Returns the page "
             "title, URL, the numbered links/buttons/fields in view and the page text.",
             _params(["url"], url=("string", "URL; for searches use e.g. "
                                    "'https://duckduckgo.com/?q=…' or 'https://www.google.com/search?q=…'.")),
             browser.browser_open, Risk.SAFE),
        Tool("browser_read",
             "Read kai's browser page again: numbered elements in view and the page text. "
             "Long pages come in parts; pass part=2, 3… to read on.",
             _params(part=("integer", "Text part to read, default 1.")),
             browser.browser_read, Risk.READ),
        Tool("browser_click", "Click a link, button or other element of kai's browser page "
             "by its number. Returns the updated page.",
             _params(["element"], element=("integer", "Element number from the last read.")),
             browser.browser_click, Risk.CONTROL,
             confirm_text=lambda element: ("Click in kai's browser", browser.describe(element))),
        Tool("browser_type",
             "Type into a field of kai's browser page by its number (replaces its content). "
             "submit=true presses Enter afterwards, e.g. to search.",
             _params(["element", "text"], element=("integer", "Field number from the last read."),
                     text=("string", "Text to type."),
                     submit=("boolean", "Press Enter after typing.")),
             browser.browser_type, Risk.CONTROL,
             confirm_text=lambda element, text, submit=False: (
                 f"Type in kai's browser ({browser.describe(element)})", text[:600])),
        Tool("browser_scroll", "Scroll kai's browser page down or up and read what comes into view.",
             _params(["direction"], direction=("string", "'down' or 'up'.")),
             browser.browser_scroll, Risk.READ),
        Tool("browser_back", "Go back to the previous page in kai's browser.",
             _params(), browser.browser_back, Risk.SAFE),
        Tool("browser_screenshot",
             "See kai's browser page as an image, for images, charts or layouts the text "
             "doesn't capture.",
             _params(), browser.browser_screenshot, Risk.READ),
        Tool("open_diagnostics",
             "Open kai's 'Send diagnostics' window so the user can review and send a report "
             "with kai's logs and system info (no conversations, no API key). Use it when the "
             "user reports a problem with kai or asks to send diagnostics. Nothing is sent "
             "until the user clicks Send.",
             _params(),
             lambda: "The diagnostics window is open. The user must click Send to upload it.",
             Risk.SAFE, ui_action=True),
        # ---- sensitive: the user confirms each call ----
        Tool("run_command",
             f"Run a {shell.SHELL_NAME} command on this computer ({OS_NAME}) and get its output. "
             "Use it for anything the other tools can't do: settings, files, network, installed "
             "software, etc. The user sees the exact command and must approve it, so prefer "
             "one clear, safe command. Runs in the user's home folder, non-interactively (no sudo or "
             "password prompts) with a 60 s timeout.",
             _params(["command", "reason"],
                     command=("string", f"The {shell.SHELL_NAME} command to run."),
                     reason=("string", "Short explanation for the user, in their language.")),
             shell.run_command, Risk.SENSITIVE,
             confirm_text=lambda command, reason="": (reason or "Run a command", command)),
        Tool("kill_process", "Close a running program by its process id (see list_processes).",
             _params(["pid"], pid=("integer", "Process id.")),
             shell.kill_process, Risk.SENSITIVE,
             confirm_text=lambda pid: ("Close a program", shell.describe_kill(pid))),
    ]
}


# Key of the JPEG in a tool result; live.py sends it as an image part, not as JSON.
IMAGE_KEY = "_image"


def declarations() -> list[types.Tool]:
    return [types.Tool(function_declarations=[t.declaration() for t in TOOLS.values()])]


def is_ui_action(name: str) -> bool:
    tool = TOOLS.get(name)
    return tool is not None and tool.ui_action


def needs_confirmation(tool: Tool, args: dict[str, Any], level: Permission) -> bool:
    if tool.risk is Risk.READ or tool.ui_action:
        return False
    if tool.name == "run_command" and is_destructive(args.get("command", "")):
        return True
    if level is Permission.STRICT:
        return True
    if level is Permission.BALANCED:
        if tool.risk is Risk.SENSITIVE:
            return True
        return tool.risk is Risk.CONTROL and desktop.is_terminal(args.get("window"))
    return False


def call(name: str, args: dict[str, Any] | None, confirm: Confirm | None = None,
         level: Permission = Permission.BALANCED) -> dict[str, Any]:
    """Run a tool and wrap its outcome in a function-response payload."""
    tool = TOOLS.get(name)
    if tool is None:
        return {"error": f"Unknown tool: {name}"}
    args = args or {}
    try:
        if needs_confirmation(tool, args, level):
            if tool.confirm_text:
                title, detail = tool.confirm_text(**args)
            else:
                title, detail = name.replace("_", " ").capitalize(), ", ".join(map(str, args.values()))
            if confirm is None or not confirm(title, detail):
                log.info("Tool %s: declined by the user", name)
                return {"error": "The user declined this action."}
        result = tool.func(**args)
        if isinstance(result, screen.Image):
            return {"result": result.text, IMAGE_KEY: result.jpeg}
        if isinstance(result, bytes):  # a bare JPEG
            return {"result": "Image attached.", IMAGE_KEY: result}
        return {"result": result}
    except Exception as e:
        # Only the exception type: messages can echo the user's arguments.
        log.warning("Tool %s raised %s", name, type(e).__name__)
        return {"error": str(e)}
