use std::path::PathBuf;
use std::sync::Mutex;

// ---------------------------------------------------------------------------
// Terminal history — rolling 64 KB so new connections replay recent output
// ---------------------------------------------------------------------------
pub struct TermHistory {
    buf: String,
}

impl TermHistory {
    pub fn new() -> Self {
        Self { buf: String::new() }
    }
    pub fn push(&mut self, text: &str) {
        self.buf.push_str(text);
        const MAX: usize = 65_536;
        if self.buf.len() > MAX * 2 {
            let trim = self.buf.len() - MAX;
            // trim at a char boundary
            let trim = self.buf.floor_char_boundary(trim);
            self.buf.drain(..trim);
        }
    }
    pub fn snapshot(&self) -> String {
        self.buf.clone()
    }
}

// ---------------------------------------------------------------------------
// Job info — stored while a job is running so we can report name + kill PID
// ---------------------------------------------------------------------------
#[derive(Clone, serde::Serialize)]
pub struct JobInfo {
    pub name: String,
    pub pid: Option<u32>,
}

// ---------------------------------------------------------------------------
// Shared app state managed by Tauri
// ---------------------------------------------------------------------------
pub struct AppState {
    pub project_root: Mutex<PathBuf>,
    pub job:          Mutex<Option<JobInfo>>,
    pub history:      Mutex<TermHistory>,
}

impl AppState {
    pub fn new() -> Self {
        Self {
            project_root: Mutex::new(load_saved_root()),
            job:          Mutex::new(None),
            history:      Mutex::new(TermHistory::new()),
        }
    }
}

fn load_saved_root() -> PathBuf {
    let fallback = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    let Some(home) = dirs::home_dir() else { return fallback };
    let state_path = home.join(".mangaeasy").join("app_state.json");
    let Ok(text) = std::fs::read_to_string(&state_path) else { return fallback };
    let Ok(val)  = serde_json::from_str::<serde_json::Value>(&text) else { return fallback };
    let Some(s)  = val["project_root"].as_str() else { return fallback };
    let p = PathBuf::from(s);
    if p.is_dir() { p } else { fallback }
}

pub fn save_root(root: &PathBuf) {
    let Some(home) = dirs::home_dir() else { return };
    let dir = home.join(".mangaeasy");
    let _ = std::fs::create_dir_all(&dir);
    let data = serde_json::json!({ "project_root": root.to_string_lossy() });
    let _ = std::fs::write(dir.join("app_state.json"), data.to_string());
}
