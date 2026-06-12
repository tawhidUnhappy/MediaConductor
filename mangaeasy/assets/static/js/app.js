/* mangaEasy control center */
"use strict";

const $ = (id) => document.getElementById(id);

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `${res.status} ${res.statusText}`);
  return data;
}

/* ── Tabs ──────────────────────────────────────────────────────────────── */
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-page").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $(`tab-${btn.dataset.tab}`).classList.add("active");
  });
});

/* ── Log console (SSE) ─────────────────────────────────────────────────── */
const logLines = $("log-lines");
function appendLog(ts, msg) {
  const div = document.createElement("div");
  div.className = "log-line";
  if (/\b(error|failed|fatal)\b/i.test(msg)) div.classList.add("err");
  else if (/\[warn\]|warning/i.test(msg)) div.classList.add("warn");
  const tsSpan = document.createElement("span");
  tsSpan.className = "ts";
  tsSpan.textContent = ts;
  div.appendChild(tsSpan);
  div.appendChild(document.createTextNode(msg));
  logLines.appendChild(div);
  while (logLines.childNodes.length > 2000) logLines.removeChild(logLines.firstChild);
  logLines.scrollTop = logLines.scrollHeight;
}

const events = new EventSource("/log_stream");
events.onmessage = (e) => {
  try {
    const entry = JSON.parse(e.data);
    if (entry.ping) return;
    appendLog(entry.ts, entry.msg);
  } catch { /* ignore malformed entries */ }
};

$("log-clear").addEventListener("click", () => (logLines.innerHTML = ""));
$("console-toggle").addEventListener("click", () => {
  const c = $("console");
  c.classList.toggle("collapsed");
  $("console-toggle").textContent = c.classList.contains("collapsed") ? "Show" : "Hide";
});

/* ── Folder picking ────────────────────────────────────────────────────── */
/* Browse… first asks the server for the native OS dialog (desktop window).
   In browser mode it falls back to the in-app folder browser modal. */

let fmOnSelect = null;
let fmCurrent = "";

async function fmLoad(path) {
  let data;
  try {
    data = await api(`/api/fs/list?path=${encodeURIComponent(path || "")}`);
  } catch (err) {
    $("fm-error").textContent = err.message;
    return;
  }
  $("fm-error").textContent = "";
  fmCurrent = data.path;
  $("fm-path").value = data.path;
  $("fm-up").disabled = !data.parent;
  $("fm-up").dataset.parent = data.parent || "";

  const shortcuts = $("fm-shortcuts");
  shortcuts.innerHTML = "";
  const links = [["🏠 Home", data.home], ...data.drives.map((d) => [d, d])];
  for (const [label, target] of links) {
    const b = document.createElement("button");
    b.className = "btn small";
    b.textContent = label;
    b.addEventListener("click", () => fmLoad(target));
    shortcuts.appendChild(b);
  }

  const list = $("fm-list");
  list.innerHTML = "";
  if (!data.dirs.length) {
    list.innerHTML = `<div class="fm-empty">No subfolders — click “Use this folder” to pick it.</div>`;
  }
  for (const name of data.dirs) {
    const row = document.createElement("div");
    row.className = "fm-dir";
    row.textContent = `📁 ${name}`;
    row.addEventListener("click", () =>
      fmLoad(fmCurrent.endsWith("\\") || fmCurrent.endsWith("/")
        ? fmCurrent + name : `${fmCurrent}/${name}`));
    list.appendChild(row);
  }
}

function openFolderModal(start, onSelect) {
  fmOnSelect = onSelect;
  $("folder-modal").classList.remove("hidden");
  fmLoad(start || "");
}

function closeFolderModal() {
  $("folder-modal").classList.add("hidden");
  fmOnSelect = null;
}

$("fm-up").addEventListener("click", () => fmLoad($("fm-up").dataset.parent));
$("fm-go").addEventListener("click", () => fmLoad($("fm-path").value.trim()));
$("fm-path").addEventListener("keydown", (e) => {
  if (e.key === "Enter") fmLoad($("fm-path").value.trim());
});
$("fm-cancel").addEventListener("click", closeFolderModal);
$("folder-modal").addEventListener("click", (e) => {
  if (e.target === $("folder-modal")) closeFolderModal();
});
$("fm-select").addEventListener("click", () => {
  if (fmOnSelect && fmCurrent) fmOnSelect(fmCurrent);
  closeFolderModal();
});

