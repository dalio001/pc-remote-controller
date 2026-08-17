"""Public tunnel via ngrok, so the phone needs no VPN app to reach this PC.

The PC dials out to ngrok, which serves a stable https URL. Nothing is
port-forwarded and no inbound firewall rule is needed.

Every failure here is logged with its real cause and left non-fatal: losing the
tunnel must never take down the LAN server, and a silent tunnel failure would
look exactly like "the app is broken" from the phone.
"""
import json
import logging
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

# ngrok's own local dashboard/API, used to read back the assigned public URL.
NGROK_API = "http://127.0.0.1:4040/api/tunnels"


class Tunnel:
    """Owns the ngrok child process."""

    def __init__(self, port: int, authtoken: str = "", domain: str = "", policy_file: str = ""):
        self.port = port
        self.authtoken = authtoken
        self.domain = domain
        self.policy_file = policy_file
        self.proc = None
        self.public_url = ""

    def _ngrok_path(self):
        return shutil.which("ngrok")

    def start(self) -> str:
        """Start ngrok and return the public URL, or "" if it could not start."""
        exe = self._ngrok_path()
        if not exe:
            logger.error(
                "Tunnel enabled but ngrok is not installed or not on PATH. "
                "Install it (winget install ngrok.ngrok) or set ENABLE_TUNNEL=false."
            )
            return ""
        if not self.authtoken:
            logger.error("Tunnel enabled but NGROK_AUTHTOKEN is empty. Get one at dashboard.ngrok.com.")
            return ""

        # Persist the token to ngrok's own config; harmless to repeat.
        try:
            res = subprocess.run(
                [exe, "config", "add-authtoken", self.authtoken],
                capture_output=True, text=True, timeout=30,
            )
            if res.returncode != 0:
                logger.error(f"ngrok rejected the authtoken: {res.stderr.strip() or res.stdout.strip()}")
                return ""
        except Exception as e:
            logger.error(f"Could not configure ngrok authtoken: {e}")
            return ""

        cmd = [exe, "http", str(self.port), "--log", "stdout"]
        if self.domain:
            cmd += ["--domain", self.domain]
        else:
            logger.warning("NGROK_DOMAIN is empty - the public URL will change on every restart.")

        # Edge auth (e.g. Google sign-in) stops strangers before they reach the app.
        # Loud about its absence: silently serving the login page to the whole
        # internet is exactly the situation this is meant to prevent.
        if self.policy_file and os.path.isfile(self.policy_file):
            cmd += ["--traffic-policy-file", self.policy_file]
            logger.info(f"Edge traffic policy: {self.policy_file}")
        else:
            logger.warning(
                "No ngrok traffic policy found - the public URL is protected by the app "
                "password ALONE. Add ngrok-policy.yml to require sign-in at the edge."
            )

        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
        except Exception as e:
            logger.error(f"Could not start ngrok: {e}")
            return ""

        url = self._await_url()
        if url:
            self.public_url = url
            logger.info("=" * 50)
            logger.info(f"  PUBLIC URL (works anywhere): {url}")
            logger.info("=" * 50)
        else:
            # Surface whatever ngrok actually said instead of failing silently.
            detail = self._drain_output()
            logger.error(f"Tunnel did not come up. ngrok said: {detail or '(no output)'}")
            self.stop()
        return url

    def _await_url(self, timeout: float = 20.0) -> str:
        """Poll ngrok's local API until it reports an https tunnel."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc and self.proc.poll() is not None:
                return ""  # ngrok already exited
            try:
                with urllib.request.urlopen(NGROK_API, timeout=2) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                for t in data.get("tunnels", []):
                    pub = t.get("public_url", "")
                    if pub.startswith("https://"):
                        return pub
            except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError):
                pass  # API not listening yet; keep waiting until the deadline
            time.sleep(0.5)
        return ""

    def _drain_output(self, limit: int = 800) -> str:
        """Best-effort read of ngrok's output for the error message."""
        if not self.proc or not self.proc.stdout:
            return ""
        try:
            if self.proc.poll() is not None:
                return (self.proc.stdout.read() or "")[-limit:].strip()
        except Exception:
            pass
        return ""

    def stop(self):
        if not self.proc:
            return
        try:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            logger.info("Tunnel stopped")
        except Exception as e:
            logger.error(f"Error stopping tunnel: {e}")
        finally:
            self.proc = None
            self.public_url = ""
