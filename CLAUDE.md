# PC Remote Controller

Control this Windows PC from a phone browser on the same WiFi. FastAPI server on port 8080;
vanilla JS frontend served from `backend/static/`; one WebSocket carries screen frames down and
mouse/keyboard input up; a small HTTP API handles screenshots, AI commands, and app launching.
LAN only, plain HTTP, password-protected.

**Run it**: `run.bat` (creates/uses `.venv` — never system Python). Phone opens `http://<LAN-IP>:8080`,
enters the password from `.env` (`AUTH_PASSWORD=...`) via the gear icon.

## Architecture

- `backend/main.py` — FastAPI app: auth, HTTP API, WebSocket (auth handshake → frame stream + input loop), SPA fallback
- `backend/screen_capture.py` — mss + Pillow; scaled JPEG frames
- `backend/input_controller.py` — pyautogui; relative 0–1 coords → pixels; `KEY_ALIASES` maps key names
- `backend/ai_integration.py` — Claude API call for the AI chat panel
- `backend/static/` — `index.html` + `app.js` + `styles.css`, no framework, no build step
- `backend/config.py` — env-driven settings, loaded from `.env`

## Current priority: make it function properly

PR #1 (working setup + auth) is merged. Still unverified on an actual phone (desktop checks
passed): latched Ctrl/Alt (tap Ctrl then C → real copy, not a typed "c"), double-tap → exactly one
double-click, click ripple lands under the fingertip, Reset applies immediately, error toast on
wrong password — plus the pro-controls gestures below.

## Touch gestures (app.js)

One two-finger gesture = one mode, decided by first movement: finger distance change → pinch zoom
(CSS transform on `#screenImg` only — `getBoundingClientRect()` reflects transforms, so all
coordinate math works unchanged while zoomed); parallel motion → scroll at 1×, pan when zoomed.
`gesture.multiTouch` suppresses `touchend` clicks until every finger lifts. One finger: tap =
click, double-tap = double click (second single click suppressed), long-press = right click,
**double-tap-and-hold + move = drag** (sent as one-shot `mouse_drag` on release). Zoom badge
(top-left) resets zoom; its events must not bubble into the screen container.

## Known issues (ordered by impact)

1. **AI control is a stub.** `ai_integration.py` always returns `"actions": []` — Claude chats about
   what it would do but nothing is parsed or executed. The README oversells this. Real fix: tool-use
   loop feeding `InputController` (and a current model — the class-signature default is still the
   deprecated `claude-3-haiku-20240307`).
2. **Multi-monitor mismatch.** Capture uses `mss monitors[0]` (all-monitor union); input scales via
   `pyautogui.size()` (primary). Identical on this single-monitor PC; clicks misalign with 2+ monitors.
3. **Config is global.** A `config` message mutates process-wide singletons — last client wins.
4. **Plain HTTP.** Password and screen content cross the LAN unencrypted. Fine on home WiFi; use
   Tailscale for anything beyond it (PC is `100.125.169.102` on Mohamed's tailnet). Never
   port-forward this to the internet.
5. **Drag is one-shot.** Double-tap-hold sends a single `mouse_drag` from→to on release; there is
   no live drag feedback while the finger moves.

## Rules — each exists because of a real bug here

- **Never swallow errors.** The defining bug class of this codebase is the silent failure: the dead
  Settings gear was `els[name + 'Panel']` → `undefined` behind an `if (panel)` guard; HTTP 401s were
  invisible behind empty catches. Frontend: check `resp.ok`, surface via `showToast`/`errorText`
  (`app.js`). Backend: log it.
- **Static responses keep `Cache-Control: no-cache`** (`static_file()` in `main.py`). Mobile Chrome
  heuristic-caches JS without it, making every frontend fix look like it did nothing.
- **The SPA catch-all stays registered last** in `main.py`. Its `{path:path}` converter matches
  slashes and silently 404'd `GET /api/system/info` when it sat above the API routes.
- **Every API endpoint gets `Depends(require_auth)`; the WebSocket requires the auth message as its
  first frame.** Comparisons via `secrets.compare_digest`. Empty `AUTH_PASSWORD` = auth off (upgrade
  compatibility).
- **Verify on the phone, not a desktop viewport.** The dead-panels bug survived a desktop check
  because nobody tapped the buttons there.
- **`.env` stays out of git** (`.gitignore` covers it). Note it carries a UTF-8 BOM — python-dotenv
  handles that, naive line parsers read `﻿AUTH_PASSWORD` and fail.
- **Windows-first.** No Linux shortcuts (ctrl+alt+t was a silent no-op for the Terminal button).
  Detached launches go through `/api/execute` with the `start <app>` pattern. Key names must route
  through `KEY_ALIASES`; modifiers use the `hotkey` message, since a bare `key_press` of ctrl/alt is a
  meaningless press-and-release.

## Deliberate decisions (don't "fix" these)

- **Reset doesn't clear the password/API key** — clearing the password would drop the connection and
  lock the user out of the very panel needed to get back in. It resets stream settings only.
- **Double tap suppresses the second single click** rather than delaying every tap by 300ms — the
  first tap's click still lands, matching real mouse select-then-open semantics.
- **`no-cache`, not `no-store`** — files are still cached, just revalidated; a 304 on LAN is free.
- **Trust model is "everyone on the WiFi is Mohamed."** Single user, home network. Per-client config
  and TLS are worth doing only if that changes.
