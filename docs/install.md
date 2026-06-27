# Installing mangaEasy

Three ways to get mangaEasy, from easiest to most hands-on.

---

## Option 1 — Download the desktop app (recommended for most users)

No Python, no uv, no ffmpeg, no dependencies — the Electron app bundles the
Python backend inside it. Just download, extract/install, and run.

### Step 1: Download

Go to the [**Releases page**](https://github.com/tawhidUnhappy/mangaEasy/releases/latest)
and download the file for your platform:

#### Windows
| File | Type | Notes |
|---|---|---|
| `mangaeasy-desktop-X.Y.Z-portable.exe` | Portable | Run directly, no install |

There is no Windows `.exe` installer by design — an installer would write a
registry uninstall key and Start Menu shortcut outside the folder you put
the app in, so deleting that folder wouldn't fully remove it. Portable-only
keeps "delete the folder, it's gone" literally true.

#### macOS
| File | Type | Notes |
|---|---|---|
| `mangaeasy-desktop-X.Y.Z.dmg` | **Installer** | Drag to Applications |
| `mangaeasy-desktop-X.Y.Z-mac.zip` | Portable | Extract and run without installing |

#### Linux
| File | Type | Notes |
|---|---|---|
| `mangaeasy-desktop-X.Y.Z.AppImage` | Portable | `chmod +x`, run — no install |
| `mangaeasy-desktop-X.Y.Z.deb` | **Installer** | For Ubuntu / Debian and derivatives |
| `mangaeasy-desktop-X.Y.Z.tar.gz` | Portable | Works on any Linux distro |

### Step 2: Install or extract

**Windows — Portable exe**
- Just run `mangaeasy-desktop-X.Y.Z-portable.exe` from wherever you put it.

**Linux — .deb installer (Ubuntu / Debian)**
```bash
sudo dpkg -i mangaeasy-desktop-X.Y.Z.deb
mangaeasy-desktop
```

**Linux — AppImage / tar.gz (any distro)**
```bash
chmod +x mangaeasy-desktop-X.Y.Z.AppImage
./mangaeasy-desktop-X.Y.Z.AppImage
```

**macOS — .dmg installer**
- Open the `.dmg`, drag mangaEasy to Applications.
- If Gatekeeper blocks it: System Settings → Privacy & Security → Allow.

**macOS — Portable zip**
```bash
unzip mangaeasy-desktop-X.Y.Z-mac.zip
xattr -cr mangaEasy.app      # clear Gatekeeper quarantine
open mangaEasy.app
```

### Step 3: Run

The app opens as a native window — there's no browser, no local web server,
and (for the installer/portable downloads above) no need to ever type
`mangaeasy app` in a terminal; that command is only relevant if you're running
from source (see Option 2/3 below).

### First-run checklist

The **Setup** tab guides you through the rest:

1. **ffmpeg** — already bundled, nothing to do.
2. **Kokoro TTS** — lightweight voice, runs on any CPU. Click **Install**.
3. **IndexTTS** (optional) — high-quality voice cloning; works best with an
   NVIDIA GPU. Click **Install** if you want it.
4. **MAGI v3** (optional) — automatic panel detection for manga pages.

These tools download once into `<install folder>/.mangaeasy/tools/` and are shared across all
your projects. GPU acceleration (NVIDIA CUDA / Apple Silicon MPS) is detected
and configured automatically — nothing to choose.

### Platform notes

**Windows**
- Windows may show a SmartScreen warning the first time ("Windows protected your
  PC"). Click *More info* → *Run anyway*. This happens because the exe is not
  code-signed.

**macOS**
- macOS Gatekeeper may block the app. Right-click → *Open* and confirm, **or**
  run this once in Terminal after extracting the portable zip:
  ```bash
  xattr -cr mangaEasy.app
  open mangaEasy.app
  ```

**Linux**
- AppImage: `chmod +x` then run it directly, no install step.

---

## Option 2 — Install with uv (for developers / power users)

Requires [uv](https://docs.astral.sh/uv/) installed on your system.

```bash
uv tool install git+https://github.com/tawhidUnhappy/mangaEasy.git
```

This puts a `mangaeasy` command on your `PATH`. Update later:

```bash
uv tool upgrade mangaeasy
```

Run without installing (useful for a quick test):

```bash
uvx --from git+https://github.com/tawhidUnhappy/mangaEasy.git mangaeasy --help
```

---

## Option 3 — From source (contributors)

```bash
git clone https://github.com/tawhidUnhappy/mangaEasy.git
cd mangaEasy
uv sync
uv run mangaeasy --help
```

Or skip the manual steps below and just run `./run.sh` (macOS/Linux) /
`run.bat` (Windows) from the repo root — it runs `uv sync`, builds the
desktop app's dev bundle the first time, and launches `mangaeasy app`.

Build the desktop app yourself: PyInstaller bundles the Python backend, then
electron-builder wraps it into the portable app (plus a macOS `.dmg`/Linux
`.deb` if you build those targets) — `desktop/scripts/bundle-backend.mjs`
runs the first step for you.

```bash
uv sync --dev
cd desktop
npm install
npm run build:win    # or build:mac / build:linux
# Output lands in desktop/dist/
```

(`npm run build:win` etc. internally run `bundle:backend`, which builds
`packaging/mangaeasy.spec` and copies the result into `desktop/resources/backend/`
before electron-builder packages everything.)

---

## Updating

### Desktop app (Windows portable / macOS / Linux)
Download the new build and copy your old install's `.mangaeasy/` folder into
the new one if you want to keep your installed AI tools without
re-downloading them; otherwise just run the new build and reinstall tools as
needed. On macOS/Linux, installing the new `.dmg`/`.deb` over the old one
leaves `<install folder>/.mangaeasy/` untouched the same way.

### uv tool
```bash
uv tool upgrade mangaeasy
```

---

## Uninstalling

### Desktop app
**Windows / portable macOS-Linux builds:** just delete the folder. There's no
installer step on Windows and no system registration for the portable
zip/AppImage/tar.gz builds, so deleting the folder removes everything,
including `<install folder>/.mangaeasy/` (AI tools, models, app state) — that
subdirectory is where everything mangaEasy ever writes lives.

**macOS `.dmg` / Linux `.deb` installs:** uninstall it the normal way for
your OS (drag the app to Trash, or `sudo dpkg -r mangaeasy-desktop`) — that
also removes its `.mangaeasy/` folder since it lives inside the app's own
install location.

### uv tool
```bash
uv tool uninstall mangaeasy
rm -rf <install folder>/.mangaeasy   # the self-contained data dir, if you ran it from a checkout
```
