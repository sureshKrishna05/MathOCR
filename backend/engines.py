"""OCR engines, ensemble voting, and the recognition pipeline for MathOCR.

Authored by Bouronikos Christos <chrisbouronikos@gmail.com>.
Donations are welcome at https://paypal.me/christosbouronikos.

Math formula recognizers (every one runs fully on the user's computer):

- ``pix2text-mfr`` — Pix2Text MFR-1.5 (ONNX). The strongest openly licensed
  printed-formula recognizer that still packages cleanly; also the source of
  the math-region detector used for full pages. This is the default.
- ``pix2tex`` — the classic LaTeX-OCR ViT model.
- ``rapid-latex`` — RapidLaTeXOCR, an ONNX port of the LaTeX-OCR family.

For each formula image the selected engines vote: outputs are normalized,
compared for agreement, checked for structural sanity (balanced braces, no
degenerate repetition), and the best candidate wins. Engines from the same
model family agree for uninteresting reasons, so their mutual agreement is
discounted.

Text recognition (for the "document" mode, Greek + English):

- ``tesseract`` — the Tesseract engine via pytesseract, reading ``ell+eng``.
- ``nougat`` — optional Meta Nougat model for English academic papers; its
  weights are non-commercial, so it is never bundled and only used on request.

Everything model-related is imported lazily; this module stays importable —
and testable — without any ML package installed.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import re
import shutil
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Protocol

from PIL import Image

from backend.geometry import Box, padded_crop_box, plan_regions
from backend.latex import (
    clean_latex,
    extract_math,
    normalize_for_comparison,
    similarity,
    structure_score,
    tokenize,
)

# Child of the "mathocr" logger so engine failures reach the app's log file
# and stderr even after pix2tex silences the root logger at load time.
logger = logging.getLogger("mathocr.engines")

# Reliability priors from side-by-side runs on printed formulas: MFR-1.5 is
# markedly stronger on large fractions, matrices, and long expressions.
ENGINE_PRIORS = {"pix2text-mfr": 1.0, "pix2tex": 0.85, "rapid-latex": 0.8}
ENGINE_LABELS = {
    "pix2text-mfr": "Pix2Text MFR-1.5",
    "pix2tex": "pix2tex (LaTeX-OCR)",
    "rapid-latex": "RapidLaTeXOCR",
    "tesseract": "Tesseract (Greek + English text)",
    "nougat": "Nougat (English papers, optional)",
}
ENGINE_PACKAGES = {"pix2text-mfr": "pix2text", "pix2tex": "pix2tex", "rapid-latex": "rapid_latex_ocr"}
# Math engines, in preference order. The first installed one is the default
# when the user asks for a single engine rather than the cross-checked vote.
ENGINE_ORDER = ("pix2text-mfr", "pix2tex", "rapid-latex")


@dataclass(frozen=True, slots=True)
class Candidate:
    """One engine's opinion about a formula image."""

    engine: str
    latex: str
    model_score: float | None = None


@dataclass(slots=True)
class RegionResult:
    """A recognized formula region, ready for the HTTP layer."""

    latex: str
    engine: str
    confidence: float | None
    alternatives: list[Candidate] = field(default_factory=list)
    box: tuple[int, int, int, int] | None = None
    kind: str = "isolated"  # isolated | embedded | full


class FormulaEngine(Protocol):
    """The narrow interface implemented by all MathOCR recognition engines."""

    id: str
    family: str

    def recognize(self, image: Image.Image) -> Candidate:
        """Return this engine's reading of one RGB formula image."""


def _require(package: str, pip_name: str):
    if importlib.util.find_spec(package) is None:
        raise RuntimeError(
            f"{pip_name} is not installed; run: pip install -r backend/requirements.txt"
        )


