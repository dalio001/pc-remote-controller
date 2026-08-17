/**
 * PC Remote Controller - Frontend App
 * Mobile-optimized touch controls for remote PC access
 */

// ===== State =====
const state = {
  ws: null, connected: false, connecting: false,
  frameUrl: null, screenWidth: 1920, screenHeight: 1080,
  shift: false, fnMode: false, symMode: false, activePanel: null,
  reconnectTimer: null, reconnectAttempts: 0, authFailed: false, authDetail: '',
  pingInterval: null,
  lastClickTimer: null,
  modifiers: { ctrl: false, alt: false, win: false },
  // Client-side zoom of the remote screen. Implemented as a CSS transform on the
  // image, so getBoundingClientRect() - and therefore every existing coordinate
  // calculation - keeps working untouched.
  view: { zoom: 1, panX: 0, panY: 0 },
  settings: {
    quality: +localStorage.getItem('quality') || 70,
    fps: +localStorage.getItem('fps') || 20,
    scale: +localStorage.getItem('scale') || 0.5,
    apiKey: localStorage.getItem('apiKey') || '',
    password: localStorage.getItem('password') || '',
  }
};

// ===== DOM Elements =====
const $ = id => document.getElementById(id);
const els = {
  status: $('status'), statusDot: $('statusDot'), statusText: $('statusText'),
  screenContainer: $('screenContainer'), screenImg: $('screenImg'), overlay: $('overlay'),
  clickIndicator: $('clickIndicator'),
  navPanel: $('navPanel'), keyboardPanel: $('keyboardPanel'), aiPanel: $('aiPanel'), settingsPanel: $('settingsPanel'),
  aiMessages: $('aiMessages'), aiInput: $('aiInput'), aiSendBtn: $('aiSendBtn'),
  textInput: $('textInput'), sendTextBtn: $('sendTextBtn'),
  qualityRange: $('qualityRange'), qualityValue: $('qualityValue'),
  fpsRange: $('fpsRange'), fpsValue: $('fpsValue'),
  scaleRange: $('scaleRange'), scaleValue: $('scaleValue'),
  apiKeyInput: $('apiKeyInput'), passwordInput: $('passwordInput'),
  zoomBadge: $('zoomBadge'), fullscreenBtn: $('fullscreenBtn'),
  app: $('app'), kbdGrip: $('kbdGrip'), kbdLetters: $('kbdLetters'), kbdSymbols: $('kbdSymbols'),
};

// ===== WebSocket =====
function connect() {
  if (state.connected || state.connecting) return;
  state.connecting = true; updateStatus('connecting');
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;
  try { state.ws = new WebSocket(wsUrl); } catch (e) { onDisconnect(); return; }
  state.ws.binaryType = 'arraybuffer';
  state.ws.onopen = () => {
    state.connected = true; state.connecting = false; state.reconnectAttempts = 0;
    updateStatus('connected'); els.overlay.classList.add('hidden'); els.screenImg.classList.add('active');
    state.ws.send(JSON.stringify({ type: 'auth', password: state.settings.password }));
    startPing(); sendSettings();
  };
  state.ws.onmessage = (e) => {
    if (typeof e.data === 'string') {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === 'frame') handleFrame(msg);
        else if (msg.type === 'auth_failed') {
          state.authFailed = true;
          // Distinguish a wrong password from a brute-force lockout, rather than
          // telling the user to re-enter a password that is already correct.
          state.authDetail = msg.detail || '';
        }
      } catch (err) {}
    }
  };
  state.ws.onerror = () => { state.connecting = false; };
  state.ws.onclose = () => onDisconnect();
}

function onDisconnect() {
  state.connected = false; state.connecting = false;
  updateStatus('error');
  els.overlay.textContent = state.authFailed
    ? (state.authDetail && state.authDetail.startsWith('Too many')
        ? state.authDetail
        : 'Wrong password. Open Settings (gear icon) to enter it.')
    : 'Disconnected. Tap to reconnect.';
  els.overlay.classList.remove('hidden'); els.screenImg.classList.remove('active');
  stopPing();
  if (!state.authFailed) scheduleReconnect();
}

