"""kai's own browser window, driven through Playwright.

kai reads pages as text plus a numbered list of the links, buttons and fields
in view, and acts on those numbers, which is far more reliable than guessing
keystrokes. It uses a separate profile (logins made there are kept), launched
with Edge or Chrome when installed, else Playwright's own Chromium, which is
downloaded on first use.

Playwright's sync API is bound to the thread that started it, so every call
runs on one dedicated worker thread.
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from kai import config

log = logging.getLogger(__name__)

TEXT_CHUNK = 3000  # characters of page text per read
MAX_ELEMENTS = 80
TIMEOUT_MS = 15_000  # page loads
ACTION_MS = 5_000  # clicking or filling an element

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kai-browser")
_pw = None
_ctx = None
_page = None
_described: dict[int, str] = {}  # element number -> description from the last read

# Marks the visible interactive elements with data-kai="n" and describes them.
_SNAPSHOT_JS = r"""
(max) => {
  const sel = 'a[href],button,input:not([type=hidden]),select,textarea,summary,' +
    '[role=button],[role=link],[role=tab],[role=menuitem],[role=checkbox],[role=radio],' +
    '[role=option],[role=switch],[role=combobox],[role=searchbox],[role=textbox],' +
    '[contenteditable=""],[contenteditable=true],[onclick]';
  document.querySelectorAll('[data-kai]').forEach(e => e.removeAttribute('data-kai'));
  const out = [];
  let n = 0;
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    if (r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) continue;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || st.opacity === '0') continue;
    const tag = el.tagName.toLowerCase();
    let role = el.getAttribute('role') || tag;
    if (tag === 'input') role = 'input:' + (el.type || 'text');
    if (tag === 'a') role = 'link';
    let label = el.getAttribute('aria-label') || el.innerText || el.value ||
                el.placeholder || el.title || el.getAttribute('alt') || '';
    if (!label.trim()) {
      const img = el.querySelector('img[alt],svg[aria-label]');
      if (img) label = img.getAttribute('alt') || img.getAttribute('aria-label') || '';
    }
    label = label.trim().replace(/\s+/g, ' ').slice(0, 80);
    if (!label && tag === 'a') label = (el.getAttribute('href') || '').slice(0, 60);
    n++;
    el.setAttribute('data-kai', n);
    let extra = '';
    if (el.checked) extra = ' [checked]';
    if (el.disabled) extra += ' [disabled]';
    out.push(n + ' ' + role + (label ? ' "' + label + '"' : '') + extra);
    if (n >= max) break;
  }
  return {elements: out, scrollY: Math.round(scrollY),
          height: document.documentElement.scrollHeight, view: innerHeight};
}
"""


def _channels() -> list[str | None]:
    if sys.platform == "win32":
        return ["msedge", "chrome", None]
    return ["chrome", "msedge", None]  # None = Playwright's bundled Chromium


def _install_chromium() -> None:
    log.info("Downloading Chromium for kai's browser")
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                   check=True, capture_output=True, timeout=600)


def _launch():
    global _pw, _ctx, _page
    from playwright.sync_api import Error, sync_playwright

    if _pw is None:
        _pw = sync_playwright().start()
    profile = config.config_dir() / "browser"
    errors = []
    for attempt in range(2):
        for channel in _channels():
            try:
                _ctx = _pw.chromium.launch_persistent_context(
                    str(profile), channel=channel, headless=False, no_viewport=True,
                    args=["--start-maximized"])
                log.info("Browser started (%s)", channel or "bundled chromium")
                break
            except Error as e:
                errors.append(f"{channel}: {str(e).splitlines()[0]}")
        if _ctx is not None or attempt:
            break
        _install_chromium()
    if _ctx is None:
        raise RuntimeError("Could not start a browser. " + " | ".join(errors[-3:]))
    _ctx.set_default_timeout(TIMEOUT_MS)
    _ctx.on("page", _on_new_page)
    _ctx.on("close", _on_closed)
    _page = _ctx.pages[0] if _ctx.pages else _ctx.new_page()


def _on_new_page(page) -> None:
    global _page
    _page = page  # links that open a new tab: follow them


def _on_closed(_ctx_) -> None:
    global _ctx, _page
    _ctx = _page = None


def _current():
    global _page
    if _ctx is None:
        _launch()
    if _page is None or _page.is_closed():
        open_pages = [p for p in _ctx.pages if not p.is_closed()]
        _page = open_pages[-1] if open_pages else _ctx.new_page()
    return _page


def _settle(page) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT_MS)
        page.wait_for_load_state("networkidle", timeout=2500)
    except Exception:
        pass  # busy pages never go idle; what has loaded is enough


def _text(page) -> str:
    text = page.evaluate("() => document.body ? document.body.innerText : ''")
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def _mark(page) -> dict:
    info = page.evaluate(_SNAPSHOT_JS, MAX_ELEMENTS)
    _described.clear()
    for line in info["elements"]:
        number, _, desc = line.partition(" ")
        _described[int(number)] = desc
    return info


def _snapshot(page, part: int = 1) -> str:
    from playwright.sync_api import Error

    page.wait_for_timeout(400)  # let a click or Enter start its navigation
    for attempt in range(3):
        _settle(page)
        try:
            info = _mark(page)
            break
        except Error as e:  # the page navigated while being read
            if "context was destroyed" not in str(e) or attempt == 2:
                raise
    text = _text(page)
    parts = max(1, -(-len(text) // TEXT_CHUNK))
    part = min(max(1, part), parts)
    chunk = text[(part - 1) * TEXT_CHUNK: part * TEXT_CHUNK]
    room = info["height"] - info["view"]
    if room <= 5:
        position = "whole page in view"
    elif info["scrollY"] <= 5:
        position = "top of the page, more below"
    elif info["scrollY"] >= room - 5:
        position = "bottom of the page"
    else:
        position = f"scrolled {round(100 * info['scrollY'] / room)}% down"
    lines = [f"Title: {page.title()}", f"URL: {page.url}",
             f"Elements in view ({position}; use their numbers):",
             *(info["elements"] or ["(none)"]),
             f"Page text, part {part} of {parts}:", chunk or "(no text)"]
    return "\n".join(lines)


def _await_navigation(page, before: str) -> None:
    """After a click or Enter, give a navigation a moment to start."""
    try:
        page.wait_for_url(lambda u: u != before, timeout=1500, wait_until="commit")
    except Exception:
        pass  # nothing navigated: the action changed the page in place


def _call(fn, *args):
    """Run on the browser thread; if the user closed the window, reopen it and retry."""
    global _ctx, _page
    from playwright.sync_api import Error

    try:
        return fn(*args)
    except Error as e:
        if "closed" not in str(e).lower() and type(e).__name__ != "TargetClosedError":
            raise
        log.info("Browser window was closed; reopening it")
        try:
            if _ctx is not None:
                _ctx.close()
        except Exception:
            pass
        _ctx = _page = None
        return fn(*args)


def _run(fn, *args):
    return _executor.submit(_call, fn, *args).result(timeout=120)


def _element(page, number: int):
    number = int(number)
    loc = page.locator(f'[data-kai="{number}"]')
    if loc.count():
        return loc.first
    # Pages often re-render after loading, dropping the marks: find it again by description.
    wanted = _described.get(number)
    _mark(page)
    for new_number, desc in _described.items():
        if wanted and desc == wanted:
            return page.locator(f'[data-kai="{new_number}"]').first
    raise LookupError(f"Element {number} is not on the page any more. Read the page again.")


def describe(number: int) -> str:
    return _described.get(int(number), f"element {number}")


# ---- tools ----

def browser_open(url: str) -> str:
    def go():
        page = _current()
        target = url if re.match(r"^[a-z]+:", url) else "https://" + url
        page.goto(target, wait_until="domcontentloaded")
        page.bring_to_front()
        return _snapshot(page)
    return _run(go)


def browser_read(part: int = 1) -> str:
    def read():
        if _ctx is None:
            raise RuntimeError("kai's browser is not open. Use browser_open first.")
        return _snapshot(_current(), part)
    return _run(read)


def browser_click(element: int) -> str:
    def click():
        page = _current()
        before = page.url
        target = _element(page, element)
        try:
            target.click(timeout=ACTION_MS)
        except Exception as e:
            if "Timeout" not in type(e).__name__:
                raise
            target.click(force=True, timeout=ACTION_MS)  # something overlays it: click anyway
        _await_navigation(page, before)
        return _snapshot(_current())  # the click may have opened a new tab
    return _run(click)


def browser_type(element: int, text: str, submit: bool = False) -> str:
    def type_():
        page = _current()
        target = _element(page, element)
        editable = target.evaluate(
            "e => e.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.tagName) "
            "|| ['textbox', 'searchbox', 'combobox'].includes(e.getAttribute('role'))")
        if not editable:
            raise ValueError(f"Element {element} is not a text field. Read the page and pick "
                             "an input, or click it first if it opens one.")
        try:
            target.fill(text, timeout=ACTION_MS)
        except Exception:  # not a plain field (e.g. rich editors): type into it
            target.click(timeout=ACTION_MS)
            page.keyboard.type(text)
        if submit:
            before = page.url
            page.keyboard.press("Enter")  # the field keeps the focus; sites may swap the node
            _await_navigation(page, before)
        return _snapshot(_current())
    return _run(type_)


def browser_scroll(direction: str = "down") -> str:
    def scroll():
        page = _current()
        sign = -1 if direction.lower().startswith("u") else 1
        page.evaluate("(s) => window.scrollBy(0, s * innerHeight * 0.8)", sign)
        page.wait_for_timeout(300)
        return _snapshot(page)
    return _run(scroll)


def browser_back() -> str:
    def back():
        page = _current()
        page.go_back(wait_until="domcontentloaded")
        return _snapshot(page)
    return _run(back)


def browser_screenshot() -> bytes:
    """JPEG of the visible part of the page, for when the text isn't enough."""
    def shot():
        if _ctx is None:
            raise RuntimeError("kai's browser is not open. Use browser_open first.")
        return _current().screenshot(type="jpeg", quality=70)
    return _run(shot)


def shutdown() -> None:
    def close():
        global _pw, _ctx, _page
        try:
            if _ctx is not None:
                _ctx.close()
            if _pw is not None:
                _pw.stop()
        except Exception:
            pass
        _pw = _ctx = _page = None
    try:
        _executor.submit(close).result(timeout=10)
    except Exception:
        pass
