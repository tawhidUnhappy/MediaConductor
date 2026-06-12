"""mangaeasy.web.app.api_workflow — the guided chapter workflow.

One endpoint backs the "Make a video" tab: it reads/writes the download
settings in config.json and reports per-step progress (pages downloaded,
panels cut, narration written, audio generated) so the UI can show how far
along the current chapter is.
"""

from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, jsonify, request

from mangaeasy.web.app.api_project import _read_json
from mangaeasy.web.app.state import log, state

bp = Blueprint("workflow", __name__)

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def _library_dir(root: Path, sys_cfg: dict) -> Path:
    """Mirror of mangaeasy.paths.library_dir, but for the *selected* project.

    The app process resolved its own PROJECT_ROOT at startup, so the package
    helper would point at the wrong folder — recompute against `root`.
    """
    sub = (sys_cfg.get("paths") or {}).get("library_subdir")
    if sub:
        return root / sub
    library = root / "library"
    legacy = root / "manga"
    if legacy.is_dir() and not library.is_dir():
        return legacy
    return library


def _count_files(folder: Path, exts: set[str]) -> int:
    if not folder.is_dir():
        return 0
    return sum(1 for p in folder.iterdir() if p.suffix.lower() in exts)


@bp.route("/api/workflow", methods=["GET", "POST"])
def api_workflow():
    root: Path = state["project_root"]
    cfg_path = root / "config.json"

    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        cfg = _read_json(cfg_path) or {}
        dl = cfg.get("download") if isinstance(cfg.get("download"), dict) else {}
        if "manga_id" in body:
            dl["manga_id"] = str(body["manga_id"]).strip()
        if "name" in body:
            dl["name"] = str(body["name"]).strip()
        if "chapter" in body:
            try:
                dl["chapter"] = int(body["chapter"])
            except (TypeError, ValueError):
                pass
        if "language" in body:
            dl["translated_language"] = str(body["language"]).strip() or "en"
        cfg["download"] = dl
        cfg.pop("_comment", None)
        cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        log(f"[app] wrote {cfg_path}")

    cfg = _read_json(cfg_path) or {}
    sys_cfg = _read_json(root / "config.system.json") or {}
    dl = cfg.get("download") if isinstance(cfg.get("download"), dict) else {}

    name = str(dl.get("name") or "")
    try:
        chapter = int(dl.get("chapter") or 1)
    except (TypeError, ValueError):
        chapter = 1
    language = str(
        dl.get("translated_language")
        or (sys_cfg.get("download_defaults") or {}).get("translated_language")
        or "en"
    )

    info: dict = {
        "manga_id": str(dl.get("manga_id") or ""),
        "name": name,
        "chapter": chapter,
        "language": language,
        "bgm_set": bool((sys_cfg.get("bgm") or {}).get("file")),
        "voice_set": bool((sys_cfg.get("tts") or {}).get("speaker_wav")),
        "paths": None,
        "status": None,
    }
    if not name:
        return jsonify(info)

    paths_cfg = sys_cfg.get("paths") or {}
    ch_dir = _library_dir(root, sys_cfg) / name / f"{chapter:02d}"
    download_dir = ch_dir / "download"
    panels_dir = ch_dir / paths_cfg.get("panels_subdir", "panels")
    audio_dir = ch_dir / paths_cfg.get("audio_subdir", "audio")
    narration = ch_dir / f"narration_{chapter:02d}.json"
    video = ch_dir / f"{chapter:02d}_{name}.mp4"
    video_bgm = ch_dir / f"{chapter:02d}_{name}_with_bgm.mp4"

    narration_items = 0
    if narration.exists():
        try:
            data = json.loads(narration.read_text(encoding="utf-8-sig"))
            narration_items = len(data) if isinstance(data, list) else 0
        except Exception:
            narration_items = 0

    info["paths"] = {
        "chapter": str(ch_dir),
        "download": str(download_dir),
        "panels": str(panels_dir),
        "audio": str(audio_dir),
        "narration": str(narration),
    }
    info["status"] = {
        "downloads": _count_files(download_dir, IMAGE_EXTS),
        "panels": _count_files(panels_dir, IMAGE_EXTS),
        "narration": narration.exists(),
        "narration_items": narration_items,
        "audio": _count_files(audio_dir, {".wav"}),
        "video": video_bgm.exists() or video.exists(),
    }
    return jsonify(info)