function scheduleReconnect() {
  if (state.reconnectTimer) return;
  const delay = Math.min(1000 * Math.pow(2, state.reconnectAttempts), 30000);
  state.reconnectAttempts++;
  state.reconnectTimer = setTimeout(() => { state.reconnectTimer = null; connect(); }, delay);
}

function stopPing() { if (state.pingInterval) { clearInterval(state.pingInterval); state.pingInterval = null; } }
function startPing() { state.pingInterval = setInterval(() => { if (state.connected && state.ws?.readyState === WebSocket.OPEN) send({ type: 'ping' }); }, 15000); }

function send(msg) { if (state.connected && state.ws?.readyState === WebSocket.OPEN) state.ws.send(JSON.stringify(msg)); }
function sendSettings() { send({ type: 'config', quality: state.settings.quality, fps: state.settings.fps, scale: state.settings.scale }); }

// ===== Frame Handling =====
function handleFrame(msg) {
  if (msg.data) {
    if (state.frameUrl) URL.revokeObjectURL(state.frameUrl);
    const binary = atob(msg.data);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const blob = new Blob([bytes], { type: 'image/jpeg' });
    state.frameUrl = URL.createObjectURL(blob);
    els.screenImg.src = state.frameUrl;
    if (msg.width) state.screenWidth = msg.width;
    if (msg.height) state.screenHeight = msg.height;
  }
}

// ===== Status =====
function updateStatus(status) {
  els.status.className = 'status ' + status;
  const texts = { connected: 'Connected', connecting: 'Connecting...', error: 'Disconnected' };
  els.statusText.textContent = texts[status] || status;
}

// ===== Touch Input =====
let touchState = { startX: 0, startY: 0, startTime: 0, longPressTimer: null, moved: false, maybeDrag: false, dragging: false };
let lastTap = 0;

// One two-finger gesture = one mode, decided by how the fingers move first:
// distance change -> pinch, parallel motion -> scroll (at 1x) or pan (zoomed in).
// multiTouch stays true until every finger lifts, so touchend can never turn the
// tail of a two-finger gesture into a stray click.
let gesture = { mode: null, multiTouch: false, startDist: 0, startZoom: 1, startPanX: 0, startPanY: 0, startMidX: 0, startMidY: 0, lastScrollY: 0, baseW: 0, baseH: 0 };

// ===== View (pinch zoom / pan) =====
// Zoom is a CSS transform on the image only. Layout is untouched, and
// getBoundingClientRect() reflects transforms, so getRelativePos() and
// showClickIndicator() keep working with zero changes while zoomed.
function applyView(baseW, baseH) {
  const v = state.view;
  v.zoom = Math.max(1, Math.min(5, v.zoom));
  if (v.zoom === 1) { v.panX = 0; v.panY = 0; }
  else if (baseW) {
    // Keep the scaled image covering the container; no panning it fully away.
    const cont = els.screenContainer.getBoundingClientRect();
    const maxX = Math.max(0, (v.zoom * baseW - cont.width) / 2);
    const maxY = Math.max(0, (v.zoom * baseH - cont.height) / 2);
    v.panX = Math.max(-maxX, Math.min(maxX, v.panX));
    v.panY = Math.max(-maxY, Math.min(maxY, v.panY));
  }
  els.screenImg.style.transform = v.zoom === 1 ? '' : `translate(${v.panX}px, ${v.panY}px) scale(${v.zoom})`;
  els.zoomBadge.textContent = v.zoom.toFixed(1) + '×';
  els.zoomBadge.classList.toggle('show', v.zoom > 1);
}

function beginTwoFinger(e) {
  clearTimeout(touchState.longPressTimer);
  touchState.maybeDrag = false; touchState.dragging = false;
  const t0 = e.touches[0], t1 = e.touches[1];
  const img = els.screenImg.getBoundingClientRect();
  gesture = {
    mode: null, multiTouch: true,
    startDist: Math.hypot(t0.clientX - t1.clientX, t0.clientY - t1.clientY),
    startZoom: state.view.zoom, startPanX: state.view.panX, startPanY: state.view.panY,
    startMidX: (t0.clientX + t1.clientX) / 2, startMidY: (t0.clientY + t1.clientY) / 2,
    lastScrollY: (t0.clientY + t1.clientY) / 2,
    // Displayed (untransformed) image size, for pan clamping.
    baseW: img.width / state.view.zoom, baseH: img.height / state.view.zoom,
  };
}

