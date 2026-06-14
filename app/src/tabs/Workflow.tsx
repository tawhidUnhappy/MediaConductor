import { useState, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useStore, runJob } from "../store";

interface ChapterStatus {
  downloads:   number;
  panels:      number;
  narration:   number;
  narr_items:  number;
  audio:       number;
  video:       number;
  ch_dir:      string | null;
}

function StatBadge({ n, label }: { n: number; label: string }) {
  return (
    <span className={`badge ${n > 0 ? "ok" : "warn"}`}>
      {n} {label}
    </span>
  );
}

export default function Workflow() {
  const { projectRoot, jobInfo } = useStore();
  const [chapter, setChapter]   = useState("");
  const [status,  setStatus]    = useState<ChapterStatus | null>(null);
  const [startCh, setStartCh]   = useState("");
  const [endCh,   setEndCh]     = useState("");
  const [fresh,   setFresh]     = useState(false);
  const [dlMode,  setDlMode]    = useState<"single" | "batch">("single");

  async function loadStatus() {
    if (!projectRoot || !chapter) return;
    try {
      const s = await invoke<ChapterStatus>("chapter_status", {
        name: projectRoot.split(/[\\/]/).pop() ?? "",
        chapter,
      });
      setStatus(s);
    } catch { setStatus(null); }
  }

  useEffect(() => { loadStatus(); }, [chapter, projectRoot]);
  // Refresh after job finishes
  useEffect(() => { if (!jobInfo) loadStatus(); }, [jobInfo]);

  const busy = !!jobInfo;

  async function openDir() {
    if (status?.ch_dir) await invoke("open_directory", { path: status.ch_dir });
  }

  async function runBatch() {
    const s = parseInt(startCh, 10);
    const e = parseInt(endCh, 10);
    if (isNaN(s) || isNaN(e)) return;
    for (let i = s; i <= e; i++) {
      await runJob("download", [String(i), ...(fresh ? ["--fresh"] : [])]);
    }
  }

  return (
    <div>
      {/* Chapter selector */}
      <div className="card">
        <div className="card-title">Chapter</div>
        <div className="input-row" style={{ marginBottom: 6 }}>
          <input
            value={chapter}
            onChange={e => setChapter(e.target.value)}
            placeholder="e.g. 001"
            style={{ maxWidth: 120 }}
          />
          <button className="btn-flat" onClick={loadStatus} disabled={!chapter}>Refresh</button>
          {status?.ch_dir && (
            <button className="btn-flat" onClick={openDir}>Open Folder</button>
          )}
        </div>
        {status && (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <StatBadge n={status.downloads}  label="downloads" />
            <StatBadge n={status.panels}     label="panels" />
            <StatBadge n={status.narr_items} label="narration lines" />
            <StatBadge n={status.audio}      label="audio" />
            <StatBadge n={status.video}      label="video" />
          </div>
        )}
      </div>

      {/* Step 1 — Download */}
      <div className="card">
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <span className="step-num">1</span>
          <span style={{ fontWeight: 600 }}>Download</span>
          {status && <StatBadge n={status.downloads} label="files" />}
        </div>

        <div className="radio-group" style={{ marginBottom: 10 }}>
          <label>
            <input type="radio" checked={dlMode === "single"} onChange={() => setDlMode("single")} />
            Single chapter
          </label>
          <label>
            <input type="radio" checked={dlMode === "batch"} onChange={() => setDlMode("batch")} />
            Batch
          </label>
        </div>

        {dlMode === "single" ? (
          <div className="btn-row">
            <button className="btn-primary" disabled={busy || !chapter}
              onClick={() => runJob("download", [chapter])}>
              Download ch {chapter || "…"}
            </button>
            <button className="btn-warning" disabled={busy || !chapter}
              onClick={() => runJob("download", [chapter, "--fresh"])}>
              Re-download (fresh)
            </button>
          </div>
        ) : (
          <>
            <div className="card-row" style={{ gap: 8, marginBottom: 8 }}>
              <div style={{ flex: 1 }}>
                <label>From chapter</label>
                <input value={startCh} onChange={e => setStartCh(e.target.value)} placeholder="1" />
              </div>
              <div style={{ flex: 1 }}>
                <label>To chapter</label>
                <input value={endCh} onChange={e => setEndCh(e.target.value)} placeholder="10" />
              </div>
            </div>
            <label className="check-row" style={{ marginBottom: 8 }}>
              <input type="checkbox" checked={fresh} onChange={e => setFresh(e.target.checked)} />
              Fresh (skip existing)
            </label>
            <div className="btn-row">
              <button className="btn-primary" disabled={busy || !startCh || !endCh}
                onClick={runBatch}>
                Batch Download {startCh}–{endCh}
              </button>
            </div>
          </>
        )}
      </div>

      {/* Step 2 — Panels */}
      <div className="card">
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <span className="step-num">2</span>
          <span style={{ fontWeight: 600 }}>Panels</span>
          {status && <StatBadge n={status.panels} label="panels" />}
        </div>
        <div className="btn-row">
          <button className="btn-primary" disabled={busy || !chapter}
            onClick={() => runJob("panels", [chapter])}>
            Extract Panels
          </button>
          <button className="btn-flat" disabled={busy || !chapter}
            onClick={() => runJob("panels", [chapter, "--reset"])}>
            Reset &amp; Re-extract
          </button>
        </div>
      </div>

      {/* Step 3 — Narration */}
      <div className="card">
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <span className="step-num">3</span>
          <span style={{ fontWeight: 600 }}>Narration</span>
          {status && <StatBadge n={status.narr_items} label="lines" />}
        </div>
        <div className="btn-row">
          <button className="btn-primary" disabled={busy || !chapter}
            onClick={() => runJob("narrate", [chapter])}>
            Generate Narration
          </button>
          <button className="btn-flat" disabled={busy || !chapter}
            onClick={() => runJob("narrate", [chapter, "--reset"])}>
            Reset &amp; Regenerate
          </button>
        </div>
      </div>

      {/* Step 4 — Audio */}
      <div className="card">
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <span className="step-num">4</span>
          <span style={{ fontWeight: 600 }}>Audio</span>
          {status && <StatBadge n={status.audio} label="files" />}
        </div>
        <div className="btn-row">
          <button className="btn-primary" disabled={busy || !chapter}
            onClick={() => runJob("audio", [chapter])}>
            Generate Audio
          </button>
          <button className="btn-flat" disabled={busy || !chapter}
            onClick={() => runJob("audio", [chapter, "--reset"])}>
            Reset &amp; Regenerate
          </button>
        </div>
      </div>

      {/* Step 5 — Video */}
      <div className="card">
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <span className="step-num">5</span>
          <span style={{ fontWeight: 600 }}>Video</span>
          {status && <StatBadge n={status.video} label="files" />}
        </div>
        <div className="btn-row">
          <button className="btn-primary" disabled={busy || !chapter}
            onClick={() => runJob("video", [chapter])}>
            Generate Video
          </button>
          <button className="btn-warning" disabled={busy || !chapter}
            onClick={() => runJob("video", [chapter, "--all"])}>
            Full Pipeline (all steps)
          </button>
        </div>
      </div>
    </div>
  );
}
