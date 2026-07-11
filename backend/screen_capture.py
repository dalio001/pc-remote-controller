"""Screen capture engine using mss + Pillow for high performance."""
import base64
import io
import threading
import logging

from PIL import Image
import mss

logger = logging.getLogger(__name__)


class ScreenCapture:
    """Thread-safe screen capture with scaling and JPEG encoding."""

    def __init__(self, scale_factor: float = 0.5, quality: int = 70):
        self.scale_factor = scale_factor
        self.quality = quality
        self._lock = threading.Lock()
        self._sct = None

    def _get_sct(self):
        """Lazy init mss capture instance (thread-local)."""
        if self._sct is None:
            self._sct = mss.mss()
        return self._sct

    def get_frame(self):
        """Capture screen, scale, encode to JPEG. Returns (jpeg_bytes, (width, height))."""
        try:
            with self._lock:
                sct = self._get_sct()
                monitor = sct.monitors[0]  # Full screen (all monitors)
                raw = sct.grab(monitor)

            # Convert to PIL Image
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            orig_w, orig_h = img.size

            # Scale down
            if self.scale_factor < 1.0:
                new_w = max(1, int(orig_w * self.scale_factor))
                new_h = max(1, int(orig_h * self.scale_factor))
                img = img.resize((new_w, new_h), Image.LANCZOS)

            # Encode JPEG
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=self.quality, optimize=True)
            jpeg_bytes = buf.getvalue()

            return jpeg_bytes, (img.width, img.height)
        except Exception as e:
            logger.error(f"Screen capture error: {e}")
            return None, (0, 0)

    def get_screenshot(self):
        """Get a single full-resolution screenshot as JPEG bytes."""
        try:
            with self._lock:
                sct = self._get_sct()
                monitor = sct.monitors[0]
                raw = sct.grab(monitor)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=90, optimize=True)
            return buf.getvalue(), (img.width, img.height)
        except Exception as e:
            logger.error(f"Screenshot error: {e}")
            return None, (0, 0)

    def get_screen_size(self):
        """Return (width, height) of the primary monitor."""
        try:
            with self._lock:
                sct = self._get_sct()
                monitor = sct.monitors[0]
            return monitor["width"], monitor["height"]
        except Exception:
            return 1920, 1080

    def close(self):
        """Release resources."""
        if self._sct:
            self._sct.close()
            self._sct = None