function twoFingerMove(e) {
  const t0 = e.touches[0], t1 = e.touches[1];
  const dist = Math.hypot(t0.clientX - t1.clientX, t0.clientY - t1.clientY);
  const midX = (t0.clientX + t1.clientX) / 2, midY = (t0.clientY + t1.clientY) / 2;

  if (!gesture.mode) {
    if (gesture.startDist > 0 && Math.abs(dist / gesture.startDist - 1) > 0.08) gesture.mode = 'pinch';
    else if (Math.hypot(midX - gesture.startMidX, midY - gesture.startMidY) > 12)
      gesture.mode = state.view.zoom > 1 ? 'pan' : 'scroll';
    else return;
  }

  if (gesture.mode === 'scroll') {
    const delta = Math.round((gesture.lastScrollY - midY) / 15);
    if (delta) {
      const pos = getRelativePos(e);
      send({ type: 'scroll', x: pos.x, y: pos.y, delta });
      gesture.lastScrollY = midY;
    }
    return;
  }

  // pinch / pan: keep the image point that started under the fingers' midpoint
  // anchored to wherever the midpoint is now.
  const v = state.view;
  if (gesture.mode === 'pinch') v.zoom = gesture.startZoom * (dist / gesture.startDist);
  const z = Math.max(1, Math.min(5, v.zoom));
  const cont = els.screenContainer.getBoundingClientRect();
  const cx = cont.left + cont.width / 2, cy = cont.top + cont.height / 2;
  const ux = (gesture.startMidX - cx - gesture.startPanX) / gesture.startZoom;
  const uy = (gesture.startMidY - cy - gesture.startPanY) / gesture.startZoom;
  v.panX = midX - cx - ux * z;
  v.panY = midY - cy - uy * z;
  applyView(gesture.baseW, gesture.baseH);
}

function getRelativePos(e) {
  const rect = els.screenImg.getBoundingClientRect();
  let cx, cy;
  if (e.touches && e.touches.length > 0) { cx = e.touches[0].clientX; cy = e.touches[0].clientY; }
  else { cx = e.clientX; cy = e.clientY; }
  const x = Math.max(0, Math.min(1, (cx - rect.left) / rect.width));
  const y = Math.max(0, Math.min(1, (cy - rect.top) / rect.height));
  return { x, y };
}

function showClickIndicator(x, y) {
  // x/y are normalized against the IMAGE, but the indicator is positioned inside
  // the CONTAINER. The image is object-fit: contain and centred, so it is
  // letterboxed whenever the PC and phone aspect ratios differ - without the
  // offset the ripple drifts away from the fingertip.
  const rect = els.screenContainer.getBoundingClientRect();
  const img = els.screenImg.getBoundingClientRect();
  els.clickIndicator.style.left = (img.left - rect.left + x * img.width) + 'px';
  els.clickIndicator.style.top = (img.top - rect.top + y * img.height) + 'px';
  els.clickIndicator.classList.remove('show');
  void els.clickIndicator.offsetWidth;
  els.clickIndicator.classList.add('show');
  setTimeout(() => els.clickIndicator.classList.remove('show'), 400);
}

els.screenContainer.addEventListener('touchstart', (e) => {
  if (!state.connected) { connect(); return; }
  if (e.touches.length === 2) { beginTwoFinger(e); return; }
  if (e.touches.length > 2 || gesture.multiTouch) return;
  const pos = getRelativePos(e);
  // Second touch within 300ms of a tap: hold + move becomes a drag
  // (double-tap-and-hold, same gesture as the Microsoft RD client).
  const maybeDrag = Date.now() - lastTap < 300;
  touchState = { startX: pos.x, startY: pos.y, startTime: Date.now(), moved: false, maybeDrag, dragging: false };
  if (!maybeDrag) {
    touchState.longPressTimer = setTimeout(() => {
      if (!touchState.moved) {
        send({ type: 'mouse_right_click', x: touchState.startX, y: touchState.startY });
        showClickIndicator(touchState.startX, touchState.startY);
        navigator.vibrate?.(20);
      }
    }, 500);
  }
}, { passive: true });

