# PC Remote Controller

Control your PC remotely from your phone! View your screen, click, type, and even use AI to control your computer - all from your mobile browser.

---

## What This Does

- **View your PC screen** on your phone in real-time
- **Tap to click**, double-tap to double-click, long-press to right-click
- **Type** using the on-screen keyboard or text input
- **Use AI** (Claude) to control your PC with natural language ("Open Chrome", "Type my password")
- **Quick actions** - open browser, file explorer, terminal, copy/paste, etc.
- **Navigation pad** for arrow keys, Enter, Esc, Tab
- **Works on your local network** - no internet required!

---

## Quick Start

### Step 1: Download This Project

Download and extract this folder to your PC.

### Step 2: Install Python (if not already installed)

**Windows:**
1. Go to https://www.python.org/downloads/
2. Download Python 3.9 or higher
3. **IMPORTANT:** During installation, check the box "Add Python to PATH"
4. Click "Install Now"

**Mac:**
1. Open Terminal
2. Run: `brew install python3` (if you have Homebrew)
   - Or download from https://www.python.org/downloads/

**Linux:**
```bash
sudo apt update && sudo apt install python3 python3-pip
```

### Step 3: Run Setup

**Windows:**
Double-click `setup.bat`

**Mac/Linux:**
Open Terminal in this folder and run:
```bash
./setup.sh
```

This installs all required Python packages automatically.

### Step 4: Start the Server

**Windows:**
Double-click `run.bat`

**Mac/Linux:**
```bash
./run.sh
```

You will see a message like:
```
OPEN THIS URL ON YOUR PHONE:
http://192.168.1.100:8080
```

### Step 5: Open on Your Phone

1. Make sure your phone is on the **same WiFi** as your PC
2. Open your phone's browser (Chrome, Safari, etc.)
3. Type the URL shown (e.g., `http://192.168.1.100:8080`)
4. You should see your PC screen!

---

## How to Use

### Screen Controls (Touch)
| Gesture | Action |
|---------|--------|
| **Single tap** | Left click |
| **Double tap** | Double click |
| **Long press** (hold 0.5s) | Right click |
| **Drag** | Move mouse / drag |
| **Two-finger swipe** | Scroll up/down |

### Bottom Buttons
- **Mouse** - Hide panels, pure screen control
- **Keys** - Open virtual keyboard + text input
- **AI** - Chat with Claude to control your PC
- **Capture** - Save a screenshot to your phone
- **Nav** - Directional pad + action buttons

### Quick Action Bar (above bottom buttons)
Quick buttons for: Open Browser, File Explorer, Terminal, Copy, Paste, Task Manager, Show Desktop, Lock PC

---

## AI Integration (Optional)

To use the AI assistant, you need a Claude API key:

1. Go to https://console.anthropic.com/
2. Sign up / log in
3. Go to "API Keys" and create a new key
4. Open the app on your phone
5. Tap the **gear icon (Settings)**
6. Paste your API key in "Claude API Key"
7. Tap **Save**

Now you can chat with the AI! Try commands like:
- "Open Chrome"
- "Open the Start menu"
- "Type hello world in the document"
- "Click the OK button"
- "Open my Documents folder"
- "Lock the computer"

---

## Troubleshooting

### "Cannot connect" on phone
- Make sure both devices are on the **same WiFi network**
- Check your PC's firewall isn't blocking port 8080
- Try disabling firewall temporarily to test
- Try accessing `http://localhost:8080` on your PC first

### Screen is laggy
- Open Settings (gear icon) on your phone
- Reduce Quality to 50
- Reduce FPS to 10
- Reduce Scale to 25%

### "Python is not installed"
- Install Python from https://www.python.org/downloads/
- Make sure to check "Add Python to PATH" during installation

### Setup script fails
Try running this manually:
```bash
pip install fastapi uvicorn websockets python-multipart mss Pillow pynput pyautogui psutil requests python-dotenv
```

### Permission denied (Mac/Linux)
Make scripts executable:
```bash
chmod +x setup.sh run.sh
```

---

## Security Notes

- This tool runs on your **local network only** - it's not exposed to the internet
- Anyone on your WiFi can access it while it's running
- You can set a password in Settings for basic protection
- Stop the server (close the window) when not in use
- Keep your Claude API key private - don't share it

---

## Requirements

- **PC:** Windows 10/11, macOS, or Linux
- **Python:** 3.9 or higher
- **Phone:** Any modern smartphone with a web browser
- **Network:** Both devices on the same WiFi

---

## Stopping the Server

Simply close the command window (Windows) or press `Ctrl+C` in the terminal (Mac/Linux).

---

## Made for Remote Control

Perfect for:
- Managing downloads on your PC from the couch
- Clicking "Authorize" or "Allow" prompts remotely
- Controlling media playback
- Quick file management
- Any task that requires direct PC interaction!