class Pix2TextMfrEngine:
    """Pix2Text MFR-1.5 formula recognizer (ONNX, CPU-friendly)."""

    id = "pix2text-mfr"
    family = "mfr"

    def __init__(self, device: str = "cpu") -> None:
        _require("pix2text", "pix2text")
        from pix2text.latex_ocr import LatexOCR

        self._model = LatexOCR(model_name="mfr-1.5", model_backend="onnx", device=device)

    def recognize(self, image: Image.Image) -> Candidate:
        outcome = self._model.recognize(image)
        latex = clean_latex(str(outcome.get("text", "")))
        score = outcome.get("score")
        return Candidate(self.id, latex, float(score) if score is not None else None)


class Pix2TexEngine:
    """pix2tex / LaTeX-OCR recognizer.

    The upstream package downloads weights into its own installation folder,
    which is read-only inside a packaged desktop app. The checkpoint files are
    therefore fetched into the MathOCR model cache and passed explicitly.
    """

    id = "pix2tex"
    family = "latex-ocr"

    def __init__(self) -> None:
        _require("pix2tex", "pix2tex")
        from munch import Munch
        from pix2tex.cli import LatexOCR

        from backend.model_store import ensure_pix2tex_weights

        weights = ensure_pix2tex_weights()
        arguments = Munch(
            {
                "config": "settings/config.yaml",  # read from the package, never written
                "checkpoint": str(weights["weights.pth"]),
                "no_cuda": True,
                "no_resize": False,
            }
        )
        self._model = LatexOCR(arguments)

    def recognize(self, image: Image.Image) -> Candidate:
        return Candidate(self.id, clean_latex(str(self._model(image))))


class RapidLatexEngine:
    """RapidLaTeXOCR recognizer (ONNX runtime, LaTeX-OCR model family)."""

    id = "rapid-latex"
    family = "latex-ocr"

    def __init__(self) -> None:
        _require("rapid_latex_ocr", "rapid-latex-ocr")
        import numpy as np  # noqa: F401  (verified for the call path below)
        from rapid_latex_ocr import LaTeXOCR

        from backend.model_store import ensure_rapid_latex_weights

        weights = ensure_rapid_latex_weights()
        self._model = LaTeXOCR(
            image_resizer_path=str(weights["image_resizer.onnx"]),
            encoder_path=str(weights["encoder.onnx"]),
            decoder_path=str(weights["decoder.onnx"]),
            tokenizer_json=str(weights["tokenizer.json"]),
        )

    def recognize(self, image: Image.Image) -> Candidate:
        import numpy as np

        # RapidLaTeXOCR expects an OpenCV-style BGR array.
        bgr = np.asarray(image.convert("RGB"))[:, :, ::-1].copy()
        latex, _elapsed = self._model(bgr)
        return Candidate(self.id, clean_latex(str(latex)))


class MathDetector:
    """Pix2Text MFD-1.5 math-region detector for full pages."""

    def __init__(self, device: str = "cpu") -> None:
        _require("pix2text", "pix2text")
        from pix2text.formula_detector import MathFormulaDetector

        self._model = MathFormulaDetector(model_name="mfd-1.5", model_backend="onnx", device=device)

    def detect(self, image: Image.Image) -> list[tuple[Box, str]]:
        """Return (box, category) pairs; category is 'isolated' or 'embedded'."""

        detections = self._model.detect(image, resized_shape=768)
        regions: list[tuple[Box, str]] = []
        for detection in detections:
            points = detection.get("box")
            if points is None:
                continue
            xs = [float(point[0]) for point in points]
            ys = [float(point[1]) for point in points]
            category = str(detection.get("type", "isolated"))
            if category in ("embedding", "embedded"):
                category = "embedded"
            regions.append((Box(min(xs), min(ys), max(xs), max(ys)), category))
        return regions


@dataclass(frozen=True, slots=True)
class TextLine:
    """One recognized line of ordinary (non-formula) text with its box."""

    box: Box
    text: str
    confidence: float


