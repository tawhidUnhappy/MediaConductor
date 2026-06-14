import { useState } from "react";
import { useStore, runJob } from "../store";

const STEPS = [
  { id: "download",  label: "Download" },
  { id: "panels",    label: "Panels" },
  { id: "narrate",   label: "Narration" },
  { id: "audio",     label: "Audio" },
  { id: "video",     label: "Video" },
];

export default function BatchVideos() {
  const { jobInfo } = useStore();
  const [start,    setStart]    = useState("");
  const [end,      setEnd]      = useState("");
  const [steps,    setSteps]    = useState<Set<string>>(new Set(STEPS.map(s => s.id)));
  const [fresh,    setFresh]    = useState(false);
  const [running,  setRunning]  = useState(false);
  const [current,  setCurrent]  = useState<string | null>(null);

  const busy = !!jobInfo || running;

  function toggleStep(id: string) {
    setSteps(prev => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  }

  function selectAll()  { setSteps(new Set(STEPS.map(s => s.id))); }
  function selectNone() { setSteps(new Set()); }

  async function run() {
    const s = parseInt(start, 10);
    const e = parseInt(end, 10);
    if (isNaN(s) || isNaN(e) || s > e) return;

    setRunning(true);
    try {
      for (let ch = s; ch <= e; ch++) {
        const chStr = String(ch).padStart(3, "0");
        for (const step of STEPS) {
          if (!steps.has(step.id)) continue;
          setCurrent(`ch ${chStr} — ${step.label}`);
          const args: string[] = [chStr];
          if (fresh && step.id === "download") args.push("--fresh");
          await runJob(step.id, args);
        }
      }
    } finally {
      setRunning(false);
      setCurrent(null);
    }
  }

  return (
    <div>
      <div className="card">
        <div className="card-title">Batch Pipeline</div>
        <p className="hint">
          Run selected pipeline steps for a range of chapters sequentially.
        </p>

        <div className="card-row" style={{ gap: 8, marginBottom: 12 }}>
          <div style={{ flex: 1 }}>
            <label>From chapter</label>
            <input value={start} onChange={e => setStart(e.target.value)} placeholder="1" />
          </div>
          <div style={{ flex: 1 }}>
            <label>To chapter</label>
            <input value={end} onChange={e => setEnd(e.target.value)} placeholder="10" />
          </div>
        </div>

        <div className="section-title">Steps to run</div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
          {STEPS.map(s => (
            <label key={s.id} className="check-row">
              <input
                type="checkbox"
                checked={steps.has(s.id)}
                onChange={() => toggleStep(s.id)}
              />
              {s.label}
            </label>
          ))}
        </div>
        <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
          <button className="btn-flat" style={{ fontSize: 11, padding: "2px 8px" }} onClick={selectAll}>All</button>
          <button className="btn-flat" style={{ fontSize: 11, padding: "2px 8px" }} onClick={selectNone}>None</button>
        </div>

        <label className="check-row" style={{ marginBottom: 12 }}>
          <input type="checkbox" checked={fresh} onChange={e => setFresh(e.target.checked)} />
          Fresh download (skip already-downloaded chapters)
        </label>

        {current && (
          <p style={{ fontSize: 12, color: "var(--blue)", marginBottom: 8 }}>
            Running: {current}
          </p>
        )}

        <div className="btn-row">
          <button
            className="btn-primary"
            disabled={busy || !start || !end || steps.size === 0}
            onClick={run}
          >
            {running ? "Running…" : `Run Batch ch ${start || "?"} → ${end || "?"}`}
          </button>
        </div>
      </div>
    </div>
  );
}
