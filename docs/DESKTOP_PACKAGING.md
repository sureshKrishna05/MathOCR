# MathOCR desktop packaging

Prepared by **Bouronikos Christos** ([chrisbouronikos@gmail.com](mailto:chrisbouronikos@gmail.com)). If this work is useful, please [support MathOCR on PayPal](https://paypal.me/christosbouronikos).

The desktop edition packages the existing frontend and Python service into an application that requires no Python, command line, Pandoc, or library installation from the end user.

## Runtime design

`desktop/main.py` starts FastAPI on a random `127.0.0.1` port, waits for its health endpoint, and opens that origin in a native pywebview window (or falls back seamlessly to the user's default browser if WebView2 or GUI drivers are unavailable). Closing the window or terminating the process gracefully stops the Uvicorn server and removes the instance lock. The service is never bound to a public network interface.

MathOCR enforces a single active instance using a lock file (`%LOCALAPPDATA%\MathOCR\mathocr.lock`). If the user clicks the shortcut while MathOCR is already running, the launcher detects the healthy server, opens the browser to that session, and exits immediately.

PyInstaller produces a one-folder application (`dist/MathOCR/`) because large machine-learning runtimes start more reliably from installed files than from a self-extracting `--onefile` executable.
- On Windows, Inno Setup 6 packages this into `dist/MathOCR-Setup.exe`.
- The installer installs per-user into `%LOCALAPPDATA%\Programs\MathOCR` by default, requiring **no administrator privileges**.
- Python-docx templates, Pandoc (`pypandoc_binary`), frontend assets, and OCR modules are all bundled.
- If Tesseract is installed separately via UB-Mannheim, MathOCR automatically discovers it at `C:\Program Files\Tesseract-OCR\tesseract.exe` or on `PATH`.

## First-launch model behavior

The installer contains the OCR libraries and bundled tools, but model weights are downloaded once on demand into a per-user directory:

- Windows: `%LOCALAPPDATA%\MathOCR\models`
- macOS: `~/Library/Application Support/MathOCR/models`
- Linux: `~/.cache/mathocr/models`

All model downloads are governed by a versioned manifest (`backend/model_store.py`) with upstream pinned URLs and cryptographic **SHA-256 checksums**:
- Atomic downloads stream to `.part` files, verify byte count and SHA-256 hash, and only then atomically replace the target file.
- Corrupted or partial downloads are immediately rejected and retried with exponential backoff (up to 3 attempts).
- Before downloading, a pre-flight disk space check ensures at least ~500 MB of free storage is available.
- Once downloaded, MathOCR operates **100% offline** without making external network calls.
- Total download is approximately **480 MB** (plus ~1.4 GB only if the user opts into Nougat).
- Upgrades and uninstalls are non-destructive: downloaded models in `%LOCALAPPDATA%\MathOCR\models` and user settings remain untouched.

## Local developer build

Build on the operating system being targeted. Python 3.11 is recommended.

```bash
python3.11 -m venv .venv-desktop
source .venv-desktop/bin/activate
python -m pip install --upgrade pip
pip install -r backend/requirements-desktop.txt
python scripts/build_desktop.py
```

On macOS, create the disk image:

```bash
bash scripts/package_macos.sh
```

On Windows, install Inno Setup 6 and run:

```powershell
.\scripts\package_windows.ps1
```

Expected outputs are:

- `dist/MathOCR-macOS-<architecture>.dmg`
- `dist/MathOCR-Setup.exe`

## GitHub builds

Run **Build MathOCR desktop installers** under GitHub Actions, or push a version tag such as `v0.1.0`. The workflow builds independently on macOS and Windows and publishes downloadable workflow artifacts.

## Signing requirements

Unsigned development artifacts are suitable for internal testing, but operating systems may display security warnings.

For public macOS distribution, sign all executable code with an Apple Developer ID, enable hardened runtime, notarize the final disk image, and staple its ticket. This requires credentials owned by the publisher and should be added as protected GitHub secrets.

For public Windows distribution, use an Authenticode code-signing certificate and sign both `MathOCR.exe` and `MathOCR-Setup.exe`. Signing credentials must never be committed to this repository.

## Release checklist

1. Run API, export, and launcher tests.
2. Build on each native target architecture.
3. Test on a clean computer without Python or Pandoc installed.
4. Verify first-run model download, offline second run, PDF limits, and Word export.
5. Include third-party license notices for every redistributed binary and model.
6. Sign, notarize where applicable, and malware-scan the final installer.
7. Publish SHA-256 checksums alongside the release.

