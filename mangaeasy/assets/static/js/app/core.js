/* core.js — shared helpers: DOM lookup, API fetch, log console, progress bar, global flags. */

export const $ = (id) => document.getElementById(id);

/* Mutable flags shared across modules. */
export const store = { jobRunning: false };

export async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `${res.status} ${res.statusText}`);
  return data;
}

/* ── Progress bar ──────────────────────────────────────────────────────── */

export function updateProgress(value, total, label) {
  const wrap = $("job-progress-wrap");
  const fill = $("job-progress-fill");
  const ind  = $("job-indicator");
  if (!wrap) return;
  wrap.style.display = "";
  if (total > 0) {
    wrap.classList.remove("indeterminate");
    const pct = Math.min(100, Math.round(value / total * 100));
    fill.style.width = pct + "%";
    if (ind && ind.classList.contains("busy") && label) {
      ind.textContent = `${label}  ${value}/${total}`;
    }
  } else {
    wrap.classList.add("indeterminate");
    fill.style.width = "35%";
  }
}

export function clearProgress() {
  const wrap = $("job-progress-wrap");
  const fill = $("job-progress-fill");
  if (wrap) { wrap.style.display = "none"; wrap.classList.remove("indeterminate"); }
  if (fill) fill.style.width = "0%";
}

/* ── Log console (SSE) ─────────────────────────────────────────────────── */

let logLines = null;
let autoScroll = true;

// Detect tqdm-style lines (non-TTY mode writes each frame with \n, not \r).
// Also catches FFmpeg frame= progress output.
function _isProgressLine(msg) {
  return /\d+%\|/.test(msg) ||           // tqdm bar: "45%|████  |"
         /^\s*frame=\s*\d+/.test(msg);   // ffmpeg:   "frame=  123 fps=..."
}

export function appendLog(ts, msg) {
  if (!logLines) return;

  // If this and the previous line are both progress frames, overwrite in place
  // instead of appending — mirrors \r terminal behaviour for non-TTY processes.
  const isProgress = _isProgressLine(msg);
  const last = logLines.lastElementChild;
  if (isProgress && last && last.dataset.progress === "1") {
    last.querySelector(".ts").textContent = ts;
    last.querySelector(".msg").textContent = msg;
    if (autoScroll) logLines.scrollTop = logLines.scrollHeight;
    return;
  }

  const div = document.createElement("div");
  div.className = "log-line";
  if (isProgress) div.dataset.progress = "1";
  if (/\b(error|failed|fatal)\b/i.test(msg)) div.classList.add("err");
  else if (/\[warn\]|warning/i.test(msg)) div.classList.add("warn");
  const tsSpan = document.createElement("span");
  tsSpan.className = "ts";
  tsSpan.textContent = ts;
  const msgSpan = document.createElement("span");
  msgSpan.className = "msg";
  msgSpan.textContent = msg;
  div.appendChild(tsSpan);
  div.appendChild(msgSpan);
  logLines.appendChild(div);
  while (logLines.childNodes.length > 2000) logLines.removeChild(logLines.firstChild);
  if (autoScroll) logLines.scrollTop = logLines.scrollHeight;
}

export function initLogConsole() {
  logLines = $("log-lines");
  const statusEl = $("term-status");
  const scrollCb = $("term-autoscroll");

  if (scrollCb) {
    scrollCb.addEventListener("change", () => { autoScroll = scrollCb.checked; });
  }

  $("log-clear").addEventListener("click", () => (logLines.innerHTML = ""));

  $("log-copy").addEventListener("click", () => {
    const text = [...logLines.querySelectorAll(".log-line")]
      .map(el => {
        const ts  = el.querySelector(".ts")?.textContent  || "";
        const msg = el.querySelector(".msg")?.textContent || "";
        return ts ? `${ts}  ${msg}` : msg;
      })
      .join("\n");
    navigator.clipboard.writeText(text).then(() => {
      const btn = $("log-copy");
      const prev = btn.textContent;
      btn.textContent = "Copied!";
      setTimeout(() => { btn.textContent = prev; }, 1500);
    }).catch(() => {});
  });

  const events = new EventSource("/log_stream");
  events.onerror = () => { if (statusEl) statusEl.textContent = "reconnecting…"; };
  let _firstOpen = true;
  events.onopen = () => {
    if (statusEl) statusEl.textContent = "connected";
    if (!_firstOpen) window.dispatchEvent(new CustomEvent("sse-reconnect"));
    _firstOpen = false;
  };

  events.onmessage = (e) => {
    try {
      const entry = JSON.parse(e.data);
      if (entry.ping) return;
      if (entry.action === "restart-app") {
        appendLog("", "[app] Restarting…");
        fetch("/api/restart", { method: "POST" }).catch(() => {});
        setTimeout(() => location.reload(), 3000);
        return;
      }
      if (entry.action) {
        window.dispatchEvent(new CustomEvent("sse-action", { detail: entry.action }));
        return;
      }
      if (entry.progress) {
        updateProgress(entry.progress.value, entry.progress.total, entry.progress.label);
        return;
      }
      appendLog(entry.ts, entry.msg);
    } catch { /* ignore malformed entries */ }
  };
}
