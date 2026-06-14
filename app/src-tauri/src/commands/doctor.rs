//! Doctor — checks prerequisites and installed AI tools.

use std::collections::HashMap;
use std::path::PathBuf;

#[derive(serde::Serialize)]
pub struct DoctorReport {
    pub executables:  HashMap<String, Option<String>>,
    pub git_lfs:      bool,
    pub gpu:          bool,
    pub tools_home:   String,
    pub tools:        HashMap<String, ToolStatus>,
}

#[derive(serde::Serialize)]
pub struct ToolStatus {
    pub title:     String,
    pub installed: bool,
    pub path:      Option<String>,
}

const TOOL_TITLES: &[(&str, &str)] = &[
    ("index-tts",      "IndexTTS"),
    ("kokoro",         "Kokoro TTS"),
    ("magi-v3",        "MAGI v3 (panel detector)"),
    ("faster-whisper", "faster-whisper"),
];

/// Check a single executable name on PATH.
fn which(name: &str) -> Option<String> {
    let path_var = std::env::var("PATH").unwrap_or_default();
    let sep = if cfg!(windows) { ';' } else { ':' };
    for dir in path_var.split(sep) {
        for candidate in candidates(name) {
            let full = PathBuf::from(dir).join(&candidate);
            if full.exists() {
                return Some(full.to_string_lossy().into_owned());
            }
        }
    }
    None
}

#[cfg(windows)]
fn candidates(name: &str) -> Vec<String> {
    vec![format!("{}.exe", name), name.to_owned(), format!("{}.cmd", name), format!("{}.bat", name)]
}
#[cfg(not(windows))]
fn candidates(name: &str) -> Vec<String> {
    vec![name.to_owned()]
}

fn tools_home() -> PathBuf {
    dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".mangaeasy")
        .join("tools")
}

fn check_tool(key: &str) -> Option<PathBuf> {
    let p = tools_home().join(key);
    if p.is_dir() { Some(p) } else { None }
}

fn check_git_lfs() -> bool {
    std::process::Command::new("git")
        .args(["lfs", "version"])
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

fn check_gpu() -> bool {
    // nvidia-smi present and exits 0
    std::process::Command::new(nvidia_smi_path())
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

fn nvidia_smi_path() -> &'static str {
    if cfg!(windows) {
        "C:\\Windows\\System32\\nvidia-smi.exe"
    } else {
        "nvidia-smi"
    }
}

#[tauri::command]
pub fn run_doctor() -> DoctorReport {
    let mut executables = HashMap::new();
    for name in ["git", "uv", "uvx", "ffmpeg", "ffprobe", "nvidia-smi"] {
        let path = if name == "nvidia-smi" {
            // check specific path on Windows first
            let explicit = PathBuf::from(nvidia_smi_path());
            if explicit.exists() {
                Some(explicit.to_string_lossy().into_owned())
            } else {
                which(name)
            }
        } else {
            which(name)
        };
        executables.insert(name.to_owned(), path);
    }

    let mut tools = HashMap::new();
    for (key, title) in TOOL_TITLES {
        let path = check_tool(key);
        tools.insert(
            key.to_string(),
            ToolStatus {
                title:     title.to_string(),
                installed: path.is_some(),
                path:      path.map(|p| p.to_string_lossy().into_owned()),
            },
        );
    }

    DoctorReport {
        executables,
        git_lfs:    check_git_lfs(),
        gpu:        check_gpu(),
        tools_home: tools_home().to_string_lossy().into_owned(),
        tools,
    }
}
