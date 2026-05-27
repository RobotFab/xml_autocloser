#!/usr/bin/env python3
"""
xml-autocloser.py — System-wide XML/HTML auto-closing tag inserter.

Feature 1 — Auto-close on >:
    Type:   <div>
    Result: <div>|</div>   (cursor at |)

Feature 2 — Click-Placement Mode:
    Activate : press < (Shift+,) three times within one second.
    1. A green overlay follows the mouse. Type your tag name (e.g. "div").
    2. Click anywhere  → injects <div> at the caret; red overlay shows </div>.
    3. Click again     → injects </div> at the caret; mode fully exits.
    Cancel   : triple < or triple Escape at any point.

Jump action — moves cursor past the auto-inserted closing tag:
    Press comma twice while the cursor is inside a tag pair.
"""

import platform
import re
import threading
import time
import tkinter as tk
from collections import deque
from pynput import keyboard, mouse

# HTML void elements — never auto-closed
VOID_ELEMENTS = {
    'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
    'link', 'meta', 'param', 'source', 'track', 'wbr',
}

SYSTEM = platform.system()   # 'Darwin', 'Windows', or 'Linux'

# --- Debug flag ---
DEBUG = True

def dbg(msg: str) -> None:
    if DEBUG:
        print(f'[DBG] {msg}', flush=True)

# --- Shared state ---
_buffer: list = []
MAX_BUFFER = 200
TRIGGER_CHAR = ','
TRIGGER_COUNT = 3
_close_stack: list = []
_inserting: bool = False
_lock = threading.Lock()

controller = keyboard.Controller()

# --- Click-Placement Mode state ---
_mode: str = 'IDLE'           # 'IDLE' | 'GREEN' | 'RED'
_fsm = None                   # ClickPlacementFSM instance, set in main()
_overlay = None               # DanglingOverlay instance, set in main()
_tk_root = None               # tk.Tk root, set in main()

def _kbd_intercept(event_type, event):
    """Per-event suppression gate used by the single keyboard listener.

    pynput calls on_press FIRST (building overlay text / auto-close logic),
    then calls this function to decide whether the event reaches the app.
    Returning None suppresses; returning event passes through.
    """
    if _inserting or _mode == 'IDLE':
        return event   # IDLE mode and our own injections must reach apps
    return None        # GREEN / RED: suppress user typing


# ---------------------------------------------------------------------------
# DanglingOverlay — floating preview window that trails the mouse
# ---------------------------------------------------------------------------

class DanglingOverlay:
    """Borderless, always-on-top Toplevel that follows the mouse cursor."""

    def __init__(self, root: tk.Tk):
        self._root = root
        self._visible = False

        self._win = tk.Toplevel(root)
        self._win.overrideredirect(True)
        self._win.wm_attributes('-topmost', True)
        self._win.wm_attributes('-alpha', 0.92)
        self._win.configure(bg='#1E1E1E')
        # macOS: prevent the overlay from stealing keyboard focus when shown,
        # and let mouse clicks fall through to windows behind it.
        if SYSTEM == 'Darwin':
            try:
                self._win.tk.call(
                    '::tk::unsupported::MacWindowStyle',
                    'style', self._win, 'help', 'noActivates ignoreClicks',
                )
            except Exception:
                pass
        self._win.withdraw()

        frame = tk.Frame(self._win, bg='#1E1E1E', padx=10, pady=5)
        frame.pack()
        self._label = tk.Label(
            frame,
            text='',
            font=('Menlo', 14, 'bold'),
            bg='#1E1E1E',
            fg='#00CC44',
        )
        self._label.pack()

    # --- Thread-safe public API (can be called from any thread) ---

    def show_green(self, text: str) -> None:
        display = f'<{text}>' if text else '<…>'
        self._root.after(0, lambda: self._apply_show(display, '#00CC44'))

    def show_red(self, text: str) -> None:
        self._root.after(0, lambda: self._apply_show(f'</{text}>', '#FF4444'))

    def hide(self) -> None:
        self._root.after(0, self._apply_hide)

    # --- Main-thread internals ---

    def _apply_show(self, text: str, color: str) -> None:
        self._label.config(text=text, fg=color)
        if not self._visible:
            self._visible = True
            self._win.deiconify()
            # deiconify() can reset window styles on macOS — reapply every time.
            if SYSTEM == 'Darwin':
                try:
                    self._win.tk.call(
                        '::tk::unsupported::MacWindowStyle',
                        'style', self._win, 'help', 'noActivates ignoreClicks',
                    )
                    dbg('MacWindowStyle reapplied')
                except Exception as e:
                    dbg(f'MacWindowStyle failed: {e}')
            self._win.lift()
            self._track_mouse()
        else:
            self._win.lift()
        self._update_position()

    def _apply_hide(self) -> None:
        self._visible = False
        self._win.withdraw()

    def _update_position(self) -> None:
        x = self._win.winfo_pointerx() + 18
        y = self._win.winfo_pointery() + 14
        self._win.geometry(f'+{x}+{y}')

    def _track_mouse(self) -> None:
        if not self._visible:
            return
        self._update_position()
        self._win.lift()   # re-raise above any window that took focus
        self._root.after(40, self._track_mouse)