els.screenContainer.addEventListener('touchmove', (e) => {
  if (!state.connected) return;
  if (e.touches.length >= 2) { e.preventDefault(); twoFingerMove(e); return; }
  if (gesture.multiTouch) return;  // leftover finger from a two-finger gesture
  const pos = getRelativePos(e);
  const dx = Math.abs(pos.x - touchState.startX);
  const dy = Math.abs(pos.y - touchState.startY);
  if (dx > 0.01 || dy > 0.01) { touchState.moved = true; clearTimeout(touchState.longPressTimer); }
  if (!touchState.moved) return;
  if (touchState.maybeDrag) { touchState.dragging = true; return; }  // released as mouse_drag in touchend
  if (Date.now() - touchState.startTime > 100) send({ type: 'mouse_move', x: pos.x, y: pos.y });
}, { passive: false });

// Single tap vs double tap is decided in ONE handler. Splitting it across two
// independent touchend listeners meant a double tap emitted click + click +
// double_click - four physical button events - which opened things twice.
els.screenContainer.addEventListener('touchend', (e) => {
  if (gesture.multiTouch) {
    // End of (or leftover finger from) a two-finger gesture - never a click.
    if (e.touches.length === 0) { gesture.multiTouch = false; gesture.mode = null; lastTap = 0; }
    return;
  }
  if (!state.connected) return;
  clearTimeout(touchState.longPressTimer);
  const elapsed = Date.now() - touchState.startTime;
  const pos = getRelativePos(e.changedTouches[0] ? { touches: [e.changedTouches[0]] } : e);
  if (touchState.dragging) {
    send({ type: 'mouse_drag', fromX: touchState.startX, fromY: touchState.startY, x: pos.x, y: pos.y });
    showClickIndicator(pos.x, pos.y);
    navigator.vibrate?.(15);
    touchState.dragging = false; touchState.maybeDrag = false; lastTap = 0;
    return;
  }
  if (touchState.moved) { send({ type: 'mouse_move', x: pos.x, y: pos.y }); lastTap = 0; return; }
  if (elapsed >= 500) return;  // long press already fired a right click

  const now = Date.now();
  if (now - lastTap < 300) {
    // Second tap of a double: send only the double click. The first tap's click
    // already landed, which is exactly the select-then-open sequence a real
    // mouse produces.
    send({ type: 'mouse_double_click', x: pos.x, y: pos.y });
    lastTap = 0;
  } else {
    send({ type: 'mouse_click', x: pos.x, y: pos.y });
    lastTap = now;
  }
  showClickIndicator(pos.x, pos.y);
  navigator.vibrate?.(10);
});

// Zoom badge: shows the current factor, tap to reset. Events must not bubble
// into the screen container or the reset tap would also click the remote PC.
['touchstart', 'touchmove', 'touchend'].forEach(ev =>
  els.zoomBadge.addEventListener(ev, (e) => e.stopPropagation()));
els.zoomBadge.addEventListener('click', (e) => {
  e.stopPropagation();
  state.view.zoom = 1; applyView();
});

// ===== Fullscreen / landscape =====
async function toggleFullscreen() {
  if (document.fullscreenElement) {
    try { screen.orientation.unlock(); } catch (e) { /* not locked / unsupported */ }
    try { await document.exitFullscreen(); } catch (e) {}
    return;
  }
  try { await document.documentElement.requestFullscreen(); }
  catch (e) { showToast('Fullscreen not available: ' + e.message, '#ef4444'); return; }
  try { await screen.orientation.lock('landscape'); }
  catch (e) { showToast('Rotate your phone for landscape'); }
}
els.fullscreenBtn.addEventListener('click', toggleFullscreen);
document.addEventListener('fullscreenchange', () =>
  els.fullscreenBtn.classList.toggle('active', !!document.fullscreenElement));

