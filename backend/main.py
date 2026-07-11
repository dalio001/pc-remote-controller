"""FastAPI main application for PC Remote Controller."""
import asyncio
import base64
import logging
import os
import platform
import sys
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import (
    HOST, PORT, FRAME_RATE, JPEG_QUALITY, SCALE_FACTOR,
    ENABLE_AI, CLAUDE_API_KEY, CLAUDE_MODEL, STATIC_DIR, AUTH_PASSWORD
)
from backend.screen_capture import ScreenCapture
from backend.input_controller import InputController
from backend.ai_integration import AIController

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# ===== Lifespan =====
async def lifespan(app: FastAPI):
    """Manage startup and shutdown."""
    logger.info("=" * 50)
    logger.info("  PC Remote Controller Starting...")
    logger.info("=" * 50)
    logger.info(f"Static files: {STATIC_DIR}")
    logger.info(f"Screen: {FRAME_RATE} FPS, Quality: {JPEG_QUALITY}, Scale: {SCALE_FACTOR}")
    logger.info(f"AI: {'Enabled' if ENABLE_AI else 'Disabled'}")
    yield
    logger.info("Shutting down...")
    if hasattr(lifespan, "capture"):
        lifespan.capture.close()

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

# Static files (React frontend build output)
if os.path.isdir(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")
else:
    os.makedirs(STATIC_DIR, exist_ok=True)


# ===== SPA Fallback - serve index.html for all routes =====
@app.get("/")
async def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({"status": "PC Remote Controller API is running"})


@app.get("/{path:path}")
async def serve_spa(path: str):
    """Serve index.html for SPA routing (except API paths)."""
    if path.startswith("api/") or path == "ws":
        return JSONResponse({"error": "Not found"}, status_code=404)
    file_path = os.path.join(STATIC_DIR, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({"error": "Not found"}, status_code=404)


# ===== API Endpoints =====
@app.post("/api/screenshot")
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


@app.post("/api/ai/command")
async def ai_command(request: dict):
    """Process a natural language command via Claude AI."""
    try:
        command = request.get("command", "")
        if not command:
            return JSONResponse({"error": "No command provided"}, status_code=400)

        result = lifespan.ai.process_command(command)
        return result
    except Exception as e:
        logger.error(f"AI command error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/system/info")
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


@app.post("/api/open")
async def open_url(request: dict):
    """Open a URL in the default browser."""
    try:
        url = request.get("url", "")
        if url:
            lifespan.input.open_url(url)
            return {"status": "opened", "url": url}
        return JSONResponse({"error": "No URL provided"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/execute")
async def execute_command(request: dict):
    """Execute a system command or open an application."""
    try:
        command = request.get("command", "")
        if command:
            lifespan.input.execute_command(command)
            return {"status": "executed", "command": command}
        return JSONResponse({"error": "No command provided"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ===== WebSocket =====
async def stream_screen(websocket: WebSocket):
    """Background task: capture screen and send frames."""
    frame_delay = 1.0 / FRAME_RATE
    logger.info("Screen streaming started")

    try:
        while True:
            if websocket.client_state.DISCONNECTED:
                break

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
                # FPS is handled by frame_delay in stream_screen
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
        await websocket.close()


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
