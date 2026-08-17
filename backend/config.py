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

# Paths
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