// ===== Panels =====
// An open panel shrinks #app's content box rather than covering the screen, so the
// remote screen stays visible above it. offsetHeight is valid even while the panel
// is still translated off-screen - transforms don't affect layout.
function setPanelHeight(panel) {
  const h = panel ? panel.offsetHeight : 0;
  document.documentElement.style.setProperty('--panel-h', h + 'px');
  els.app.classList.toggle('panel-open', h > 0);
}

function openPanel(name) {
  if (state.activePanel === name) { closeAllPanels(); return; }
  closeAllPanels(); state.activePanel = name;
  const panel = els[name]; if (panel) { panel.classList.add('open'); setPanelHeight(panel); }
  document.querySelectorAll('.ctrl-btn').forEach(b => b.classList.remove('active'));
  const btnMap = { navPanel: 'btnNav', keyboardPanel: 'btnKeyboard', aiPanel: 'btnAI' };
  const btnId = btnMap[name]; if (btnId) $(btnId)?.classList.add('active');
}
function closeAllPanels() {
  ['navPanel', 'keyboardPanel', 'aiPanel', 'settingsPanel'].forEach(n => { els[n]?.classList.remove('open'); });
  state.activePanel = null;
  setPanelHeight(null);
  document.querySelectorAll('.ctrl-btn').forEach(b => b.classList.remove('active'));
}

// ===== Keyboard resize =====
// Drag the grip to trade remote-screen height against key height. Clamped so the
// panel can never swallow the screen or shrink below a usable key grid.
function applyKbdHeight(px) {
  const min = window.innerHeight * 0.3, max = window.innerHeight * 0.75;
  const h = Math.max(min, Math.min(max, px));
  els.keyboardPanel.style.height = h + 'px';
  els.keyboardPanel.style.maxHeight = 'none';  // beats the .panel 60vh cap
  if (state.activePanel === 'keyboardPanel') setPanelHeight(els.keyboardPanel);
  return h;
}
const savedKbdHeight = +localStorage.getItem('kbdHeight');
if (savedKbdHeight) applyKbdHeight(savedKbdHeight);

let gripStartY = 0, gripStartH = 0;
els.kbdGrip.addEventListener('touchstart', (e) => {
  gripStartY = e.touches[0].clientY;
  gripStartH = els.keyboardPanel.offsetHeight;
}, { passive: true });
els.kbdGrip.addEventListener('touchmove', (e) => {
  e.preventDefault();  // dragging the grip must not scroll the page
  applyKbdHeight(gripStartH + (gripStartY - e.touches[0].clientY));
}, { passive: false });
els.kbdGrip.addEventListener('touchend', () => {
  localStorage.setItem('kbdHeight', els.keyboardPanel.offsetHeight);
});

// Mouse is the default mode, so closeAllPanels() alone left it as the only
// control with no selected indicator.
$('btnMouse').addEventListener('click', () => { closeAllPanels(); $('btnMouse').classList.add('active'); });
$('btnKeyboard').addEventListener('click', () => openPanel('keyboardPanel'));
$('btnAI').addEventListener('click', () => openPanel('aiPanel'));
$('btnScreenshot').addEventListener('click', takeScreenshot);
$('btnNav').addEventListener('click', () => openPanel('navPanel'));
$('menuBtn').addEventListener('click', () => openPanel('settingsPanel'));
$('closeNav').addEventListener('click', closeAllPanels);
$('closeKeyboard').addEventListener('click', closeAllPanels);
$('closeAI').addEventListener('click', closeAllPanels);
$('closeSettings').addEventListener('click', closeAllPanels);

// ===== Navigation Pad =====
document.querySelectorAll('.nav-btn[data-key]').forEach(btn => {
  btn.addEventListener('click', () => {
    const key = btn.dataset.key;
    if (key === 'up') send({ type: 'key_press', key: 'up' });
    else if (key === 'down') send({ type: 'key_press', key: 'down' });
    else if (key === 'left') send({ type: 'key_press', key: 'left' });
    else if (key === 'right') send({ type: 'key_press', key: 'right' });
    else if (key === 'enter') send({ type: 'key_press', key: 'enter' });
  });
});
document.querySelectorAll('.action-btn[data-key]').forEach(btn => {
  btn.addEventListener('click', () => { send({ type: 'key_press', key: btn.dataset.key }); });
});

