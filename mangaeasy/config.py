"""mangaeasy.config
Loader for the two workspace config files.

  config.json         — per-manga / per-run settings (name, chapter, bgm file …)
  config.system.json  — system-wide settings that rarely change (resolution,
                        fps, encoder params, whisper model …)

PROJECT_ROOT here is the **workspace root** (the folder holding config.json,
library/, music/, …) — resolved from $MANGAEASY_PROJECT_ROOT or the cwd. It is
NOT the `--project-root` flag of the video pipeline (that one names the folder
containing item folders, e.g. library/<name>); the two concepts share a name
for historical reasons only.

This module is import-safe for libraries and servers: loaders raise
ConfigError instead of exiting, and nothing mutates os.environ at import time.
(It used to set HF_HOME to <cwd>/.hf_cache on import, which fought the
force-pinned per-install caches in mangaeasy.tools.external.tool_env() — the
tool envs own ML cache placement now; see that module.)
"""

import json
import os
from pathlib import Path

_PACKAGE_ROOT: Path = Path(__file__).resolve().parent.parent


class ConfigError(RuntimeError):
    """A required config file is missing or unparseable.

    Raised instead of sys.exit so the MCP server, tests, and any embedder
    get an exception they can handle; the CLI dispatcher converts it into a
    clean `[ERROR] ...` on stderr with exit code 1.
    """


def _project_root() -> Path:
    configured = os.environ.get("MANGAEASY_PROJECT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.cwd().resolve()


PROJECT_ROOT: Path = _project_root()

CONFIG_FILE:        Path = PROJECT_ROOT / "config.json"
SYSTEM_CONFIG_FILE: Path = PROJECT_ROOT / "config.system.json"

# Legacy in-workspace ML cache location. Only used as a last-resort fallback
# by code that may run outside a tool env; tool_env() pins the real caches.
HF_CACHE_DIR:   Path = PROJECT_ROOT / ".hf_cache"
TORCH_HOME_DIR: Path = PROJECT_ROOT / ".cache" / "torch"


# ── Config loaders ────────────────────────────────────────────────────────────

def load_config() -> dict:
    """Return the full parsed config.json (per-manga / per-run settings)."""
    if not CONFIG_FILE.exists():
        raise ConfigError(f"config.json not found at {CONFIG_FILE}")
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ConfigError(f"Invalid config.json: {exc}") from exc


_warned_missing_system_config = False


def load_system_config() -> dict:
    """Return the full parsed config.system.json (system-wide settings).

    Falls back to an empty dict if the file is missing so callers can use
    .get() with their own defaults — avoids hard failures on first run.
    """
    global _warned_missing_system_config
    if not SYSTEM_CONFIG_FILE.exists():
        # Many helpers re-read the config; one warning per process is enough.
        if not _warned_missing_system_config:
            import sys
            print(f"[WARN] config.system.json not found at {SYSTEM_CONFIG_FILE} — using defaults",
                  file=sys.stderr)
            _warned_missing_system_config = True
        return {}
    try:
        return json.loads(SYSTEM_CONFIG_FILE.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ConfigError(f"Invalid config.system.json: {exc}") from exc


def load_download_config() -> dict:
    """Return merged download settings.

    Base defaults come from config.system.json → download_defaults.
    Per-manga overrides (manga_id, name, chapter) come from config.json → download.
    Project values always win over system defaults.
    """
    syscfg   = load_system_config()
    cfg      = load_config()
    defaults = syscfg.get("download_defaults", {})
    project  = cfg.get("download")
    if not project or not isinstance(project, dict):
        raise ConfigError("'download' key missing in config.json")
    # Merge: defaults first, project values override
    merged = {**defaults, **project}
    return merged
