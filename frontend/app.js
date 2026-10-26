/**
 * MathOCR browser client by Bouronikos Christos <chrisbouronikos@gmail.com>.
 * Support the project at https://paypal.me/christosbouronikos.
 *
 * Plain JavaScript, no build step: the same files run from GitHub Pages, from
 * the local FastAPI service, and inside the packaged desktop application.
 * All text lives in the translations table so the interface is fully
 * bilingual (English / Greek).
 */

"use strict";

const APP_VERSION = "1.0.6";
const MAX_FILE_BYTES = 25 * 1024 * 1024;
const MAX_FILES = 12;
const RELEASES_URL = "https://github.com/ChristosBouronikos/MathOCR/releases/latest";
const ENGINE_SHORT_NAMES = {
  "pix2text-mfr": "Pix2Text MFR",
  pix2tex: "pix2tex",
  "rapid-latex": "RapidLaTeX",
};

const translations = {
  en: {
    pageTitle: "Qryptex — Academic Document & Math to Word",
    brandBy: "Academic Document & Math to Word",
    refreshPage: "Refresh",
    updateTitle: "A new version is available",
    updateDetail: "Qryptex {{latest}} is available — you have {{current}}.",
    updateNotes: "Release notes ↗",
    updateNow: "Update now",
    updateDownload: "Download ↗",
    updateStartedWin: "Installer launched. Qryptex will now close to finish updating.",
    updateStartedMac: "Update downloaded to your Downloads folder. Drag Qryptex into Applications to replace the old version, then reopen it.",
    updateFailed: "The update could not be downloaded — try again or download it from GitHub.",
    checkUpdates: "Check for updates",
    checkingUpdates: "Checking for updates…",
    upToDate: "You have the latest version ({{version}}).",
    updateCheckFailed: "Could not check for updates — check your connection.",
    serviceChecking: "Checking engine…",
    serviceReady: "Local engine ready",
    serviceNoPandoc: "OCR ready · Pandoc missing",
    serviceOffline: "Engine offline",
    eyebrow: "ACADEMIC DOCUMENT & MATH OCR",
    introTitle: "Images and PDFs into editable Word documents.",
    introCopy: "Drop a file, review the reconstructed document, and export editable Word equations. Everything runs locally on your computer.",
    engineBannerTitle: "The local engine is not running.",
    engineBannerCopy: "Recognition happens on your computer, so the local engine must be running.",
    engineBannerAction: "Get the desktop app",
    dropFiles: "Drop images or PDFs here",
    browseFiles: "click to browse, or paste a screenshot (Ctrl+V) · PNG, JPG, WEBP, TIFF, PDF",
    inputType: "What do you want to recognize?",
    modeDocument: "All text + math (whole document)",
    modeMixed: "Only the math inside a page of text",
    modeFormula: "Only one equation (cropped image)",
    mathEngine: "Math engine",
    engineBest: "Cross-check all engines (slower)",
    enginePix2text: "MFR-1.5 — fast (recommended)",
    enginePix2tex: "pix2tex (LaTeX-OCR)",
    engineRapid: "RapidLaTeXOCR",
    docReader: "Text reader (document mode)",
    docLayout: "Greek + English (Tesseract)",
    docNougat: "Nougat — English papers",
    docNougatUnavailable: "Nougat — download it below first",
    pageLimit: "PDF page limit",
    recognize: "Recognize document & mathematics",
    engineAddress: "Advanced: engine address",
    checkConnection: "Check connection",
    connectionInitial: "Start the local engine to enable recognition and Word export.",
    filesStayLocal: "Files are sent only to the local engine on this computer.",
    installPandoc: "OCR works, but Pandoc is required for Word export.",
    startEngine: "Start the local engine to enable recognition and Word export.",
    readingMath: "Reading document & mathematics…",
    processingNote: "The first run loads the model into memory and can take a minute or two; later runs are much faster.",
    loadingModel: "Preparing your first recognition…",
    processingFirstRun: "Loading models if needed · {{elapsed}} elapsed. The first run can take a minute or two.",
    processingElapsed: "Recognizing document · {{elapsed}} elapsed. Keep the window open while it works.",
    processingStillWorking: "Still recognizing · {{elapsed}} elapsed. Large pages and cross-checking take longer.",
    reconstructedDocument: "Reconstructed document",
    documentHint: "Edit the text and math below, then export the whole document to Word.",
    copyDocument: "Copy text",
    downloadDocWord: "Download document (Word)",
    editableDocument: "Editable document text and LaTeX",
    documentCopied: "Document text copied",
    documentTitle: "Qryptex Document",
    recognizedEquations: "Recognized equations",
    resultsOne: "1 equation found. Edit the LaTeX and the preview updates live.",
    resultsMany: "{{count}} equations found. Edit the LaTeX and the preview updates live.",
    noEquationsDetected: "No equations were detected. Try a clearer image, or the “One cropped equation” mode.",
    reviewReminder: "OCR can make convincing mistakes — always compare with the source.",
    ensembleAdviceTitle: "Want a second opinion?",
    ensembleAdvice: "If the result is not satisfactory, select “Cross-check all engines” and recognize the file again.",
    copyAll: "Copy all LaTeX",
    downloadTex: "Download .tex",
    downloadWord: "Download Word",
    page: "Page",
    confidence: "confidence",
    alternativeReadings: "Other engines read:",
    editableLatex: "Editable LaTeX",
    renderedPreview: "Rendered equation preview",
    copyLatex: "Copy",
    remove: "Remove",
    latexCopied: "LaTeX copied",
    allLatexCopied: "All LaTeX copied",
    clipboardBlocked: "Clipboard access was blocked",
    nothingToExport: "There are no equations to export",
    buildingWord: "Building Word…",
    wordFailed: "Word export failed",
    wordCreated: "Editable Word document created",
    fallbackImage: "Image Fallback",
    docStyle: "Document Style",
    styleAcademic: "Academic Textbook",
    styleResearch: "Research Paper",
    styleStandard: "Standard Editable Document",
    stylePreserve: "Preserve Original Layout",
    savedTo: "Saved to {{path}}",
    texTitle: "MathOCR equations",
    unsupportedFile: "{{name}}: unsupported file type",
    fileTooLarge: "{{name}}: file is larger than 25 MB",
    maximumFiles: "A maximum of {{count}} files is allowed",
    removeFile: "Remove file",
    pastedImage: "Pasted image added",
    recognitionFailed: "Recognition failed",
    recognitionHttpFailed: "Recognition failed (HTTP {{status}})",
    foundOne: "Found 1 equation",
    foundMany: "Found {{count}} equations",
    storageTitle: "Models on this computer",
    storageCopy: "Recognition models are downloaded once and stored locally. Delete them anytime to free disk space; they download again when needed.",
    storageTotal: "Total space used",
    storagePath: "Storage folder",
    storageNotInstalled: "not installed",
    storageEmpty: "not downloaded",
    storageReady: "ready",
    storageLoaded: "in memory",
    storageOptional: "optional · English documents",
    storageWeightsMissing: "installed · weights not downloaded",
    downloadModel: "Download",
    installingNougat: "Installing Nougat… downloads ~1.4 GB, several minutes",
    nougatReady: "Nougat is ready — select it in the document reader menu",
    nougatInstallFailed: "Nougat installation failed",
    nougatNeedsSource: "Available when running MathOCR from source",
    role_math: "math",
    role_text: "text",
    role_optional: "optional",
    downloadModels: "Download all models now",
    downloadingModels: "Downloading models… this can take several minutes",
    modelsReady: "Models are ready ({{size}})",
    modelsDownloadFailed: "Model download failed — check the connection",
    deleteAllModels: "Delete all models",
    deleteModel: "Delete",
    confirmDelete: "Click again to confirm",
    modelsDeleted: "Freed {{size}} of disk space",
    modelsDeleteFailed: "Some files could not be deleted — close the app and delete the folder manually",
    storageUnavailable: "Storage information needs the local engine.",
    privateTitle: "Private by design.",
    privateCopy: "Files are processed only by the MathOCR engine running on this computer and never leave it.",
    footerTagline: "Local mathematics recognition with editable output.",
    footerProject: "Project",
    footerSource: "Source code",
    footerDownloads: "Downloads",
    footerReportBug: "Report a bug",
    footerAuthor: "Author",
    footerGithub: "GitHub profile",
    footerDonate: "Support on PayPal ♥",
    footerLicense: "MIT License",
    footerMadeWith: "made for students, teachers, and researchers",
  },
  el: {
    pageTitle: "Qryptex | Έγγραφα & Μαθηματικά σε Word",
    brandBy: "Έγγραφα & Μαθηματικά σε Word",
    refreshPage: "Ανανέωση",
    updateTitle: "Διαθέσιμη νέα έκδοση",
    updateDetail: "Η έκδοση Qryptex {{latest}} είναι διαθέσιμη — έχετε την {{current}}.",
    updateNotes: "Σημειώσεις έκδοσης ↗",
    updateNow: "Ενημέρωση τώρα",
    updateDownload: "Λήψη ↗",
    updateStartedWin: "Ο εγκαταστάτης ξεκίνησε. Το Qryptex θα κλείσει τώρα για να ολοκληρωθεί η ενημέρωση.",
    updateStartedMac: "Η ενημέρωση κατέβηκε στον φάκελο Λήψεις. Σύρετε το Qryptex στις Εφαρμογές για να αντικαταστήσετε την παλιά έκδοση και ανοίξτε το ξανά.",
    updateFailed: "Η ενημέρωση δεν κατέβηκε — δοκιμάστε ξανά ή κατεβάστε την από το GitHub.",
    checkUpdates: "Έλεγχος για ενημερώσεις",
    checkingUpdates: "Έλεγχος για ενημερώσεις…",
    upToDate: "Έχετε την τελευταία έκδοση ({{version}}).",
    updateCheckFailed: "Δεν ήταν δυνατός ο έλεγχος ενημερώσεων — ελέγξτε τη σύνδεσή σας.",
    serviceChecking: "Έλεγχος μηχανής…",
    serviceReady: "Η τοπική μηχανή είναι έτοιμη",
    serviceNoPandoc: "OCR έτοιμο · λείπει το Pandoc",
    serviceOffline: "Μηχανή εκτός λειτουργίας",
    eyebrow: "ΤΟΠΙΚΗ ΑΝΑΓΝΩΡΙΣΗ ΕΓΓΡΑΦΩΝ & ΜΑΘΗΜΑΤΙΚΩΝ",
    introTitle: "Εικόνες και PDF σε επεξεργάσιμα έγγραφα Word.",
    introCopy: "Αφήστε ένα αρχείο, ελέγξτε το ανακατασκευασμένο έγγραφο και εξαγάγετε σε Word με φυσικές εξισώσεις. Όλα εκτελούνται τοπικά στον υπολογιστή σας.",
    engineBannerTitle: "Η τοπική μηχανή δεν εκτελείται.",
    engineBannerCopy: "Η αναγνώριση γίνεται στον υπολογιστή σας, οπότε η τοπική μηχανή πρέπει να εκτελείται.",
    engineBannerAction: "Κατεβάστε την εφαρμογή",
    dropFiles: "Σύρετε εδώ εικόνες ή PDF",
    browseFiles: "κλικ για επιλογή, ή επικόλληση στιγμιότυπου (Ctrl+V) · PNG, JPG, WEBP, TIFF, PDF",
    inputType: "Τι θέλετε να αναγνωρίσετε;",
    modeDocument: "Όλο το κείμενο + μαθηματικά (ολόκληρο έγγραφο)",
    modeMixed: "Μόνο τα μαθηματικά μέσα σε σελίδα με κείμενο",
    modeFormula: "Μόνο μία εξίσωση (κομμένη εικόνα)",
    mathEngine: "Μηχανή μαθηματικών",
    engineBest: "Διασταύρωση όλων των μηχανών (πιο αργό)",
    enginePix2text: "MFR-1.5 — γρήγορο (προτείνεται)",
    enginePix2tex: "pix2tex (LaTeX-OCR)",
    engineRapid: "RapidLaTeXOCR",
    docReader: "Ανάγνωση κειμένου (λειτουργία εγγράφου)",
    docLayout: "Ελληνικά + Αγγλικά (Tesseract)",
    docNougat: "Nougat — αγγλικές εργασίες",
    docNougatUnavailable: "Nougat — κατεβάστε το πρώτα πιο κάτω",
    pageLimit: "Όριο σελίδων PDF",
    recognize: "Αναγνώριση εγγράφου & μαθηματικών",
    engineAddress: "Για προχωρημένους: διεύθυνση μηχανής",
    checkConnection: "Έλεγχος σύνδεσης",
    connectionInitial: "Εκκινήστε την τοπική μηχανή για αναγνώριση και εξαγωγή Word.",
    filesStayLocal: "Τα αρχεία αποστέλλονται μόνο στην τοπική μηχανή αυτού του υπολογιστή.",
    installPandoc: "Το OCR λειτουργεί, αλλά για εξαγωγή Word απαιτείται το Pandoc.",
    startEngine: "Εκκινήστε την τοπική μηχανή για αναγνώριση και εξαγωγή Word.",
    readingMath: "Ανάγνωση εγγράφου & μαθηματικών…",
    processingNote: "Η πρώτη εκτέλεση φορτώνει το μοντέλο στη μνήμη και μπορεί να πάρει ένα-δύο λεπτά· οι επόμενες είναι πολύ πιο γρήγορες.",
    loadingModel: "Προετοιμασία πρώτης αναγνώρισης…",
    processingFirstRun: "Φόρτωση μοντέλων αν χρειάζεται · {{elapsed}}. Η πρώτη εκτέλεση μπορεί να πάρει ένα-δύο λεπτά.",
    processingElapsed: "Αναγνώριση εγγράφου · {{elapsed}}. Κρατήστε το παράθυρο ανοικτό όσο λειτουργεί.",
    processingStillWorking: "Η αναγνώριση συνεχίζεται · {{elapsed}}. Οι μεγάλες σελίδες και η διασταύρωση χρειάζονται περισσότερο χρόνο.",
    reconstructedDocument: "Ανακατασκευασμένο έγγραφο",
    documentHint: "Επεξεργαστείτε το κείμενο και τα μαθηματικά και εξαγάγετε όλο το έγγραφο σε Word.",
    copyDocument: "Αντιγραφή κειμένου",
    downloadDocWord: "Λήψη εγγράφου (Word)",
    editableDocument: "Επεξεργάσιμο κείμενο εγγράφου και LaTeX",
    documentCopied: "Το κείμενο του εγγράφου αντιγράφηκε",
    documentTitle: "Έγγραφο Qryptex",
    recognizedEquations: "Αναγνωρισμένες εξισώσεις",
    resultsOne: "Βρέθηκε 1 εξίσωση. Επεξεργαστείτε το LaTeX και η προεπισκόπηση ενημερώνεται άμεσα.",
    resultsMany: "Βρέθηκαν {{count}} εξισώσεις. Επεξεργαστείτε το LaTeX και η προεπισκόπηση ενημερώνεται άμεσα.",
    noEquationsDetected: "Δεν εντοπίστηκαν εξισώσεις. Δοκιμάστε καθαρότερη εικόνα ή τη λειτουργία «Μία εξίσωση».",
    reviewReminder: "Το OCR μπορεί να κάνει πειστικά λάθη — συγκρίνετε πάντα με το πρωτότυπο.",
    ensembleAdviceTitle: "Θέλετε μια δεύτερη γνώμη;",
    ensembleAdvice: "Αν το αποτέλεσμα δεν σας ικανοποιεί, επιλέξτε «Διασταύρωση όλων των μηχανών» και αναγνωρίστε ξανά το αρχείο.",
    copyAll: "Αντιγραφή όλου του LaTeX",
    downloadTex: "Λήψη .tex",
    downloadWord: "Λήψη Word",
    page: "Σελίδα",
    confidence: "βεβαιότητα",
    alternativeReadings: "Άλλες μηχανές διάβασαν:",
    editableLatex: "Επεξεργάσιμο LaTeX",
    renderedPreview: "Προεπισκόπηση εξίσωσης",
    copyLatex: "Αντιγραφή",
    remove: "Αφαίρεση",
    latexCopied: "Το LaTeX αντιγράφηκε",
    allLatexCopied: "Όλο το LaTeX αντιγράφηκε",
    clipboardBlocked: "Η πρόσβαση στο πρόχειρο αποκλείστηκε",
    nothingToExport: "Δεν υπάρχουν εξισώσεις για εξαγωγή",
    buildingWord: "Δημιουργία Word…",
    wordFailed: "Η εξαγωγή Word απέτυχε",
    wordCreated: "Το επεξεργάσιμο έγγραφο Word δημιουργήθηκε",
    fallbackImage: "Εφεδρική εικόνα",
    docStyle: "Στυλ εγγράφου",
    styleAcademic: "Ακαδημαϊκό σύγγραμμα",
    styleResearch: "Επιστημονικό άρθρο",
    styleStandard: "Τυπικό επεξεργάσιμο έγγραφο",
    stylePreserve: "Διατήρηση αρχικής διάταξης",
    savedTo: "Αποθηκεύτηκε στο {{path}}",
    texTitle: "Εξισώσεις MathOCR",
    unsupportedFile: "{{name}}: μη υποστηριζόμενος τύπος αρχείου",
    fileTooLarge: "{{name}}: το αρχείο ξεπερνά τα 25 MB",
    maximumFiles: "Επιτρέπονται έως {{count}} αρχεία",
    removeFile: "Αφαίρεση αρχείου",
    pastedImage: "Η επικολλημένη εικόνα προστέθηκε",
    recognitionFailed: "Η αναγνώριση απέτυχε",
    recognitionHttpFailed: "Η αναγνώριση απέτυχε (HTTP {{status}})",
    foundOne: "Βρέθηκε 1 εξίσωση",
    foundMany: "Βρέθηκαν {{count}} εξισώσεις",
    storageTitle: "Μοντέλα σε αυτόν τον υπολογιστή",
    storageCopy: "Τα μοντέλα αναγνώρισης κατεβαίνουν μία φορά και αποθηκεύονται τοπικά. Μπορείτε να τα διαγράψετε όποτε θέλετε για να ελευθερώσετε χώρο· θα κατέβουν ξανά όταν χρειαστούν.",
    storageTotal: "Συνολικός χώρος",
    storagePath: "Φάκελος αποθήκευσης",
    storageNotInstalled: "μη εγκατεστημένη",
    storageEmpty: "δεν έχει κατέβει",
    storageReady: "έτοιμο",
    storageLoaded: "στη μνήμη",
    storageOptional: "προαιρετικό · αγγλικά έγγραφα",
    storageWeightsMissing: "εγκατεστημένο · δεν έχουν κατέβει τα βάρη",
    downloadModel: "Λήψη",
    installingNougat: "Εγκατάσταση Nougat… κατεβάζει ~1,4 GB, μερικά λεπτά",
    nougatReady: "Το Nougat είναι έτοιμο — επιλέξτε το στο μενού ανάγνωσης εγγράφου",
    nougatInstallFailed: "Η εγκατάσταση του Nougat απέτυχε",
    nougatNeedsSource: "Διαθέσιμο όταν το MathOCR εκτελείται από τον πηγαίο κώδικα",
    role_math: "μαθηματικά",
    role_text: "κείμενο",
    role_optional: "προαιρετικό",
    downloadModels: "Λήψη όλων των μοντέλων τώρα",
    downloadingModels: "Λήψη μοντέλων… μπορεί να διαρκέσει αρκετά λεπτά",
    modelsReady: "Τα μοντέλα είναι έτοιμα ({{size}})",
    modelsDownloadFailed: "Η λήψη των μοντέλων απέτυχε — ελέγξτε τη σύνδεση",
    deleteAllModels: "Διαγραφή όλων των μοντέλων",
    deleteModel: "Διαγραφή",
    confirmDelete: "Πατήστε ξανά για επιβεβαίωση",
    modelsDeleted: "Ελευθερώθηκαν {{size}} χώρου",
    modelsDeleteFailed: "Κάποια αρχεία δεν διαγράφηκαν — κλείστε την εφαρμογή και διαγράψτε τον φάκελο χειροκίνητα",
    storageUnavailable: "Οι πληροφορίες αποθήκευσης απαιτούν την τοπική μηχανή.",
    privateTitle: "Σχεδιασμένο για ιδιωτικότητα.",
    privateCopy: "Τα αρχεία επεξεργάζονται μόνο από τη μηχανή MathOCR αυτού του υπολογιστή και δεν φεύγουν ποτέ από αυτόν.",
    footerTagline: "Τοπική αναγνώριση μαθηματικών με επεξεργάσιμο αποτέλεσμα.",
    footerProject: "Έργο",
    footerSource: "Πηγαίος κώδικας",
    footerDownloads: "Λήψεις",
    footerReportBug: "Αναφορά σφάλματος",
    footerAuthor: "Δημιουργός",
    footerGithub: "Προφίλ GitHub",
    footerDonate: "Υποστήριξη μέσω PayPal ♥",
    footerLicense: "Άδεια MIT",
    footerMadeWith: "φτιαγμένο για μαθητές, εκπαιδευτικούς και ερευνητές",
  },
};

