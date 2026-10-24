# Qryptex — Academic Document & Math OCR
### 🏛️ Bharathidasan University Edition
**Turn photos, scans, and PDFs of academic mathematics into native, editable Microsoft Word equations and LaTeX — 100% locally and privately on your computer.**

Official Portal: [qryptex.in](https://qryptex.in) · Developed for **Bharathidasan University** · Core Engine: [MIT License](LICENSE)

---

## 📌 Overview

**Qryptex** converts mathematical documents, handwritten formulas, textbook camera photos, and PDF chapters into clean **LaTeX** code and **native, editable Microsoft Word documents (`.docx`)**. 

Everything operates **100% offline and locally on your own computer** — your private exam papers, research drafts, and notes are never sent to third-party cloud APIs.

### 🌟 Key Highlights
- **Native Word Equations (OMML)**: Formulas are exported as real Microsoft Word equation objects (`<m:oMath>`), directly selectable and editable in Word’s equation editor (not blurry screenshot images or raw text).
- **Multi-Engine Voting Ensemble**: Three independent neural engines cross-check and vote on every formula to catch and correct edge-case errors:
  1. **Pix2Text MFR-1.5** (Primary detector + recognizer)
  2. **pix2tex / LaTeX-OCR** (Second opinion vision transformer)
  3. **RapidLaTeXOCR** (High-speed ONNX tie-breaker)
  4. **Tesseract OCR** (Full page text reader for documents)
- **Smartphone Camera Photo Support**: Take a flat photo of a physical textbook or blackboard with your mobile phone and drop it directly into the interface.
- **Academic Document Layouts**: Reconstructs paragraphs, section headings, multi-column reading orders, and genuine Word tables with embedded math.

---

## ⚡ Quick Start on Windows

### Option 1: One-Click Source Launcher (Easiest for local setup)

1. **Prerequisites**:
   - Install **[Python 3.11 (64-bit)](https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe)** *(Note: Check the box "Add python.exe to PATH" during setup).*
   - Install **[Git for Windows](https://git-scm.com/download/win)**.
   - *(Optional for full page text)*: Install **[Tesseract OCR (UB-Mannheim)](https://github.com/UB-Mannheim/tesseract/wiki)**. Math recognition works out-of-the-box without it.

2. **Clone and Run**:
   ```cmd
   git clone https://github.com/sureshKrishna05/MathOCR.git
   cd MathOCR
   run.bat
   ```
   *(Or simply double-click `run.bat` in File Explorer).*

3. **Access Qryptex**:
   - The launcher will automatically configure a local `.venv`, install requirements, and open your browser to **[http://127.0.0.1:8000](http://127.0.0.1:8000)**.
   - On first launch, click **"Download all models now"** (~480 MB) to enable complete offline operation.

---

### Option 2: Build the Standalone Desktop Installer (`.exe`)

To compile a standalone installer that requires **no Python or command line** on end-user computers:

1. Install **[Inno Setup 6](https://jrsoftware.org/isdl.php)**.
2. In PowerShell:
   ```powershell
   # 1. Activate build environment
   python -m venv .venv-desktop
   .\.venv-desktop\Scripts\Activate.ps1

   # 2. Install desktop build tools
   pip install -r backend\requirements-desktop.txt

   # 3. Compile standalone application
   python scripts\build_desktop.py

   # 4. Create Windows setup wizard
   .\scripts\package_windows.ps1
   ```
3. Your installer will be ready at: **`dist\Qryptex-Setup.exe`**.

---

## 🐧 Quick Start on Linux (Docker / Omarchy)

Run cleanly inside an isolated Docker container with pre-configured Tesseract and model volume persistence:

```bash
cd MathOCR

# Start the Qryptex container in background
sudo docker compose up -d --build

# View real-time logs
sudo docker compose logs -f

# Pre-download models inside container
sudo docker compose exec mathocr python scripts/download_models.py
```
Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.

*(To stop: `sudo docker compose down`)*

---

## 💻 Hardware Requirements & Performance Guide

| Component | Minimum Specification | Recommended Specification |
| :--- | :--- | :--- |
| **Operating System** | Windows 10/11 (64-bit) or Linux (Ubuntu, Arch, Omarchy) | Windows 11 (64-bit) |
| **Processor** | Intel Core i3 / AMD Ryzen 3 | Intel Core i5/i7 or AMD Ryzen 5/7 |
| **RAM** | **4 GB** (Single engine mode) | **8 GB** (Ensemble voting mode) |
| **Disk Space** | ~2 GB (App + ~480 MB pre-trained models) | ~4 GB |
| **GPU (Optional)** | None (runs CPU multi-threaded) | NVIDIA RTX (CUDA) for 5x–10x speedup |

### 📊 Benchmark on Intel Core i3 with 8 GB RAM (Tested & Verified):
- **Safe Batch Size**: **10 pages per PDF run** or **12 textbook photos at once**.
- **Processing Speed**: **~8 to 14 seconds per page** on Core i3 CPU.
- **Memory Footprint**: Models stay loaded at ~1.6 GB RAM; intermediate page tensors are recycled with per-page garbage collection, ensuring **0% memory thrashing**.

---

## 📖 How to Use Qryptex

1. **Add Your Files**:
   - Drag and drop PDF chapters or camera images (`PNG`, `JPG`, `WEBP`, `TIFF`, `PDF`).
   - Or paste an equation screenshot directly with <kbd>Ctrl</kbd> + <kbd>V</kbd>.
2. **Select Recognition Mode**:
   - **All text + math (whole document)**: Reconstructs paragraphs, tables, and equations into an editable Word document.
   - **Only the math inside a page of text**: Extracts equations as a list of LaTeX formulas.
   - **Only one equation**: Cropped single equation mode for quick formula lookup.
3. **Choose Engine Mode**:
   - **MFR-1.5 — fast (recommended)**: Best balance of speed and high accuracy.
   - **Cross-check all engines**: Highest precision voting mode across all 3 models.
   - **RapidLaTeXOCR**: Ultralight ONNX model for rapid recognition.
4. **Export**:
   - Click **Download document (Word)** for a native `.docx` with selectable Word equations.
   - Or click **Copy text** / **Copy all LaTeX** for direct pasting into Overleaf, Notion, or Obsidian.

---

## 🔧 Project Structure

```text
MathOCR/
├── backend/               # FastAPI backend, OCR routing, and document builder
│   ├── app.py             # REST API routes and file handlers
│   ├── document.py        # Structured layout and geometry models
│   ├── docx_export.py     # Native Word (OMML) XML generator
│   ├── engines.py         # OCR voting ensemble and model adapters
│   ├── model_store.py     # Local model cache & SHA-256 verification
│   └── requirements.txt   # Pinned Python dependencies
├── frontend/              # Modern Qryptex web interface
│   ├── index.html         # Main dashboard
│   ├── styles.css         # Modern responsive styling
│   └── app.js             # Client state, KaTeX preview, and export handlers
├── desktop/               # Native pywebview desktop launcher
├── packaging/             # PyInstaller spec and Inno Setup Windows scripts
├── scripts/
│   ├── build_desktop.py   # Desktop packaging pipeline
│   ├── package_windows.ps1# Inno Setup Windows compiler
│   └── download_models.py # Offline model downloader
├── compose.yaml           # Docker Compose specification
├── Dockerfile             # Multi-stage Linux container definition
└── run.bat                # Windows auto-detection launcher
```

---

## 🛡️ Privacy & Security

- **Zero Cloud Leakage**: Files stay entirely in local memory during processing.
- **No External Telemetry**: No tracking, analytics, or external logging.
- **Local Address Binding**: The service binds strictly to `127.0.0.1` (localhost loopback).

---

## 📜 Credits & License

- **Edition**: Developed for **Bharathidasan University** · [qryptex.in](https://qryptex.in).
- **Core Technology**: Based on open-source MathOCR by **Bouronikos Christos** ([chrisbouronikos@gmail.com](mailto:chrisbouronikos@gmail.com)).
- **License**: Released under the **[MIT License](LICENSE)**. Third-party components and neural model weights are attributed in [NOTICE](NOTICE).