async function pickFolder(input) {
  const start = input.value.trim();
  try {
    const res = await api("/api/pick-folder", {
      method: "POST",
      body: JSON.stringify({ start }),
    });
    if (res.folder) {
      input.value = res.folder;
      input.dispatchEvent(new Event("change"));
      return;
    }
    if (!res.unsupported) return; // native dialog shown, user cancelled
  } catch { /* fall through to the in-app browser */ }
  openFolderModal(start, (folder) => {
    input.value = folder;
    input.dispatchEvent(new Event("change"));
  });
}

document.querySelectorAll("[data-browse]").forEach((btn) =>
  btn.addEventListener("click", () => pickFolder($(btn.dataset.browse))));

document.querySelectorAll("[data-open]").forEach((btn) =>
  btn.addEventListener("click", async () => {
    const path = $(btn.dataset.open).value.trim();
    try {
      await api("/api/open-folder", { method: "POST", body: JSON.stringify({ path }) });
    } catch (err) {
      appendLog("", `open folder: ${err.message}`);
    }
  }));

/* ── Remembered UI state ───────────────────────────────────────────────── */
const PERSIST_VALUES = [
  "run-manga-dir", "run-output-dir", "run-step", "run-tts",
  "run-encoder", "run-device", "run-items", "run-name",
];
const PERSIST_CHECKS = ["run-long", "run-ow-audio", "run-ow-video"];

let saveTimer = null;
function scheduleSaveState() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    const ui = {};
    for (const id of PERSIST_VALUES) ui[id] = $(id).value;
    for (const id of PERSIST_CHECKS) ui[id] = $(id).checked;
    try {
      await api("/api/appstate", { method: "POST", body: JSON.stringify(ui) });
    } catch { /* persistence is best-effort */ }
  }, 400);
}

async function loadUiState() {
  try {
    const { ui } = await api("/api/appstate");
    for (const id of PERSIST_VALUES) if (ui[id] != null) $(id).value = ui[id];
    for (const id of PERSIST_CHECKS) if (ui[id] != null) $(id).checked = !!ui[id];
  } catch { /* fresh defaults are fine */ }
  updateStepUI();
}

for (const id of [...PERSIST_VALUES, ...PERSIST_CHECKS]) {
  $(id).addEventListener("change", scheduleSaveState);
}

/* ── Setup tab ─────────────────────────────────────────────────────────── */
const PREREQ_LABELS = {
  git: "Git", uv: "uv", uvx: "uvx",
  ffmpeg: "FFmpeg", ffprobe: "FFprobe", "nvidia-smi": "NVIDIA GPU",
};

let jobRunning = false;

async function loadDoctor() {
  let report;
  try {
    report = await api("/api/doctor");
  } catch (err) {
    appendLog("", `doctor failed: ${err.message}`);
    return;
  }

  $("tools-home").textContent = `Tools folder: ${report.tools_home}`;

  const grid = $("prereq-grid");
  grid.innerHTML = "";
  for (const [exe, where] of Object.entries(report.executables)) {
    const optional = exe === "nvidia-smi";
    const cls = where ? "ok" : optional ? "na" : "bad";
    grid.insertAdjacentHTML("beforeend",
      `<div class="prereq" title="${where || "not found on PATH"}">
         <span class="dot ${cls}"></span>${PREREQ_LABELS[exe] || exe}</div>`);
  }
  grid.insertAdjacentHTML("beforeend",
    `<div class="prereq"><span class="dot ${report.git_lfs ? "ok" : "bad"}"></span>git-lfs</div>`);

  const cards = $("tool-cards");
  cards.innerHTML = "";
  for (const [key, info] of Object.entries(report.tools)) {
    let badge, action = "";
    if (info.installed) {
      badge = `<span class="badge installed">installed</span>`;
      action = `<button class="btn small" data-install="${key}" ${jobRunning ? "disabled" : ""}>Reinstall</button>`;
    } else if (!info.configured) {
      badge = `<span class="badge unconfigured">repo URL not set</span>`;
    } else {
      badge = `<span class="badge missing">not installed</span>`;
      action = `<button class="btn primary" data-install="${key}" ${jobRunning ? "disabled" : ""}>Install</button>`;
    }
    cards.insertAdjacentHTML("beforeend",
      `<div class="card">
         <div class="info">
           <div class="title">${info.title}<span class="key">${key}</span></div>
           <div class="desc">${info.notes}</div>
           ${info.path ? `<div class="path">${info.path}</div>` : ""}
         </div>
         ${badge}${action}
       </div>`);
  }

  cards.querySelectorAll("[data-install]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const name = btn.dataset.install;
      btn.disabled = true;
      try {
        await api(`/api/install-tool/${name}`, {
          method: "POST",
          body: JSON.stringify({
            cpu: $("opt-cpu").checked,
            skip_model: $("opt-skip-model").checked,
          }),
        });
        appendLog("", `install started: ${name} (watch the logs below)`);
      } catch (err) {
        appendLog("", `install failed to start: ${err.message}`);
        btn.disabled = false;
      }
    });
  });
}