def find_tesseract_binary() -> str | None:
    """Locate the Tesseract program: override, desktop bundle, standard paths, then PATH."""

    override = os.getenv("MATHOCR_TESSERACT_PATH")
    if override and os.path.isfile(override):
        return override
    executable = "tesseract.exe" if sys.platform == "win32" else "tesseract"
    from backend.app import APP_ROOT  # local import avoids a cycle at module load

    bundled = APP_ROOT / "vendor" / "tesseract" / executable
    if bundled.is_file():
        return str(bundled)

    on_path = shutil.which("tesseract")
    if on_path:
        return on_path

    if sys.platform == "win32":
        standard_windows_paths = [
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Tesseract-OCR" / "tesseract.exe",
            Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "Tesseract-OCR" / "tesseract.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR" / "tesseract.exe",
        ]
        for candidate in standard_windows_paths:
            if candidate.is_file():
                return str(candidate)

    return None


class TesseractTextEngine:
    """Greek + English text recognition through Tesseract (pytesseract)."""

    id = "tesseract"

    def __init__(self) -> None:
        _require("pytesseract", "pytesseract")
        import pytesseract

        from backend.model_store import ensure_tesseract_langs

        binary = find_tesseract_binary()
        if not binary:
            raise RuntimeError(
                "The Tesseract program was not found. Install it (macOS: 'brew install "
                "tesseract tesseract-lang'; Debian/Ubuntu: 'sudo apt install tesseract-ocr "
                "tesseract-ocr-ell'; Windows: install from UB-Mannheim) to read page text."
            )
        pytesseract.pytesseract.tesseract_cmd = binary
        self._pt = pytesseract
        self._tessdata = str(ensure_tesseract_langs())

    def read_lines(self, image: Image.Image) -> list[TextLine]:
        """Return text lines (merged from words) with their bounding boxes."""

        config = f'--psm 4 --oem 1 --tessdata-dir "{self._tessdata}"'
        data = self._pt.image_to_data(
            image, lang="ell+eng", output_type=self._pt.Output.DICT, config=config
        )
        grouped: dict[tuple[int, int, int], list[int]] = {}
        for index, word in enumerate(data["text"]):
            if not word.strip():
                continue
            try:
                confidence = float(data["conf"][index])
            except (TypeError, ValueError):
                confidence = -1.0
            if confidence >= 0 and confidence < 30:
                clean_w = word.strip()
                # Retain short tokens, numbers, punctuation, and abbreviations for review instead of discarding
                is_meaningful = (
                    len(clean_w) <= 4
                    or clean_w.isupper()
                    or any(c.isdigit() for c in clean_w)
                    or any(c in ".,;:()[]{}%+-=<>/" for c in clean_w)
                )
                if not is_meaningful and confidence < 15:
                    continue
            key = (data["block_num"][index], data["par_num"][index], data["line_num"][index])
            grouped.setdefault(key, []).append(index)

        lines: list[TextLine] = []
        for indices in grouped.values():
            # Split line into column segments if there is a wide horizontal gap (e.g. table columns)
            sub_groups: list[list[int]] = []
            current_sub: list[int] = []
            for i in indices:
                if not current_sub:
                    current_sub.append(i)
                else:
                    prev_i = current_sub[-1]
                    prev_r = data["left"][prev_i] + data["width"][prev_i]
                    curr_l = data["left"][i]
                    prev_h = max(10, data["height"][prev_i])
                    if curr_l - prev_r > max(35.0, 2.2 * prev_h):
                        sub_groups.append(current_sub)
                        current_sub = [i]
                    else:
                        current_sub.append(i)
            if current_sub:
                sub_groups.append(current_sub)

            for sub in sub_groups:
                words = [data["text"][i] for i in sub]
                lefts = [data["left"][i] for i in sub]
                tops = [data["top"][i] for i in sub]
                rights = [data["left"][i] + data["width"][i] for i in sub]
                bottoms = [data["top"][i] + data["height"][i] for i in sub]
                confidences = [float(data["conf"][i]) for i in sub]
                text = " ".join(words).strip()
                if not text:
                    continue
                lines.append(
                    TextLine(
                        box=Box(min(lefts), min(tops), max(rights), max(bottoms)),
                        text=text,
                        confidence=sum(confidences) / len(confidences) / 100.0,
                    )
                )
        return lines