const params = new URLSearchParams(window.location.search);
const isDesktop = params.get("desktop") === "1";
const savedLanguage = localStorage.getItem("mathocr-language");
const initialLanguage = savedLanguage || (navigator.language.toLowerCase().startsWith("el") ? "el" : "en");

const state = {
  files: [],
  results: [],
  documents: [],
  online: false,
  pandoc: false,
  textAvailable: false,
  nougatAvailable: false,
  nougatReady: false,
  nougatInstallable: false,
  busy: false,
  recognitionStartedAt: null,
  recognitionTimer: null,
  hasCompletedRecognition: false,
  language: initialLanguage,
  storage: null,
  update: null,
};

function t(key, variables = {}) {
  const template = translations[state.language][key] || translations.en[key] || key;
  return Object.entries(variables).reduce(
    (value, [name, replacement]) => value.replaceAll(`{{${name}}}`, String(replacement)),
    template,
  );
}

const elements = {};
for (const id of [
  "apiUrl", "connectionHelp", "copyAllButton", "copyDocButton", "deleteAllModelsButton",
  "downloadModelsButton", "downloadDocWordButton", "downloadTexButton", "downloadWordButton",
  "docTemplate",
  "dropZone", "engineBanner", "engineBannerLink", "advancedSettings", "docEngine", "docEngineField",
  "documentList", "documentSection", "ensembleAdvice", "fileInput", "fileList", "footerVersion", "mathEngine",
  "pageLimit", "progressPanel", "recognitionMode", "recognizeButton", "recheckButton", "refreshPageButton",
  "progressTitle", "processingNote", "resultList", "resultsSection", "resultsSummary", "servicePill", "serviceText", "storageList",
  "storagePathValue", "storageSection", "storageTotalBytes", "toast",
  "updateBanner", "updateButton", "updateDetail", "updateNotesLink", "checkUpdatesButton",
]) {
  elements[id] = document.querySelector(`#${id}`);
}

