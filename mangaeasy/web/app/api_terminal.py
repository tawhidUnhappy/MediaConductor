"""mangaeasy.web.app.api_terminal — in-app xterm.js display terminal.

/ws/terminal is a pure output channel: when a browser client connects,
it is registered with TerminalBroadcaster and immediately receives the
64 KB history buffer (everything since the app started), then continues
to receive live output.

There is no second shell process.  The TerminalBroadcaster already
captures everything via the stdout/stderr tee installed in create_app(),
plus raw subprocess bytes from job runners.  This endpoint just delivers
that stream to xterm.js.
"""

from __future__ import annotations

import threading

from mangaeasy.web.flask_utils import terminal_broadcaster


def register_ws(sock) -> None:
    @sock.route("/ws/terminal")
    def ws_terminal(ws):
        ws_lock = threading.Lock()

        def safe_send(text: str) -> None:
            try:
                with ws_lock:
                    ws.send(text)
            except Exception:
                pass

        terminal_broadcaster.add_client(safe_send)
        try:
            while True:
                msg = ws.receive()
                if msg is None:
                    break
                # Input from the xterm keyboard is ignored for now;
                # operations are triggered through the GUI buttons.
        except Exception:
            pass
        finally:
            terminal_broadcaster.remove_client(safe_send)