class RapidOcrTextEngine:
    """Document text recognition through RapidOCR (ONNX runtime, standalone)."""

    id = "rapidocr"

    def __init__(self) -> None:
        _require("rapidocr", "rapidocr")
        import numpy as np
        from rapidocr import RapidOCR

        self._np = np
        self._engine = RapidOCR()

    def read_lines(self, image: Image.Image) -> list[TextLine]:
        rgb = image.convert("RGB")
        res = self._engine(self._np.array(rgb))
        lines: list[TextLine] = []
        if res is None:
            return lines

        # Object return style (res.boxes, res.txts, res.scores)
        if hasattr(res, "txts") and res.txts:
            boxes = getattr(res, "boxes", [])
            scores = getattr(res, "scores", [1.0] * len(res.txts))
            for box, text, score in zip(boxes, res.txts, scores):
                stripped = text.strip()
                if not stripped:
                    continue
                xs = [float(pt[0]) for pt in box]
                ys = [float(pt[1]) for pt in box]
                lines.append(
                    TextLine(
                        box=Box(min(xs), min(ys), max(xs), max(ys)),
                        text=stripped,
                        confidence=float(score) if score is not None else 1.0,
                    )
                )
        # Tuple return style ((result_list, elapse_list))
        elif isinstance(res, (tuple, list)) and len(res) > 0 and res[0]:
            for item in res[0]:
                if len(item) >= 3:
                    box, text, score = item[0], item[1], item[2]
                    stripped = str(text).strip()
                    if not stripped:
                        continue
                    xs = [float(pt[0]) for pt in box]
                    ys = [float(pt[1]) for pt in box]
                    lines.append(
                        TextLine(
                            box=Box(min(xs), min(ys), max(xs), max(ys)),
                            text=stripped,
                            confidence=float(score) if score is not None else 1.0,
                        )
                    )
        return lines


class NougatEngine:
    """Optional Meta Nougat document recognizer (English papers, CC-BY-NC).

    Nougat reads a whole page directly into Markdown with embedded LaTeX, so it
    replaces the layout+text+math reconstruction when the user selects it.
    """

    id = "nougat"

    def __init__(self, device: str = "cpu") -> None:
        _require("nougat", "nougat-ocr")
        import torch
        from nougat import NougatModel
        from nougat.utils.device import move_to_device

        from backend.model_store import ensure_nougat_model

        checkpoint = ensure_nougat_model()
        self._torch = torch
        self._model = NougatModel.from_pretrained(checkpoint)
        self._model = move_to_device(self._model, bf16=False, cuda=(device != "cpu"))
        self._model.eval()

    def recognize_document(self, image: Image.Image) -> str:
        from nougat.postprocessing import markdown_compatible

        prepared = self._model.encoder.prepare_input(image.convert("RGB"), random_padding=False)
        with self._torch.no_grad():
            output = self._model.inference(image_tensors=prepared.unsqueeze(0))
        prediction = output["predictions"][0]
        return markdown_compatible(prediction)


_ENGINE_CLASSES = {
    "pix2text-mfr": Pix2TextMfrEngine,
    "pix2tex": Pix2TexEngine,
    "rapid-latex": RapidLatexEngine,
}


def installed_engine_ids() -> list[str]:
    """Math-engine ids whose Python package is importable (no model load)."""

    return [
        engine_id
        for engine_id in ENGINE_ORDER
        if importlib.util.find_spec(ENGINE_PACKAGES[engine_id]) is not None
    ]


def resolve_math_engines(selection: str) -> list[str]:
    """Turn a UI engine choice into the ordered list of engines to run.

    ``auto`` means the cross-checked vote across every installed engine; any
    other value pins recognition to that single engine (falling back to the
    default when it is not installed).
    """

    installed = installed_engine_ids()
    if selection and selection != "auto":
        return [selection] if selection in installed else installed[:1]
    return installed


