"""The one map of where mangaEasy puts things on disk.

Two roots, and only two:

``<workspace>/data/``
    Everything mangaEasy downloads or generates: source chapters,
    cropped panels, narration, TTS takes, renders, review evidence, job
    logs, scratch. **Deleting this folder returns the install to a clean
    slate** — that is its entire reason to exist. Nothing else in the
    workspace is production state, so nothing else has to be hunted down.

``<install>/runtime/``
    The multi-gigabyte, re-downloadable machinery: isolated AI tool envs,
    model/wheel caches, install-level state, OAuth tokens. Kept *outside*
    ``data/`` on purpose — a fresh start should cost seconds, not an 80 GB
    re-download — and re-creatable with ``mangaeasy setup``.

``bgm/`` and ``vocal/`` sit beside both and belong to the user: licensed
music and narrator reference takes that mangaEasy reads and never
writes. Deleting ``data/`` must never touch them.

Every persistent path in the codebase resolves through a function here, so
"where does X live" has exactly one answer and ``workspace-layout`` can
report the truth rather than a hopeful description. Module-level imports
stay stdlib-only and every ``mangaeasy`` import is function-local:
``tools.external`` calls back into this module for its runtime root, and a
module-level edge in either direction would deadlock that cycle at import.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DATA_DIRNAME = "data"
RUNTIME_DIRNAME = "runtime"

# Subfolders of data/, in the order a production actually flows through them.
DATA_SUBDIRS: tuple[tuple[str, str], ...] = (
    ("library", "downloaded chapters, cropped panels, narration, and review records"),
    ("audio", "raw TTS takes with their provenance sidecars"),
    ("audio_faded", "render-safe narration derivatives (8 ms edge fades)"),
    ("output", "item videos, the joined full video, and quality reports"),
    ("review", "review sheets and evidence rendered for approval"),
    ("work", "scratch space and background job logs — safe to delete any time"),
)

# Subfolders of runtime/.
RUNTIME_SUBDIRS: tuple[tuple[str, str], ...] = (
    ("tools", "isolated AI tool environments (install-tool)"),
    ("cache", "Hugging Face, Torch, uv, Triton and Inductor caches"),
    ("state", "install-level state: which workspace this install points at"),
    ("secrets", "gitignored OAuth tokens — never printed, only paths/booleans"),
)

# Cache subfolder per environment variable that external tools honour.
CACHE_SUBDIRS: dict[str, str] = {
    "hf": "Hugging Face hub downloads (models, tokenizers)",
    "torch": "torch.hub checkpoints",
    "torch_extensions": "compiled torch C++/CUDA extensions",
    "torchinductor": "TorchInductor compilation cache",
    "triton": "Triton kernel cache",
    "uv": "uv wheel/source cache",
    "uv_python": "uv-managed Python interpreters",
    "xdg": "XDG_CACHE_HOME for tools that ignore the rest",
}


def _resolved(value: str) -> Path:
    return Path(value).expanduser().resolve()


# ── The two roots ─────────────────────────────────────────────────────────────

def workspace_root() -> Path:
    """The workspace this process is operating on (holds config.json, data/)."""
    from mangaeasy.config import PROJECT_ROOT

    return PROJECT_ROOT


def data_root() -> Path:
    """``<workspace>/data`` — the single deletable home for production state.

    ``MANGAEASY_DATA_ROOT`` relocates it wholesale (a second drive, a
    scratch volume). Overriding one *sub*-root instead is what scatters a
    production across a machine, so the individual roots below deliberately
    have no separate environment variables.
    """
    configured = os.environ.get("MANGAEASY_DATA_ROOT")
    if configured:
        return _resolved(configured)
    return (workspace_root() / DATA_DIRNAME).resolve()


def runtime_root() -> Path:
    """``<install>/runtime`` — tool envs, caches, state, secrets.

    Anchored to the *install*, not the workspace: tool envs are provisioned
    per install and survive a ``data/`` wipe. ``MANGAEASY_HOME``
    relocates it (e.g. to share one 80 GB tool tree across checkouts).
    """
    configured = os.environ.get("MANGAEASY_HOME")
    if configured:
        return _resolved(configured)
    from mangaeasy.tools.external import app_root

    return (app_root() / RUNTIME_DIRNAME).resolve()


# ── data/ sub-roots ───────────────────────────────────────────────────────────

def _paths_config() -> dict:
    """config.system.json → paths, read without the missing-file warning.

    layout is imported by nearly every command; a first run without a
    config.system.json should not print a warning for the privilege of
    knowing where library/ is.
    """
    from mangaeasy.config import SYSTEM_CONFIG_FILE

    try:
        loaded = json.loads(SYSTEM_CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    value = loaded.get("paths") if isinstance(loaded, dict) else None
    return value if isinstance(value, dict) else {}


def library_root() -> Path:
    """Every downloaded title, one subfolder each: ``data/library/<project>``.

    Renameable via config.system.json → paths.library_subdir, validated as a
    relative subpath so a stray ``"../.."`` cannot walk out of data/.
    """
    from mangaeasy.path_safety import validate_relative_subpath

    configured = _paths_config().get("library_subdir")
    if configured:
        subdir = validate_relative_subpath(configured, label="configured library subdirectory")
        return data_root() / subdir
    return data_root() / "library"


def audio_root() -> Path:
    return data_root() / "audio"


def faded_audio_root() -> Path:
    return data_root() / "audio_faded"


def output_root() -> Path:
    return data_root() / "output"


def review_root() -> Path:
    return data_root() / "review"


def work_root() -> Path:
    return data_root() / "work"


def project_memory_path(project_root: Path) -> Path:
    """The one canonical path for a project's durable story memory.

    Always scoped to ``data/library/<project>/MEMORY.json``.
    Never global; never shared across projects.
    """
    return project_root / "MEMORY.json"


# ── runtime/ sub-roots ────────────────────────────────────────────────────────

def tools_root() -> Path:
    configured = os.environ.get("MANGAEASY_TOOLS_DIR")
    if configured:
        return _resolved(configured)
    return runtime_root() / "tools"


def cache_root() -> Path:
    return runtime_root() / "cache"


def cache_dir(name: str) -> Path:
    """One named cache under ``runtime/cache`` (see CACHE_SUBDIRS)."""
    if name not in CACHE_SUBDIRS:
        raise KeyError(f"unknown cache {name!r}; known: {', '.join(sorted(CACHE_SUBDIRS))}")
    return cache_root() / name


def state_root() -> Path:
    return runtime_root() / "state"


def secrets_root() -> Path:
    return runtime_root() / "secrets"


# ── Creating the layout ───────────────────────────────────────────────────────

DATA_README = """# mangaEasy data

