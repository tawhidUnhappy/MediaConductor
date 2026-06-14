import { create } from "zustand";
import { invoke } from "@tauri-apps/api/core";

export interface JobInfo {
  name: string;
  pid: number | null;
}

export interface Progress {
  value: number;
  total: number;
  label: string;
}

interface Store {
  tab: string;
  setTab: (t: string) => void;

  projectRoot: string;
  setProjectRoot: (r: string) => void;
  loadProjectRoot: () => Promise<void>;

  jobInfo: JobInfo | null;
  setJobInfo: (j: JobInfo | null) => void;

  progress: Progress;
  setProgress: (p: Progress) => void;

  progressStart: number | null;
  setProgressStart: (t: number | null) => void;
}

export const useStore = create<Store>((set) => ({
  tab: "setup",
  setTab: (tab) => set({ tab }),

  projectRoot: "",
  setProjectRoot: (r) => set({ projectRoot: r }),
  loadProjectRoot: async () => {
    const r = await invoke<string>("get_project_root");
    set({ projectRoot: r });
  },

  jobInfo: null,
  setJobInfo: (j) => set({ jobInfo: j }),

  progress: { value: 0, total: 0, label: "" },
  setProgress: (p) => set({ progress: p }),

  progressStart: null,
  setProgressStart: (t) => set({ progressStart: t }),
}));

// ── Job helpers used by multiple tabs ────────────────────────────────────────

export async function runJob(command: string, args: string[] = []) {
  await invoke("run_job", { command, args });
}

export async function stopJob() {
  await invoke("stop_job");
}

export function fmtTime(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(s / 60);
  return m ? `${m}m ${s % 60}s` : `${s}s`;
}
