import { useEffect, useRef } from "react";
import { Terminal as XTerm } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { listen } from "@tauri-apps/api/event";
import { invoke } from "@tauri-apps/api/core";
import "@xterm/xterm/css/xterm.css";

export default function Terminal() {
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef      = useRef<XTerm | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const term = new XTerm({
      cursorBlink: false,
      disableStdin: true,
      fontSize: 13,
      fontFamily: "Consolas, 'Courier New', monospace",
      theme: {
        background:    "#0d0d0d",
        foreground:    "#d4d4d4",
        cursor:        "#ffffff",
        selectionBackground: "rgba(255,255,255,0.2)",
        black:        "#000000", red:           "#cc0000",
        green:        "#4caf50", yellow:        "#e6c000",
        blue:         "#4d9de0", magenta:       "#af87d7",
        cyan:         "#00bcd4", white:         "#d4d4d4",
        brightBlack:  "#555555", brightRed:     "#f87171",
        brightGreen:  "#6fd388", brightYellow:  "#fbbf24",
        brightBlue:   "#6cc0ff", brightMagenta: "#c084fc",
        brightCyan:   "#67e8f9", brightWhite:   "#ffffff",
      },
      scrollback: 20_000,
      allowProposedApi: true,
    });

    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(containerRef.current);
    fit.fit();
    termRef.current = term;

    // Replay history from Rust
    invoke<string>("get_terminal_history").then((h) => {
      if (h) term.write(h);
    });

    // Listen for live output events
    const unlisten = listen<string>("terminal:output", (e) => {
      term.write(e.payload);
    });

    const ro = new ResizeObserver(() => fit.fit());
    ro.observe(containerRef.current);

    return () => {
      unlisten.then((f) => f());
      ro.disconnect();
      term.dispose();
    };
  }, []);

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", height: "100%", background: "#0d0d0d" }}
    />
  );
}