$("doctor-refresh").addEventListener("click", loadDoctor);

/* ── Project tab ───────────────────────────────────────────────────────── */
async function loadProject() {
  const data = await api("/api/config");
  $("project-root").value = data.root;

  const cfg = data.config || data.config_example || {};
  const dl = cfg.download || {};
  $("cfg-manga-id").value = dl.manga_id || "";
  $("cfg-name").value = dl.name || "";
  $("cfg-chapter").value = dl.chapter ?? 1;
  $("cfg-status").textContent = data.config ? "" : "config.json not found yet — Save creates it.";

  const sys = data.system || data.system_example || {};
  $("syscfg").value = JSON.stringify(sys, null, 2);
  $("syscfg-status").textContent = data.system ? "" : "config.system.json not found yet — Save creates it.";
}

async function setProjectRoot() {
  try {
    await api("/api/project", { method: "POST", body: JSON.stringify({ root: $("project-root").value }) });
    await loadProject();
    await pollStatus();
  } catch (err) {
    appendLog("", `project: ${err.message}`);
  }
}

$("project-set").addEventListener("click", setProjectRoot);
// Browsing to a folder is a clear intent — apply it without a second click.
$("project-root").addEventListener("change", setProjectRoot);

$("cfg-save").addEventListener("click", async () => {
  const data = await api("/api/config");
  const cfg = data.config || data.config_example || {};
  cfg.download = {
    ...(cfg.download || {}),
    manga_id: $("cfg-manga-id").value.trim(),
    name: $("cfg-name").value.trim(),
    chapter: parseInt($("cfg-chapter").value, 10) || 1,
  };
  delete cfg._comment;
  await api("/api/config", { method: "POST", body: JSON.stringify({ config: cfg }) });
  $("cfg-status").textContent = "saved ✓";
  setTimeout(() => ($("cfg-status").textContent = ""), 2500);
});

$("syscfg-save").addEventListener("click", async () => {
  let parsed;
  try {
    parsed = JSON.parse($("syscfg").value);
  } catch (err) {
    $("syscfg-status").textContent = `invalid JSON: ${err.message}`;
    return;
  }
  delete parsed._comment;
  await api("/api/config", { method: "POST", body: JSON.stringify({ system: parsed }) });
  $("syscfg-status").textContent = "saved ✓";
  setTimeout(() => ($("syscfg-status").textContent = ""), 2500);
});

/* ── Create videos (run) tab ───────────────────────────────────────────── */
const STEPS_WITH_OUTPUT = new Set(["video", "video-render", "video-join", "video-validate"]);

function updateStepUI() {
  const step = $("run-step").value;
  $("run-tts").disabled = step !== "video";
  $("run-long").disabled = step !== "video";
  $("run-output-dir").disabled = !STEPS_WITH_OUTPUT.has(step);
}
$("run-step").addEventListener("change", updateStepUI);