# ---------------------------------------------------------------------------
# ClickPlacementFSM — state machine for Click-Placement Mode
# ---------------------------------------------------------------------------

class ClickPlacementFSM:

    HOTKEY_WINDOW = 1.0   # seconds within which triple-press is counted

    def __init__(self, overlay: DanglingOverlay, root: tk.Tk):
        self._overlay = overlay
        self._root = root
        self._text: str = ''
        self._lt_times: deque = deque()    # timestamps of '<' presses
        self._esc_times: deque = deque()   # timestamps of Escape presses
        self._mouse_listener = None

    # --- Called from keyboard listener threads ---

    def handle_key(self, key) -> bool:
        """Return True if key was consumed and should NOT reach the app."""
        global _mode

        try:
            ch = key.char
        except AttributeError:
            ch = None

        is_lt  = (ch == '<')
        is_esc = (key == keyboard.Key.esc)

        # Triple '<' detection — works in all modes
        if is_lt:
            now = time.monotonic()
            self._lt_times.append(now)
            while self._lt_times and now - self._lt_times[0] > self.HOTKEY_WINDOW:
                self._lt_times.popleft()
            if len(self._lt_times) >= 3:
                self._lt_times.clear()
                dbg(f'TRIPLE-< detected, mode={_mode}')
                if _mode == 'IDLE':
                    self._enter_green(backspaces=3)
                else:
                    self._exit_to_idle()
                return True  # consumed

        # Triple Escape detection — works in all modes
        if is_esc:
            now = time.monotonic()
            self._esc_times.append(now)
            while self._esc_times and now - self._esc_times[0] > self.HOTKEY_WINDOW:
                self._esc_times.popleft()
            if len(self._esc_times) >= 3:
                self._esc_times.clear()
                if _mode != 'IDLE':
                    self._exit_to_idle()
                return True  # consumed

        if _mode == 'IDLE':
            return False  # let auto-close / comma-jump handle it

        if _mode == 'GREEN':
            return self._handle_green(key, ch)

        # RED phase: block all typing
        return True

    def _handle_green(self, key, ch) -> bool:
        """Process a key during GREEN phase; always consumes it."""
        if key == keyboard.Key.backspace:
            if self._text:
                self._text = self._text[:-1]
            self._overlay.show_green(self._text)
        elif ch is not None and ch.isprintable() and ch != '<':
            self._text += ch
            self._overlay.show_green(self._text)
        return True

    # --- State transitions ---

    def _enter_green(self, backspaces: int = 0) -> None:
        global _mode
        dbg(f'_enter_green backspaces={backspaces}')
        _mode = 'GREEN'
        self._text = ''
        self._lt_times.clear()
        self._esc_times.clear()
        # Overlay is shown AFTER backspaces (see _cleanup_then_arm), so it
        # cannot steal focus while cleanup keystrokes are in flight.
        self._start_mouse_listener()
        threading.Thread(
            target=self._cleanup_then_arm,
            args=(backspaces,),
            daemon=True,
        ).start()

    def _cleanup_then_arm(self, backspaces: int) -> None:
        """Delete trigger chars from the app, then show overlay and enable suppression."""
        global _inserting
        time.sleep(0.06)   # let all 3 '<' arrive in the app before backspacing
        if backspaces:
            _inserting = True
            try:
                for _ in range(backspaces):
                    controller.press(keyboard.Key.backspace)
                    controller.release(keyboard.Key.backspace)
                    time.sleep(0.015)
            finally:
                _inserting = False
        # Release Shift so the next click isn't treated as a shift-click.
        for mod in (keyboard.Key.shift, keyboard.Key.shift_r):
            try:
                controller.release(mod)
            except Exception:
                pass
        time.sleep(0.04)   # let modifier releases arrive in the app
        # Show overlay only after cleanup — overlay must not steal focus while
        # backspace events are in flight.
        self._overlay.show_green(self._text)

    def _enter_red(self) -> None:
        global _mode
        dbg(f'_enter_red text="{self._text}"')
        _mode = 'RED'
        self._overlay.show_red(self._text)

    def _exit_to_idle(self) -> None:
        global _mode
        dbg('_exit_to_idle')
        _mode = 'IDLE'
        self._text = ''
        self._lt_times.clear()
        self._esc_times.clear()
        self._overlay.hide()
        self._stop_mouse_listener()

    # --- Mouse click handler (mouse listener thread) ---

    def handle_click(self, x, y, button, pressed) -> None:
        if button != mouse.Button.left or not pressed:
            return
        dbg(f'handle_click mode={_mode} text="{self._text}"')
        if _mode == 'GREEN':
            captured = self._text
            self._enter_red()
            # Pause suppression so the injected '<tag>' reaches the app,
            # then re-arm suppression for the RED phase.
            threading.Thread(
                target=self._inject_green,
                args=(captured,),
                daemon=True,
            ).start()
        elif _mode == 'RED':
            captured = self._text
            self._exit_to_idle()   # stops suppress listener, hides overlay
            threading.Thread(
                target=lambda: self._inject_red(captured),
                daemon=True,
            ).start()

    def _inject_red(self, tag: str) -> None:
        """Wait for click to register, then inject closing tag."""
        time.sleep(0.15)
        self._inject(f'</{tag}>')

    def _inject_green(self, tag: str) -> None:
        """Wait for click to register, then inject opening tag."""
        time.sleep(0.15)   # let the click move the cursor in the target app
        self._inject(f'<{tag}>')
        # RED phase needs no suppression — user only clicks, doesn't type

    def _inject(self, text: str) -> None:
        global _inserting
        dbg(f'_inject start text="{text}"')
        for _ in range(10):
            if not _inserting:
                break
            time.sleep(0.02)
        _inserting = True
        try:
            controller.type(text)
            dbg(f'_inject done text="{text}"')
        except Exception as e:
            dbg(f'_inject FAILED: {e}')
        finally:
            _inserting = False

    # --- Mouse listener lifecycle ---

    def _start_mouse_listener(self) -> None:
        if self._mouse_listener is not None:
            return
        self._mouse_listener = mouse.Listener(
            on_click=self.handle_click,
            suppress=False,
        )
        self._mouse_listener.daemon = True
        self._mouse_listener.start()

    def _stop_mouse_listener(self) -> None:
        if self._mouse_listener is not None:
            self._mouse_listener.stop()
            self._mouse_listener = None


