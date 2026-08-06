"""mangaeasy.tools.install — provision external AI tool environments."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from mangaeasy import runtime
from mangaeasy.brand import CLI_NAME, PRODUCT_NAME
from mangaeasy.tools.external import (
    python_command,
    resolve_tool_dir,
    tool_env,
    tools_home,
)
from mangaeasy.tools.hardware import (
    default_torch_build,
    detect_gpu,
    find_nvidia_smi,
    has_nvidia_gpu,
    nvidia_gpu_name,
    which,
)

LogFn = Callable[[str], None]
HF_CLI_REQUIREMENT = "huggingface-hub==1.23.0"
ASSETS_TOOLS = Path(__file__).resolve().parents[1] / "assets" / "tools"


class InstallError(RuntimeError):
    """Raised when a provisioning step fails."""


@dataclass
class ToolSpec:
    key: str
    title: str
    kind: str  # "uv_project" | "managed_env"
    git_url: str | None
    ref: str | None = None
    model_repo: str | None = None
    model_revision: str | None = None
    model_subdir: str | None = None
    required_model_files: tuple[str, ...] = ()
    adapter: str | None = None
    extra_adapters: list[str] = field(default_factory=list)
    env_deps: list[str] = field(default_factory=list)
    exclude_extras: list[str] = field(default_factory=list)
    verify_import: str | None = None
    python: str = "3.12"
    sync_args: list[str] = field(default_factory=lambda: ["--all-extras"])
    preserve_upstream_torch: bool = False
    needs_gpu: bool = False
    notes: str = ""


TOOLS: dict[str, ToolSpec] = {
    "index-tts": ToolSpec(
        key="index-tts",
        title="IndexTTS 2",
        kind="uv_project",
        git_url="https://github.com/index-tts/index-tts",
        ref="13495845e3028f0bb6ca1462ad22aa0e76349e40",
        model_repo="IndexTeam/IndexTTS-2",
        model_revision="740dcaff396282ffb241903d150ac011cd4b1ede",
        model_subdir="checkpoints",
        required_model_files=(
            "config.yaml", "bpe.model", "gpt.pth", "s2mel.pth",
            "qwen0.6bemo4-merge/model.safetensors",
        ),
        exclude_extras=["deepspeed", "accel", "webui", "torch_compile", "test"],
        python="3.11",
        needs_gpu=True,
        notes="High-quality voice-cloning TTS. ~5.9 GB model download from Hugging Face.",
    ),
    "magi-v3": ToolSpec(
        key="magi-v3",
        title="MAGI v3 (panel detection)",
        kind="managed_env",
        git_url=None,
        model_repo="ragavsachdeva/magiv3",
        adapter="detect_magi.py",
        extra_adapters=["batch_detect_magi.py"],
        env_deps=[
            "torch>=2.5.0",
            "torchvision>=0.20.0",
            "transformers>=4.41,<4.50",
            "accelerate>=1.12.0",
            "safetensors>=0.4.0",
            "timm>=0.9.0",
            "einops>=0.8.2",
            "pillow>=10.0.0",
            "numpy>=1.24.0",
            "pytorch_metric_learning>=2.0.0",
            "matplotlib>=3.7.0",
            "shapely>=2.0.0",
            "networkx>=3.0",
        ],
        verify_import="transformers",
        needs_gpu=True,
        notes="Detects manga panels. Model downloads from Hugging Face.",
    ),
    "deepseek-ocr2": ToolSpec(
        key="deepseek-ocr2",
        title="DeepSeek-OCR 2",
        kind="managed_env",
        git_url=None,
        model_repo="deepseek-ai/DeepSeek-OCR-2",
        model_revision="aaa02f3811945a91062062994c5c4a3f4c0af2b0",
        model_subdir="model",
        required_model_files=(
            "config.json", "processor_config.json", "tokenizer.json",
            "model.safetensors.index.json", "model-00001-of-000001.safetensors",
        ),
        env_deps=[
            "torch>=2.6.0",
            "torchvision>=0.21.0",
            "transformers==4.46.3",
            "tokenizers>=0.20.3",
            "accelerate>=1.0.0",
            "safetensors>=0.4.0",
            "pillow>=10.0.0",
            "numpy>=1.24.0",
            "einops>=0.8.0",
            "addict>=2.4.0",
            "easydict>=1.13",
            "matplotlib>=3.8.0",
            "tqdm>=4.66.0",
        ],
        verify_import="transformers",
        needs_gpu=True,
        notes="DeepSeek-OCR 2 model downloaded directly from Hugging Face.",
    ),
    "kokoro-82m": ToolSpec(
        key="kokoro-82m",
        title="Kokoro 82M (default TTS)",
        kind="managed_env",
        git_url=None,
        model_repo="hexgrad/Kokoro-82M",
        env_deps=[
            "kokoro>=0.9",
            "torch>=2.5.0",
            "soundfile>=0.12",
            "numpy>=1.24.0",
        ],
        verify_import="kokoro",
        needs_gpu=False,
        notes="Lightweight CPU TTS. Model weights downloaded from Hugging Face.",
    ),
    "whisper-turbo": ToolSpec(
        key="whisper-turbo",
        title="Whisper large-v3-turbo",
        kind="managed_env",
        git_url=None,
        model_repo="deepdml/faster-whisper-large-v3-turbo-ct2",
        model_subdir="model",
        env_deps=[
            "faster-whisper>=1.1.0",
            "ctranslate2>=4.0.0",
            "torch>=2.5.0",
            "torchaudio>=2.5.0",
            "huggingface-hub>=0.23.0",
        ],
        verify_import="faster_whisper",
        needs_gpu=True,
        notes="Whisper large-v3-turbo ASR model for subtitles downloaded directly from Hugging Face.",
    ),
}


def _run_pipe(cmd: list[str], log: LogFn, cwd: Path | None = None, env: dict | None = None) -> None:
    try:
        proc = runtime.popen(
            cmd,
            cwd=str(cwd) if cwd else None,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except FileNotFoundError as exc:
        raise InstallError(f"command not found: {cmd[0]} ({exc})") from exc
    assert proc.stdout is not None
    for line in proc.stdout:
        log(line.rstrip("\n"))
    code = proc.wait()
    if code != 0:
        raise InstallError(f"command failed (exit {code}): {' '.join(cmd)}")


def _run(cmd: list[str], log: LogFn, cwd: Path | None = None, env: dict | None = None) -> None:
    if env is None:
        env = tool_env()
    log(f"$ {' '.join(str(c) for c in cmd)}")
    _run_pipe(cmd, log, cwd=cwd, env=env)


def _clone_or_update(
    git_url: str,
    dest: Path,
    ref: str | None,
    log: LogFn,
    *,
    skip_lfs_smudge: bool = True,
) -> None:
    env = dict(tool_env())
    if skip_lfs_smudge:
        env["GIT_LFS_SKIP_SMUDGE"] = "1"

    if not (dest / ".git").is_dir():
        log(f"Cloning {git_url} -> {dest}...")
        _run(
            ["git", "clone", "--filter=blob:none", "--depth", "1", "--no-tags", "--no-checkout", git_url, str(dest)],
            log,
            cwd=dest.parent,
            env=env,
        )

    if ref:
        log(f"Fetching ref {ref}...")
        _run(["git", "fetch", "--depth", "1", "--filter=blob:none", "origin", ref], log, cwd=dest, env=env)
        _run(["git", "checkout", "--detach", "FETCH_HEAD"], log, cwd=dest, env=env)


def _download_hf_snapshot(
    repo: str,
    revision: str | None,
    target: Path,
    required_files: tuple[str, ...],
    include: tuple[str, ...],
    log: LogFn,
) -> None:
    log(f"Downloading model {repo} -> {target} from Hugging Face...")
    env = {**tool_env(), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    command = [
        "uvx", "--from", HF_CLI_REQUIREMENT,
        "hf", "download", repo, "--local-dir", str(target),
    ]
    if revision:
        command += ["--revision", revision]
    for pattern in include:
        command += ["--include", pattern]
    _run(command, log, env=env)


def _download_model(spec: ToolSpec, dest: Path, log: LogFn) -> None:
    if spec.model_repo:
        _download_hf_snapshot(
            spec.model_repo,
            spec.model_revision,
            dest / (spec.model_subdir or "checkpoints"),
            spec.required_model_files,
            (),
            log,
        )


def _verify_tool_python(dest: Path, import_check: str, log: LogFn) -> None:
    cmd = [*python_command(dest), "-c", f"import {import_check}; print('ok: {import_check}')"]
    _run(cmd, log, cwd=dest, env=tool_env())


def _install_adapter_files(spec: ToolSpec, dest: Path, log: LogFn) -> None:
    for adapter_name in ([spec.adapter] if spec.adapter else []) + spec.extra_adapters:
        src = ASSETS_TOOLS / adapter_name
        if src.exists():
            shutil.copyfile(src, dest / adapter_name)
            log(f"Installed adapter: {adapter_name}")


def _write_managed_pyproject(spec: ToolSpec, dest: Path, gpu_mode: str) -> None:
    deps = ",\n    ".join(f'"{d}"' for d in spec.env_deps)
    content = (
        f"# Auto-generated by `{CLI_NAME} install-tool`. Isolated env for {spec.title}.\n"
        "[project]\n"
        f'name = "{spec.key}-env"\n'
        'version = "0.0.0"\n'
        f'requires-python = ">={spec.python}"\n'
        "dependencies = [\n    "
        f"{deps}\n]\n"
    )
    (dest / "pyproject.toml").write_text(content, encoding="utf-8")


def install_tool(
    key: str,
    *,
    ref: str | None = None,
    dest: str | Path | None = None,
    skip_model: bool = False,
    gpu: str = "auto",
    clone: bool = False,
    update: bool = False,
    log: LogFn = print,
) -> Path:
    if key not in TOOLS:
        raise InstallError(f"unknown tool '{key}'. Known: {', '.join(TOOLS)}")
    spec = TOOLS[key]
    target = Path(dest).expanduser().resolve() if dest else (tools_home() / spec.key)
    target.mkdir(parents=True, exist_ok=True)

    gpu_mode = gpu if gpu in ("cuda", "cpu") else default_torch_build()
    log(f"=== Installing {spec.title} -> {target} ===")

    if spec.kind == "uv_project" and spec.git_url:
        _clone_or_update(spec.git_url, target, ref or spec.ref, log)
        sync_cmd = ["uv", "sync", "--python", spec.python]
        if spec.exclude_extras:
            for ex in spec.exclude_extras:
                sync_cmd.extend(["--no-extra", ex])
        elif spec.sync_args:
            sync_cmd.extend(spec.sync_args)
        _run(sync_cmd, log, cwd=target)
    else:
        _write_managed_pyproject(spec, target, gpu_mode)
        _run(["uv", "sync", "--python", spec.python], log, cwd=target)

    _install_adapter_files(spec, target, log)

    if spec.verify_import:
        _verify_tool_python(target, spec.verify_import, log)

    if spec.model_repo and not skip_model:
        _download_model(spec, target, log)

    marker = {
        "schema_version": 1,
        "tool": spec.key,
        "model": spec.model_repo,
        "installed_at": datetime.now(timezone.utc).isoformat(),
    }
    (target / "READY.json").write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    log(f"=== Done. Tool '{spec.key}' installed at {target} ===")
    return target


def doctor(*, check_updates: bool = False, mode: str | None = None) -> dict:
    executables = {exe: shutil.which(exe) for exe in ("git", "uv", "uvx", "ffmpeg", "ffprobe", "nvidia-smi")}
    gpu_info = detect_gpu()
    tools = {}
    for key, spec in TOOLS.items():
        path = resolve_tool_dir(key, required=False)
        tools[key] = {
            "title": spec.title,
            "installed": path is not None and (path / "READY.json").is_file(),
            "path": str(path) if path else None,
            "needs_gpu": spec.needs_gpu,
        }
    return {
        "tools_home": str(tools_home()),
        "gpu": gpu_info.has_nvidia,
        "gpu_backend": gpu_info.backend,
        "executables": executables,
        "tools": tools,
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog=f"{CLI_NAME} install-tool")
    parser.add_argument("name", nargs="?", help="Tool to install.")
    parser.add_argument("--skip-model", action="store_true")
    args = parser.parse_args()

    if not args.name:
        print("Available tools: " + ", ".join(TOOLS))
        return 0

    try:
        install_tool(args.name, skip_model=args.skip_model)
    except InstallError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())