// ===== Keyboard =====
const fnKeys = { q: 'f1', w: 'f2', e: 'f3', r: 'f4', t: 'f5', y: 'f6', u: 'f7', i: 'f8', o: 'f9', p: 'f10', a: 'f11', s: 'f12' };

// Ctrl and Alt latch instead of firing a bare press-and-release. Tapping them
// alone previously did nothing observable, so Ctrl then C typed a plain "c"
// rather than copying.
function activeModifiers() {
  const mods = [];
  if (state.modifiers.ctrl) mods.push('ctrl');
  if (state.modifiers.alt) mods.push('alt');
  if (state.modifiers.win) mods.push('win');
  // Shift joins only alongside another modifier (Ctrl+Shift+Esc). Shift alone keeps
  // using the proven type_text uppercase path below.
  if (mods.length && state.shift) mods.push('shift');
  return mods;
}
function clearModifiers() {
  state.modifiers.ctrl = false; state.modifiers.alt = false; state.modifiers.win = false;
  // Selected by data-action: these buttons carry no id in index.html.
  document.querySelectorAll('.k[data-action="ctrl"], .k[data-action="alt"], .k[data-action="win"]')
    .forEach(b => b.classList.remove('active'));
  toggleShift(false);
}
function toggleModifier(name, btn) {
  state.modifiers[name] = !state.modifiers[name];
  btn.classList.toggle('active', state.modifiers[name]);
}

// Route a key through any latched modifiers, consuming them.
function sendKey(key) {
  const mods = activeModifiers();
  if (mods.length) { send({ type: 'hotkey', keys: [...mods, key] }); clearModifiers(); }
  else send({ type: 'key_press', key });
}

document.querySelectorAll('.k[data-k]').forEach(btn => {
  btn.addEventListener('click', () => {
    let key = btn.dataset.k;
    if (state.fnMode && fnKeys[key]) { sendKey(fnKeys[key]); return; }
    if (key === ' ') { sendKey('space'); toggleShift(false); return; }
    if (activeModifiers().length) { sendKey(key); toggleShift(false); return; }
    if (state.shift) { const upper = key.toUpperCase(); if (upper !== key) { send({ type: 'type_text', text: upper }); toggleShift(false); return; } }
    send({ type: 'type_text', text: key });
  });
});

// Keys that are just a keypress (and so route through any latched modifiers).
const PLAIN_ACTIONS = ['backspace', 'enter', 'esc', 'tab', 'up', 'down', 'left', 'right'];

document.querySelectorAll('.k[data-action]').forEach(btn => {
  btn.addEventListener('click', () => {
    const action = btn.dataset.action;
    if (action === 'shift') toggleShift();
    else if (action === 'fn') toggleFn();
    else if (action === 'symbols') toggleSymbols();
    else if (action === 'ctrl') toggleModifier('ctrl', btn);
    else if (action === 'alt') toggleModifier('alt', btn);
    else if (action === 'win') toggleModifier('win', btn);
    else if (PLAIN_ACTIONS.includes(action)) sendKey(action);
  });
});

// Symbols layer: swaps which key grid is visible. The generic .k[data-k] handler
// types whatever character the button carries, so no per-symbol wiring is needed.
function toggleSymbols() {
  state.symMode = !state.symMode;
  els.kbdLetters.classList.toggle('hidden', state.symMode);
  els.kbdSymbols.classList.toggle('hidden', !state.symMode);
  $('symBtn').classList.toggle('active', state.symMode);
  $('symBtn').textContent = state.symMode ? 'ABC' : '?123';
  if (state.activePanel === 'keyboardPanel') setPanelHeight(els.keyboardPanel);
}

function toggleShift(force) { state.shift = force !== undefined ? force : !state.shift; $('shiftBtn')?.classList.toggle('active', state.shift); }
function toggleFn() {
  state.fnMode = !state.fnMode;
  document.querySelectorAll('.k[data-k]').forEach(k => { const ch = k.dataset.k; if (ch && fnKeys[ch]) k.textContent = state.fnMode ? fnKeys[ch].toUpperCase() : ch.toUpperCase(); });
  document.querySelector('.k-fn')?.classList.toggle('active', state.fnMode);
}

