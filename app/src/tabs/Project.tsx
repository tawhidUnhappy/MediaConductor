import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useStore } from "../store";

type Cfg = Record<string, unknown>;

export default function Project() {
  const { projectRoot, setProjectRoot, loadProjectRoot } = useStore();
  const [cfg,    setCfg]    = useState<Cfg>({});
  const [sysCfg, setSysCfg] = useState<Cfg>({});
  const [saved,  setSaved]  = useState(false);

  async function loadConfig() {
    try {
      const [c, s] = await invoke<[Cfg, Cfg]>("read_config");
      setCfg(c);
      setSysCfg(s);
    } catch {/* no project root set yet */}
  }

  useEffect(() => {
    loadProjectRoot().then(loadConfig);
  }, []);

  async function pickRoot() {
    const p = await invoke<string | null>("pick_directory");
    if (p) {
      await invoke("set_project_root", { path: p });
      setProjectRoot(p);
      await loadConfig();
    }
  }

  async function openRoot() {
    if (projectRoot) await invoke("open_directory", { path: projectRoot });
  }

  function str(obj: Cfg, key: string): string {
    return (obj[key] as string) ?? "";
  }

  function set(key: string, val: string) {
    setCfg((p) => ({ ...p, [key]: val }));
  }

  function setSys(key: string, val: string) {
    setSysCfg((p) => ({ ...p, [key]: val }));
  }

  async function save() {
    await invoke("write_config", { cfg, sysCfg });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <div>
      {/* Project root */}
      <div className="card">
        <div className="card-title">Project Root</div>
        <div className="input-row" style={{ marginBottom: 6 }}>
          <input value={projectRoot} readOnly placeholder="Select a folder…" />
          <button className="btn-primary" onClick={pickRoot}>Browse</button>
          {projectRoot && (
            <button className="btn-flat" onClick={openRoot}>Open</button>
          )}
        </div>
        <p className="hint">Root folder that contains your manga project (chapter folders live here).</p>
      </div>

      {projectRoot && (
        <>
          {/* Project config */}
          <div className="card">
            <div className="card-title">Project Config</div>
            <div className="card-grid2">
              <div>
                <label>Manga name (slug)</label>
                <input value={str(cfg, "name")} onChange={e => set("name", e.target.value)} />
              </div>
              <div>
                <label>Title (display)</label>
                <input value={str(cfg, "title")} onChange={e => set("title", e.target.value)} />
              </div>
              <div>
                <label>Language</label>
                <input value={str(cfg, "language")} onChange={e => set("language", e.target.value)} />
              </div>
              <div>
                <label>Author</label>
                <input value={str(cfg, "author")} onChange={e => set("author", e.target.value)} />
              </div>
            </div>
            <div style={{ marginBottom: 8 }}>
              <label>Description</label>
              <textarea
                rows={3}
                value={str(cfg, "description")}
                onChange={e => set("description", e.target.value)}
              />
            </div>
          </div>

          {/* System config */}
          <div className="card">
            <div className="card-title">System Config</div>
            <div className="card-grid2">
              <div>
                <label>TTS Engine</label>
                <select value={str(sysCfg, "tts_engine")} onChange={e => setSys("tts_engine", e.target.value)}>
                  <option value="">auto</option>
                  <option value="index-tts">IndexTTS</option>
                  <option value="kokoro">Kokoro</option>
                </select>
              </div>
              <div>
                <label>GPU device</label>
                <input value={str(sysCfg, "gpu_device")} onChange={e => setSys("gpu_device", e.target.value)} placeholder="cuda:0" />
              </div>
            </div>
          </div>

          <div className="btn-row">
            <button className="btn-primary" onClick={save}>
              {saved ? "Saved ✓" : "Save Config"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
