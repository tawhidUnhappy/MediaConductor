"""mangaeasy.download.mangadex — polite MangaDex chapter downloader.

Follows MangaDex API etiquette:
  - Identifies itself with a proper User-Agent header.
  - Enforces a minimum gap between every API request.
  - Backs off exponentially on 429 (rate-limit) and 5xx responses.
  - Reports every image download result to the at-home CDN network as
    required by MangaDex's usage guidelines (best-effort, never fatal).
  - Adds ±20 % jitter to inter-image delays so traffic is not
    machine-exact.
  - Paginates the chapter feed so manga with > 100 chapters in a
    language work correctly.
  - Skips images that already exist and are non-empty (safe to re-run).
"""

from __future__ import annotations

import os
import random
import re
import sys
import time
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urlparse

import requests

from mangaeasy import __version__
from mangaeasy.config import load_download_config
from mangaeasy.paths import manga_dir

# ── Constants ─────────────────────────────────────────────────────────────────

API_BASE   = "https://api.mangadex.org"
REPORT_URL = "https://api.mangadex.network/report"

_USER_AGENT = (
    f"mangaEasy/{__version__} "
    "(+https://github.com/tawhidUnhappy/mangaEasy)"
)

# Minimum seconds between consecutive MangaDex API calls.
# MangaDex asks clients to stay well below 5 req/s.
_MIN_API_INTERVAL = 0.4

_last_api_call: float = 0.0


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = _USER_AGENT
    return s


def _api_get(
    sess: requests.Session,
    url: str,
    params: dict | None = None,
    retries: int = 6,
) -> requests.Response:
    """GET with polite inter-call spacing and exponential back-off."""
    global _last_api_call
    gap = _MIN_API_INTERVAL - (time.monotonic() - _last_api_call)
    if gap > 0:
        time.sleep(gap)

    for attempt in range(retries):
        try:
            resp = sess.get(url, params=params, timeout=25)
            _last_api_call = time.monotonic()

            if resp.status_code == 429:
                wait = max(float(resp.headers.get("Retry-After", 60)),
                           30 * (2 ** attempt))
                print(f"[WARN] Rate-limited (429). Waiting {wait:.0f}s…", flush=True)
                time.sleep(wait)
                continue

            if resp.status_code >= 500:
                wait = min(120, 10 * (2 ** attempt))
                print(f"[WARN] Server error {resp.status_code}. Retry in {wait:.0f}s…",
                      flush=True)
                time.sleep(wait)
                continue

            resp.raise_for_status()
            return resp

        except requests.exceptions.RequestException as exc:
            _last_api_call = time.monotonic()
            if attempt < retries - 1:
                wait = min(60, 5 * (2 ** attempt))
                print(f"[WARN] Network error: {exc}. Retry in {wait:.0f}s…", flush=True)
                time.sleep(wait)
            else:
                raise

    raise RuntimeError(f"All {retries} attempts failed for {url}")


def _report_image(
    sess: requests.Session,
    url: str,
    success: bool,
    cached: bool,
    bytes_dl: int,
    duration_ms: int,
) -> None:
    """Report an image download result to the MangaDex at-home network.

    This is a CDN health signal — required by MangaDex guidelines.
    Failures are silently swallowed so they never break the download.
    """
    try:
        sess.post(
            REPORT_URL,
            json={
                "url": url,
                "success": success,
                "cached": cached,
                "bytes": bytes_dl,
                "duration": duration_ms,
            },
            timeout=6,
        )
    except Exception:
        pass


# ── MangaDex API calls ────────────────────────────────────────────────────────

def normalize_manga_id(raw: str) -> str:
    raw = raw.strip()
    if not raw.startswith(("http://", "https://")):
        return raw
    uuid_re = re.compile(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
        r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    )
    m = uuid_re.search(urlparse(raw).path)
    if m:
        return m.group()
    print(f"[ERROR] Could not extract manga UUID from URL: {raw}")
    sys.exit(1)


def find_chapter_id(
    sess: requests.Session, manga_id: str, chapter: str, lang: str
) -> str:
    """Return the chapter UUID, paginating the full feed if necessary."""
    offset   = 0
    limit    = 100
    checked  = 0
    ch_str   = str(chapter)

    while True:
        print(f"[INFO] Fetching chapter feed (offset={offset})…", flush=True)
        resp = _api_get(
            sess,
            f"{API_BASE}/manga/{manga_id}/feed",
            params={
                "translatedLanguage[]": [lang],
                "order[chapter]": "asc",
                "limit": limit,
                "offset": offset,
            },
        )
        data  = resp.json()
        items = data.get("data", [])
        total = data.get("total", 0)

        for ch_obj in items:
            attrs = ch_obj.get("attributes", {})
            # MangaDex stores chapter numbers as strings ("1", "1.5", …)
            if str(attrs.get("chapter") or "") == ch_str:
                cid = ch_obj["id"]
                title = attrs.get("title") or ""
                print(f"[INFO] Found chapter {ch_str}: {cid}"
                      + (f' "{title}"' if title else ""), flush=True)
                return cid

        checked += len(items)
        offset  += len(items)
        if not items or checked >= total or len(items) < limit:
            break

    print(
        f"[ERROR] Chapter '{chapter}' not found for manga {manga_id} "
        f"in language '{lang}' (checked {checked} entries).",
        flush=True,
    )
    sys.exit(1)


