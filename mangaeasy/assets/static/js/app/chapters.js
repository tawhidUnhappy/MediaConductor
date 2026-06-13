/* chapters.js — chapter progress overview table + batch-download form. */

import { $, api, appendLog } from "./core.js";
import { pollStatus } from "./status.js";

function renderTable(data) {
  const grid = $("chapters-grid");
  const summary = $("chapters-summary");
  if (!grid) return;

  const chapters = data.chapters || [];

  if (chapters.length === 0) {
    const msg = data.name
      ? `No chapter folders found for <b>${data.name}</b> yet — download one first.`
      : "Set a manga name in the Project tab first.";
    grid.innerHTML = `<span class="ch-empty">${msg}</span>`;
    if (summary) summary.textContent = "";
    return;
  }

  const total  = chapters.length;
  const dlCnt  = chapters.filter(c => c.downloaded > 0).length;
  const panCnt = chapters.filter(c => c.panels > 0).length;
  const audCnt = chapters.filter(c => c.audio > 0).length;
  const vidCnt = chapters.filter(c => c.video).length;

  if (summary) {
    summary.textContent =
      `${total} chapters — ${dlCnt} downloaded · ${panCnt} cropped · ${audCnt} audio · ${vidCnt} video`;
  }

  let html = `<div class="ch-table">
    <div class="ch-row ch-header">
      <span class="ch-num">Ch</span>
      <span class="ch-cell">Pages</span>
      <span class="ch-cell">Panels</span>
      <span class="ch-cell">Audio</span>
      <span class="ch-cell">Video</span>
    </div>`;

  for (const ch of chapters) {
    const n   = String(ch.chapter).padStart(2, "0");
    const dl  = ch.downloaded > 0;
    const pan = ch.panels > 0;
    const aud = ch.audio > 0;
    const vid = ch.video;
    html += `<div class="ch-row">
      <span class="ch-num">${n}</span>
      <span class="ch-cell ${dl  ? "done" : ""}">${dl  ? ch.downloaded : "—"}</span>
      <span class="ch-cell ${pan ? "done" : ""}">${pan ? ch.panels     : "—"}</span>
      <span class="ch-cell ${aud ? "done" : ""}">${aud ? ch.audio      : "—"}</span>
      <span class="ch-cell ${vid ? "done" : ""}">${vid ? "✓"           : "—"}</span>
    </div>`;
  }

  html += "</div>";
  grid.innerHTML = html;
}

export async function loadChapters() {
  try {
    renderTable(await api("/api/workflow/chapters"));
  } catch { /* no project yet */ }
}

export function initChapters() {
  const refreshBtn = $("chapters-refresh");
  if (refreshBtn) refreshBtn.addEventListener("click", loadChapters);

  const runBtn  = $("bdl-run");
  const stopBtn = $("bdl-stop");
  const statEl  = $("bdl-status");

  if (runBtn) {
    runBtn.addEventListener("click", async () => {
      const start = parseInt($("bdl-start").value, 10) || 1;
      const end   = parseInt($("bdl-end").value,   10) || start;
      try {
        await api("/api/workflow/batch-download", {
          method: "POST",
          body: JSON.stringify({ start, end }),
        });
        if (statEl) statEl.textContent =
          `downloading ch ${String(start).padStart(2,"0")}–${String(end).padStart(2,"0")}…`;
      } catch (err) {
        appendLog("", `batch-download: ${err.message}`);
      }
      pollStatus();
    });
  }

  if (stopBtn) {
    stopBtn.addEventListener("click", async () => {
      try { await api("/api/stop", { method: "POST" }); }
      catch (err) { appendLog("", err.message); }
    });
  }
}
