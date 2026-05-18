#!/usr/bin/env python3
"""
xml_autocloser.py — System-wide XML/HTML auto-closing tag inserter.

When you type the '>' of an opening tag like <div>, this script
immediately inserts </div> and places the cursor between the tags:

    Type:   <div>
    Result: <div>|</div>   (cursor at |)

Jump action — moves cursor past the closing tag:
    Press comma twice while inside an auto-inserted tag pair.
"""

import platform
import re
import threading
import time
from pynput import keyboard

# HTML void elements — never need a closing tag
VOID_ELEMENTS = {
    'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
    'link', 'meta', 'param', 'source', 'track', 'wbr',
}

SYSTEM = platform.system()   # 'Darwin', 'Windows', or 'Linux'

_buffer: list = []
MAX_BUFFER = 200
TRIGGER_CHAR = ','
TRIGGER_COUNT = 2
_close_stack: list = []
_inserting: bool = False
_lock = threading.Lock()

controller = keyboard.Controller()


def _get_opening_tag(text: str):
    """
    Return the tag name if text ends with a complete, non-void, non-self-closing
    opening tag. Returns None otherwise.

    Matches:  <div>  <div class="x">  <ns:tag>
    Skips:    </div>  <br>  <img/>  <input type="text">
    """
    if text.endswith('/>'):
        return None
    m = re.search(r'<([a-zA-Z][a-zA-Z0-9:_-]*)(?:\s[^>]*)?>$', text)
    if not m:
        return None
    if m.group(1).lower() in VOID_ELEMENTS:
        return None
    return m.group(1)   # preserve original casing


def _insert_closing_tag(tag_name: str) -> None:
    """Inject closing tag then move cursor left to sit between the two tags."""
    global _inserting

    closing = f'</{tag_name}>'
    close_len = len(closing)

    _inserting = True
    try:
        controller.type(closing)
        time.sleep(0.02)
        for _ in range(close_len):
            controller.press(keyboard.Key.left)
            controller.release(keyboard.Key.left)
            time.sleep(0.004)
        with _lock:
            _close_stack.append(close_len)
    finally:
        _inserting = False


def _jump_past_close(close_len: int, chars_to_delete: int = 0) -> None:
    """Delete trigger characters, then move cursor right past a closing tag."""
    global _inserting

    _inserting = True
    try:
        for _ in range(chars_to_delete):
            controller.press(keyboard.Key.backspace)
            controller.release(keyboard.Key.backspace)
            time.sleep(0.004)
        for _ in range(close_len):
            controller.press(keyboard.Key.right)
            controller.release(keyboard.Key.right)
            time.sleep(0.004)
    finally:
        _inserting = False


def _handle_trigger_char(char: str) -> bool:
    """Track trigger characters and jump after enough in a tag pair."""
    close_len = 0

    with _lock:
        _buffer.append(char)
        if len(_buffer) > MAX_BUFFER:
            _buffer.pop(0)

        if ''.join(_buffer[-TRIGGER_COUNT:]) != char * TRIGGER_COUNT or not _close_stack:
            return False

        close_len = _close_stack.pop()
        del _buffer[-TRIGGER_COUNT:]

    threading.Thread(
        target=_jump_past_close,
        args=(close_len, TRIGGER_COUNT),
        daemon=True,
    ).start()
    return True


def on_press(key) -> None:
    global _buffer

    if _inserting:
        return

    # --- Special (non-printable) keys ---
    try:
        char = key.char
    except AttributeError:
        with _lock:
            if key == keyboard.Key.backspace:
                if _buffer:
                    _buffer.pop()
            elif key == keyboard.Key.enter:
                _buffer.append('\n')
            elif key == keyboard.Key.space:
                _buffer.append(' ')
            elif key == keyboard.Key.tab:
                _buffer.append('\t')
            elif key in {
                keyboard.Key.left, keyboard.Key.right,
                keyboard.Key.up, keyboard.Key.down,
                keyboard.Key.home, keyboard.Key.end,
            }:
                _close_stack.clear()
        return

    if char is None:
        return

    # --- Jump trigger: comma comma ---
    if char == TRIGGER_CHAR:
        _handle_trigger_char(char)
        return

    # --- Update buffer ---
    with _lock:
        _buffer.append(char)
        if len(_buffer) > MAX_BUFFER:
            _buffer.pop(0)
        snapshot = ''.join(_buffer)

    # --- Auto-close detection ---
    if char == '>':
        tag_name = _get_opening_tag(snapshot)
        if tag_name:
            threading.Timer(
                0.05, lambda t=tag_name: _insert_closing_tag(t)
            ).start()


def on_release(key) -> None:
    pass


def main() -> None:
    print(f"XML AutoCloser v1.0 — {SYSTEM}")
    print()

    if SYSTEM == 'Darwin':
        print("  Jump action : press comma twice inside a tag pair")
        print()
        print("  macOS requires Accessibility permission:")
        print("  System Settings → Privacy & Security → Accessibility")
        print("  Add your Terminal app (or the Python executable).")
    elif SYSTEM == 'Windows':
        print("  Jump action : press comma twice inside a tag pair")
    else:
        print("  Jump action : press comma twice inside a tag pair")
        print("  Note: Wayland support is limited. X11 recommended.")

    print()
    print("  Auto-close is ACTIVE. Press Ctrl+C to stop.")
    print()

    try:
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()
    except KeyboardInterrupt:
        print("\nXML AutoCloser stopped.")


if __name__ == '__main__':
    main()
