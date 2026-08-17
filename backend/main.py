"""FastAPI main application for PC Remote Controller."""
import asyncio
import base64
import logging
import os
import platform
import secrets
import sys
import time
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import (
    HOST, PORT, FRAME_RATE, JPEG_QUALITY, SCALE_FACTOR,
    ENABLE_AI, CLAUDE_API_KEY, CLAUDE_MODEL, STATIC_DIR, AUTH_PASSWORD,
    ENABLE_TUNNEL, NGROK_AUTHTOKEN, NGROK_DOMAIN, MIN_PUBLIC_PASSWORD_LEN
)
from backend.screen_capture import ScreenCapture
from backend.input_controller import InputController
from backend.ai_integration import AIController
from backend.tunnel import Tunnel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# ===== Startup safety =====
def check_public_exposure():
    """Refuse to publish an unlocked PC to the internet.

    An empty AUTH_PASSWORD means auth is OFF (see password_ok). That is a
    reasonable default on a private LAN and a catastrophe behind a public URL,
    so the tunnel and a weak password must never combine.
    """
    if not ENABLE_TUNNEL:
        return
    if not AUTH_PASSWORD:
        raise RuntimeError(
            "ENABLE_TUNNEL=true with an empty AUTH_PASSWORD would publish this PC "
            "to the internet with no password at all. Set AUTH_PASSWORD in .env."
        )
    if len(AUTH_PASSWORD) < MIN_PUBLIC_PASSWORD_LEN:
        raise RuntimeError(
            f"AUTH_PASSWORD is only {len(AUTH_PASSWORD)} characters. The tunnel makes this "
            f"PC reachable from the internet, so at least {MIN_PUBLIC_PASSWORD_LEN} are required."
        )


# ===== Lifespan =====
async def lifespan(app: FastAPI):
    """Manage startup and shutdown."""
    logger.info("=" * 50)
    logger.info("  PC Remote Controller Starting...")
    logger.info("=" * 50)
    logger.info(f"Static files: {STATIC_DIR}")
    logger.info(f"Screen: {FRAME_RATE} FPS, Quality: {JPEG_QUALITY}, Scale: {SCALE_FACTOR}")
    logger.info(f"AI: {'Enabled' if ENABLE_AI else 'Disabled'}")
    logger.info(f"Auth: {'Enabled' if AUTH_PASSWORD else 'DISABLED (no password set)'}")

    if ENABLE_TUNNEL:
        logger.warning("Tunnel enabled - this PC will be reachable from the internet.")
        lifespan.tunnel = Tunnel(PORT, NGROK_AUTHTOKEN, NGROK_DOMAIN)
        lifespan.tunnel.start()
    else:
        logger.info("Tunnel: Disabled (LAN + Tailscale only)")

    yield

    logger.info("Shutting down...")
    if getattr(lifespan, "tunnel", None):
        lifespan.tunnel.stop()
    if hasattr(lifespan, "capture"):
        lifespan.capture.close()

# Fail fast, before the socket is even opened, if the tunnel would expose an
# unlocked PC.
check_public_exposure()

