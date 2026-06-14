/* terminal.js — in-app output terminal.

   The backend sends everything to this xterm: Python stdout/stderr (Flask
   startup, errors, tracebacks) and raw job subprocess output (tqdm bars,
   ANSI colours).  There is no second shell — one process, one terminal.

   Flow:
     1. initTerminal() connects the WebSocket immediately so nothing is missed.
     2. Backend replays its 64 KB history buffer on connect.
     3. xterm.open() is deferred until the Terminal tab is first clicked
        (xterm requires a visible, sized container to render correctly).
     4. Output buffered before the tab opens is flushed on open().
*/

let term    = null;
let fitAddon = null;
let ws      = null;
let _buf    = [];      // output queued before xterm is opened
let _ready  = false;

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

let _reconnectTimer = null;

function _connect() {
  if (ws && ws.readyState <= WebSocket.OPEN) return;
  clearTimeout(_reconnectTimer);

  ws = new WebSocket(_wsUrl());
  ws.binaryType = "arraybuffer";

  ws.onmessage = (e) => {
    const data = typeof e.data === "string" ? e.data : new Uint8Array(e.data);
    if (_ready && term) {
      term.write(data);
    } else {
      _buf.push(data);
    }
  };

  ws.onclose = () => {
    if (_ready && term) {
      term.write("\r\n\x1b[2m[output stream disconnected — reconnecting…]\x1b[0m\r\n");
    }
    _reconnectTimer = setTimeout(_connect, 3000);
  };
}

function _openXterm() {
  if (_ready) return;

  const container = document.getElementById("xterm-container");
  if (!container || !window.Terminal) return;

  term = new window.Terminal({
    cursorBlink: false,
    disableStdin: true,   // display-only; keyboard input is not forwarded
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

  fitAddon.fit();

  // Flush everything buffered before the tab was opened.
  _buf.forEach(item => term.write(item));
  _buf = [];

  if (window.ResizeObserver) {
    new ResizeObserver(() => { if (fitAddon) fitAddon.fit(); }).observe(container);
  }
}

export function initTerminal() {
  // Connect immediately — backend replays history on connect.
  _connect();

  // Open xterm only when the terminal tab becomes visible.
  const tabBtn = document.querySelector('.tab[data-tab="terminal"]');
  if (tabBtn) {
    tabBtn.addEventListener("click", () => {
      _openXterm();
      requestAnimationFrame(() => { if (fitAddon) fitAddon.fit(); });
    });
  }
}
