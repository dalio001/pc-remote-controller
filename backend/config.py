"""Configuration settings for PC Remote Controller."""
import os
from dotenv import load_dotenv

load_dotenv()

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))

# Screen Capture
FRAME_RATE = int(os.getenv("FRAME_RATE", "20"))  # Target FPS
JPEG_QUALITY = int(os.getenv("JPEG_QUALITY", "70"))  # 1-100
SCALE_FACTOR = float(os.getenv("SCALE_FACTOR", "0.5"))  # 0.25-1.0

# AI
ENABLE_AI = os.getenv("ENABLE_AI", "true").lower() == "true"
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")

# Security
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "")

# Public tunnel (ngrok). Off by default: enabling it publishes this PC to the
# internet, where the only thing between a stranger and full mouse/keyboard
# control is AUTH_PASSWORD.
ENABLE_TUNNEL = os.getenv("ENABLE_TUNNEL", "false").lower() == "true"
NGROK_AUTHTOKEN = os.getenv("NGROK_AUTHTOKEN", "")
NGROK_DOMAIN = os.getenv("NGROK_DOMAIN", "")
# Minimum password length accepted when the tunnel is on.
MIN_PUBLIC_PASSWORD_LEN = 12

# Paths
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