def text_engine_available() -> bool:
    """True when page text can be read (Tesseract binary present or RapidOCR installed)."""

    if importlib.util.find_spec("pytesseract") is not None and find_tesseract_binary() is not None:
        return True
    return importlib.util.find_spec("rapidocr") is not None


def nougat_available() -> bool:
    """True when the optional Nougat package is importable."""

    return importlib.util.find_spec("nougat") is not None


def nougat_ready() -> bool:
    """True when Nougat can actually run: package installed and weights present."""

    if not nougat_available():
        return False
    from backend import model_store

    weights_dir = model_store.default_cache_root() / "nougat"
    return model_store.directory_size(weights_dir) > 0


def can_install_packages() -> bool:
    """Whether new Python packages can be pip-installed at runtime.

    False inside a frozen PyInstaller bundle, where ``sys.executable`` is the
    app itself and site-packages is read-only. In that case Nougat has to be
    part of the build (or run from source) rather than added on demand.
    """

    return not getattr(sys, "frozen", False)


class EngineRegistry:
    """Create expensive models on first use and safely share them between requests."""

    def __init__(self, device: str = "cpu") -> None:
        self._device = device
        self._engines: dict[str, FormulaEngine] = {}
        self._detector: MathDetector | None = None
        self._text_engine: TesseractTextEngine | None = None
        self._nougat: NougatEngine | None = None
        self._lock = threading.Lock()

    def engine(self, engine_id: str) -> FormulaEngine:
        with self._lock:
            if engine_id not in self._engines:
                started = time.perf_counter()
                logger.info("Loading recognition engine | engine=%s", engine_id)
                if engine_id == "pix2text-mfr":
                    self._engines[engine_id] = Pix2TextMfrEngine(self._device)
                else:
                    self._engines[engine_id] = _ENGINE_CLASSES[engine_id]()
                logger.info(
                    "Recognition engine loaded | engine=%s | elapsed=%.2fs",
                    engine_id,
                    time.perf_counter() - started,
                )
            return self._engines[engine_id]

    def detector(self) -> MathDetector:
        with self._lock:
            if self._detector is None:
                started = time.perf_counter()
                logger.info("Loading math-region detector")
                self._detector = MathDetector(self._device)
                logger.info("Math-region detector loaded | elapsed=%.2fs", time.perf_counter() - started)
            return self._detector

    def text_engine(self) -> Any:
        with self._lock:
            if self._text_engine is None:
                if find_tesseract_binary() is not None and importlib.util.find_spec("pytesseract") is not None:
                    self._text_engine = TesseractTextEngine()
                elif importlib.util.find_spec("rapidocr") is not None:
                    self._text_engine = RapidOcrTextEngine()
                else:
                    self._text_engine = TesseractTextEngine()
            return self._text_engine

    def nougat_engine(self) -> NougatEngine:
        with self._lock:
            if self._nougat is None:
                self._nougat = NougatEngine(self._device)
            return self._nougat

    def select_engines(self, selection: str) -> list[FormulaEngine]:
        """Instantiate the math engines named by a UI selection (``auto`` = all)."""

        engines: list[FormulaEngine] = []
        failures: list[str] = []
        for engine_id in resolve_math_engines(selection):
            try:
                engines.append(self.engine(engine_id))
            except Exception as error:  # a broken optional engine must not sink the request
                # Full traceback to the log; a short reason for the error message.
                logger.warning("Engine %s unavailable", engine_id, exc_info=True)
                failures.append(f"{engine_id}: {type(error).__name__}: {error}")
        if not engines:
            raise RuntimeError(
                "No recognition engine could be loaded — " + " | ".join(failures)
            )
        return engines

    def unload_all(self) -> None:
        """Drop model instances so their files can be deleted (Windows mmaps)."""

        with self._lock:
            self._engines.clear()
            self._detector = None
            self._text_engine = None
            self._nougat = None

    @property
    def loaded(self) -> list[str]:
        """Names of models already resident in memory, useful for health checks."""

        names = sorted(self._engines)
        if self._detector is not None:
            names.append("math-detector")
        if self._text_engine is not None:
            names.append("tesseract")
        if self._nougat is not None:
            names.append("nougat")
        return names