Everything mangaEasy downloaded or generated lives here, and nothing
else does.

**Delete this whole folder to start completely fresh.** Nothing outside it
has to be cleaned up afterwards, and nothing you own is lost with it: your
licensed music (`../bgm/`), your narrator reference takes (`../vocal/`),
your config files, and the installed AI tool environments (`../runtime/`,
tens of gigabytes) all sit outside and survive.

To clear productions without deleting by hand, use
`mangaeasy workspace-reset` — same result, but it refuses to run while
a job is still writing and it tells you what it removed.

## What is in here

{subdirs}

## Where a recap lives while it is being made

    library/<project>/01/panels/      cropped panels for chapter 01
    library/<project>/01/narration.json
    audio/<project>/01/*.wav          one narration take per panel
    audio_faded/<project>/01/*.wav    what actually gets rendered
    output/<project>/                 01.mp4 ... plus <project>_full.mp4

`work/` is pure scratch: deleting it mid-production costs you nothing but
re-render time. `library/` is the only folder holding anything that cannot
be regenerated from the others, because it holds the source pages and the
narration text.
"""


def data_readme_text() -> str:
    lines = [f"- `{name}/` — {description}" for name, description in DATA_SUBDIRS]
    return DATA_README.format(subdirs="\n".join(lines))


def ensure_data_root(write_readme: bool = True) -> Path:
    """Create ``data/`` and its subfolders; return the root.

    The README is rewritten whenever it is missing or stale so the folder
    explains itself to whoever opens it in a file manager six months from
    now — the audience that cannot run ``workspace-layout``.
    """
    root = data_root()
    for name, _ in DATA_SUBDIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    if write_readme:
        readme = root / "README.md"
        text = data_readme_text()
        try:
            if not readme.exists() or readme.read_text(encoding="utf-8") != text:
                readme.write_text(text, encoding="utf-8")
        except OSError:
            pass
    return root


def ensure_runtime_root() -> Path:
    """Create ``runtime/`` and its subfolders; return the root."""
    root = runtime_root()
    for name, _ in RUNTIME_SUBDIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    return root
