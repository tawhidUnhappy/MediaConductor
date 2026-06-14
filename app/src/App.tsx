import { useEffect, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import { invoke } from "@tauri-apps/api/core";
import { useStore, fmtTime } from "./store";
import Setup       from "./tabs/Setup";
import Project     from "./tabs/Project";
import Workflow    from "./tabs/Workflow";
import BatchVideos from "./tabs/BatchVideos";
import TerminalTab from "./tabs/TerminalTab";

const TABS = [
  { id: "setup",    label: "Setup" },
  { id: "project",  label: "Project" },
  { id: "workflow", label: "Workflow" },
  { id: "batch",    label: "Batch Videos" },
  { id: "terminal", label: "Terminal" },
];

interface BootstrapStatus {
  uv_found: boolean;
  uv_path: string | null;
  mangaeasy_installed: boolean;
}

export default function App() {
  const { tab, setTab, jobInfo, setJobInfo, progress, setProgress,
          setProgressStart, progressStart, loadProjectRoot } = useStore();

  const [bootstrap, setBootstrap] = useState<BootstrapStatus | null>(null);
  const [bootstrapDone, setBootstrapDone] = useState(false);
  const [bootstrapping, setBootstrapping] = useState(false);

  // Init
  useEffect(() => {
    loadProjectRoot();
    invoke<BootstrapStatus>("bootstrap_check").then((s) => {
      setBootstrap(s);
      if (s.mangaeasy_installed) setBootstrapDone(true);
    });
  }, []);

  // Tauri event listeners
  useEffect(() => {
    const u1 = listen<{ name: string; pid: number | null }>("job:start", (e) => {
      setJobInfo(e.payload);
      setProgressStart(Date.now());
      setProgress({ value: 0, total: 0, label: "" });
    });
    const u2 = listen<{ exit_code: number }>("job:finish", () => {
      setJobInfo(null);
      setProgressStart(null);
    });
    const u3 = listen<{ value: number; total: number; label: string }>("job:progress", (e) => {
      setProgress(e.payload);
    });
    return () => { u1.then(f=>f()); u2.then(f=>f()); u3.then(f=>f()); };
  }, []);

  const elapsed = progressStart ? fmtTime(Date.now() - progressStart) : "";
  const progPct = progress.total > 0
    ? Math.round((progress.value / progress.total) * 100)
    : 0;
  const showProg = !!jobInfo;

  // Bootstrap screen
  if (!bootstrapDone) {
    return (
      <div className="app" style={{ justifyContent: "center", alignItems: "center", gap: 16 }}>
        <div style={{ textAlign: "center" }}>
          <div className="header-title" style={{ fontSize: 22, marginBottom: 8 }}>mangaEasy</div>
          {bootstrap === null ? (
            <p style={{ color: "var(--muted)" }}>Checking environment…</p>
          ) : !bootstrap.uv_found ? (
            <>
              <p style={{ color: "var(--red)", marginBottom: 12 }}>
                <b>uv</b> not found — cannot install mangaEasy.
              </p>
              <p style={{ color: "var(--muted)", fontSize: 12 }}>
                Please install uv from <code>https://docs.astral.sh/uv</code> and restart.
              </p>
            </>
          ) : (
            <>
              <p style={{ color: "var(--muted)", marginBottom: 12 }}>
                mangaEasy Python package not installed.{" "}
                {bootstrapping ? "Installing…" : "Click below to install."}
              </p>
              {!bootstrapping && (
                <button
                  className="btn-primary"
                  onClick={async () => {
                    setBootstrapping(true);
                    setTab("terminal");
                    try {
                      await invoke("bootstrap_install");
                      const s = await invoke<BootstrapStatus>("bootstrap_check");
                      if (s.mangaeasy_installed) setBootstrapDone(true);
                    } finally {
                      setBootstrapping(false);
                    }
                  }}
                >
                  Install mangaEasy
                </button>
              )}
              {bootstrapping && (
                <div style={{ marginTop: 12 }}>
                  <TerminalTab />
                </div>
              )}
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      {/* Header */}
      <div className="header">
        <span className="header-title">mangaEasy</span>
        <span className="header-version">v0.9</span>
        <div className="header-spacer" />
        <span className={`job-badge ${jobInfo ? "running" : ""}`}>
          {jobInfo ? `⏳ ${jobInfo.name}` : "idle"}
        </span>
      </div>

      {/* Progress bar */}
      <div className={`prog-bar-row ${showProg ? "" : "hidden"}`}>
        <div className="prog-bar-bg">
          <div
            className="prog-bar-fill"
            style={{ width: `${progPct}%` }}
          />
        </div>
        <span className="prog-bar-label">
          {progress.total > 0
            ? `${progress.value}/${progress.total} — ${progress.label} — ${elapsed}`
            : progress.label || elapsed}
        </span>
      </div>

      {/* Tabs */}
      <div className="tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={`tab-btn ${tab === t.id ? "active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Panels */}
      <div className="tab-panels">
        <div className={`tab-panel ${tab === "setup"    ? "active" : ""}`}><Setup /></div>
        <div className={`tab-panel ${tab === "project"  ? "active" : ""}`}><Project /></div>
        <div className={`tab-panel ${tab === "workflow" ? "active" : ""}`}><Workflow /></div>
        <div className={`tab-panel ${tab === "batch"    ? "active" : ""}`}><BatchVideos /></div>
        <div className={`tab-panel terminal-panel ${tab === "terminal" ? "active" : ""}`}>
          <TerminalTab />
        </div>
      </div>
    </div>
  );
}