function buildRunArgs() {
  const step = $("run-step").value;
  const mangaDir = $("run-manga-dir").value.trim() || "content";
  const outputDir = $("run-output-dir").value.trim() || "output";
  const name = $("run-name").value.trim();
  const items = $("run-items").value.trim();
  const args = ["--project-root", mangaDir];

  if (STEPS_WITH_OUTPUT.has(step)) args.push("--output-root", outputDir);
  if (items) args.push("--item-range", items);
  if (name) args.push("--project-name", name);

  if (step === "video") {
    args.push("--tts", $("run-tts").value);
    args.push("--encoder", $("run-encoder").value, "--device", $("run-device").value);
    if ($("run-long").checked) args.push("--build-long-video");
    if ($("run-ow-audio").checked) args.push("--overwrite-audio");
    if ($("run-ow-video").checked) args.push("--overwrite-video");
  } else if (step === "video-check") {
    args.push("--strict");
  } else if (step === "video-audio") {
    args.push("--device", $("run-device").value);
    if ($("run-ow-audio").checked) args.push("--overwrite");
  } else if (step === "video-audio-indextts") {
    if ($("run-ow-audio").checked) args.push("--overwrite");
  } else if (step === "video-render") {
    args.push("--encoder", $("run-encoder").value);
    if ($("run-ow-video").checked) args.push("--overwrite");
  }
  return { command: step, args };
}

$("run-start").addEventListener("click", async () => {
  try {
    const payload = buildRunArgs();
    await api("/api/run", { method: "POST", body: JSON.stringify(payload) });
  } catch (err) {
    appendLog("", `run: ${err.message}`);
  }
  pollStatus();
});

$("run-stop").addEventListener("click", async () => {
  try { await api("/api/stop", { method: "POST" }); } catch (err) { appendLog("", err.message); }
});

$("chap-run").addEventListener("click", async () => {
  const command = $("chap-cmd").value;
  const extra = $("chap-args").value.trim();
  const args = extra ? extra.split(/\s+/) : [];
  try {
    await api("/api/run", { method: "POST", body: JSON.stringify({ command, args }) });
  } catch (err) {
    appendLog("", `run: ${err.message}`);
  }
  pollStatus();
});

/* ── Editors tab ───────────────────────────────────────────────────────── */
const EDITORS = [
  { key: "cut-page", title: "Cut Page", desc: "Cut downloaded pages into panels (with AI panel detection)." },
  { key: "panel-editor", title: "Panel Editor", desc: "Arrange panels for vertical manhwa / webtoons." },
  { key: "narration-editor", title: "Narration Editor", desc: "Write narration for the current chapter." },
  { key: "narration-editor-all", title: "Narration Editor (All)", desc: "Write narration across all chapters." },
  { key: "narration-review", title: "Narration Review", desc: "Review and QA narration before TTS." },
];

let editorState = {};

function renderEditors() {
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
         ${running ? `<span class="badge running">running</span>
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

/* ── Status polling ────────────────────────────────────────────────────── */
async function pollStatus() {
  let st;
  try { st = await api("/api/status"); } catch { return; }

  const wasRunning = jobRunning;
  jobRunning = !!(st.job && st.job.running);

  const ind = $("job-indicator");
  if (jobRunning) {
    ind.className = "busy";
    ind.textContent = `${st.job.kind}: ${st.job.name}`;
  } else {
    ind.className = "idle";
    ind.textContent = "idle";
  }

  $("run-start").disabled = jobRunning;
  $("chap-run").disabled = jobRunning;
  $("run-stop").disabled = !(jobRunning && st.job.kind === "run");
  if (jobRunning && st.job.kind === "run") {
    $("run-status").textContent = `running: ${st.job.name}…`;
  } else if (wasRunning && !jobRunning) {
    $("run-status").textContent = "finished — see the log below ✓";
    setTimeout(() => {
      if (!jobRunning) $("run-status").textContent = "";
    }, 8000);
  }

  const edChanged = JSON.stringify(st.editors) !== JSON.stringify(editorState);
  editorState = st.editors || {};
  if (edChanged) renderEditors();

  // refresh tool cards when an install just finished
  if (wasRunning && !jobRunning) loadDoctor();
}

/* ── Init ──────────────────────────────────────────────────────────────── */
(async function init() {
  renderEditors();
  await Promise.allSettled([loadDoctor(), loadProject(), loadUiState(), pollStatus()]);
  setInterval(pollStatus, 2000);
})();