/* ---------- language ---------- */

function applyLanguage(language) {
  state.language = language === "el" ? "el" : "en";
  localStorage.setItem("mathocr-language", state.language);
  document.documentElement.lang = state.language;
  document.title = t("pageTitle");
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    element.textContent = t(element.dataset.i18n);
  });
  document.querySelectorAll("[data-language]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.language === state.language));
  });
  updateServiceCopy();
  updateModeOptions();
  renderFiles();
  renderStorage();
  renderUpdateBanner();
  if (elements.documentSection && !elements.documentSection.hidden) renderDocuments();
  if (elements.resultsSection && !elements.resultsSection.hidden) renderResults(false);
  if (state.busy) updateRecognitionProgress();
}

/* ---------- helpers ---------- */

function normalizedApiUrl() {
  return elements.apiUrl.value.trim().replace(/\/+$/, "");
}

function humanBytes(bytes) {
  if (!bytes) return "0 MB";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(0)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

let toastTimer;
function showToast(message) {
  clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.add("visible");
  toastTimer = setTimeout(() => elements.toast.classList.remove("visible"), 3200);
}

function updateControls() {
  elements.recognizeButton.disabled = !state.online || !state.files.length || state.busy;
  elements.fileInput.disabled = state.busy;
  elements.apiUrl.disabled = state.busy;
}

function formatElapsed(seconds) {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

function updateRecognitionProgress() {
  if (state.recognitionStartedAt == null) return;
  const elapsedSeconds = Math.floor((Date.now() - state.recognitionStartedAt) / 1000);
  const elapsed = formatElapsed(Math.max(0, elapsedSeconds));

  if (!state.hasCompletedRecognition) {
    elements.progressTitle.textContent = t("loadingModel");
    elements.processingNote.textContent = t("processingFirstRun", { elapsed });
  } else if (elapsedSeconds >= 45) {
    elements.progressTitle.textContent = t("readingMath");
    elements.processingNote.textContent = t("processingStillWorking", { elapsed });
  } else {
    elements.progressTitle.textContent = t("readingMath");
    elements.processingNote.textContent = t("processingElapsed", { elapsed });
  }
}

function startRecognitionProgress() {
  stopRecognitionProgress();
  state.recognitionStartedAt = Date.now();
  updateRecognitionProgress();
  state.recognitionTimer = setInterval(updateRecognitionProgress, 1000);
}

function stopRecognitionProgress() {
  if (state.recognitionTimer != null) clearInterval(state.recognitionTimer);
  state.recognitionTimer = null;
  state.recognitionStartedAt = null;
}

/* ---------- engine status ---------- */

function updateServiceCopy() {
  if (state.online) {
    elements.serviceText.textContent = state.pandoc ? t("serviceReady") : t("serviceNoPandoc");
    elements.connectionHelp.textContent = state.pandoc ? t("filesStayLocal") : t("installPandoc");
  } else {
    elements.serviceText.textContent = t("serviceOffline");
    elements.connectionHelp.textContent = t("startEngine");
  }
  elements.engineBanner.hidden = state.online || isDesktop;
}

async function checkService() {
  elements.servicePill.className = "service-pill";
  elements.serviceText.textContent = t("serviceChecking");
  try {
    const response = await fetch(`${normalizedApiUrl()}/api/health`, { signal: AbortSignal.timeout(2800) });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const health = await response.json();
    state.online = true;
    state.pandoc = Boolean(health.pandoc);
    state.textAvailable = Boolean(health.text_available);
    state.nougatAvailable = Boolean(health.nougat_available);
    state.nougatReady = Boolean(health.nougat_ready);
    state.nougatInstallable = Boolean(health.nougat_installable);
    elements.servicePill.classList.add("online");
    refreshStorage();
    checkUpdate(); // non-blocking: reveal the banner if a newer release exists
  } catch (_error) {
    state.online = false;
    state.pandoc = false;
    state.textAvailable = false;
    state.nougatAvailable = false;
    state.nougatReady = false;
    state.nougatInstallable = false;
    state.storage = null;
    elements.servicePill.classList.add("offline");
    renderStorage();
  }
  updateServiceCopy();
  updateModeOptions();
  updateControls();
}

/* ---------- in-app updates ---------- */

async function checkUpdate(manual = false) {
  // ``manual`` = triggered by the button, so we give explicit feedback (a
  // "you're up to date" toast). The automatic startup check stays silent.
  if (manual) showToast(t("checkingUpdates"));
  try {
    const response = await fetch(`${normalizedApiUrl()}/api/update/check`, {
      signal: AbortSignal.timeout(9000),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.update = await response.json();
  } catch (_error) {
    if (manual) showToast(t("updateCheckFailed"));
    return; // never let an update check disrupt normal use
  }
  renderUpdateBanner();
  if (manual && !(state.update && state.update.update_available)) {
    showToast(t("upToDate", { version: state.update ? state.update.current : "" }));
  }
}

function renderUpdateBanner() {
  const info = state.update;
  if (!info || !info.update_available) {
    elements.updateBanner.hidden = true;
    return;
  }
  elements.updateBanner.hidden = false;
  elements.updateDetail.textContent = t("updateDetail", {
    latest: info.latest,
    current: info.current,
  });
  elements.updateNotesLink.href = info.notes_url || "#";
  // In the packaged app the button installs in place; from source (or a browser)
  // it becomes a plain link to the releases page.
  elements.updateButton.textContent = info.can_install ? t("updateNow") : t("updateDownload");
}

async function installUpdate() {
  const info = state.update || {};
  if (!info.can_install) {
    window.open(info.notes_url || "https://github.com/ChristosBouronikos/MathOCR/releases/latest", "_blank");
    return;
  }
  elements.updateButton.disabled = true;
  elements.updateButton.textContent = t("downloadingModels");
  try {
    const response = await fetch(`${normalizedApiUrl()}/api/update/install`, { method: "POST" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || t("updateFailed"));
    const message = payload.platform === "darwin" ? t("updateStartedMac") : t("updateStartedWin");
    elements.updateDetail.textContent = message;
    elements.updateButton.hidden = true;
    showToast(message);
  } catch (error) {
    showToast(error.message || t("updateFailed"));
    elements.updateButton.disabled = false;
    elements.updateButton.textContent = t("updateNow");
  }
}

/* ---------- mode + engine options ---------- */

function updateModeOptions() {
  const isDocument = elements.recognitionMode.value === "document";
  elements.docEngineField.hidden = !isDocument;
  // Nougat is selectable only once it is fully downloaded and ready.
  const nougatOption = elements.docEngine.querySelector('option[value="nougat"]');
  if (nougatOption) {
    nougatOption.disabled = !state.nougatReady;
    nougatOption.textContent = state.nougatReady ? t("docNougat") : t("docNougatUnavailable");
    if (!state.nougatReady && elements.docEngine.value === "nougat") {
      elements.docEngine.value = "layout";
    }
  }
}

/* ---------- file selection ---------- */

function addFiles(fileList) {
  const incoming = Array.from(fileList);
  const accepted = [];
  for (const file of incoming) {
    const extension = (file.name.split(".").pop() || "").toLowerCase();
    const allowed = ["pdf", "png", "jpg", "jpeg", "webp", "tif", "tiff"].includes(extension);
    if (!allowed) {
      showToast(t("unsupportedFile", { name: file.name }));
    } else if (file.size > MAX_FILE_BYTES) {
      showToast(t("fileTooLarge", { name: file.name }));
    } else {
      accepted.push(file);
    }
  }
  if (state.files.length + accepted.length > MAX_FILES) showToast(t("maximumFiles", { count: MAX_FILES }));
  state.files = [...state.files, ...accepted].slice(0, MAX_FILES);
  renderFiles();
  updateControls();
}

function renderFiles() {
  elements.fileList.replaceChildren();
  state.files.forEach((file, index) => {
    const row = document.createElement("div");
    row.className = "file-item";
    row.innerHTML = '<span class="file-type"></span><span class="file-name"></span><span class="file-size"></span><button type="button">×</button>';
    row.querySelector(".file-type").textContent = (file.name.split(".").pop() || "?").toUpperCase();
    row.querySelector(".file-name").textContent = file.name;
    row.querySelector(".file-size").textContent = humanBytes(file.size);
    const removeButton = row.querySelector("button");
    removeButton.setAttribute("aria-label", t("removeFile"));
    removeButton.addEventListener("click", () => {
      state.files.splice(index, 1);
      renderFiles();
      updateControls();
    });
    elements.fileList.append(row);
  });
}

/* ---------- recognition ---------- */

async function recognize() {
  if (!state.files.length || !state.online || state.busy) return;
  state.busy = true;
  updateControls();
  elements.progressPanel.hidden = false;
  startRecognitionProgress();
  elements.progressPanel.scrollIntoView({ behavior: "smooth", block: "center" });

  const body = new FormData();
  state.files.forEach((file) => body.append("files", file, file.name));
  body.append("mode", elements.recognitionMode.value);
  body.append("engine", elements.mathEngine.value);
  body.append("doc_engine", elements.docEngine.value);
  body.append("max_pdf_pages", elements.pageLimit.value);

  try {
    const response = await fetch(`${normalizedApiUrl()}/api/ocr`, { method: "POST", body });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || t("recognitionHttpFailed", { status: response.status }));
    state.results = payload.results || [];
    state.documents = payload.documents || [];
    if (!state.documents.length && state.results.length) {
      const mathMarkdown = state.results.map((r) => `$$\n${r.latex}\n$$`).join("\n\n");
      state.documents = [{
        source: state.results[0]?.source || "Equations",
        markdown: mathMarkdown,
      }];
    }
    state.hasCompletedRecognition = true;
    renderDocuments();
    if (elements.resultsSection) {
      renderResults();
    }
    (payload.warnings || []).forEach((warning) => showToast(warning));
    if (!payload.warnings || !payload.warnings.length) {
      showToast(state.results.length === 1 ? t("foundOne") : t("foundMany", { count: state.results.length }));
    }
    refreshStorage(); // sizes change after a first-run model download
  } catch (error) {
    showToast(error.message || t("recognitionFailed"));
  } finally {
    state.busy = false;
    stopRecognitionProgress();
    elements.progressPanel.hidden = true;
    updateControls();
  }
}

function renderMath(latex, target) {
  target.textContent = latex;
  if (window.katex) {
    try {
      window.katex.render(latex, target, { displayMode: true, throwOnError: false, strict: "ignore" });
    } catch (_error) {
      target.textContent = latex;
    }
  }
}

function confidenceChip(confidence) {
  if (confidence == null) return null;
  const chip = document.createElement("span");
  const percent = Math.round(confidence * 100);
  chip.className = `confidence-chip ${percent >= 75 ? "high" : percent >= 45 ? "medium" : "low"}`;
  chip.textContent = `${percent}% ${t("confidence")}`;
  return chip;
}

function renderResults(shouldScroll = true) {
  if (!elements.resultsSection || !elements.resultList) return;
  elements.resultList.replaceChildren();
  elements.resultsSection.hidden = false;
  if (elements.ensembleAdvice) elements.ensembleAdvice.hidden = !state.results.length;
  if (elements.resultsSummary) {
    elements.resultsSummary.textContent = state.results.length
      ? `${state.results.length === 1 ? t("resultsOne") : t("resultsMany", { count: state.results.length })} ${t("reviewReminder")}`
      : t("noEquationsDetected");
  }

  state.results.forEach((result, index) => {
    const card = document.createElement("article");
    card.className = "result-card";
    card.innerHTML = `
      <div class="result-source">
        <span class="result-origin"></span>
        <span class="result-badges"></span>
      </div>
      <div class="result-preview"></div>
      <div class="result-editor">
        <textarea spellcheck="false"></textarea>
        <div class="result-alternatives" hidden><span></span></div>
        <div class="result-actions">
          <button class="mini-button copy" type="button"></button>
          <button class="mini-button danger" type="button"></button>
        </div>
      </div>`;

    card.querySelector(".result-origin").textContent =
      result.page ? `${result.source} · ${t("page")} ${result.page}` : result.source;

    const badges = card.querySelector(".result-badges");
    const engineBadge = document.createElement("span");
    engineBadge.className = "engine-badge";
    engineBadge.textContent = ENGINE_SHORT_NAMES[result.engine] || result.engine;
    badges.append(engineBadge);
    const chip = confidenceChip(result.confidence);
    if (chip) badges.append(chip);
    if (result.fallback_image || (result.confidence != null && result.confidence < 0.8)) {
      const fallbackBadge = document.createElement("span");
      fallbackBadge.className = "confidence-chip low";
      fallbackBadge.textContent = t("fallbackImage") || "Image Fallback";
      badges.append(fallbackBadge);
    }

    const preview = card.querySelector(".result-preview");
    const textarea = card.querySelector("textarea");
    preview.setAttribute("aria-label", t("renderedPreview"));
    textarea.setAttribute("aria-label", t("editableLatex"));
    textarea.value = result.latex;
    renderMath(result.latex, preview);

    const alternativesRow = card.querySelector(".result-alternatives");
    if (result.alternatives && result.alternatives.length) {
      alternativesRow.hidden = false;
      alternativesRow.querySelector("span").textContent = t("alternativeReadings");
      for (const alternative of result.alternatives) {
        const chipButton = document.createElement("button");
        chipButton.type = "button";
        chipButton.className = "alternative-chip";
        chipButton.textContent = ENGINE_SHORT_NAMES[alternative.engine] || alternative.engine;
        chipButton.title = alternative.latex;
        chipButton.addEventListener("click", () => {
          // Swap: the current reading becomes the alternative.
          const previous = { engine: result.engine, latex: textarea.value.trim() };
          result.latex = alternative.latex;
          result.engine = alternative.engine;
          const position = result.alternatives.indexOf(alternative);
          result.alternatives.splice(position, 1, previous);
          renderResults(false);
        });
        alternativesRow.append(chipButton);
      }
    }

    textarea.addEventListener("input", () => {
      state.results[index].latex = textarea.value.trim();
      renderMath(textarea.value, preview);
    });
    const copyButton = card.querySelector(".copy");
    copyButton.textContent = t("copyLatex");
    copyButton.addEventListener("click", () => copyText(textarea.value, t("latexCopied")));
    const removeButton = card.querySelector(".danger");
    removeButton.textContent = t("remove");
    removeButton.addEventListener("click", () => {
      state.results.splice(index, 1);
      renderResults(false);
    });
    elements.resultList.append(card);
  });
  if (shouldScroll) elements.resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ---------- document reconstruction view ---------- */

// Render Markdown (paragraphs + tables + headings + $inline$ / $$display$$ math)
function _renderInlineContent(text, container) {
  const parts = text.split(/(\$[^$]+\$)/);
  for (const part of parts) {
    const inline = part.match(/^\$([^$]+)\$$/);
    if (inline && window.katex) {
      const span = document.createElement("span");
      try {
        window.katex.render(inline[1], span, { displayMode: false, throwOnError: false, strict: "ignore" });
      } catch (_error) {
        span.textContent = part;
      }
      container.append(span);
    } else if (part) {
      container.append(document.createTextNode(part));
    }
  }
}

// Minimal, safe Markdown renderer: turns headings, equations, tables, and paragraphs
// into an element. No external Markdown library is needed for this preview.
function renderMarkdownPreview(markdown, target) {
  target.replaceChildren();
  const blocks = markdown.split(/\n{2,}/);
  for (const block of blocks) {
    let trimmed = block.trim();
    if (!trimmed) continue;

    // Check alignment tag: <p align="center">...</p>, <center>...</center>, ->...<-
    let blockAlign = null;
    const alignMatch = trimmed.match(/^<(?:p\s+align=["'](center|right|justify)["']|center)>([\s\S]*?)(?:<\/(?:p|center)>)?$/i);
    if (alignMatch) {
      blockAlign = alignMatch[1] ? alignMatch[1].toLowerCase() : "center";
      trimmed = alignMatch[2].trim();
    } else if (trimmed.startsWith("->") && trimmed.endsWith("<-") && trimmed.length > 4) {
      blockAlign = "center";
      trimmed = trimmed.slice(2, -2).trim();
    } else if (trimmed.startsWith("->") && trimmed.length > 2) {
      blockAlign = "right";
      trimmed = trimmed.slice(2).trim();
    }

    // Headings
    const headingMatch = trimmed.match(/^(#{1,6})\s+(.*)$/);
    if (headingMatch) {
      const hLevel = headingMatch[1].length;
      const hElem = document.createElement(`h${Math.min(hLevel + 1, 6)}`);
      let hText = headingMatch[2].trim();
      const innerAlign = hText.match(/^<(?:p\s+align=["'](center|right|justify)["']|center)>([\s\S]*?)(?:<\/(?:p|center)>)?$/i);
      if (innerAlign) {
        blockAlign = innerAlign[1] ? innerAlign[1].toLowerCase() : "center";
        hText = innerAlign[2].trim();
      }
      _renderInlineContent(hText, hElem);
      if (blockAlign) {
        hElem.style.textAlign = blockAlign;
      }
      target.append(hElem);
      continue;
    }

    // Display math
    const displayMatch = trimmed.match(/^\$\$([\s\S]+?)\$\$(?:\s*\{#eq:(\d{1,3})\})?$/);
    if (displayMatch && window.katex) {
      const wrapper = document.createElement("div");
      wrapper.className = "doc-math";
      try {
        window.katex.render(displayMatch[1].trim(), wrapper, { displayMode: true, throwOnError: false, strict: "ignore" });
      } catch (_error) {
        wrapper.textContent = trimmed;
      }
      if (displayMatch[2]) {
        const number = document.createElement("span");
        number.className = "doc-equation-number";
        number.textContent = `(${displayMatch[2]})`;
        number.style.float = "right";
        wrapper.append(number);
      }
      target.append(wrapper);
      continue;
    }

    // Bullet lists
    if (/^[-*+]\s+/.test(trimmed)) {
      const ul = document.createElement("ul");
      trimmed.split("\n").forEach((itemLine) => {
        const itemTrim = itemLine.trim();
        if (/^[-*+]\s+/.test(itemTrim)) {
          const li = document.createElement("li");
          _renderInlineContent(itemTrim.replace(/^[-*+]\s+/, ""), li);
          ul.append(li);
        }
      });
      target.append(ul);
      continue;
    }

    // Tables
    if (trimmed.includes("|") && trimmed.split("\n").length >= 2) {
      const lines = trimmed.split("\n").map((l) => l.trim()).filter(Boolean);
      if (lines.every((l) => l.includes("|"))) {
        const table = document.createElement("table");
        table.className = "preview-table";
        const tbody = document.createElement("tbody");
        lines.forEach((line, idx) => {
          if (/^\|?[\s:-|-]+\|?$/.test(line) && line.includes("-")) return;
          const tr = document.createElement("tr");
          let cleanLine = line;
          if (cleanLine.startsWith("|")) cleanLine = cleanLine.slice(1);
          if (cleanLine.endsWith("|")) cleanLine = cleanLine.slice(0, -1);
          const cells = cleanLine.split("|");
          cells.forEach((cell) => {
            const cellElem = document.createElement(idx === 0 ? "th" : "td");
            _renderInlineContent(cell.trim(), cellElem);
            tr.append(cellElem);
          });
          tbody.append(tr);
        });
        table.append(tbody);
        target.append(table);
        continue;
      }
    }

    // Images / Figures
    const imgMatch = trimmed.match(/^!\[(.*?)\]\((.*?)\)$/);
    if (imgMatch) {
      const figure = document.createElement("figure");
      figure.className = "preview-figure";
      if (blockAlign) figure.style.textAlign = blockAlign;
      const img = document.createElement("img");
      const src = imgMatch[2].trim();
      if (src.startsWith("asset:")) {
        img.src = `${normalizedApiUrl()}/api/assets/${src.slice(6)}`;
      } else if (/^[0-9a-fA-F]{16,64}$/.test(src)) {
        img.src = `${normalizedApiUrl()}/api/assets/${src}`;
      } else {
        img.src = src;
      }
      img.alt = imgMatch[1].trim() || "Figure";
      img.style.maxWidth = "100%";
      img.style.height = "auto";
      img.style.borderRadius = "4px";
      img.style.display = "block";
      img.style.margin = blockAlign === "center" ? "0 auto" : (blockAlign === "right" ? "0 0 0 auto" : "0");
      figure.append(img);
      if (imgMatch[1].trim()) {
        const figcap = document.createElement("figcaption");
        figcap.style.fontSize = "0.85rem";
        figcap.style.color = "var(--text-muted, #666)";
        figcap.style.marginTop = "4px";
        figcap.style.fontStyle = "italic";
        figcap.textContent = imgMatch[1].trim();
        figure.append(figcap);
      }
      target.append(figure);
      continue;
    }

    const paragraph = document.createElement("p");
    if (blockAlign) {
      paragraph.style.textAlign = blockAlign;
    }
    _renderInlineContent(trimmed, paragraph);
    target.append(paragraph);
  }
}

function renderDocuments() {
  const list = elements.documentList;
  list.replaceChildren();
  elements.documentSection.hidden = !state.documents.length;
  if (!state.documents.length) return;

  state.documents.forEach((doc, index) => {
    const card = document.createElement("article");
    card.className = "document-card";
    card.innerHTML = `
      <div class="document-source"></div>
      <div class="document-grid">
        <textarea class="document-editor" spellcheck="false"></textarea>
        <div class="document-preview"></div>
      </div>`;
    card.querySelector(".document-source").textContent =
      doc.page ? `${doc.source} · ${t("page")} ${doc.page}` : doc.source;
    const editor = card.querySelector(".document-editor");
    const preview = card.querySelector(".document-preview");
    editor.setAttribute("aria-label", t("editableDocument"));
    editor.value = doc.markdown;
    renderMarkdownPreview(doc.markdown, preview);
    editor.addEventListener("input", () => {
      state.documents[index].markdown = editor.value;
      renderMarkdownPreview(editor.value, preview);
    });
    list.append(card);
  });
  elements.documentSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

function documentMarkdown() {
  const editors = document.querySelectorAll(".document-editor");
  if (editors.length) {
    return Array.from(editors).map((el) => el.value.trim()).filter(Boolean).join("\n\n---\n\n");
  }
  return state.documents.map((doc) => doc.markdown.trim()).filter(Boolean).join("\n\n---\n\n");
}

async function triggerDocxDownload(body, defaultFilename) {
  const saveToDownloads = isDesktop;
  const response = await fetch(`${normalizedApiUrl()}/api/export/docx`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, save_to_downloads: saveToDownloads }),
  });

  const contentType = (response.headers.get("content-type") || "").toLowerCase();

  if (!response.ok) {
    let errorDetail = "";
    if (contentType.includes("application/json")) {
      const errJson = await response.json().catch(() => ({}));
      errorDetail = errJson.detail || "";
    } else {
      errorDetail = await response.text().catch(() => "");
    }
    throw new Error(errorDetail || t("wordFailed"));
  }

  // Desktop save to local Downloads folder
  if (contentType.includes("application/json")) {
    const payload = await response.json();
    savedToast(payload);
    return;
  }

  // Browser download: binary DOCX stream
  const blob = await response.blob();
  let filename = defaultFilename || "Qryptex Document.docx";
  const disposition = response.headers.get("content-disposition");
  if (disposition) {
    const matchUtf8 = disposition.match(/filename\*=utf-8''([^;\r\n]+)/i);
    if (matchUtf8) {
      try {
        filename = decodeURIComponent(matchUtf8[1]);
      } catch (_) {
        filename = matchUtf8[1];
      }
    } else {
      const matchPlain = disposition.match(/filename="?([^";\r\n]+)"?/i);
      if (matchPlain) {
        filename = matchPlain[1];
      }
    }
  }

  const blobUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  setTimeout(() => URL.revokeObjectURL(blobUrl), 1500);

  const warningsHeader = response.headers.get("x-export-warnings");
  let warnings = [];
  if (warningsHeader) {
    try {
      warnings = JSON.parse(warningsHeader);
    } catch (_) {}
  }

  const exportSummary = warnings.find((w) => typeof w === "string" && w.startsWith("Export summary:"));
  if (exportSummary) {
    showToast(`${t("wordCreated")} (${exportSummary.replace("Export summary: ", "")})`);
  } else if (warnings && warnings.length > 0) {
    showToast(`${t("wordCreated")} (${warnings.length} warning(s))`);
  } else {
    showToast(t("wordCreated"));
  }
}

async function downloadDocumentWord() {
  const markdown = documentMarkdown();
  if (!markdown) return showToast(t("nothingToExport"));
  const button = elements.downloadDocWordButton;
  const label = button.textContent;
  button.disabled = true;
  button.textContent = t("buildingWord");
  try {
    const template = elements.docTemplate ? elements.docTemplate.value : "academic_textbook";
    let combinedDocument = null;
    let sourceTitle = "";
    if (state.documents && state.documents.length > 0) {
      const allElements = [];
      const allMetadata = {};
      state.documents.forEach((d) => {
        if (d.document && Array.isArray(d.document.elements)) {
          allElements.push(...d.document.elements);
          if (d.document.metadata) Object.assign(allMetadata, d.document.metadata);
          if (!sourceTitle && typeof d.document.title === "string" && d.document.title.trim()) {
            sourceTitle = d.document.title.trim();
          }
        }
      });
      if (allElements.length > 0) {
        combinedDocument = {
          // An absent source title must remain absent; inventing a product
          // title changes the reconstructed document itself.
          title: sourceTitle,
          elements: allElements,
          metadata: allMetadata,
        };
      }
    }
    await triggerDocxDownload(
      {
        title: sourceTitle,
        markdown,
        document: combinedDocument,
        template,
        equation_image_fallback_threshold: 0.8,
      },
      `Qryptex Document.docx`
    );
  } catch (error) {
    showToast(error.message || t("wordFailed"));
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

/* ---------- export ---------- */

async function copyText(value, successMessage) {
  try {
    await navigator.clipboard.writeText(value);
    showToast(successMessage);
  } catch (_error) {
    showToast(t("clipboardBlocked"));
  }
}

function activeLatex() {
  return state.results.map((result) => result.latex.trim()).filter(Boolean);
}

// Report where a saved file landed. The backend returns an absolute path; we
// show the folder + filename so the user knows it went to Downloads.
function savedToast(payload) {
  const path = payload && payload.path ? payload.path : "";
  const warnings = (payload && Array.isArray(payload.warnings)) ? payload.warnings : [];
  const exportSummary = warnings.find((w) => typeof w === "string" && w.startsWith("Export summary:"));
  const summaryText = exportSummary ? exportSummary.replace("Export summary: ", "") : null;
  if (summaryText) {
    showToast(path ? `${t("savedTo", { path })} (${summaryText})` : `${t("wordCreated")} (${summaryText})`);
  } else if (warnings.length > 0) {
    showToast(path ? `${t("savedTo", { path })} (${warnings.length} equation warning(s))` : t("wordCreated"));
  } else {
    showToast(path ? t("savedTo", { path }) : t("wordCreated"));
  }
}

async function downloadTex() {
  const equations = activeLatex();
  if (!equations.length) return showToast(t("nothingToExport"));
  const body = equations.map((latex) => `\\[\n${latex}\n\\]`).join("\n\n");
  const tex = `% MathOCR export by Bouronikos Christos <chrisbouronikos@gmail.com>.\n% Support: https://paypal.me/christosbouronikos\n\\documentclass{article}\n\\usepackage{amsmath,amssymb}\n\\begin{document}\n${body}\n\\end{document}\n`;
  try {
    const response = await fetch(`${normalizedApiUrl()}/api/export/text`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: t("texTitle"), extension: "tex", content: tex }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || t("wordFailed"));
    savedToast(payload);
  } catch (error) {
    showToast(error.message || t("wordFailed"));
  }
}

async function downloadWord() {
  const equations = activeLatex();
  if (!equations.length) return showToast(t("nothingToExport"));
  const buttonText = elements.downloadWordButton.textContent;
  elements.downloadWordButton.disabled = true;
  elements.downloadWordButton.textContent = t("buildingWord");
  try {
    const template = elements.docTemplate ? elements.docTemplate.value : "academic_textbook";
    const docElements = (state.results || []).map((r) => ({
      type: "display_equation",
      latex: r.latex,
      confidence: r.confidence,
      asset_id: r.asset_id,
      fallback_image: Boolean(r.fallback_image),
      box: r.region,
    }));
    await triggerDocxDownload(
      {
        title: t("texTitle"),
        equations,
        document: { title: t("texTitle"), elements: docElements },
        template,
        equation_image_fallback_threshold: 0.8,
      },
      `MathOCR equations by Bouronikos Christos.docx`
    );
  } catch (error) {
    showToast(error.message || t("wordFailed"));
  } finally {
    elements.downloadWordButton.disabled = false;
    elements.downloadWordButton.textContent = buttonText;
  }
}

/* ---------- model storage ---------- */

async function refreshStorage() {
  if (!state.online) return renderStorage();
  try {
    const response = await fetch(`${normalizedApiUrl()}/api/models`, { signal: AbortSignal.timeout(8000) });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.storage = await response.json();
  } catch (_error) {
    state.storage = null;
  }
  renderStorage();
}

function renderStorage() {
  const list = elements.storageList;
  list.replaceChildren();
  if (!state.storage) {
    elements.storageTotalBytes.textContent = "—";
    elements.storagePathValue.textContent = "—";
    const note = document.createElement("p");
    note.className = "storage-note";
    note.textContent = t("storageUnavailable");
    list.append(note);
    elements.downloadModelsButton.disabled = true;
    elements.deleteAllModelsButton.disabled = true;
    return;
  }

  elements.storageTotalBytes.textContent = humanBytes(state.storage.total_bytes);
  elements.storagePathValue.textContent = state.storage.cache_root;
  elements.downloadModelsButton.disabled = state.busy;
  elements.deleteAllModelsButton.disabled = state.busy || !state.storage.total_bytes;

  for (const engine of state.storage.engines) {
    const row = document.createElement("div");
    row.className = "storage-row";
    row.innerHTML = `
      <div class="storage-name"><strong></strong><span class="storage-role"></span><span class="storage-status"></span></div>
      <span class="storage-size"></span>
      <span class="storage-action"></span>`;
    row.querySelector("strong").textContent = engine.label;
    const roleTag = row.querySelector(".storage-role");
    roleTag.textContent = t(`role_${engine.role}`);
    roleTag.classList.add(`role-${engine.role}`);
    const status = row.querySelector(".storage-status");
    const action = row.querySelector(".storage-action");

    // Nougat needs its optional package installed first; every other engine
    // is bundled with the app and can be fetched directly.
    if (engine.id === "nougat" && !engine.ready) {
      status.textContent = engine.installed ? t("storageWeightsMissing") : t("storageOptional");
      row.querySelector(".storage-size").textContent = "—";
      const installButton = document.createElement("button");
      installButton.type = "button";
      installButton.className = "mini-button install";
      installButton.textContent = t("downloadModel");
      installButton.disabled = !state.nougatInstallable && !engine.installed;
      if (installButton.disabled) installButton.title = t("nougatNeedsSource");
      installButton.addEventListener("click", installNougat);
      action.append(installButton);
      list.append(row);
      continue;
    }

    if (engine.loaded) status.textContent = t("storageLoaded");
    else if (engine.ready && !engine.bytes) status.textContent = t("storageReady");
    else if (!engine.installed) status.textContent = t("storageNotInstalled");
    else if (!engine.bytes) status.textContent = t("storageEmpty");
    row.querySelector(".storage-size").textContent = engine.bytes ? humanBytes(engine.bytes) : "—";

    const downloadButton = document.createElement("button");
    downloadButton.type = "button";
    downloadButton.className = "mini-button install";
    downloadButton.textContent = t("downloadModel");
    downloadButton.disabled = state.busy || !engine.ready;
    if (!engine.ready) downloadButton.title = t("storageNotInstalled");
    downloadButton.addEventListener("click", () => downloadEngine(engine.id, downloadButton));
    action.append(downloadButton);

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "mini-button danger";
    deleteButton.textContent = t("deleteModel");
    deleteButton.disabled = !engine.bytes;
    armConfirm(deleteButton, () => deleteModels(engine.id === "pix2text-mfr" ? "pix2text" : engine.id));
    action.append(deleteButton);
    list.append(row);
  }
}

async function installNougat() {
  showToast(t("installingNougat"));
  try {
    const response = await fetch(`${normalizedApiUrl()}/api/models/nougat/install`, { method: "POST" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || t("nougatInstallFailed"));
    await checkService(); // refresh readiness so the dropdown enables Nougat
    showToast(state.nougatReady ? t("nougatReady") : t("nougatInstallFailed"));
  } catch (error) {
    showToast(error.message || t("nougatInstallFailed"));
  }
}

/**
 * Two-step inline confirmation: first click arms the button, second click
 * within four seconds executes. Native confirm() dialogs are unreliable
 * inside the desktop webview.
 */
function armConfirm(button, action) {
  let armed = false;
  let timer;
  const original = () => (button.dataset.originalText = button.dataset.originalText || button.textContent);
  button.addEventListener("click", () => {
    if (!armed) {
      original();
      armed = true;
      button.classList.add("armed");
      button.textContent = t("confirmDelete");
      timer = setTimeout(() => {
        armed = false;
        button.classList.remove("armed");
        button.textContent = button.dataset.originalText;
      }, 4000);
    } else {
      clearTimeout(timer);
      armed = false;
      button.classList.remove("armed");
      button.textContent = button.dataset.originalText;
      action();
    }
  });
}

async function deleteModels(engineId) {
  const query = engineId ? `?engine=${encodeURIComponent(engineId)}` : "";
  try {
    const response = await fetch(`${normalizedApiUrl()}/api/models${query}`, { method: "DELETE" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const report = await response.json();
    if (report.failed_paths && report.failed_paths.length) {
      showToast(t("modelsDeleteFailed"));
    } else {
      showToast(t("modelsDeleted", { size: humanBytes(report.freed_bytes) }));
    }
  } catch (_error) {
    showToast(t("modelsDeleteFailed"));
  }
  refreshStorage();
}

async function downloadModels() {
  elements.downloadModelsButton.disabled = true;
  const original = elements.downloadModelsButton.textContent;
  elements.downloadModelsButton.textContent = t("downloadingModels");
  try {
    const response = await fetch(`${normalizedApiUrl()}/api/models/download`, { method: "POST" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    await refreshStorage();
    showToast(t("modelsReady", { size: humanBytes(state.storage ? state.storage.total_bytes : 0) }));
  } catch (_error) {
    showToast(t("modelsDownloadFailed"));
  } finally {
    elements.downloadModelsButton.textContent = original;
    elements.downloadModelsButton.disabled = false;
    renderStorage();
  }
}

async function downloadEngine(engineId, button) {
  button.disabled = true;
  const original = button.textContent;
  button.textContent = t("downloadingModels");
  try {
    const response = await fetch(
      `${normalizedApiUrl()}/api/models/download?engine=${encodeURIComponent(engineId)}`,
      { method: "POST" }
    );
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
    await refreshStorage();
    showToast(t("modelsReady", { size: humanBytes(state.storage ? state.storage.total_bytes : 0) }));
  } catch (error) {
    showToast(error.message || t("modelsDownloadFailed"));
  } finally {
    renderStorage(); // rebuilds the row, so no need to restore original/disabled here
  }
}

/* ---------- events ---------- */

elements.fileInput.addEventListener("change", (event) => {
  addFiles(event.target.files);
  event.target.value = "";
});
["dragenter", "dragover"].forEach((eventName) =>
  document.addEventListener(eventName, (event) => {
    event.preventDefault();
    elements.dropZone.classList.add("dragging");
  }),
);
["dragleave", "drop"].forEach((eventName) =>
  document.addEventListener(eventName, (event) => {
    event.preventDefault();
    if (eventName === "dragleave" && event.relatedTarget) return;
    elements.dropZone.classList.remove("dragging");
  }),
);
document.addEventListener("drop", (event) => {
  if (event.dataTransfer && event.dataTransfer.files.length) addFiles(event.dataTransfer.files);
});
document.addEventListener("paste", (event) => {
  const items = Array.from(event.clipboardData ? event.clipboardData.items : []);
  const images = items
    .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
    .map((item) => item.getAsFile())
    .filter(Boolean)
    .map((file, index) => {
      const extension = (file.type.split("/")[1] || "png").replace("jpeg", "jpg");
      const stamp = new Date().toISOString().slice(0, 19).replaceAll(":", "-");
      return new File([file], `pasted-${stamp}-${index + 1}.${extension}`, { type: file.type });
    });
  if (images.length) {
    addFiles(images);
    showToast(t("pastedImage"));
  }
});

elements.recognizeButton.addEventListener("click", recognize);
elements.recognitionMode.addEventListener("change", updateModeOptions);
elements.copyDocButton.addEventListener("click", () => copyText(documentMarkdown(), t("documentCopied")));
elements.downloadDocWordButton.addEventListener("click", downloadDocumentWord);
elements.recheckButton.addEventListener("click", checkService);
elements.refreshPageButton.addEventListener("click", () => location.reload());
elements.updateButton.addEventListener("click", installUpdate);
elements.checkUpdatesButton.addEventListener("click", () => checkUpdate(true));
elements.apiUrl.addEventListener("change", () => {
  localStorage.setItem("mathocr-api-url", normalizedApiUrl());
  checkService();
});
elements.copyAllButton?.addEventListener("click", () => copyText(activeLatex().join("\n\n"), t("allLatexCopied")));
elements.downloadTexButton?.addEventListener("click", downloadTex);
elements.downloadWordButton?.addEventListener("click", downloadWord);
elements.downloadModelsButton.addEventListener("click", downloadModels);
armConfirm(elements.deleteAllModelsButton, () => deleteModels(null));
document.querySelectorAll("[data-language]").forEach((button) => {
  button.addEventListener("click", () => applyLanguage(button.dataset.language));
});

/* ---------- startup ---------- */

// The desktop launcher supplies its private random port through the query
// string. Browser and GitHub Pages use the remembered address or the default.
const suppliedApiUrl = params.get("api");
elements.apiUrl.value = suppliedApiUrl || localStorage.getItem("mathocr-api-url") || elements.apiUrl.value;
if (isDesktop) {
  elements.advancedSettings.hidden = true; // the port is private and per-launch
  elements.engineBanner.hidden = true;
}
elements.footerVersion.textContent = APP_VERSION;
applyLanguage(state.language);
checkService();
setInterval(() => {
  if (!state.busy && !state.online) checkService();
}, 5000);
