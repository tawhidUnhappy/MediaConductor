"""Verify that built distributions include agent docs/assets and no user media."""

from __future__ import annotations

from pathlib import Path
import sys
import tarfile
import zipfile


MEDIA_SUFFIXES = {".avi", ".flac", ".m4a", ".mkv", ".mov", ".mp3", ".mp4", ".wav", ".webm"}
WHEEL_REQUIRED = {
    "mediaconductor/agent_skills/manga-video/SKILL.md",
    "mediaconductor/agent_skills/manga-video/references/youtube-publishing.md",
    "mediaconductor/assets/tools/batch_detect_magi.py",
    "mediaconductor/assets/tools/detect_magi.py",
    "mediaconductor/assets/prompts/narration.md",
    "mediaconductor/assets/fonts/edosz.ttf",
}
SDIST_REQUIRED_SUFFIXES = {
    "/AGENTS.md",
    "/LICENSE",
    "/README.md",
    "/SECURITY.md",
    "/THIRD_PARTY_NOTICES.md",
    "/mcp.example.json",
    "/skills/manga-video/SKILL.md",
}
# Anything a distribution must never advertise again. A wheel that still ships
# a removed pipeline's skill or adapter is a working install of a feature the
# CLI no longer registers — the exact drift the registry tests exist to stop.
FORBIDDEN_TOKENS = (
    "ai-story", "song-video", "media-conductor/SKILL",
    "ace_step", "generate_zimage", "separate_demucs", "transcribe_whisperx",
    "/story/", "/song/", "images/pdf", "images/convert", "images/watermark",
)


def _one(paths: list[Path], label: str) -> Path:
    if len(paths) != 1:
        raise SystemExit(f"expected exactly one {label} in dist, found: {paths}")
    return paths[0]


def _reject_media(names: set[str], artifact: Path) -> None:
    media = sorted(name for name in names if Path(name).suffix.lower() in MEDIA_SUFFIXES)
    if media:
        raise SystemExit(f"user/generated media leaked into {artifact.name}: {media}")


def _reject_removed_features(names: set[str], artifact: Path) -> None:
    leaked = sorted(
        name for name in names
        if any(token in name for token in FORBIDDEN_TOKENS)
    )
    if leaked:
        raise SystemExit(f"removed features leaked into {artifact.name}: {leaked}")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    dist = Path(args[0] if args else "dist")
    wheel = _one(sorted(dist.glob("*.whl")), "wheel")
    sdist = _one(sorted(dist.glob("*.tar.gz")), "source archive")

    with zipfile.ZipFile(wheel) as archive:
        wheel_names = set(archive.namelist())
    missing_wheel = sorted(WHEEL_REQUIRED - wheel_names)
    if missing_wheel:
        raise SystemExit(f"wheel is missing required files: {missing_wheel}")
    _reject_media(wheel_names, wheel)
    _reject_removed_features(wheel_names, wheel)

    with tarfile.open(sdist, "r:gz") as archive:
        sdist_names = {member.name for member in archive.getmembers() if member.isfile()}
    missing_sdist = sorted(
        suffix for suffix in SDIST_REQUIRED_SUFFIXES
        if not any(name.endswith(suffix) for name in sdist_names)
    )
    if missing_sdist:
        raise SystemExit(f"source archive is missing required files: {missing_sdist}")
    _reject_media(sdist_names, sdist)
    _reject_removed_features(sdist_names, sdist)

    print(f"Distribution payload passed: {wheel.name}, {sdist.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
