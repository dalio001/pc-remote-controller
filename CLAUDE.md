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

## Panels and keyboard (app.js / styles.css)

Panels **make room, they don't cover**: `setPanelHeight()` measures `panel.offsetHeight` into
`--panel-h`, and `#app.panel-open { padding-bottom: var(--panel-h) }` shrinks the flex column so
`screen-container` (and the letterboxed image inside it) stays fully visible above the panel.
`offsetHeight` is valid even while the panel is still translated off-screen — transforms don't
affect layout. The keyboard height is drag-resizable via `#kbdGrip` (clamped 30–75vh, persisted
as `kbdHeight`), which sets an explicit `height` + `maxHeight: none` to beat the `.panel` 60vh cap.

Keyboard has two layers (`#kbdLetters` / `#kbdSymbols`, toggled by `?123`); symbol keys need no
wiring because the generic `.k[data-k]` handler just `type_text`s the character. Latching
modifiers are **ctrl / alt / win**; `shift` joins `activeModifiers()` only when another modifier
is already latched, so plain Shift+letter keeps the proven `type_text` uppercase path. Because
Win latches, a bare Win press lives in the `start-menu` quick action instead.

## Reaching the PC (three paths, in order of preference)

1. **Home WiFi** — `http://192.168.1.104:8080`. Nothing extra needed.
2. **Tailscale** — `http://100.125.169.102:8080`, works anywhere, encrypted, nothing public,
   but needs the Tailscale app signed in on the phone. Required a firewall rule
   (`PC Remote Controller 8080 (LAN + Tailscale)`, TCP 8080, `RemoteAddress 100.64.0.0/10,
   192.168.1.0/24`): the pre-existing Python allow rules were **Public**-profile only, and the
   Tailscale adapter is **Private**, so tailnet traffic was silently dropped while LAN worked.
   Rules here are port-based on purpose — the venv `python.exe` resolves to the base interpreter,
   so program-path rules are unreliable.
3. **ngrok tunnel** (`ENABLE_TUNNEL=true`) — a stable public https URL, no app on the phone.
   `backend/tunnel.py` spawns ngrok and reads the URL back from its local API at
   `127.0.0.1:4040`. Outbound only, so no inbound firewall rule. Free `ngrok-free.app` domains
   show a one-time browser interstitial; it affects top-level navigation only, not `/ws`.

**Enabling the tunnel makes this PC internet-reachable**, which is why these exist and must not
be loosened: `check_public_exposure()` aborts startup if the tunnel is on with an empty or
sub-12-char password (empty `AUTH_PASSWORD` still means auth *off*); `FAILED_AUTH` throttles
per-IP guessing (5 strikes → 60s, doubling to 15 min) on both the HTTP dependency and the WS
handshake; and `/api/execute` takes an **action key** resolved through `ALLOWED_COMMANDS`, never
a raw string — it reaches `Popen(shell=True)`, so free-form input there was RCE behind one
password.

## Known issues (ordered by impact)

1. **AI control is a stub.** `ai_integration.py` always returns `"actions": []` — Claude chats about
   what it would do but nothing is parsed or executed. The README oversells this. Real fix: tool-use
   loop feeding `InputController` (and a current model — the class-signature default is still the
   deprecated `claude-3-haiku-20240307`).
2. **Multi-monitor mismatch.** Capture uses `mss monitors[0]` (all-monitor union); input scales via
   `pyautogui.size()` (primary). Identical on this single-monitor PC; clicks misalign with 2+ monitors.
3. **Config is global.** A `config` message mutates process-wide singletons — last client wins.
4. **Plain HTTP on the LAN.** Password and screen content cross the local network unencrypted.
   Fine on home WiFi. Off-LAN, use Tailscale (PC is `100.125.169.102`) or the ngrok tunnel,
   which terminates TLS at the edge. **Never port-forward this to the internet** — the tunnel
   is the supported way out, since it needs no inbound rule at all.
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
