from __future__ import annotations

import argparse
import gc
import json
import os
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from kokoro import KPipeline


SAMPLE_RATE = 24000
CACHE_RELEASE_INTERVAL = 25


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch Kokoro TTS worker for make-video.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--voice", default="af_heart")
    parser.add_argument("--lang", default="a")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--device", choices=("auto", "cuda", "mps", "cpu"), default="auto")
    parser.add_argument("--split-pattern", default=r"\n+")
    parser.add_argument("--repo-id", default="hexgrad/Kokoro-82M")
    return parser.parse_args()


def _mps_available() -> bool:
    return sys.platform == "darwin" and getattr(torch.backends, "mps", None) is not None \
        and torch.backends.mps.is_available()


def resolve_device(requested: str) -> str:
    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if _mps_available():
        return "mps"
    return "cpu"


def configure_torch(device: str) -> None:
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested, but PyTorch cannot see a CUDA GPU.")
    if device == "mps" and not _mps_available():
        raise RuntimeError("MPS was requested, but PyTorch cannot see an Apple Silicon GPU.")
    if torch.cuda.is_available():
        torch.backends.cuda.matmul.allow_tf32 = True
        # cudnn.benchmark autotunes per unique input shape, but narration text
        # length varies on nearly every call -- it rarely gets to reuse a
        # cached algorithm, so there's little to gain. With several
        # --gpu-workers processes hitting the same GPU at once, that constant
        # re-benchmarking is also a plausible contributor to the sporadic
        # CUDNN_STATUS_EXECUTION_FAILED crashes seen at higher worker counts.
        torch.backends.cudnn.benchmark = False
        torch.set_float32_matmul_precision("high")


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array.")
    return data


def synthesize(pipeline: KPipeline, text: str, voice: str, speed: float, split_pattern: str) -> np.ndarray:
    chunks: list[np.ndarray] = []
    with torch.inference_mode():
        for result in pipeline(text, voice=voice, speed=speed, split_pattern=split_pattern):
            if result.audio is None:
                continue
            chunks.append(result.audio.detach().cpu().numpy())
    if not chunks:
        raise RuntimeError("Kokoro produced no audio for a manifest entry.")
    if len(chunks) == 1:
        return chunks[0]
    return np.concatenate(chunks)


def build_pipeline(lang: str, repo_id: str, device: str) -> KPipeline:
    """Construct KPipeline, preferring the local Hugging Face cache.

    Every call otherwise hits the Hub for a freshness check (the
    "unauthenticated requests" warning) even when the model is already fully
    cached -- wasteful on its own, and with several --gpu-workers processes
    doing it concurrently it adds avoidable network round-trips right as
    each worker is starting up. Try fully offline first; if anything's
    actually missing from the cache (first run, a new voice, etc.), retry
    once with network access so it can be fetched as before.
    """
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    try:
        return KPipeline(lang_code=lang, repo_id=repo_id, device=device)
    except Exception:
        os.environ["HF_HUB_OFFLINE"] = "0"
        return KPipeline(lang_code=lang, repo_id=repo_id, device=device)


def main() -> int:
    args = parse_args()
    device = resolve_device(args.device)
    configure_torch(device)

    print(f"Kokoro device: {device}", flush=True)
    if device == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}", flush=True)
        print(f"Torch CUDA build: {torch.version.cuda}", flush=True)
    print(f"Voice: {args.voice}", flush=True)
    print(f"Language: {args.lang}", flush=True)

    pipeline = build_pipeline(args.lang, args.repo_id, device)
    entries = read_manifest(args.manifest)
    chapter_names = list(dict.fromkeys(
        (entry.get("label") or "").split(":", 1)[0] for entry in entries
    ))
    total_chapters = len(chapter_names) or 1
    print(f"MEDIACONDUCTOR_PROGRESS 0/{total_chapters} Generating audio", flush=True)
    chapters_done = 0
    current_chapter = None
    for index, entry in enumerate(entries, start=1):
        label = entry.get("label") or f"{index}/{len(entries)}"
        chapter = label.split(":", 1)[0]
        if current_chapter is not None and chapter != current_chapter:
            chapters_done += 1
            print(f"MEDIACONDUCTOR_PROGRESS {chapters_done}/{total_chapters} Generated audio for {current_chapter}", flush=True)
        current_chapter = chapter
        text = (entry.get("text") or "").strip()
        output = Path(entry.get("output") or "")
        if not text or not str(output):
            raise ValueError(f"Bad manifest entry: {entry}")
        output.parent.mkdir(parents=True, exist_ok=True)
        audio = synthesize(pipeline, text, args.voice, args.speed, args.split_pattern)
        sf.write(output, audio, SAMPLE_RATE)
        print(f"[{index:04d}/{len(entries):04d}] {label} -> {output}", flush=True)

        # Every narration line is a different length, so each call asks the
        # CUDA caching allocator for a differently-shaped tensor. PyTorch
        # never returns that memory to the driver on its own -- it just
        # keeps caching more blocks it can't reuse, so usage climbs over a
        # long run even though nothing is actually leaking. Periodically
        # force a real release so it plateaus instead.
        if index % CACHE_RELEASE_INTERVAL == 0:
            gc.collect()
            if device == "cuda":
                torch.cuda.empty_cache()
    if current_chapter is not None:
        chapters_done += 1
        print(f"MEDIACONDUCTOR_PROGRESS {chapters_done}/{total_chapters} Generated audio for {current_chapter}", flush=True)

    if device == "cuda":
        torch.cuda.synchronize()
        peak = torch.cuda.max_memory_allocated(0) / 1024**3
        print(f"Peak PyTorch CUDA allocation: {peak:.2f} GiB", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