app = FastAPI(title="PC Remote Controller", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared instances
lifespan.capture = ScreenCapture(scale_factor=SCALE_FACTOR, quality=JPEG_QUALITY)
lifespan.input = InputController()
lifespan.ai = AIController(api_key=CLAUDE_API_KEY, model=CLAUDE_MODEL)
lifespan.fps = FRAME_RATE


def password_ok(provided: str) -> bool:
    """Constant-time password check. No password configured means auth is off."""
    if not AUTH_PASSWORD:
        return True
    return secrets.compare_digest(provided or "", AUTH_PASSWORD)


# ===== Brute-force throttling =====
# A public URL means anyone can try passwords as fast as the network allows, so
# failures cost the caller time. Keyed by client IP: [failure count, locked until].
FAILED_AUTH = {}
MAX_ATTEMPTS = 5
BASE_LOCKOUT = 60      # seconds, after MAX_ATTEMPTS failures
MAX_LOCKOUT = 15 * 60  # doubling is capped here


def lockout_remaining(ip: str) -> int:
    """Seconds left on this IP's lockout, 0 if it may try again."""
    entry = FAILED_AUTH.get(ip)
    if not entry:
        return 0
    remaining = entry[1] - time.time()
    if remaining <= 0:
        return 0
    return int(remaining) + 1


def record_auth_failure(ip: str):
    entry = FAILED_AUTH.setdefault(ip, [0, 0.0])
    entry[0] += 1
    if entry[0] >= MAX_ATTEMPTS:
        # 5th failure -> 60s, 6th -> 120s, ... capped at MAX_LOCKOUT.
        penalty = min(BASE_LOCKOUT * (2 ** (entry[0] - MAX_ATTEMPTS)), MAX_LOCKOUT)
        entry[1] = time.time() + penalty
        logger.warning(f"Auth lockout: {ip} blocked for {penalty}s after {entry[0]} failures")


def record_auth_success(ip: str):
    FAILED_AUTH.pop(ip, None)


def check_auth(provided: str, ip: str) -> tuple:
    """Return (ok, detail). Locked-out callers are refused without a password check."""
    if not AUTH_PASSWORD:
        return True, ""
    wait = lockout_remaining(ip)
    if wait:
        return False, f"Too many failed attempts. Try again in {wait}s."
    if password_ok(provided):
        record_auth_success(ip)
        return True, ""
    record_auth_failure(ip)
    logger.warning(f"Failed auth from {ip}")
    return False, "Invalid password"


def require_auth(request: Request, x_auth_password: str = Header(default="")):
    ip = request.client.host if request.client else "unknown"
    ok, detail = check_auth(x_auth_password, ip)
    if not ok:
        # 429 when throttled so the client can tell "wrong password" from "slow down".
        status = 429 if detail.startswith("Too many") else 401
        raise HTTPException(status_code=status, detail=detail)

os.makedirs(STATIC_DIR, exist_ok=True)


# ===== API Endpoints =====
@app.post("/api/screenshot", dependencies=[Depends(require_auth)])
async def take_screenshot():
    """Take a single full-resolution screenshot."""
    try:
        jpeg_bytes, (w, h) = lifespan.capture.get_screenshot()
        if jpeg_bytes:
            b64 = base64.b64encode(jpeg_bytes).decode("utf-8")
            return {"image": b64, "width": w, "height": h}
        return JSONResponse({"error": "Failed to capture"}, status_code=500)
    except Exception as e:
        logger.error(f"Screenshot error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/ai/command", dependencies=[Depends(require_auth)])
async def ai_command(request: dict):
    """Process a natural language command via Claude AI."""
    try:
        command = request.get("command", "")
        if not command:
            return JSONResponse({"error": "No command provided"}, status_code=400)

        api_key = request.get("api_key", "")
        if api_key:
            lifespan.ai.api_key = api_key

        result = lifespan.ai.process_command(command)
        return result
    except Exception as e:
        logger.error(f"AI command error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/system/info", dependencies=[Depends(require_auth)])
async def system_info():
    """Get system information."""
    try:
        w, h = lifespan.input.get_screen_size()
        return {
            "os": platform.system(),
            "hostname": platform.node(),
            "screen_width": w,
            "screen_height": h,
            "platform": platform.platform(),
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/open", dependencies=[Depends(require_auth)])
async def open_url(request: dict):
    """Open an http(s) URL in the default browser."""
    try:
        url = request.get("url", "")
        if not url:
            return JSONResponse({"error": "No URL provided"}, status_code=400)
        # http/https only: webbrowser.open would happily hand file:// or a custom
        # protocol handler to the OS.
        if urlparse(url).scheme not in ("http", "https"):
            logger.warning(f"Rejected non-http URL: {url!r}")
            return JSONResponse({"error": "Only http and https URLs are allowed"}, status_code=400)
        lifespan.input.open_url(url)
        return {"status": "opened", "url": url}
    except Exception as e:
        logger.error(f"Open URL error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# Allowlist, not free-form strings. This endpoint reaches Popen(shell=True), so
# accepting an arbitrary "command" was remote code execution behind one password -
# survivable on a private LAN, unacceptable once the tunnel makes it public.
# Callers send an action key; the command itself is a constant defined here.
ALLOWED_COMMANDS = {
    "terminal": "start wt",
    "explorer": "start explorer",
    "notepad": "start notepad",
    "calculator": "start calc",
    "settings": "start ms-settings:",
    "task-manager": "start taskmgr",
}


@app.post("/api/execute", dependencies=[Depends(require_auth)])
async def execute_command(request: dict):
    """Launch one of the allowlisted applications by action key."""
    try:
        action = request.get("action") or request.get("command", "")
        command = ALLOWED_COMMANDS.get(action)
        if not command:
            logger.warning(f"Rejected non-allowlisted execute action: {action!r}")
            return JSONResponse(
                {"error": f"Unknown action. Allowed: {', '.join(sorted(ALLOWED_COMMANDS))}"},
                status_code=400,
            )
        lifespan.input.execute_command(command)
        return {"status": "executed", "action": action}
    except Exception as e:
        logger.error(f"Execute error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ===== Static files / SPA fallback =====
# Registered last on purpose: the catch-all below uses a `path` converter, which
# matches slashes and would otherwise shadow every GET /api/* route.
def static_file(path: str) -> FileResponse:
    """Serve a static file, telling the browser to revalidate rather than reuse.

    Phones aggressively heuristic-cache JS with no Cache-Control, which makes
    frontend edits look like they did nothing. "no-cache" still caches - it just
    forces an ETag check, which is a cheap 304 over a LAN.
    """
    return FileResponse(path, headers={"Cache-Control": "no-cache"})


@app.get("/")
async def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return static_file(index_path)
    return JSONResponse({"status": "PC Remote Controller API is running"})


@app.get("/{path:path}")
async def serve_spa(path: str):
    """Serve index.html for SPA routing (except API paths)."""
    if path.startswith("api/") or path == "ws":
        return JSONResponse({"error": "Not found"}, status_code=404)
    static_root = os.path.realpath(STATIC_DIR)
    file_path = os.path.realpath(os.path.join(static_root, path))
    try:
        contained = os.path.commonpath([static_root, file_path]) == static_root
    except ValueError:
        # Different drives (e.g. a "/C:/Windows/..." request) - never contained.
        contained = False
    if contained and os.path.isfile(file_path):
        return static_file(file_path)
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return static_file(index_path)
    return JSONResponse({"error": "Not found"}, status_code=404)


# ===== WebSocket =====
async def stream_screen(websocket: WebSocket):
    """Background task: capture screen and send frames."""
    logger.info("Screen streaming started")

    try:
        while True:
            if websocket.client_state != WebSocketState.CONNECTED:
                break

            frame_delay = 1.0 / max(1, lifespan.fps)
            jpeg_bytes, (w, h) = lifespan.capture.get_frame()
            if jpeg_bytes:
                b64 = base64.b64encode(jpeg_bytes).decode("utf-8")
                msg = {
                    "type": "frame",
                    "data": b64,
                    "width": w,
                    "height": h
                }
                try:
                    await websocket.send_json(msg)
                except Exception:
                    break

            await asyncio.sleep(frame_delay)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Stream error: {e}")
    finally:
        logger.info("Screen streaming stopped")


async def handle_control(websocket: WebSocket):
    """Handle incoming control messages from client."""
    inp = lifespan.input

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if msg_type == "config":
                # Update capture settings
                quality = data.get("quality")
                scale = data.get("scale")
                fps = data.get("fps")
                if quality is not None:
                    lifespan.capture.quality = max(10, min(100, quality))
                if scale is not None:
                    lifespan.capture.scale_factor = max(0.25, min(1.0, scale))
                if fps is not None:
                    lifespan.fps = max(1, min(60, fps))
                continue

            if msg_type == "mouse_move":
                inp.move_mouse(data.get("x", 0), data.get("y", 0))

            elif msg_type == "mouse_click":
                inp.click(data.get("x", 0), data.get("y", 0), data.get("button", "left"))

            elif msg_type == "mouse_double_click":
                inp.double_click(data.get("x", 0), data.get("y", 0))

            elif msg_type == "mouse_right_click":
                inp.right_click(data.get("x", 0), data.get("y", 0))

            elif msg_type == "mouse_drag":
                inp.drag(
                    data.get("fromX", 0), data.get("fromY", 0),
                    data.get("x", 0), data.get("y", 0)
                )

            elif msg_type == "scroll":
                inp.scroll(data.get("x", 0), data.get("y", 0), data.get("delta", 0))

            elif msg_type == "key_press":
                inp.key_press(data.get("key", ""))

            elif msg_type == "type_text":
                inp.type_text(data.get("text", ""))

            elif msg_type == "hotkey":
                keys = data.get("keys", [])
                if keys:
                    inp.hotkey(keys)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Control handler error: {e}")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    if AUTH_PASSWORD:
        ip = websocket.client.host if websocket.client else "unknown"
        try:
            first = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        except Exception:
            await websocket.close(code=1008)
            return
        ok, detail = (False, "Invalid password")
        if first.get("type") == "auth":
            ok, detail = check_auth(first.get("password", ""), ip)
        if not ok:
            logger.warning(f"Rejected unauthenticated client: {websocket.client} ({detail})")
            await websocket.send_json({"type": "auth_failed", "detail": detail})
            await websocket.close(code=1008)
            return
        await websocket.send_json({"type": "auth_ok"})

    logger.info(f"Client connected: {websocket.client}")

    # Start screen stream and control handler concurrently
    stream_task = asyncio.create_task(stream_screen(websocket))
    control_task = asyncio.create_task(handle_control(websocket))

    try:
        # Wait for either task to finish (usually control handler when client disconnects)
        done, pending = await asyncio.wait(
            [stream_task, control_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        # Cancel remaining tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        logger.info("Client disconnected")
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
            except Exception:
                pass


# ===== Entry Point =====
if __name__ == "__main__":
    import uvicorn

    # Print access info
    import socket
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = "localhost"

    print("\n" + "=" * 50)
    print("  PC Remote Controller is running!")
    print("=" * 50)
    print(f"  Local:   http://localhost:{PORT}")
    print(f"  Network: http://{local_ip}:{PORT}")
    print("=" * 50)
    print("  Open the Network URL on your phone")
    print("  (both devices must be on the same WiFi)")
    print("=" * 50 + "\n")

    uvicorn.run(
        "backend.main:app",
        host=HOST,
        port=PORT,
        log_level="warning",
        access_log=False
    )
