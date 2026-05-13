#!/usr/bin/env python3
"""
xml_autocloser.py — System-wide XML/HTML auto-closing tag inserter.

When you type the '>' of an opening tag like <div>, this script
immediately inserts </div> and places the cursor between the tags:

    Type:   <div>
    Result: <div>|</div>   (cursor at |)

Jump hotkey — moves cursor past the closing tag:
    macOS:         Cmd + < (i.e. Cmd + Shift + ,)
    Windows/Linux: Alt + < (i.e. Alt + Shift + ,)
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
_last_close_len: int = 0
_inserting: bool = False
_modifiers: set = set()
_lock = threading.Lock()

controller = keyboard.Controller()

# All modifier key variants to track
_MODIFIER_KEYS = {
    keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r,
    keyboard.Key.cmd,   keyboard.Key.cmd_l,   keyboard.Key.cmd_r,
    keyboard.Key.alt,   keyboard.Key.alt_l,   keyboard.Key.alt_r,
    keyboard.Key.ctrl,  keyboard.Key.ctrl_l,  keyboard.Key.ctrl_r,
}

_CMD_KEYS = {keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r}
_ALT_KEYS = {keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r}


def _cmd_held() -> bool:
    return bool(_modifiers & _CMD_KEYS)


def _alt_held() -> bool:
    return bool(_modifiers & _ALT_KEYS)


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
    global _last_close_len, _inserting

    closing = f'</{tag_name}>'
    _last_close_len = len(closing)

    _inserting = True
    try:
        controller.type(closing)
        time.sleep(0.02)
        for _ in range(_last_close_len):
            controller.press(keyboard.Key.left)
            controller.release(keyboard.Key.left)
            time.sleep(0.004)
    finally:
        _inserting = False


def _jump_past_close() -> None:
    """Move cursor right by the length of the last inserted closing tag."""
    if _last_close_len > 0:
        for _ in range(_last_close_len):
            controller.press(keyboard.Key.right)
            controller.release(keyboard.Key.right)
            time.sleep(0.004)


def on_press(key) -> None:
    global _buffer

    # Always track modifier state, even while inserting
    if key in _MODIFIER_KEYS:
        _modifiers.add(key)
        return

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
        return

    if char is None:
        return

    # --- Jump hotkey: Cmd+< on macOS, Alt+< on Win/Linux ---
    if char == '<':
        if (SYSTEM == 'Darwin' and _cmd_held()) or \
           (SYSTEM != 'Darwin' and _alt_held()):
            threading.Thread(target=_jump_past_close, daemon=True).start()
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
    _modifiers.discard(key)


def main() -> None:
    print(f"XML AutoCloser v1.0 — {SYSTEM}")
    print()

    if SYSTEM == 'Darwin':
        print("  Jump hotkey : Cmd + < (Cmd + Shift + ,)")
        print()
        print("  macOS requires Accessibility permission:")
        print("  System Settings → Privacy & Security → Accessibility")
        print("  Add your Terminal app (or the Python executable).")
    elif SYSTEM == 'Windows':
        print("  Jump hotkey : Alt + < (Alt + Shift + ,)")
    else:
        print("  Jump hotkey : Alt + < (Alt + Shift + ,)")
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
