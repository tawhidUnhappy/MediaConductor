/* terminal.js — integrated xterm.js terminal.

   Architecture:
     - WebSocket connects immediately at startup (before user opens the tab)
       so no output is missed. The backend replays its 64 KB history buffer
       on connect, so the user sees everything since the app launched.
     - The xterm Terminal object is only created when the user first clicks the
       Terminal tab, because xterm needs a visible, sized container to render.
     - All text written via write() before xterm is ready is queued locally and
       flushed into xterm when it opens. Combined with the backend replay, the
       Terminal tab shows the full history the first time it is opened.
*/

let term  = null;
let fitAddon = null;
let ws    = null;
let _buf  = [];      // queued before xterm is open (strings or Uint8Arrays)
let _ready = false;  // true once term.open() has been called

export function write(text) {
  if (_ready && term) {
    term.write(text);
  } else {
    _buf.push(text);
  }
}

function _wsUrl() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}/ws/terminal`;
}

function _sendResize() {
  if (!ws || ws.readyState !== WebSocket.OPEN || !term) return;
  ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
}

let _reconnectTimer = null;

function _connect() {
  if (ws && ws.readyState <= WebSocket.OPEN) return;
  clearTimeout(_reconnectTimer);

  ws = new WebSocket(_wsUrl());
  ws.binaryType = "arraybuffer";

  ws.onopen  = () => { _sendResize(); };
  ws.onmessage = (e) => {
    const data = typeof e.data === "string" ? e.data : new Uint8Array(e.data);
    if (_ready && term) {
      term.write(data);
    } else {
      _buf.push(data);   // buffer until xterm is opened by the tab click
    }
  };
  ws.onclose = () => {
    if (_ready && term) term.write("\r\n\x1b[2m[terminal disconnected — reconnecting…]\x1b[0m\r\n");
    _reconnectTimer = setTimeout(_connect, 3000);
  };
}

function _openXterm() {
  if (_ready) return;

  const container = document.getElementById("xterm-container");
  if (!container || !window.Terminal) return;

  term = new window.Terminal({
    cursorBlink: true,
    fontSize: 13,
    fontFamily: "Consolas, 'Courier New', monospace",
    theme: {
      background:    "#0d0d0d",
      foreground:    "#d4d4d4",
      cursor:        "#ffffff",
      selectionBackground: "rgba(255,255,255,0.2)",
      black:         "#000000",   red:           "#cc0000",
      green:         "#4caf50",   yellow:        "#e6c000",
      blue:          "#4d9de0",   magenta:       "#af87d7",
      cyan:          "#00bcd4",   white:         "#d4d4d4",
      brightBlack:   "#555555",   brightRed:     "#f87171",
      brightGreen:   "#6fd388",   brightYellow:  "#fbbf24",
      brightBlue:    "#6cc0ff",   brightMagenta: "#c084fc",
      brightCyan:    "#67e8f9",   brightWhite:   "#ffffff",
    },
    scrollback: 20000,
    allowProposedApi: true,
  });

  fitAddon = new window.FitAddon.FitAddon();
  term.loadAddon(fitAddon);
  term.open(container);
  _ready = true;

  // Size correctly now that the container is visible.
  fitAddon.fit();

  // Flush everything that arrived before the tab was opened.
  _buf.forEach(item => term.write(item));
  _buf = [];

  // Send the current size to the PTY backend.
  _sendResize();

  // User keystrokes → PTY stdin.
  term.onData((data) => {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(data);
  });

  // Refit when the container is resized (window resize, split panes, etc.).
  term.onResize(() => _sendResize());
  if (window.ResizeObserver) {
    new ResizeObserver(() => {
      if (fitAddon) { fitAddon.fit(); _sendResize(); }
    }).observe(container);
  }
}

export function initTerminal() {
  // Connect to the WebSocket immediately — backend buffers output and replays
  // it when we connect, so we get all history including app startup messages.
  _connect();

  // Open xterm (which needs a visible container) only on first tab click.
  const tabBtn = document.querySelector('.tab[data-tab="terminal"]');
  if (tabBtn) {
    tabBtn.addEventListener("click", () => {
      _openXterm();
      // Re-fit a frame later to handle any layout settling.
      requestAnimationFrame(() => { if (fitAddon) fitAddon.fit(); });
    });
  }
}
