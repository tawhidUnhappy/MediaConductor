/* editors.js — Editors tab cards + in-app editor tab management. */

import { $, api, appendLog } from "./core.js";
import { pollStatus } from "./status.js";

const EDITORS = [
  { key: "cut-page",            title: "Webtoon Cropper",      desc: "Cut downloaded pages into panels (with AI panel detection)." },
  { key: "panel-editor",        title: "Panel Editor",         desc: "Arrange panels for vertical manhwa / webtoons." },
  { key: "narration-editor",    title: "Narration Editor",     desc: "Write narration for the current chapter." },
  { key: "narration-editor-all",title: "Narration Editor (All)",desc: "Write narration across all chapters." },
  { key: "narration-review",    title: "Narration Review",     desc: "Review and QA narration before TTS." },
];

const EDITOR_LABELS = Object.fromEntries(EDITORS.map(e => [e.key, e.title]));

let editorState = {};

// ── Editor cards (Editors tab) ─────────────────────────────────────────────

export function renderEditors() {
  const cards = $("editor-cards");
  cards.innerHTML = "";
  for (const ed of EDITORS) {
    const running = !!editorState[ed.key];
    cards.insertAdjacentHTML("beforeend",
      `<div class="card">
         <div class="info">
           <div class="title">${ed.title}<span class="key">${ed.key}</span></div>
           <div class="desc">${ed.desc}</div>
         </div>
         ${running
           ? `<span class="badge running">running</span>
              <button class="btn small danger" data-ed-stop="${ed.key}">Stop</button>`
           : `<button class="btn primary" data-ed-launch="${ed.key}">Launch</button>`}
       </div>`);
  }
  cards.querySelectorAll("[data-ed-launch]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try { await api(`/api/editor/${btn.dataset.edLaunch}/launch`, { method: "POST" }); }
      catch (err) { appendLog("", err.message); }
      pollStatus();
    }));
  cards.querySelectorAll("[data-ed-stop]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      try { await api(`/api/editor/${btn.dataset.edStop}/stop`, { method: "POST" }); }
      catch (err) { appendLog("", err.message); }
      pollStatus();
    }));
}

/* Called by status polling — re-renders cards and auto-closes tabs for
   editors that just went offline. */
export function updateEditors(next) {
  const prev = editorState;
  const changed = JSON.stringify(next || {}) !== JSON.stringify(prev);
  editorState = next || {};
  if (changed) renderEditors();
  for (const [name, wasAlive] of Object.entries(prev)) {
    if (wasAlive && !editorState[name]) _removeEditorTab(name);
  }
}

// ── In-app editor tabs ─────────────────────────────────────────────────────

function _frames() { return document.getElementById("editor-frames"); }

function _activateEditorTab(name) {
  document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".tab-page").forEach(p => p.classList.remove("active"));
  document.querySelectorAll(".editor-frame-wrap").forEach(f => f.classList.remove("active"));
  document.querySelector("main").style.display = "none";
  _frames().classList.add("active");
  document.querySelector(`.editor-tab[data-editor="${name}"]`)?.classList.add("active");
  document.querySelector(`.editor-frame-wrap[data-editor="${name}"]`)?.classList.add("active");
}

/* Open (or re-focus) an editor as an in-app tab with an iframe.
   Called from Python via window.evaluate_js("window.openEditorTab(…)"). */
export function openEditorTab(name, url) {
  const tabsEl = document.getElementById("tabs");
  let tabBtn = document.querySelector(`.editor-tab[data-editor="${name}"]`);
  if (!tabBtn) {
    const label = EDITOR_LABELS[name] || name;
    tabBtn = document.createElement("button");
    tabBtn.className = "tab editor-tab";
    tabBtn.dataset.editor = name;
    tabBtn.innerHTML = `${label} <span class="editor-tab-close" title="Close">×</span>`;
    tabsEl.appendChild(tabBtn);
    tabBtn.querySelector(".editor-tab-close").addEventListener("click", (e) => {
      e.stopPropagation();
      closeEditorTab(name);
    });
    tabBtn.addEventListener("click", () => _activateEditorTab(name));
  }

  if (!document.querySelector(`.editor-frame-wrap[data-editor="${name}"]`)) {
    const wrap = document.createElement("div");
    wrap.className = "editor-frame-wrap";
    wrap.dataset.editor = name;
    const iframe = document.createElement("iframe");
    iframe.src = url;
    iframe.className = "editor-iframe";
    iframe.title = EDITOR_LABELS[name] || name;
    wrap.appendChild(iframe);
    _frames().appendChild(wrap);
  }

  _activateEditorTab(name);
}

/* Close an editor tab and stop its backend process. */
export function closeEditorTab(name) {
  _removeEditorTab(name);
  fetch(`/api/editor/${name}/stop`, { method: "POST" }).catch(() => {});
}

/* Remove tab + frame without calling the stop API (process already dead). */
function _removeEditorTab(name) {
  const tabBtn = document.querySelector(`.editor-tab[data-editor="${name}"]`);
  if (!tabBtn) return;
  const wasActive = tabBtn.classList.contains("active");
  tabBtn.remove();
  document.querySelector(`.editor-frame-wrap[data-editor="${name}"]`)?.remove();
  if (!wasActive) return;
  // Tab was active — find somewhere to go
  const nextEditor = document.querySelector(".editor-tab");
  if (nextEditor) {
    nextEditor.click();
  } else {
    // No more editor tabs; fall back to the first main tab
    document.querySelector(".tab:not(.editor-tab)")?.click();
  }
}

// Expose for pywebview's evaluate_js bridge (Python opens editor tab via JS)
window.openEditorTab = openEditorTab;