def fetch_at_home(sess: requests.Session, chapter_id: str) -> dict:
    print("[INFO] Fetching at-home CDN server…", flush=True)
    resp = _api_get(sess, f"{API_BASE}/at-home/server/{chapter_id}")
    data = resp.json()
    if "baseUrl" not in data or "chapter" not in data:
        raise RuntimeError(f"Unexpected at-home response: {data}")
    return data


def build_image_urls(
    at_home: dict, use_data_saver: bool
) -> Tuple[List[str], List[str]]:
    base       = at_home["baseUrl"]
    info       = at_home["chapter"]
    ch_hash    = info["hash"]
    key, qdir  = ("dataSaver", "data-saver") if use_data_saver else ("data", "data")
    files = info.get(key)
    if not files:
        raise RuntimeError(f"No images found under key '{key}' in at-home data")
    return [f"{base}/{qdir}/{ch_hash}/{f}" for f in files], files


# ── Image downloader ──────────────────────────────────────────────────────────

def download_images(
    sess: requests.Session,
    urls: List[str],
    filenames: List[str],
    output_dir: Path,
    delay: float,
    chapter_str: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    total     = len(urls)
    pad       = max(2, len(str(total)))
    skipped   = 0

    for idx, (url, fname) in enumerate(zip(urls, filenames), start=1):
        ext      = os.path.splitext(fname)[1] or ".jpg"
        dest     = output_dir / f"{chapter_str}_{idx:0{pad}d}{ext}"

        if dest.exists() and dest.stat().st_size > 0:
            skipped += 1
            print(f"[{idx}/{total}] skip (exists): {dest.name}", flush=True)
            continue

        print(f"[{idx}/{total}] {dest.name}", flush=True)

        t0       = time.monotonic()
        success  = False
        bytes_dl = 0
        cached   = False

        for attempt in range(3):
            try:
                with sess.get(url, stream=True, timeout=60) as r:
                    r.raise_for_status()
                    cached  = r.headers.get("X-Cache", "").upper().startswith("HIT")
                    content = b"".join(r.iter_content(chunk_size=65_536))
                    bytes_dl = len(content)
                    dest.write_bytes(content)
                success = True
                break
            except Exception as exc:
                if attempt < 2:
                    wait = 4 * (2 ** attempt)  # 4s, 8s
                    print(f"  ! attempt {attempt + 1}/3 failed: {exc}."
                          f" Retry in {wait}s…", flush=True)
                    time.sleep(wait)
                else:
                    print(f"  ! Gave up on {dest.name}: {exc}", flush=True)

        duration_ms = int((time.monotonic() - t0) * 1000)
        _report_image(sess, url, success, cached, bytes_dl, duration_ms)

        # Polite inter-image pause with ±20 % jitter.
        if idx < total:
            jitter  = random.uniform(-0.2, 0.2) * delay
            time.sleep(max(0.5, delay + jitter))

    downloaded = total - skipped
    if skipped:
        print(f"\n[INFO] {downloaded} new + {skipped} already existed → {output_dir.resolve()}", flush=True)
    else:
        print(f"\n[INFO] {total} pages saved → {output_dir.resolve()}", flush=True)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    dl_cfg = load_download_config()

    raw_id = str(dl_cfg.get("manga_id", "")).strip()
    if not raw_id:
        print("[ERROR] 'manga_id' is missing in config.json download section")
        sys.exit(1)

    chapter = dl_cfg.get("chapter")
    if chapter is None:
        print("[ERROR] 'chapter' is missing in config.json download section")
        sys.exit(1)

    manga_id       = normalize_manga_id(raw_id)
    chapter_str    = str(chapter).zfill(2)
    lang           = dl_cfg.get("translated_language", "en")
    output_dir     = manga_dir(str(dl_cfg.get("name"))) / chapter_str / "download"
    use_data_saver = bool(dl_cfg.get("use_data_saver", False))
    delay          = float(dl_cfg.get("download_delay", 1.5))

    print("=== MangaDex downloader ===")
    print(f"  User-Agent: {_USER_AGENT}")
    print(f"  Manga     : {manga_id}")
    print(f"  Chapter   : {chapter_str}  Language: {lang}")
    print(f"  Output    : {output_dir}")
    print(f"  Quality   : {'data-saver' if use_data_saver else 'original'}")
    print(f"  Img delay : {delay}s ± 20 %")
    print("===========================\n")

    sess           = _session()
    chapter_id     = find_chapter_id(sess, manga_id, str(chapter), lang)
    at_home        = fetch_at_home(sess, chapter_id)
    urls, fnames   = build_image_urls(at_home, use_data_saver)

    print(f"[INFO] {len(urls)} page(s) to download.\n", flush=True)
    download_images(sess, urls, fnames, output_dir, delay, chapter_str)


if __name__ == "__main__":
    main()