els.sendTextBtn.addEventListener('click', () => { const text = els.textInput.value; if (text) { send({ type: 'type_text', text }); els.textInput.value = ''; } });
els.textInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') els.sendTextBtn.click(); });

// ===== AI Chat =====
function addMessage(text, sender) {
  const div = document.createElement('div'); div.className = 'ai-msg ' + sender;
  const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  div.innerHTML = escapeHtml(text) + `<div class="msg-time">${time}</div>`;
  els.aiMessages.appendChild(div); els.aiMessages.scrollTop = els.aiMessages.scrollHeight;
}
function escapeHtml(t) { const d = document.createElement('div'); d.textContent = t; return d.innerHTML; }

async function sendAICommand() {
  const cmd = els.aiInput.value.trim(); if (!cmd) return;
  addMessage(cmd, 'user'); els.aiInput.value = ''; els.aiSendBtn.classList.add('loading');
  try {
    const resp = await fetch('/api/ai/command', { method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify({ command: cmd, api_key: state.settings.apiKey }) });
    if (!resp.ok) { addMessage(await errorText(resp), 'ai'); }
    else { const data = await resp.json(); addMessage(data.response || data.error || 'No response', 'ai'); }
  } catch (e) { addMessage('Error: ' + e.message, 'ai'); }
  els.aiSendBtn.classList.remove('loading');
}
els.aiSendBtn.addEventListener('click', sendAICommand);
els.aiInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') sendAICommand(); });

// ===== Quick Actions =====
const quickActions = {
  'open-browser': () => apiPost('/api/open', { url: 'https://google.com' }),
  'open-files': () => send({ type: 'hotkey', keys: ['win', 'e'] }),
  // ctrl+alt+t is a GNOME shortcut and a no-op on Windows. The server maps this
  // action key to an allowlisted "start" command - it no longer accepts raw
  // command strings.
  'open-terminal': () => apiPost('/api/execute', { action: 'terminal' }),
  'copy': () => send({ type: 'hotkey', keys: ['ctrl', 'c'] }),
  'paste': () => send({ type: 'hotkey', keys: ['ctrl', 'v'] }),
  // Task View stays open after the hotkey, so a follow-up tap picks the window.
  'task-view': () => send({ type: 'hotkey', keys: ['win', 'tab'] }),
  // The keyboard's Win key latches for combos, so a bare Win press lives here.
  'start-menu': () => send({ type: 'key_press', key: 'win' }),
  'task-manager': () => send({ type: 'hotkey', keys: ['ctrl', 'shift', 'esc'] }),
  'desktop': () => send({ type: 'hotkey', keys: ['win', 'd'] }),
  'lock': () => send({ type: 'hotkey', keys: ['win', 'l'] }),
};
document.querySelectorAll('.qa-btn[data-action]').forEach(btn => {
  btn.addEventListener('click', () => {
    const action = btn.dataset.action;
    if (quickActions[action]) quickActions[action]();
    btn.style.transform = 'scale(0.85)'; setTimeout(() => btn.style.transform = '', 150);
  });
});

function authHeaders(extra) { return Object.assign({ 'X-Auth-Password': state.settings.password }, extra || {}); }

// Turn a failed response into readable text. A 401 here almost always means the
// password in Settings is wrong, which is worth saying outright.
async function errorText(resp) {
  if (resp.status === 401) return 'Wrong password - check Settings';
  let detail = '';
  try { const data = await resp.json(); detail = data.detail || data.error || ''; } catch (e) {}
  return detail || `Request failed (${resp.status})`;
}

async function apiPost(url, body) {
  try {
    const resp = await fetch(url, { method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify(body) });
    if (!resp.ok) { showToast(await errorText(resp), '#ef4444'); return null; }
    return resp;
  } catch (e) { showToast('Network error: ' + e.message, '#ef4444'); return null; }
}