def vote(candidates: list[Candidate]) -> tuple[Candidate, float, list[Candidate]]:
    """Pick the best candidate from the ensemble and estimate confidence.

    Scoring blends three signals: the engine's reliability prior, structural
    sanity of the produced LaTeX, and weighted agreement with the *other*
    engines. Same-family agreement is discounted because sibling models make
    identical mistakes. Returns (winner, confidence, distinct alternatives).
    """

    real = [candidate for candidate in candidates if clean_latex(candidate.latex)]
    if not real:
        raise ValueError("no non-empty candidates")

    families = {candidate.engine: _family_of(candidate.engine) for candidate in real}
    structures = {candidate.engine: structure_score(candidate.latex) for candidate in real}

    def agreement(candidate: Candidate) -> float:
        others = [other for other in real if other.engine != candidate.engine]
        if not others:
            return 0.0
        total = 0.0
        weight_sum = 0.0
        for other in others:
            weight = ENGINE_PRIORS.get(other.engine, 0.7)
            if families[other.engine] == families[candidate.engine]:
                weight *= 0.6
            total += weight * similarity(candidate.latex, other.latex)
            weight_sum += weight
        return total / weight_sum if weight_sum else 0.0

    agreements = {candidate.engine: agreement(candidate) for candidate in real}

    def score(candidate: Candidate) -> float:
        prior = ENGINE_PRIORS.get(candidate.engine, 0.7)
        return (
            prior * (0.45 + 0.55 * structures[candidate.engine])
            + 0.9 * agreements[candidate.engine]
        )

    winner = max(real, key=score)

    if len(real) == 1:
        base = winner.model_score if winner.model_score is not None else 0.6
        confidence = base * structures[winner.engine]
    else:
        confidence = 0.75 * agreements[winner.engine] + 0.25 * structures[winner.engine]

    seen_forms = {normalize_for_comparison(winner.latex)}
    alternatives: list[Candidate] = []
    for candidate in real:
        if candidate.engine == winner.engine:
            continue
        form = normalize_for_comparison(candidate.latex)
        if form in seen_forms:
            continue
        seen_forms.add(form)
        alternatives.append(candidate)

    return winner, round(min(1.0, max(0.0, confidence)), 3), alternatives


def _family_of(engine_id: str) -> str:
    return "mfr" if engine_id == "pix2text-mfr" else "latex-ocr"


def _is_trivial_embedded(latex: str) -> bool:
    """True for inline fragments like a lone variable; they are noise, not math."""

    return len(tokenize(normalize_for_comparison(latex))) < 2


@dataclass(slots=True)
class PageOutcome:
    """Everything one page produced: equation cards and optional document text."""

    regions: list[RegionResult]
    markdown: str | None = None  # present only in document mode
    text_available: bool = True  # False when page text could not be read
    document: Any = None  # Structured Document intermediate representation


def _overlap_fraction(inner: Box, outer: Box) -> float:
    """Fraction of ``inner``'s area covered by its intersection with ``outer``."""

    left = max(inner.left, outer.left)
    top = max(inner.top, outer.top)
    right = min(inner.right, outer.right)
    bottom = min(inner.bottom, outer.bottom)
    if right <= left or bottom <= top or inner.area <= 0:
        return 0.0
    return (right - left) * (bottom - top) / inner.area


def reconstruct_markdown(
    text_lines: list[TextLine],
    math_results: list[RegionResult],
    page_height: float,
    page_width: float = 0.0,
    figures: list[Any] | None = None,
    table_cell_rects: list[Box] | None = None,
    page_number: int = 1,
) -> str:
    """Interleave text lines, math results, and figures into reading-order Markdown.

    Constructs the canonical Document representation and renders it to Markdown,
    guaranteeing that the structured document and editable Markdown are in 100% agreement.
    """
    from backend.document import Document

    doc = Document.from_layout(
        text_lines=text_lines,
        math_results=math_results,
        page_height=page_height,
        page_width=page_width,
        figures=figures,
        table_cell_rects=table_cell_rects,
        page_number=page_number,
    )
    return doc.to_markdown()


