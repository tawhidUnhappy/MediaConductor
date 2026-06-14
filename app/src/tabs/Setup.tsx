import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";

interface ToolStatus {
  installed: boolean;
  dir: string | null;
}

interface DoctorReport {
  executables: Record<string, string | null>;
  tools: Record<string, ToolStatus>;
  git_lfs: boolean;
  gpu: string | null;
  cuda: string | null;
  tools_home: string | null;
}

const EXEC_LABELS: Record<string, string> = {
  python:     "Python",
  git:        "git",
  ffmpeg:     "ffmpeg",
  imagemagick:"ImageMagick",
};

const TOOL_LABELS: Record<string, [string, string]> = {
  "index-tts":      ["IndexTTS",       "Text-to-speech (chapter audio)"],
  "kokoro":         ["Kokoro TTS",     "Alternative TTS engine"],
  "magi-v3":        ["MAGI v3",        "AI panel understanding"],
  "faster-whisper": ["Faster Whisper", "Speech-to-text (narration)"],
};

function dot(ok: boolean | null) {
  const cls = ok === null ? "muted" : ok ? "ok" : "err";
  return <span className={`dot ${cls}`} />;
}

export default function Setup() {
  const [report, setReport] = useState<DoctorReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [installingTool, setInstallingTool] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    try {
      const r = await invoke<DoctorReport>("run_doctor");
      setReport(r);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh(); }, []);

  async function installTool(key: string) {
    setInstallingTool(key);
    try {
      await invoke("run_job", { command: `install-${key}`, args: [] });
    } finally {
      setInstallingTool(null);
    }
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
        <span style={{ fontSize: 15, fontWeight: 600, color: "#fff" }}>System Check</span>
        <button className="btn-flat" onClick={refresh} disabled={loading} style={{ marginLeft: "auto" }}>
          {loading ? "Checking…" : "Refresh"}
        </button>
      </div>

      {/* Executables */}
      <div className="card">
        <div className="card-title">Prerequisites</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px 20px" }}>
          {Object.entries(EXEC_LABELS).map(([k, label]) => {
            const val = report?.executables[k];
            const ok  = val !== undefined ? val !== null : null;
            return (
              <div key={k} className="prereq-item">
                {dot(ok)}
                <span>{label}</span>
                {val && <span style={{ color: "var(--muted)", fontSize: 11, marginLeft: "auto" }}>{val}</span>}
              </div>
            );
          })}
          <div className="prereq-item">
            {dot(report?.git_lfs ?? null)}
            <span>git-lfs</span>
          </div>
          <div className="prereq-item">
            {dot(report?.gpu !== null && report?.gpu !== undefined ? true : null)}
            <span>GPU</span>
            {report?.gpu && (
              <span style={{ color: "var(--muted)", fontSize: 11, marginLeft: "auto" }}>
                {report.gpu}
              </span>
            )}
          </div>
        </div>
        {report?.cuda && (
          <p style={{ marginTop: 8, fontSize: 12, color: "var(--muted)" }}>CUDA: {report.cuda}</p>
        )}
      </div>

      {/* AI Tools */}
      <div className="card">
        <div className="card-title">AI Tools</div>
        {report?.tools_home && (
          <p className="hint">Tools directory: {report.tools_home}</p>
        )}
        {Object.entries(TOOL_LABELS).map(([key, [name, notes]]) => {
          const ts  = report?.tools[key];
          const ok  = ts?.installed ?? false;
          const busy = installingTool === key;
          return (
            <div key={key} className="card tool-card" style={{ margin: "6px 0", padding: "10px 14px" }}>
              <div className="tool-info">
                <div className="tool-name">{name}</div>
                <div className="tool-notes">{notes}</div>
              </div>
              <span className={`badge ${ok ? "ok" : "err"}`}>{ok ? "Installed" : "Missing"}</span>
              {!ok && (
                <button
                  className="btn-primary"
                  style={{ marginLeft: 8 }}
                  disabled={busy || !!installingTool}
                  onClick={() => installTool(key)}
                >
                  {busy ? "Installing…" : "Install"}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