# ---------------------------------------------------------------------------
# Auto-close helpers
# ---------------------------------------------------------------------------

def _get_opening_tag(text: str):
    """
    Return the tag name if text ends with a complete, non-void, non-self-closing
    opening tag, else None.
    """
    if text.endswith('/>'):
        return None
    m = re.search(r'<([a-zA-Z][a-zA-Z0-9:_-]*)(?:\s[^>]*)?>$', text)
    if not m:
        return None
    if m.group(1).lower() in VOID_ELEMENTS:
        return None
    return m.group(1)


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
    """Track trigger characters and jump when enough consecutive ones are typed."""
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


# ---------------------------------------------------------------------------
# Keyboard listener callbacks
# ---------------------------------------------------------------------------

def on_press(key) -> None:
    global _buffer

    # Skip while an auto-insertion is in progress
    if _inserting:
        return

    # GREEN mode: build overlay text.  _kbd_intercept suppresses the event
    # AFTER this callback returns, so the char never reaches the app — no
    # echo-cancel or separate suppress listener required.
    if _mode == 'GREEN':
        if _fsm is not None:
            _fsm.handle_key(key)
        return

    # RED mode: user only clicks; no keystrokes to process
    if _mode != 'IDLE':
        return

    # FSM handles <<< detection in IDLE mode
    if _fsm is not None and _fsm.handle_key(key):
        return

    # Buffer / auto-close / comma-jump logic
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

    if char == TRIGGER_CHAR:
        _handle_trigger_char(char)
        return

    with _lock:
        _buffer.append(char)
        if len(_buffer) > MAX_BUFFER:
            _buffer.pop(0)
        snapshot = ''.join(_buffer)

    if char == '>':
        tag_name = _get_opening_tag(snapshot)
        if tag_name:
            threading.Timer(
                0.05, lambda t=tag_name: _insert_closing_tag(t)
            ).start()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    global _fsm, _overlay, _tk_root

    print(f"XML AutoCloser v2.1 — {SYSTEM}")
    print()
    print("  Auto-close  : type an opening tag → closing tag auto-inserted")
    print("  Jump        : press comma twice inside a tag pair")
    print("  Click-Place : triple < (Shift+,) → green overlay → click,click")
    print("  Cancel mode : triple < or triple Escape")
    print()

    if SYSTEM == 'Darwin':
        print("  macOS requires Accessibility permission:")
        print("  System Settings → Privacy & Security → Accessibility")
        print("  Add your Terminal (or Python executable).")
        print()
    elif SYSTEM == 'Linux':
        print("  Note: Wayland support is limited. X11 recommended.")
        print()

    print("  Active. Press Ctrl+C to stop.")
    print()

    _tk_root = tk.Tk()
    _tk_root.withdraw()

    _overlay = DanglingOverlay(_tk_root)
    _fsm = ClickPlacementFSM(_overlay, _tk_root)

    # Single listener with per-event intercept: passes keys through in IDLE mode,
    # suppresses them in GREEN/RED mode so they never reach the text editor.
    listener = keyboard.Listener(
        on_press=on_press,
        suppress=False,
        intercept=_kbd_intercept,
    )
    listener.daemon = True
    listener.start()

    try:
        _tk_root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        listener.stop()
        print("\nXML AutoCloser stopped.")


if __name__ == '__main__':
    main()