async function takeScreenshot() {
  try {
    const resp = await fetch('/api/screenshot', { method: 'POST', headers: authHeaders() });
    if (!resp.ok) { showToast(await errorText(resp), '#ef4444'); return; }
    const data = await resp.json();
    if (!data.image) { showToast(data.error || 'Capture failed', '#ef4444'); return; }
    const a = document.createElement('a');
    a.href = 'data:image/jpeg;base64,' + data.image;
    a.download = 'screenshot_' + Date.now() + '.jpg';
    a.click();
  } catch (e) { showToast('Network error: ' + e.message, '#ef4444'); }
}

// ===== Settings =====
els.qualityRange.value = state.settings.quality; els.qualityValue.textContent = state.settings.quality;
els.qualityRange.addEventListener('input', (e) => { state.settings.quality = +e.target.value; els.qualityValue.textContent = e.target.value; });
els.fpsRange.value = state.settings.fps; els.fpsValue.textContent = state.settings.fps;
els.fpsRange.addEventListener('input', (e) => { state.settings.fps = +e.target.value; els.fpsValue.textContent = e.target.value; });
els.scaleRange.value = state.settings.scale * 100; els.scaleValue.textContent = Math.round(state.settings.scale * 100) + '%';
els.scaleRange.addEventListener('input', (e) => { state.settings.scale = +e.target.value / 100; els.scaleValue.textContent = e.target.value + '%'; });
els.apiKeyInput.value = state.settings.apiKey; els.passwordInput.value = state.settings.password;

function showToast(text, color) {
  const el = document.createElement('div'); el.textContent = text;
  el.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:' + (color || '#22c55e') +
    ';color:#fff;padding:12px 24px;border-radius:12px;font-size:14px;font-weight:600;z-index:9999;max-width:80vw;text-align:center;animation:fadeInOut 1.5s forwards;';
  document.body.appendChild(el); setTimeout(() => el.remove(), 1500);
}

// Persist every setting, not just the credentials - the sliders used to silently
// revert to their defaults on reload while the "Saved!" toast claimed otherwise.
function persistSettings() {
  localStorage.setItem('apiKey', state.settings.apiKey);
  localStorage.setItem('password', state.settings.password);
  localStorage.setItem('quality', state.settings.quality);
  localStorage.setItem('fps', state.settings.fps);
  localStorage.setItem('scale', state.settings.scale);
}

$('saveSettings').addEventListener('click', () => {
  state.settings.quality = +els.qualityRange.value; state.settings.fps = +els.fpsRange.value;
  state.settings.scale = +els.scaleRange.value / 100; state.settings.apiKey = els.apiKeyInput.value;
  state.settings.password = els.passwordInput.value;
  persistSettings();
  sendSettings(); closeAllPanels();
  if (state.authFailed || !state.connected) { state.authFailed = false; state.reconnectAttempts = 0; state.ws?.close(); connect(); }
  showToast('Saved!');
});

// Reset used to only repaint the inputs, leaving the live stream and the stored
// values untouched until the user separately pressed Save. It now applies
// immediately, but deliberately leaves the password and API key alone: clearing
// the password would drop the connection and lock the user out of the very panel
// they would need to get back in.
$('resetSettings').addEventListener('click', () => {
  els.qualityRange.value = 70; els.qualityValue.textContent = '70';
  els.fpsRange.value = 20; els.fpsValue.textContent = '20';
  els.scaleRange.value = 50; els.scaleValue.textContent = '50%';
  state.settings.quality = 70; state.settings.fps = 20; state.settings.scale = 0.5;
  persistSettings(); sendSettings();
  showToast('Stream settings reset');
});
const style = document.createElement('style');
style.textContent = '@keyframes fadeInOut{0%{opacity:0;transform:translate(-50%,-50%)scale(.8)}20%{opacity:1;transform:translate(-50%,-50%)scale(1)}80%{opacity:1}100%{opacity:0}}';
document.head.appendChild(style);

// ===== Init =====
connect();
document.addEventListener('visibilitychange', () => { if (!document.hidden && !state.connected) connect(); });
els.overlay.addEventListener('click', () => { if (!state.connected) connect(); });
