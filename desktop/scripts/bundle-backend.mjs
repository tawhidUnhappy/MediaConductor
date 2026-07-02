#!/usr/bin/env node
// Builds the PyInstaller mangaeasy backend (packaging/mangaeasy.spec) from
// the repo root and copies it into desktop/resources/backend/, where
// electron-builder.yml's extraResources picks it up. Run before
// `electron-builder` — `npm run build:win/:mac/:linux` already does this.
import { execFileSync } from 'node:child_process'
import { cpSync, existsSync, mkdirSync, rmSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const desktopDir = path.resolve(__dirname, '..')
const repoRoot = path.resolve(desktopDir, '..')
const distDir = path.join(repoRoot, 'dist')
const backendOut = path.join(desktopDir, 'resources', 'backend')

console.log('[bundle-backend] running PyInstaller…')
execFileSync(
  'uv',
  [
    'run',
    'pyinstaller',
    'packaging/mangaeasy.spec',
    '--distpath',
    'dist',
    '--workpath',
    'build-tmp',
    '--noconfirm',
    '--clean'
  ],
  { cwd: repoRoot, stdio: 'inherit' }
)

// PyInstaller's spec produces dist/mangaEasy/ everywhere (plus a
// dist/mangaEasy.app bundle on macOS). Always take the plain onedir output:
// the .app's Contents/MacOS is NOT self-contained under PyInstaller 6 — its
// payload lives in Contents/Frameworks with symlinks pointing there, so
// copying MacOS/ alone ships dangling symlinks and a backend that dies on
// launch (caught by the release workflow's frozen-backend smoke test).
const sourceDir = path.join(distDir, 'mangaEasy')

if (!existsSync(sourceDir)) {
  console.error(`[bundle-backend] expected PyInstaller output at ${sourceDir}, found nothing.`)
  process.exit(1)
}

rmSync(backendOut, { recursive: true, force: true })
mkdirSync(backendOut, { recursive: true })
cpSync(sourceDir, backendOut, { recursive: true })

console.log(`[bundle-backend] copied ${sourceDir} -> ${backendOut}`)
