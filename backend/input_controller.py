"""Mouse and keyboard control using pyautogui."""
import logging
import subprocess
import sys
import webbrowser

import pyautogui

logger = logging.getLogger(__name__)

# Disable pyautogui failsafe (we handle safety ourselves)
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.01  # Minimal delay between actions

# Key name mapping for common keys
KEY_ALIASES = {
    "space": "space",
    "enter": "enter",
    "return": "enter",
    "tab": "tab",
    "esc": "esc",
    "escape": "esc",
    "backspace": "backspace",
    "delete": "delete",
    "del": "delete",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "home": "home",
    "end": "end",
    "pageup": "pageup",
    "pagedown": "pagedown",
    "pgup": "pageup",
    "pgdn": "pagedown",
    "f1": "f1", "f2": "f2", "f3": "f3", "f4": "f4",
    "f5": "f5", "f6": "f6", "f7": "f7", "f8": "f8",
    "f9": "f9", "f10": "f10", "f11": "f11", "f12": "f12",
    "ctrl": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "win": "win",
    "command": "command",
}


class InputController:
    """Controls mouse and keyboard input on the host PC."""

    def __init__(self):
        self.screen_w, self.screen_h = pyautogui.size()

    def _to_pixels(self, x: float, y: float):
        """Convert relative coords (0.0-1.0) to screen pixels."""
        self.screen_w, self.screen_h = pyautogui.size()
        px = int(x * self.screen_w)
        py = int(y * self.screen_h)
        return px, py

    def move_mouse(self, x: float, y: float):
        """Move mouse to relative position."""
        try:
            px, py = self._to_pixels(x, y)
            pyautogui.moveTo(px, py, duration=0)
        except Exception as e:
            logger.error(f"Mouse move error: {e}")

    def click(self, x: float, y: float, button: str = "left"):
        """Click at relative position."""
        try:
            px, py = self._to_pixels(x, y)
            pyautogui.click(px, py, button=button, duration=0)
        except Exception as e:
            logger.error(f"Click error: {e}")

    def double_click(self, x: float, y: float):
        """Double-click at relative position."""
        try:
            px, py = self._to_pixels(x, y)
            pyautogui.doubleClick(px, py, duration=0)
        except Exception as e:
            logger.error(f"Double click error: {e}")

    def right_click(self, x: float, y: float):
        """Right-click at relative position."""
        try:
            px, py = self._to_pixels(x, y)
            pyautogui.rightClick(px, py, duration=0)
        except Exception as e:
            logger.error(f"Right click error: {e}")

    def drag(self, start_x: float, start_y: float, end_x: float, end_y: float):
        """Drag from start to end (relative coords)."""
        try:
            sx, sy = self._to_pixels(start_x, start_y)
            ex, ey = self._to_pixels(end_x, end_y)
            pyautogui.moveTo(sx, sy, duration=0)
            pyautogui.dragTo(ex, ey, duration=0.2, button="left")
        except Exception as e:
            logger.error(f"Drag error: {e}")

    def scroll(self, x: float, y: float, delta: int):
        """Scroll at position. Positive = up, negative = down."""
        try:
            px, py = self._to_pixels(x, y)
            pyautogui.moveTo(px, py, duration=0)
            pyautogui.scroll(delta * 50)
        except Exception as e:
            logger.error(f"Scroll error: {e}")

    def key_press(self, key: str):
        """Press a single key."""
        try:
            key = KEY_ALIASES.get(key.lower(), key)
            pyautogui.press(key, interval=0)
        except Exception as e:
            logger.error(f"Key press error: {e}")

    def type_text(self, text: str):
        """Type a string of text."""
        try:
            pyautogui.typewrite(text, interval=0.01)
        except Exception as e:
            logger.error(f"Type text error: {e}")

    def hotkey(self, keys: list):
        """Press a key combination like ['ctrl', 'c']."""
        try:
            mapped = [KEY_ALIASES.get(k.lower(), k) for k in keys]
            pyautogui.hotkey(*mapped, interval=0)
        except Exception as e:
            logger.error(f"Hotkey error: {e}")

    def get_screen_size(self):
        """Return (width, height) of the primary screen."""
        return pyautogui.size()

    @staticmethod
    def open_url(url: str):
        """Open a URL in the default browser."""
        try:
            webbrowser.open(url)
        except Exception as e:
            logger.error(f"Open URL error: {e}")

    @staticmethod
    def execute_command(command: str):
        """Execute a system command or open an application."""
        try:
            if sys.platform == "win32":
                subprocess.Popen(command, shell=True)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-a", command])
            else:
                subprocess.Popen(command.split())
        except Exception as e:
            logger.error(f"Execute error: {e}")
