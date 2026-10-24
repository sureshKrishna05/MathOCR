# MathOCR

**Turn images and PDFs of mathematics into editable LaTeX and Microsoft Word equations — entirely on your own computer.**

Created by **Bouronikos Christos** ([chrisbouronikos@gmail.com](mailto:chrisbouronikos@gmail.com)) · [GitHub](https://github.com/ChristosBouronikos) · If MathOCR helps you, please consider a [PayPal donation](https://paypal.me/christosbouronikos).

🇬🇧 **English** below · 🇬🇷 [Ελληνικά πιο κάτω](#ελληνικά)

---

## English

MathOCR reads mathematics from screenshots, photos, scans, and PDFs and gives you back clean **LaTeX** and editable **Word** equations. Everything runs locally: your files never leave your computer. The interface is in **English and Greek**, and it reads both **Greek and English text** as well as the mathematics.

### Why it is accurate

Three math-recognition engines run at once and **vote** on every formula, so a mistake by one is caught by the others. A detector first finds each formula and, crucially, **merges the pieces of a tall fraction or a wide equation back together** before reading it — that is why large fractions and complicated expressions are recognized as one equation instead of being split into parts.

| Engine | Role | License |
|---|---|---|
| **Pix2Text MFR-1.5** | Primary recognizer + math-region detector (the default) | MIT |
| **pix2tex / LaTeX-OCR** | Second opinion | MIT |
| **RapidLaTeXOCR** | Fast tie-breaker | Apache-2.0 |
| **Tesseract** (Greek + English) | Page text in *document* mode | Apache-2.0 |
| **Nougat** (optional, English papers) | Alternative document reader — **not bundled**, non-commercial weights | code MIT / weights CC-BY-NC |

You can keep the default (**Best — cross-check all**) or pick a single engine in the interface.

### What you can do

- **Drag and drop** an image or PDF (or paste a screenshot with <kbd>Ctrl</kbd>+<kbd>V</kbd>).
- Choose what to recognize:
  1. **All text + math** — reconstructs the whole page (Greek/English text *and* equations) into an editable document.
  2. **Only the math inside a page of text** — returns just the equations.
  3. **Only one equation** — for a single cropped formula.
- Review every result with a **live equation preview**, and swap in another engine's reading when they disagree.
- **Copy LaTeX**, **download a `.tex`**, or **download a Word document** with native, editable equations.
- Manage disk space: **download or delete the models** from inside the app at any time.

> Downloaded Word/LaTeX files are automatically named ending in **"by Bouronikos Christos"** (e.g. `MathOCR document by Bouronikos Christos.docx`).

> ⚠️ OCR can make convincing mistakes. Always compare important formulas with the source.

### Requirements

| | Minimum | Recommended |
|---|---|---|
| Operating system | Windows 10/11 (64-bit) or macOS 12+ | latest |
| RAM | **4 GB** | **8 GB** (cross-checking all engines is memory-hungry) |
| Free disk space | see below | |
| Internet | only for the **first** recognition (to download models); offline afterwards | |
| Python / setup | **none for the desktop app** — Python, all libraries, and Pandoc are bundled inside | |

**Disk space:**

- The installed application is roughly **1.5–2 GB** (it bundles Python and the OCR libraries).
- Recognition models are downloaded on first use into a per-user folder:
  - Pix2Text MFR-1.5 ≈ **190 MB**, pix2tex ≈ **115 MB**, RapidLaTeXOCR ≈ **170 MB**, Tesseract (Greek + English) ≈ **5 MB** → **about 480 MB total**.
  - Optional Nougat (English papers) adds ≈ **1.4 GB** and is only fetched when you press its **Download** button in the model panel. When running from source, that button installs the engine and its weights for you; the packaged app needs a Nougat-enabled build or a source run to add it.
- You can delete any model from the app's **"Models on this computer"** panel to reclaim the space; it re-downloads automatically when next needed.

Models are stored in:

- **macOS:** `~/Library/Application Support/MathOCR/models`
- **Windows:** `%LOCALAPPDATA%\MathOCR\models`

### Install and run

#### Option 1 — Desktop app (recommended, zero setup)

Download the installer for your system from the [latest release](https://github.com/ChristosBouronikos/MathOCR/releases/latest):

- **Windows 10 / 11 (64-bit):**
  1. Download and run `MathOCR-Setup.exe`.
  2. The installer installs per-user into `%LOCALAPPDATA%\Programs\MathOCR` by default — **no administrator/UAC privileges required**.
  3. Check the box if you want a **Desktop Shortcut** (Start Menu shortcut is created automatically).
  4. Launch MathOCR from the Start Menu or Desktop.
  5. On first launch, click **"Download all models now"** (or simply drag in a file). The application downloads and verifies the model weights using SHA-256 integrity checksums. Once downloaded (~480 MB), MathOCR works **100% offline**.
- **macOS (12+):**
  1. Open `MathOCR-macOS-*.dmg` and drag **MathOCR** to Applications.
  2. Launch MathOCR from Applications.

#### Option 2 — Run from source (auto-installs Python)

Clone the repository and start it with the launcher for your system. If Python is missing it is installed for you.

- **macOS:** double-click **`run.command`** (or `./run.command` in Terminal).
- **Windows:** double-click **`run.bat`**.

The launcher creates a local environment, installs the dependencies on first run, then opens MathOCR at <http://127.0.0.1:8000>. Greek page-text recognition needs **Tesseract** with the `ell` language — the macOS launcher installs it with Homebrew; on Windows install it from the [UB Mannheim build](https://github.com/UB-Mannheim/tesseract/wiki). MathOCR automatically checks `C:\Program Files\Tesseract-OCR\tesseract.exe` and PATH. Math recognition works without Tesseract.

#### Option 3 — Manual (for developers)

```bash
python3.11 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Then open <http://127.0.0.1:8000>. Install [Pandoc](https://pandoc.org/installing.html) for Word export and [Tesseract](https://tesseract-ocr.github.io/) (+ Greek data) for document-mode text.

### User Guide: How to Use MathOCR

1. **Converting Documents & Images**:
   - Drag and drop an image (PNG, JPEG, WebP) or PDF file directly onto the interface, or press <kbd>Ctrl</kbd>+<kbd>V</kbd> to paste from the clipboard.
   - Choose your document style (e.g. *Academic Textbook*, *Formal Report*, or *Standard Editable*).
   - Click **Recognize Document**.
2. **Reviewing and Editing**:
   - MathOCR provides a live preview of reconstructed text, tables, and equations.
   - Click any equation or text block to make manual corrections before exporting.
3. **Downloading Editable Word Documents**:
   - Click **Download document (Word)**.
   - In the desktop application, the file is automatically saved into your Windows **Downloads** folder (`%USERPROFILE%\Downloads`), named as `MathOCR document by Bouronikos Christos.docx` (with automatic number incrementing if a file with the same name exists).
   - In browser mode, your browser prompts you to save the file.
   - Open the `.docx` file in Microsoft Word or LibreOffice. Equations are native OMML objects selectable and editable directly in Word's equation editor!

### Troubleshooting & FAQ

- **MathOCR is already running**:
  MathOCR prevents duplicate background servers using a single-instance lock (`%LOCALAPPDATA%\MathOCR\mathocr.lock`). Launching the shortcut while MathOCR is already running automatically focuses or opens your browser to the active session.
- **WebView2 is missing on Windows 10**:
  If the Microsoft WebView2 runtime is not installed, MathOCR gracefully falls back to your default web browser (Edge, Chrome, Firefox) on a private loopback address (`127.0.0.1`).
- **Insufficient Disk Space Error**:
  Before downloading models, MathOCR checks that at least 500 MB of free space is available in `%LOCALAPPDATA%\MathOCR\models`. Free up space on your `C:` drive and retry.
- **Corrupted or Interrupted Downloads**:
  Model files are downloaded atomically with `.part` staging files and verified against upstream SHA-256 cryptographic checksums. If a network interruption occurs, MathOCR retries up to 3 times with exponential backoff. Incomplete downloads never corrupt existing models.
- **Page text recognition is missing (Tesseract)**:
  Math recognition works out-of-the-box. For full document page-text OCR, install Tesseract OCR from [UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki). MathOCR automatically detects installations in `C:\Program Files\Tesseract-OCR\tesseract.exe` without needing manual PATH configuration.
- **How to Update**:
  Download and run the new `MathOCR-Setup.exe`. Your downloaded models in `%LOCALAPPDATA%\MathOCR\models` and user settings are preserved across upgrades.
- **How to Uninstall**:
  Go to Windows **Settings > Apps > Installed apps**, find **MathOCR**, and click **Uninstall**. The uninstaller cleanly removes application binaries from `%LOCALAPPDATA%\Programs\MathOCR` while keeping your exported documents and models safe.

### Native Word (OMML) & Structured Document Export

MathOCR exports documents and equations directly into editable Microsoft Word (`.docx`) files with full support for:
- **Native OMML Equations**: Formulas are converted into Office Math Markup Language (`<m:oMath>` and `<m:oMathPara>`), making them directly selectable and editable in Microsoft Word's equation editor (not images or raw text).
- **Fractions, Superscripts, Integrals, Roots, Matrices, and Greek letters**: Comprehensive support for academic mathematical notation.
- **Genuine Word Tables**: Reconstructed tables use real Word table XML (`<w:tbl>`, `<w:tr>`, `<w:tc>`) with editable cells and embedded formulas.
- **Document Structure**: Section headings, paragraphs, bulleted and numbered lists, and reading order are preserved.
- **Error Handling**: If a mathematical expression contains unsupported or malformed syntax, a clear warning is generated and an explicit placeholder is inserted without leaking raw LaTeX into ordinary text.

#### Setup & Offline Operation

Once dependencies and models are installed locally, all OCR recognition, mathematical formula conversion, and DOCX generation operate **100% offline** on your computer. No data is ever sent to external cloud APIs.

```bash
# Install dependencies including python-docx and lxml
pip install -r backend/requirements.txt

# Start the application server locally
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

#### Running Tests

Automated tests cover equation conversion, Word tables, mixed academic documents, offline operation, and LibreOffice compatibility:

```bash
# Run the complete test suite
pytest tests/ -v

# Run the structured DOCX export tests specifically
pytest tests/test_structured_docx.py -v
```

#### Known Limitations

- Complex multi-page merged table cells across page boundaries require manual verification.
- Heavily distorted, low-contrast scans or non-standard mathematical shorthands may require formula review in the editor before final export.

### Build the desktop installers

On each target operating system:

```bash
python3.11 -m venv .venv-desktop
source .venv-desktop/bin/activate
pip install -r backend/requirements-desktop.txt
python scripts/build_desktop.py
bash scripts/package_macos.sh        # macOS DMG
# Windows: ./scripts/package_windows.ps1  (needs Inno Setup 6)
```

GitHub Actions can build both platforms through the **Build MathOCR desktop installers** workflow. Full details, code-signing, and how to bundle Tesseract are in [docs/DESKTOP_PACKAGING.md](docs/DESKTOP_PACKAGING.md).

### Privacy

Files are processed only by the MathOCR engine running on your computer and are held in memory during recognition. Temporary export files are deleted right after download. The service binds to `127.0.0.1`; do not expose it to the network.

### License and credits

MathOCR is released under the [MIT License](LICENSE) — © 2026 **Bouronikos Christos**. Please keep the credit to the original author if you fork or redistribute it. Bundled third-party components and their licenses are listed in [NOTICE](NOTICE). Questions and contributions are welcome at [chrisbouronikos@gmail.com](mailto:chrisbouronikos@gmail.com); support the project on [PayPal](https://paypal.me/christosbouronikos).

---

## Ελληνικά

Το **MathOCR** διαβάζει μαθηματικά από στιγμιότυπα οθόνης, φωτογραφίες, σαρώσεις και PDF, και σας δίνει καθαρό **LaTeX** και επεξεργάσιμες εξισώσεις **Word**. Όλα εκτελούνται τοπικά: τα αρχεία σας δεν φεύγουν ποτέ από τον υπολογιστή σας. Το περιβάλλον είναι στα **Ελληνικά και τα Αγγλικά**, και αναγνωρίζει τόσο **ελληνικό και αγγλικό κείμενο** όσο και τα μαθηματικά.

### Γιατί είναι ακριβές

Τρεις μηχανές αναγνώρισης μαθηματικών εκτελούνται ταυτόχρονα και **ψηφίζουν** για κάθε τύπο, ώστε το λάθος της μίας να διορθώνεται από τις άλλες. Ένας ανιχνευτής εντοπίζει πρώτα κάθε τύπο και, το σημαντικότερο, **επανενώνει τα κομμάτια ενός ψηλού κλάσματος ή μιας μεγάλης εξίσωσης** πριν τα διαβάσει — γι' αυτό τα μεγάλα κλάσματα και οι σύνθετες παραστάσεις αναγνωρίζονται ως **μία** εξίσωση αντί να σπάνε σε κομμάτια.

| Μηχανή | Ρόλος | Άδεια |
|---|---|---|
| **Pix2Text MFR-1.5** | Κύρια μηχανή + ανιχνευτής περιοχών (προεπιλογή) | MIT |
| **pix2tex / LaTeX-OCR** | Δεύτερη γνώμη | MIT |
| **RapidLaTeXOCR** | Γρήγορη κρίση ισοπαλίας | Apache-2.0 |
| **Tesseract** (Ελληνικά + Αγγλικά) | Κείμενο σελίδας στη λειτουργία *εγγράφου* | Apache-2.0 |
| **Nougat** (προαιρετικό, αγγλικές εργασίες) | Εναλλακτική ανάγνωση εγγράφου — **δεν συμπεριλαμβάνεται**, μη εμπορική άδεια βαρών | κώδικας MIT / βάρη CC-BY-NC |

Μπορείτε να κρατήσετε την προεπιλογή (**Βέλτιστη — διασταύρωση όλων**) ή να επιλέξετε μία μηχανή μέσα από το περιβάλλον.

### Τι μπορείτε να κάνετε

- **Σύρετε και αφήστε** μια εικόνα ή ένα PDF (ή επικολλήστε στιγμιότυπο με <kbd>Ctrl</kbd>+<kbd>V</kbd>).
- Επιλέξτε τι θα αναγνωριστεί:
  1. **Όλο το κείμενο + μαθηματικά** — ανακατασκευάζει ολόκληρη τη σελίδα (ελληνικό/αγγλικό κείμενο *και* εξισώσεις) σε επεξεργάσιμο έγγραφο.
  2. **Μόνο τα μαθηματικά μέσα σε σελίδα με κείμενο** — επιστρέφει μόνο τις εξισώσεις.
  3. **Μόνο μία εξίσωση** — για μία κομμένη εικόνα τύπου.
- Ελέγξτε κάθε αποτέλεσμα με **ζωντανή προεπισκόπηση** της εξίσωσης, και αντικαταστήστε με την ανάγνωση άλλης μηχανής όταν διαφωνούν.
- **Αντιγράψτε LaTeX**, **κατεβάστε `.tex`**, ή **κατεβάστε έγγραφο Word** με εγγενείς, επεξεργάσιμες εξισώσεις.
- Διαχειριστείτε τον χώρο στον δίσκο: **κατεβάστε ή διαγράψτε τα μοντέλα** μέσα από την εφαρμογή όποτε θέλετε.

> Τα αρχεία Word/LaTeX που κατεβάζετε ονομάζονται αυτόματα με κατάληξη **«by Bouronikos Christos»** (π.χ. `Έγγραφο MathOCR by Bouronikos Christos.docx`).

> ⚠️ Το OCR μπορεί να κάνει πειστικά λάθη. Συγκρίνετε πάντα τους σημαντικούς τύπους με το πρωτότυπο.

### Απαιτήσεις

| | Ελάχιστες | Προτεινόμενες |
|---|---|---|
| Λειτουργικό σύστημα | Windows 10/11 (64-bit) ή macOS 12+ | το πιο πρόσφατο |
| Μνήμη RAM | **4 GB** | **8 GB** (η διασταύρωση όλων των μηχανών θέλει μνήμη) |
| Ελεύθερος χώρος δίσκου | δείτε παρακάτω | |
| Σύνδεση στο διαδίκτυο | μόνο για την **πρώτη** αναγνώριση (λήψη μοντέλων)· μετά λειτουργεί εκτός σύνδεσης | |
| Python / εγκατάσταση | **καμία για την εφαρμογή** — η Python, όλες οι βιβλιοθήκες και το Pandoc περιλαμβάνονται | |

**Χώρος στον δίσκο:**

- Η εγκατεστημένη εφαρμογή είναι περίπου **1,5–2 GB** (περιλαμβάνει την Python και τις βιβλιοθήκες OCR).
- Τα μοντέλα αναγνώρισης κατεβαίνουν στην πρώτη χρήση σε φάκελο του χρήστη:
  - Pix2Text MFR-1.5 ≈ **190 MB**, pix2tex ≈ **115 MB**, RapidLaTeXOCR ≈ **170 MB**, Tesseract (Ελληνικά + Αγγλικά) ≈ **5 MB** → **περίπου 480 MB συνολικά**.
  - Το προαιρετικό Nougat (αγγλικές εργασίες) προσθέτει ≈ **1,4 GB** και κατεβαίνει μόνο όταν πατήσετε το κουμπί **Λήψη** στο πλαίσιο μοντέλων. Όταν εκτελείτε από τον πηγαίο κώδικα, το κουμπί εγκαθιστά τη μηχανή και τα βάρη της· η εφαρμογή χρειάζεται έκδοση με ενσωματωμένο Nougat ή εκτέλεση από πηγαίο κώδικα για να το προσθέσει.
- Μπορείτε να διαγράψετε οποιοδήποτε μοντέλο από το πλαίσιο **«Μοντέλα σε αυτόν τον υπολογιστή»** για να ελευθερώσετε χώρο· κατεβαίνει ξανά αυτόματα όταν χρειαστεί.

Τα μοντέλα αποθηκεύονται στο:

- **macOS:** `~/Library/Application Support/MathOCR/models`
- **Windows:** `%LOCALAPPDATA%\MathOCR\models`

### Εγκατάσταση και εκτέλεση

#### Επιλογή 1 — Εφαρμογή για υπολογιστή (προτεινόμενη, χωρίς ρυθμίσεις)

Κατεβάστε το πρόγραμμα εγκατάστασης για το σύστημά σας από την [πιο πρόσφατη έκδοση](https://github.com/ChristosBouronikos/MathOCR/releases/latest):

- **macOS:** ανοίξτε το `MathOCR-macOS-*.dmg` και σύρετε το **MathOCR** στις Εφαρμογές.
- **Windows:** εκτελέστε το `MathOCR-Setup.exe`.

Ανοίξτε το MathOCR όπως κάθε εφαρμογή και σύρετε μέσα ένα αρχείο. Η πρώτη αναγνώριση κατεβάζει τα μοντέλα (λίγα λεπτά)· μετά όλα λειτουργούν εκτός σύνδεσης. Δεν εγκαθιστάτε ποτέ Python ή οτιδήποτε άλλο.

#### Επιλογή 2 — Εκτέλεση από τον πηγαίο κώδικα (εγκαθιστά αυτόματα την Python)

Κλωνοποιήστε το αποθετήριο και ξεκινήστε το με τον εκκινητή του συστήματός σας. Αν λείπει η Python, εγκαθίσταται για εσάς.

- **macOS:** διπλό κλικ στο **`run.command`** (ή `./run.command` στο Terminal).
- **Windows:** διπλό κλικ στο **`run.bat`**.

Ο εκκινητής δημιουργεί ένα τοπικό περιβάλλον, εγκαθιστά τις εξαρτήσεις στην πρώτη εκτέλεση και ανοίγει το MathOCR στη διεύθυνση <http://127.0.0.1:8000>. Η αναγνώριση ελληνικού κειμένου χρειάζεται το **Tesseract** με τη γλώσσα `ell` — ο εκκινητής του macOS το εγκαθιστά μέσω Homebrew· στα Windows εγκαταστήστε το από την [έκδοση UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki). Η αναγνώριση μαθηματικών λειτουργεί και χωρίς το Tesseract.

#### Επιλογή 3 — Χειροκίνητα (για προγραμματιστές)

```bash
python3.11 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Έπειτα ανοίξτε <http://127.0.0.1:8000>. Εγκαταστήστε το [Pandoc](https://pandoc.org/installing.html) για εξαγωγή Word και το [Tesseract](https://tesseract-ocr.github.io/) (+ ελληνικά δεδομένα) για κείμενο στη λειτουργία εγγράφου.

### Δημιουργία των εγκαταστατών

Σε κάθε λειτουργικό σύστημα-στόχο:

```bash
python3.11 -m venv .venv-desktop
source .venv-desktop/bin/activate
pip install -r backend/requirements-desktop.txt
python scripts/build_desktop.py
bash scripts/package_macos.sh        # DMG για macOS
# Windows: ./scripts/package_windows.ps1  (χρειάζεται Inno Setup 6)
```

Το GitHub Actions μπορεί να χτίσει και για τα δύο συστήματα μέσω της ροής **Build MathOCR desktop installers**. Λεπτομέρειες, ψηφιακή υπογραφή και ο τρόπος ενσωμάτωσης του Tesseract υπάρχουν στο [docs/DESKTOP_PACKAGING.md](docs/DESKTOP_PACKAGING.md).

### Ιδιωτικότητα

Τα αρχεία επεξεργάζονται μόνο από τη μηχανή MathOCR που εκτελείται στον υπολογιστή σας και κρατούνται στη μνήμη κατά την αναγνώριση. Τα προσωρινά αρχεία εξαγωγής διαγράφονται αμέσως μετά τη λήψη. Η υπηρεσία δεσμεύεται στο `127.0.0.1`· μην την εκθέσετε στο δίκτυο.

### Άδεια και μνεία

Το MathOCR διατίθεται με την [άδεια MIT](LICENSE) — © 2026 **Bouronikos Christos**. Παρακαλώ διατηρήστε τη μνεία στον αρχικό δημιουργό αν το αντιγράψετε ή το αναδιανείμετε. Τα ενσωματωμένα στοιχεία τρίτων και οι άδειές τους αναφέρονται στο [NOTICE](NOTICE). Ερωτήσεις και συνεισφορές είναι ευπρόσδεκτες στο [chrisbouronikos@gmail.com](mailto:chrisbouronikos@gmail.com)· υποστηρίξτε το έργο στο [PayPal](https://paypal.me/christosbouronikos).
