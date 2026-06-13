# Installing mangaEasy

Three ways to get mangaEasy, from easiest to most hands-on.

---

## Option 1 — Download the standalone app (recommended for most users)

No Python, no uv, no dependencies. Just download, extract, and run.

### Step 1: Download

Go to the [**Releases page**](https://github.com/tawhidUnhappy/mangaEasy/releases/latest)
and download the file for your platform:

| Platform | File | Notes |
|---|---|---|
| **Windows — Installer** | `mangaEasy-Setup-vX.Y.Z.exe` | Recommended — installs to Program Files, adds Start Menu shortcut |
| **Windows — Portable** | `mangaEasy-windows.zip` | No install needed — extract and run from anywhere |
| Linux (x64) | `mangaEasy-linux.tar.gz` | |
| macOS (Intel or Apple Silicon) | `mangaEasy-macos.tar.gz` | |

### Step 2: Install or extract

**Windows — Installer (recommended)**
- Double-click `mangaEasy-Setup-vX.Y.Z.exe` and follow the wizard.
- Installs to `C:\Program Files\mangaEasy\`, adds a Start Menu shortcut,
  and optionally adds `mangaeasy` to your system PATH.

**Windows — Portable zip**
- Right-click the zip → *Extract All* → choose any permanent folder.
- You get a `mangaEasy\` folder. Move it wherever you like.

**Linux / macOS**
- `tar -xzf mangaEasy-*.tar.gz`
- You get a `mangaEasy/` folder.

### Step 3: Run

| Platform | How to start |
|---|---|
| Windows (installer) | Start Menu → **mangaEasy**, or `mangaeasy app` in any terminal |
| Windows (portable) | Double-click **`mangaeasy.exe`** inside the extracted `mangaEasy\` folder |
| Linux | `./mangaEasy/mangaeasy` |
| macOS | `./mangaEasy/mangaeasy` |

The control centre opens automatically in your browser at `http://127.0.0.1:5000`.

### First-run checklist

The **Setup** tab guides you through the rest:

1. **ffmpeg** — click **Install ffmpeg** (or install it yourself and put it on
   your `PATH`; the app checks automatically).
2. **Kokoro TTS** — lightweight voice, runs on any CPU. Click **Install**.
3. **IndexTTS** (optional) — high-quality voice cloning; requires an NVIDIA GPU.
   Click **Install** if you want it.
4. **MAGI v3** (optional) — automatic panel detection for manga pages.

These tools download once into `~/.mangaeasy/tools/` and are shared across all
your projects.

### Platform notes

**Windows**
- Windows may show a SmartScreen warning the first time ("Windows protected your
  PC"). Click *More info* → *Run anyway*. This happens because the exe is not
  code-signed.
- The console window that opens alongside the app is normal — it shows logs.
  Don't close it while the app is running.

**macOS**
- macOS Gatekeeper may block the binary. Right-click → *Open* and confirm, **or**
  run this once in Terminal after extracting:
  ```bash
  xattr -cr mangaEasy
  ./mangaEasy/mangaeasy
  ```

**Linux**
- Make the binary executable first:
  ```bash
  chmod +x mangaEasy/mangaeasy
  ./mangaEasy/mangaeasy
  ```
- If the browser doesn't open automatically, navigate to `http://127.0.0.1:5000`.

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

Build the standalone bundle yourself (requires PyInstaller, included as a dev dep):

```bash
uv sync --dev
uv run pyinstaller packaging/mangaeasy.spec --distpath dist --workpath build-tmp --noconfirm
# The ready-to-run folder is at dist/mangaEasy/
```

---

## Updating

### Standalone download
Download the latest release from the Releases page and replace your old
`mangaEasy/` folder. Your project files and the AI tools in `~/.mangaeasy/tools/`
are untouched.

### uv tool
```bash
uv tool upgrade mangaeasy
```

---

## Uninstalling

### Standalone download
Delete the `mangaEasy/` folder. To also remove the AI tools and app state:
```bash
# All platforms
rm -rf ~/.mangaeasy
```

### uv tool
```bash
uv tool uninstall mangaeasy
rm -rf ~/.mangaeasy   # optional: removes AI tools + app state
```