def _row_center(row: list[tuple[Box, str, str]]) -> float:
    return sum((box.top + box.bottom) / 2 for box, _kind, _payload in row) / len(row)


class MathPipeline:
    """Detect, merge, recognize: turn a page or crop into equations and text.

    Modes:

    - ``formula``  — the whole image is one equation.
    - ``mixed``    — find the equations inside a page and return only those.
    - ``document`` — reconstruct the whole page (Greek/English text + math) into
      editable Markdown, and also return each equation as a card.
    """

    def __init__(self, registry: EngineRegistry) -> None:
        self._registry = registry
        # Model backends are not guaranteed thread-safe; recognition is
        # CPU-bound anyway, so requests take turns.
        self._inference_lock = threading.Lock()

    def process(
        self,
        image: Image.Image,
        mode: str,
        engine: str = "auto",
        doc_engine: str = "layout",
        page_source: Any | None = None,
    ) -> PageOutcome:
        with self._inference_lock:
            if mode == "formula":
                return PageOutcome(regions=[self._recognize_region(image, engine, kind="full")])
            if mode == "document" and doc_engine == "nougat":
                return self._process_with_nougat(image)
            regions = self._recognize_page_math(image, mode, engine)
            if mode != "document":
                return PageOutcome(regions=regions)
            return self._assemble_document(image, regions, page_source=page_source)

    def _recognize_page_math(self, image: Image.Image, mode: str, engine: str) -> list[RegionResult]:
        started = time.perf_counter()
        detected = self._registry.detector().detect(image)
        logger.info(
            "Math detection timing | image=%sx%s | detections=%s | elapsed=%.2fs",
            image.width,
            image.height,
            len(detected),
            time.perf_counter() - started,
        )
        boxes = [box for box, _category in detected]
        regions = plan_regions(image.width, image.height, boxes, assume_small_is_formula=True)
        if regions is None:
            return [self._recognize_region(image, engine, kind="full")]

        results: list[RegionResult] = []
        for region in regions:
            kind = self._region_kind(region, detected)
            crop_box = padded_crop_box(region, image.width, image.height)
            crop = image.crop(
                (int(crop_box.left), int(crop_box.top), int(crop_box.right), int(crop_box.bottom))
            )
            try:
                result = self._recognize_region(crop, engine, kind=kind)
            finally:
                crop.close()
            if not result.latex:
                continue
            if kind == "embedded" and _is_trivial_embedded(result.latex):
                continue
            result.box = (
                int(region.left),
                int(region.top),
                int(region.right),
                int(region.bottom),
            )
            results.append(result)
        return results

    def _assemble_document(
        self,
        image: Image.Image,
        regions: list[RegionResult],
        page_source: Any | None = None,
    ) -> PageOutcome:
        """Add page text, figures, and geometry around the recognized formulas to build a document."""

        if not text_engine_available():
            return PageOutcome(regions=regions, markdown=None, text_available=False)
        try:
            text_lines = self._registry.text_engine().read_lines(image)
        except Exception as error:
            logger.warning("Text recognition failed: %s", error)
            return PageOutcome(regions=regions, markdown=None, text_available=False)

        # Drop text that sits on top of a formula; it is the mangled formula.
        math_boxes = [Box(*result.box) for result in regions if result.box is not None]
        kept_text = [
            line
            for line in text_lines
            if all(
                _overlap_fraction(line.box, math_box) < 0.45
                and _overlap_fraction(math_box, line.box) < 0.75
                for math_box in math_boxes
            )
        ]

        figures = []
        table_cell_rects = []
        page_num = 1
        if page_source is not None:
            figures = list(getattr(page_source, "figures", []))
            table_cell_rects = list(getattr(page_source, "table_cell_rects", []))
            page_num = getattr(page_source, "page_number", 1)
            if getattr(page_source, "is_scanned", False) and not figures:
                from backend.layout import detect_scanned_figures

                occupied = math_boxes + [l.box for l in kept_text]
                figures = detect_scanned_figures(image, occupied, page_num=page_num)
        else:
            from backend.layout import detect_scanned_figures

            occupied = math_boxes + [l.box for l in kept_text]
            figures = detect_scanned_figures(image, occupied, page_num=page_num)

        from backend.document import Document

        doc = Document.from_layout(
            kept_text,
            regions,
            page_height=image.height,
            page_width=image.width,
            figures=figures,
            table_cell_rects=table_cell_rects,
            page_number=page_num,
        )
        markdown = doc.to_markdown()
        return PageOutcome(regions=regions, markdown=markdown, document=doc)

    def _process_with_nougat(self, image: Image.Image) -> PageOutcome:
        markdown = self._registry.nougat_engine().recognize_document(image)
        regions = [
            RegionResult(latex=latex, engine="nougat", confidence=None, kind="isolated")
            for latex in extract_math(markdown)
        ]
        from backend.document import Document
        doc = Document.from_markdown(markdown)
        return PageOutcome(regions=regions, markdown=markdown, document=doc)

    @staticmethod
    def _region_kind(region: Box, detected: list[tuple[Box, str]]) -> str:
        kinds = {category for box, category in detected if region.overlaps(box)}
        return "embedded" if kinds and kinds <= {"embedded", "embedding"} else "isolated"

    def _recognize_region(self, image: Image.Image, engine: str, kind: str) -> RegionResult:
        started = time.perf_counter()
        engines = self._registry.select_engines(engine)

        candidates: list[Candidate] = []
        # Fast cascade optimization for multi-engine ensemble (auto):
        # pix2text-mfr and rapid-latex are fast ONNX models (~20ms-50ms).
        # pix2tex is a heavy ViT model on PyTorch CPU (~1500ms-3500ms).
        # If fast engines agree or embedded crop is simple, skip slow pix2tex to prevent hanging!
        if len(engines) > 1 and any(e.id == "pix2tex" for e in engines):
            fast_engines = [e for e in engines if e.id != "pix2tex"]
            slow_engines = [e for e in engines if e.id == "pix2tex"]

            for math_engine in fast_engines:
                try:
                    candidates.append(math_engine.recognize(image))
                except Exception as error:
                    logger.warning("Engine %s failed on a region: %s", math_engine.id, error)

            skip_slow = False
            if len(candidates) >= 2:
                from backend.latex import similarity
                sim = similarity(candidates[0].latex, candidates[1].latex)
                if sim >= 0.85:
                    skip_slow = True
            elif len(candidates) == 1 and kind == "embedded":
                skip_slow = True

            if not skip_slow:
                for math_engine in slow_engines:
                    try:
                        candidates.append(math_engine.recognize(image))
                    except Exception as error:
                        logger.warning("Engine %s failed on a region: %s", math_engine.id, error)
        else:
            for math_engine in engines:
                try:
                    candidates.append(math_engine.recognize(image))
                except Exception as error:
                    logger.warning("Engine %s failed on a region: %s", math_engine.id, error)

        try:
            winner, confidence, alternatives = vote(candidates)
        except ValueError:
            logger.info(
                "Formula recognition timing | kind=%s | engines=%s | candidates=0 | elapsed=%.2fs",
                kind,
                ",".join(math_engine.id for math_engine in engines),
                time.perf_counter() - started,
            )
            return RegionResult(latex="", engine="none", confidence=None, kind=kind)
        logger.info(
            "Formula recognition timing | kind=%s | engines=%s | candidates=%s | elapsed=%.2fs",
            kind,
            ",".join(math_engine.id for math_engine in engines),
            len(candidates),
            time.perf_counter() - started,
        )
        return RegionResult(
            latex=winner.latex,
            engine=winner.engine,
            confidence=confidence,
            alternatives=alternatives,
            kind=kind,
        )
