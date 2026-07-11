"""Claude AI integration for natural language PC control."""
import logging
import os

import requests

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a PC control assistant. You help users control their computer through natural language commands.

Available actions you can perform:
- click(x, y) - Click at screen position (0.0-1.0 coordinates)
- double_click(x, y) - Double-click at position
- right_click(x, y) - Right-click at position
- type(text) - Type text on the keyboard
- press_key(key) - Press a single key (enter, esc, tab, space, up, down, left, right, etc.)
- hotkey(keys) - Press key combination (e.g., ctrl+c, win+d, alt+f4)
- open_url(url) - Open a URL in the default browser
- open_application(name) - Open an application
- scroll(x, y, amount) - Scroll at position

When the user asks you to do something, respond with:
1. A brief confirmation of what you'll do
2. The specific action steps

Keep responses concise and friendly. If you're unsure about coordinates, ask the user to clarify."""


class AIController:
    """Integration with Anthropic Claude API for AI-powered PC control."""

    def __init__(self, api_key: str = None, model: str = "claude-3-haiku-20240307"):
        self.api_key = api_key or os.getenv("CLAUDE_API_KEY", "")
        self.model = model
        self.api_url = "https://api.anthropic.com/v1/messages"

    def is_configured(self) -> bool:
        """Check if API key is set."""
        return bool(self.api_key) and self.api_key.startswith("sk-")

    def process_command(self, command: str) -> dict:
        """Send a natural language command to Claude and return the response."""
        if not self.is_configured():
            return {
                "response": "AI is not configured. Please add your Claude API key in Settings. Get one at https://console.anthropic.com/",
                "actions": []
            }

        try:
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }

            payload = {
                "model": self.model,
                "max_tokens": 500,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": command}]
            }

            resp = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()

            ai_text = data.get("content", [{}])[0].get("text", "No response")
            return {"response": ai_text, "actions": []}

        except requests.exceptions.Timeout:
            return {"response": "AI request timed out. Please try again.", "actions": []}
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                return {"response": "Invalid API key. Please check your Claude API key in Settings.", "actions": []}
            return {"response": f"AI API error: {e.response.status_code}. Please try again.", "actions": []}
        except Exception as e:
            logger.error(f"AI error: {e}")
            return {"response": f"AI error: {str(e)}", "actions": []}
