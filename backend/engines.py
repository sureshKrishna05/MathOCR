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
import io
import logging
import os
import re
import shutil
import sys
import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from statistics import median
from typing import Any, Protocol

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
    numbering: str | None = None
    review_flags: list[str] = field(default_factory=list)
    asset_id: str | None = None
    fallback_image: bool = False


@dataclass(frozen=True, slots=True)
class MathDetection:
    """One raw formula-detector result, kept for review before region planning.

    The detector is deliberately not trusted as a source of truth.  Keeping its
    category, score (when a backend supplies one), and source index lets the
    document path explain why a box was accepted, retained for review, or
    rejected without deleting the corresponding page pixels.
    """

    box: Box
    category: str
    confidence: float | None = None
    source_index: int = 0


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

    def detect_detailed(self, image: Image.Image) -> list[MathDetection]:
        """Return raw detections with the backend's category and score.

        MFD versions do not all expose a confidence field, therefore ``None``
        is preserved rather than pretending an inferred geometry score came
        from the model.
        """

        detections = self._model.detect(image, resized_shape=768)
        regions: list[MathDetection] = []
        for source_index, detection in enumerate(detections, start=1):
            points = detection.get("box")
            if points is None:
                continue
            xs = [float(point[0]) for point in points]
            ys = [float(point[1]) for point in points]
            category = str(detection.get("type", "isolated"))
            if category in ("embedding", "embedded"):
                category = "embedded"
            raw_score = detection.get("score", detection.get("confidence"))
            try:
                score = float(raw_score) if raw_score is not None else None
            except (TypeError, ValueError):
                score = None
            regions.append(
                MathDetection(
                    Box(min(xs), min(ys), max(xs), max(ys)),
                    category,
                    score,
                    source_index,
                )
            )
        return regions

    def detect(self, image: Image.Image) -> list[tuple[Box, str]]:
        """Return legacy ``(box, category)`` pairs for callers and plugins."""

        return [(item.box, item.category) for item in self.detect_detailed(image)]


@dataclass(frozen=True, slots=True)
class TextLine:
    """One recognized line of ordinary (non-formula) text with its box."""

    box: Box
    text: str
    confidence: float
    engine: str = ""
    background_color: str | None = None
    foreground_color: str | None = None


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
            # Keep even low-confidence words.  A later layout decision may
            # retain them as the only reading of a small label; discarding at
            # this stage made omissions impossible to audit or recover.
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
                        engine=self.id,
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
                        engine=self.id,
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
                            engine=self.id,
                        )
                    )
        return lines


class EnsembleTextEngine:
    """Choose the most reliable fully-local text reading for one page.

    Tesseract remains important for Greek material, while RapidOCR is often
    substantially stronger on small, anti-aliased English screenshots.  Mixing
    their lines produces duplicates, so this class retains each raw reading and
    selects one complete reading using confidence, coverage, and character
    plausibility.  The rejected reading stays available through ``last_audit``.
    """

    id = "ensemble"

    def __init__(self, engines: list[Any]) -> None:
        self._engines = engines
        self.last_audit: dict[str, Any] = {}

    @staticmethod
    def _score(lines: list[TextLine]) -> float:
        if not lines:
            return -1.0
        weighted_confidence = sum(
            max(0.0, min(1.0, line.confidence)) * max(1.0, line.box.width)
            for line in lines
        )
        coverage = sum(max(1.0, line.box.width) for line in lines)
        text = " ".join(line.text for line in lines)
        alphanumeric = sum(ch.isalnum() for ch in text)
        printable = sum(ch.isprintable() and not ch.isspace() for ch in text)
        plausibility = alphanumeric / max(1, printable)
        # Coverage is deliberately a small component: a formula OCR can emit
        # many tiny fragments, but it should not beat a confident page reader.
        return weighted_confidence / max(1.0, coverage) + 0.08 * plausibility + min(0.12, len(lines) / 600.0)

    def read_lines(self, image: Image.Image) -> list[TextLine]:
        readings: dict[str, list[TextLine]] = {}
        failures: dict[str, str] = {}
        for engine in self._engines:
            try:
                readings[engine.id] = engine.read_lines(image)
            except Exception as error:
                logger.warning("Text engine %s failed: %s", engine.id, error)
                failures[engine.id] = f"{type(error).__name__}: {error}"

        scores = {engine_id: self._score(lines) for engine_id, lines in readings.items()}
        selected_id = max(scores, key=scores.get) if scores else ""
        selected = readings.get(selected_id, [])
        self.last_audit = {
            "selected_engine": selected_id,
            "scores": {key: round(value, 4) for key, value in scores.items()},
            "line_counts": {key: len(value) for key, value in readings.items()},
            "failures": failures,
            "raw_lines": {
                key: [
                    {
                        "text": line.text,
                        "confidence": round(line.confidence, 4),
                        "box": _box_tuple(line.box),
                    }
                    for line in lines
                ]
                for key, lines in readings.items()
            },
        }
        return _annotate_source_styles(image, selected)


def _box_tuple(box: Box) -> tuple[int, int, int, int]:
    return (int(box.left), int(box.top), int(box.right), int(box.bottom))


def _hex_color(red: int, green: int, blue: int) -> str:
    return f"{red:02X}{green:02X}{blue:02X}"


def _annotate_source_styles(image: Image.Image, lines: list[TextLine]) -> list[TextLine]:
    """Attach conservative source colour hints to OCR lines.

    This is intentionally only a colour sampler, not a classifier: a coloured
    dominant background becomes paragraph shading, and a strongly saturated
    foreground becomes a run colour.  Neutral paper and anti-aliased black
    text stay unstyled.  Keeping the thresholds conservative avoids applying a
    template colour merely because of compression noise.
    """

    annotated: list[TextLine] = []
    rgb = image.convert("RGB")
    for line in lines:
        box = line.box.clamped(rgb.width, rgb.height)
        if box.width < 2 or box.height < 2:
            annotated.append(line)
            continue
        crop = rgb.crop((int(box.left), int(box.top), int(box.right), int(box.bottom)))
        # Bounded sampling prevents a full-resolution page from making style
        # recovery expensive while retaining enough pixels for small text.
        crop.thumbnail((180, 48))
        pixels = list(crop.get_flattened_data()) if hasattr(crop, "get_flattened_data") else list(crop.getdata())
        crop.close()
        if not pixels:
            annotated.append(line)
            continue

        quantized: dict[tuple[int, int, int], int] = {}
        for red, green, blue in pixels:
            key = (red // 16 * 16, green // 16 * 16, blue // 16 * 16)
            quantized[key] = quantized.get(key, 0) + 1
        dominant, dominant_count = max(quantized.items(), key=lambda item: item[1])
        dr, dg, db = dominant
        chroma = max(dominant) - min(dominant)
        background = None
        if dominant_count >= max(4, int(0.12 * len(pixels))) and chroma >= 24:
            # Do not treat dark coloured glyphs as a page-wide background.
            if (dr + dg + db) >= 250:
                background = _hex_color(dr, dg, db)

        saturated = [
            (red, green, blue)
            for red, green, blue in pixels
            if max(red, green, blue) - min(red, green, blue) >= 60
            and red + green + blue <= 650
        ]
        foreground = None
        # True colored text has a substantial fraction of saturated pixels (>= 12%),
        # whereas chromatic aberration at black-white glyph edges only produces 1-3% fringing.
        if len(saturated) >= max(20, int(0.12 * len(pixels))):
            sr = sum(pixel[0] for pixel in saturated) // len(saturated)
            sg = sum(pixel[1] for pixel in saturated) // len(saturated)
            sb = sum(pixel[2] for pixel in saturated) // len(saturated)
            if max(sr, sg, sb) - min(sr, sg, sb) >= 45:
                foreground = _hex_color(sr, sg, sb)

        # White type on a coloured marker is visually important even though it
        # is not a saturated foreground.  The run background keeps the marker
        # editable in Word rather than converting it into an image.
        if background and (dr + dg + db) < 510:
            foreground = "FFFFFF"
        annotated.append(
            replace(
                line,
                background_color=background,
                foreground_color=foreground,
            )
        )
    return annotated


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
        from nougat.model import BARTDecoder
        from nougat.utils.device import move_to_device

        # Patch BARTDecoder.prepare_inputs_for_inference to accept **kwargs (e.g. cache_position in transformers >= 4.41)
        orig_prepare = getattr(BARTDecoder, "_orig_prepare_inputs_for_inference", None)
        if orig_prepare is None:
            BARTDecoder._orig_prepare_inputs_for_inference = BARTDecoder.prepare_inputs_for_inference

            def _compatible_prepare_inputs(
                self,
                input_ids,
                encoder_outputs,
                past=None,
                past_key_values=None,
                use_cache=None,
                attention_mask=None,
                **kwargs,
            ):
                return BARTDecoder._orig_prepare_inputs_for_inference(
                    self,
                    input_ids,
                    encoder_outputs,
                    past=past,
                    past_key_values=past_key_values,
                    use_cache=use_cache,
                    attention_mask=attention_mask,
                )

            BARTDecoder.prepare_inputs_for_inference = _compatible_prepare_inputs

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
        self._text_engine: Any | None = None
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
                readers: list[Any] = []
                if find_tesseract_binary() is not None and importlib.util.find_spec("pytesseract") is not None:
                    readers.append(TesseractTextEngine())
                if importlib.util.find_spec("rapidocr") is not None:
                    readers.append(RapidOcrTextEngine())
                if not readers:
                    # Preserve the existing useful error when neither local
                    # reader is installed.
                    readers.append(TesseractTextEngine())
                self._text_engine = readers[0] if len(readers) == 1 else EnsembleTextEngine(readers)
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
    audit: dict[str, Any] = field(default_factory=dict)


def _overlap_fraction(inner: Box, outer: Box) -> float:
    """Fraction of ``inner``'s area covered by its intersection with ``outer``."""

    left = max(inner.left, outer.left)
    top = max(inner.top, outer.top)
    right = min(inner.right, outer.right)
    bottom = min(inner.bottom, outer.bottom)
    if right <= left or bottom <= top or inner.area <= 0:
        return 0.0
    return (right - left) * (bottom - top) / inner.area


def _parse_equation_number(text: str) -> str | None:
    """Read a right-margin equation label such as ``(1)`` from OCR output.

    Small labels are frequently mis-OCR'd (``..(1()``, ``...(2))``).  The
    tolerant patterns below only accept a line that is *label-shaped*: at most
    dots, parentheses, whitespace and one 1-3 digit number.  Prose containing
    parenthesised numbers can never match because other characters are present.
    """

    if not text:
        return None
    stripped = text.strip()
    clean = re.search(r"\(\s*(\d{1,3})\s*\)", stripped)
    if clean:
        return clean.group(1)
    misread_close = re.search(r"\(\s*(\d{1,3})\s*\(", stripped)
    if misread_close:
        return misread_close.group(1)
    whole_label = re.match(r"^[\s.()|:;]*\(\s*(\d{1,3})[\s.()|:;]*$", stripped)
    if whole_label:
        return whole_label.group(1)
    return None


def _looks_like_formula_text(text: str) -> bool:
    """Cheap test for a short standalone formula read as ordinary text."""

    stripped = text.strip()
    if not stripped or len(stripped) > 20:
        return False
    return any(ch in stripped for ch in "=+/^_×÷√πλΔ∴≈≠≤≥→∫")


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
        self._last_math_audit: dict[str, Any] = {}

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
            if mode != "document":
                regions = self._recognize_page_math(image, mode, engine, page_source=page_source)
                return PageOutcome(regions=regions, audit=self._last_math_audit)

            # Read the page before planning math.  Text geometry supplies the
            # crucial evidence that a small screenshot is a document page, not
            # a generously padded single formula crop.
            if not text_engine_available():
                regions = self._recognize_page_math(image, mode, engine, text_lines=[], page_source=page_source)
                return PageOutcome(
                    regions=regions,
                    markdown=None,
                    text_available=False,
                    audit=self._last_math_audit,
                )
            try:
                text_engine = self._registry.text_engine()
                text_lines = text_engine.read_lines(image)
                text_audit = dict(getattr(text_engine, "last_audit", {}))
            except Exception as error:
                logger.warning("Text recognition failed: %s", error)
                regions = self._recognize_page_math(image, mode, engine, text_lines=[], page_source=page_source)
                return PageOutcome(
                    regions=regions,
                    markdown=None,
                    text_available=False,
                    audit=self._last_math_audit,
                )

            regions = self._recognize_page_math(image, mode, engine, text_lines=text_lines, page_source=page_source)
            audit = {**self._last_math_audit, "text": text_audit}
            return self._assemble_document(
                image,
                regions,
                text_lines=text_lines,
                page_source=page_source,
                audit=audit,
            )

    def _recognize_page_math(
        self,
        image: Image.Image,
        mode: str,
        engine: str,
        text_lines: list[TextLine] | None = None,
        page_source: Any | None = None,
    ) -> list[RegionResult]:
        started = time.perf_counter()
        self._equation_label_boxes: list[Box] = []
        detector = self._registry.detector()
        if hasattr(detector, "detect_detailed"):
            detected_details = detector.detect_detailed(image)
        else:  # Test doubles and third-party plugins retain the original API.
            detected_details = [
                MathDetection(box=box, category=category, source_index=index)
                for index, (box, category) in enumerate(detector.detect(image), start=1)
            ]
        logger.info(
            "Math detection timing | image=%sx%s | detections=%s | elapsed=%.2fs",
            image.width,
            image.height,
            len(detected_details),
            time.perf_counter() - started,
        )
        table_cell_rects = getattr(page_source, "table_cell_rects", None) if page_source else None
        accepted, review, upgrades, upgraded_indexes = self._filter_math_detections(
            image,
            detected_details,
            text_lines if mode == "document" else None,
        )
        boxes = [item.box for item in accepted]
        separators = [line.box for line in text_lines or []]
        regions = plan_regions(
            image.width,
            image.height,
            boxes,
            # Only explicit formula mode is permitted to interpret a small
            # empty image as a formula.  Mixed/document inputs are pages.
            assume_small_is_formula=(mode == "mixed" and text_lines is None),
            separators=separators,
        )
        self._last_math_audit = {
            "detected_math_regions": [
                {
                    "id": item.source_index,
                    "box": _box_tuple(item.box),
                    "category": item.category,
                    "confidence": item.confidence,
                    "decision": (
                        "upgraded-to-display"
                        if item.source_index in upgraded_indexes
                        else ("accepted" if item in accepted else "review")
                    ),
                }
                for item in detected_details
            ],
            "review_math_regions": review,
            "upgraded_math_regions": upgrades,
            "planned_math_regions": [] if regions is None else [_box_tuple(box) for box in regions],
            "whole_image_formula": regions is None,
        }
        if regions is None:
            full_asset_id: str | None = None
            try:
                from backend.assets import default_asset_store

                asset = default_asset_store.store_image(
                    image,
                    source_page=1,
                    bbox=(0, 0, image.width, image.height),
                    metadata={
                        "purpose": "math-region-crop",
                        "kind": "full",
                        "coordinate_space": "image_pixels",
                        "source_bbox": (0, 0, image.width, image.height),
                    },
                )
                full_asset_id = asset.asset_id
            except Exception as store_err:
                logger.warning("Could not store full image asset: %s", store_err)

            full_res = self._recognize_region(image, engine, kind="full")
            full_res.box = (0, 0, image.width, image.height)
            full_res.asset_id = full_asset_id
            self._validate_region_result(full_res)
            return [full_res]

        results: list[RegionResult] = []
        for region in regions:
            kind = self._region_kind(region, [(item.box, item.category) for item in accepted])
            crop_box = padded_crop_box(region, image.width, image.height)
            crop_tuple = (
                int(crop_box.left),
                int(crop_box.top),
                int(crop_box.right),
                int(crop_box.bottom),
            )
            crop = image.crop(crop_tuple)
            crop_asset_id: str | None = None
            try:
                from backend.assets import default_asset_store

                asset = default_asset_store.store_image(
                    crop,
                    source_page=1,
                    bbox=crop_tuple,
                    metadata={
                        "purpose": "math-region-crop",
                        "kind": kind,
                        "coordinate_space": "image_pixels",
                        "source_bbox": crop_tuple,
                    },
                )
                crop_asset_id = asset.asset_id
            except Exception as store_err:
                logger.warning("Could not store equation crop asset: %s", store_err)

            try:
                result = self._recognize_region(crop, engine, kind=kind)
            finally:
                crop.close()
            if not result.latex:
                if kind != "embedded" and crop_asset_id:
                    fallback_res = RegionResult(
                        latex=r"\text{[equation]}",
                        engine=engine,
                        confidence=0.0,
                        box=(int(region.left), int(region.top), int(region.right), int(region.bottom)),
                        kind=kind,
                        asset_id=crop_asset_id,
                        fallback_image=True,
                    )
                    results.append(fallback_res)
                continue
            if kind == "embedded" and _is_trivial_embedded(result.latex):
                continue
            result.box = (
                int(region.left),
                int(region.top),
                int(region.right),
                int(region.bottom),
            )
            result.asset_id = crop_asset_id
            self._validate_region_result(result)
            if crop_asset_id:
                try:
                    from backend.assets import default_asset_store

                    asset_obj = default_asset_store.get(crop_asset_id)
                    if asset_obj:
                        asset_obj.metadata.update(
                            {
                                "confidence": result.confidence,
                                "recognized_candidate": result.latex,
                                "fallback_reason": (
                                    ", ".join(result.review_flags) if result.review_flags else None
                                ),
                                "render_mode": "image_fallback" if result.fallback_image else "omml",
                            }
                        )
                except Exception:
                    pass
            results.append(result)
        if text_lines:
            self._associate_equation_numbers(image, results, text_lines)
        return results

    def _filter_math_detections(
        self,
        image: Image.Image,
        detections: list[MathDetection],
        text_lines: list[TextLine] | None,
    ) -> tuple[list[MathDetection], list[dict[str, Any]], list[dict[str, Any]], set[int]]:
        """Rank detector output before sending crops to a formula recognizer.

        In document mode, isolated detector boxes are plausible display math.
        Embedded boxes are only accepted if ordinary OCR has not already read
        the same region.  The latter rule prevents a coloured example sentence
        from becoming a formula solely because it contains a few symbols.
        Unaccepted boxes are stored as crop assets for review, never silently
        treated as deleted page content.
        """
        accepted: list[MathDetection] = []
        review: list[dict[str, Any]] = []
        upgrades: list[dict[str, Any]] = []
        upgraded_indexes: set[int] = set()
        min_width = max(18.0, image.width * 0.025)
        min_height = max(8.0, image.height * 0.012)
        for detection in detections:
            reason: str | None = None
            covering_line: TextLine | None = None
            if detection.box.width < min_width or detection.box.height < min_height:
                reason = "too small to be a complete formula region"
            elif text_lines is not None and detection.category == "embedded":
                max_text_overlap = 0.0
                for line in text_lines:
                    overlap = _overlap_fraction(detection.box, line.box)
                    if overlap > max_text_overlap:
                        max_text_overlap = overlap
                        covering_line = line
                if max_text_overlap >= 0.45:
                    if self._is_numbered_display_candidate(image, detection, covering_line, text_lines):
                        # OCR read the formula as a short text line and the
                        # right margin carries its equation number: treat the
                        # region as display math so the number stays attached
                        # and the line is re-read by the formula engines.
                        upgraded = replace(detection, category="isolated")
                        accepted.append(upgraded)
                        upgraded_indexes.add(detection.source_index)
                        upgrades.append(
                            {
                                "id": detection.source_index,
                                "box": _box_tuple(detection.box),
                                "covering_text": covering_line.text if covering_line else "",
                                "reason": "short formula text with aligned equation number label",
                            }
                        )
                        continue
                    reason = "embedded region is already covered by an OCR text line"
                elif (
                    detection.box.width < 0.06 * image.width
                    or detection.box.height < 0.016 * image.height
                ):
                    reason = "small inline symbol retained in text OCR rather than promoted to formula"

            if reason is None:
                accepted.append(detection)
                continue

            crop_asset_id = self._store_review_crop(image, detection, reason)
            review.append(
                {
                    "id": detection.source_index,
                    "box": _box_tuple(detection.box),
                    "category": detection.category,
                    "confidence": detection.confidence,
                    "reason": reason,
                    "source_crop_asset_id": crop_asset_id,
                }
            )
        return accepted, review, upgrades, upgraded_indexes

    @staticmethod
    def _is_numbered_display_candidate(
        image: Image.Image,
        detection: MathDetection,
        covering_line: TextLine | None,
        text_lines: list[TextLine],
    ) -> bool:
        """Detect an OCR-read short formula that carries a numbered label.

        A detector box classified as ``embedded`` is normally left in ordinary
        text.  But when the covering text is itself a short formula-like line
        *and* a label-shaped line such as ``...(2)`` sits to its right at the
        same height, the source clearly shows a numbered display equation that
        plain OCR happened to read correctly as text.
        """

        if covering_line is None:
            return False
        if not _looks_like_formula_text(covering_line.text):
            return False
        horizontal_overlap = _overlap_fraction(covering_line.box, detection.box)
        if horizontal_overlap < 0.55:
            return False
        line_center_y = (covering_line.box.top + covering_line.box.bottom) / 2
        tolerance = max(16.0, detection.box.height * 0.9)
        for line in text_lines:
            if line is covering_line:
                continue
            if line.box.left < max(detection.box.right + 4, image.width * 0.72):
                continue
            if abs((line.box.top + line.box.bottom) / 2 - line_center_y) > tolerance:
                continue
            if _parse_equation_number(line.text):
                return True
        return False

    @staticmethod
    def _store_review_crop(
        image: Image.Image, detection: MathDetection, reason: str
    ) -> str | None:
        """Retain a rejected detector crop in the normal in-memory asset store."""

        try:
            from backend.assets import default_asset_store

            crop_box = padded_crop_box(detection.box, image.width, image.height)
            crop = image.crop(
                (int(crop_box.left), int(crop_box.top), int(crop_box.right), int(crop_box.bottom))
            )
            try:
                asset = default_asset_store.store_image(
                    crop,
                    source_page=1,
                    bbox=_box_tuple(detection.box),
                    metadata={
                        "purpose": "math-region-review",
                        "detector_category": detection.category,
                        "reason": reason,
                    },
                )
                return asset.asset_id
            finally:
                crop.close()
        except Exception as error:
            logger.warning("Could not retain review crop for math region %s: %s", detection.source_index, error)
            return None

    @staticmethod
    def _validate_region_result(result: RegionResult) -> None:
        """Flag weak mathematical readings and mark fallback_image when below threshold."""

        if result.confidence is not None and result.confidence < 0.80:
            result.review_flags.append(f"low ensemble confidence ({result.confidence:.2f} < 0.80)")
            result.fallback_image = True
        if result.alternatives:
            best_alternative = max(
                (similarity(result.latex, alternative.latex) for alternative in result.alternatives),
                default=1.0,
            )
            if best_alternative < 0.45:
                result.review_flags.append("formula engines substantially disagree")
                result.fallback_image = True
        if structure_score(result.latex) < 0.45:
            result.review_flags.append("formula failed structural sanity check")
            result.fallback_image = True

    def _associate_equation_numbers(
        self,
        image: Image.Image,
        results: list[RegionResult],
        text_lines: list[TextLine],
    ) -> None:
        """Attach right-side equation labels to their display-math blocks.

        The label is read separately from the formula crop.  This avoids asking
        a formula model to interpret ellipses and tiny numerals, and preserves
        the label as metadata rather than an unrelated body paragraph.
        """

        label_boxes: list[Box] = []
        events: list[dict[str, Any]] = []
        for result in results:
            if result.kind == "embedded" or result.box is None:
                continue
            formula_box = Box(*result.box)
            center_y = (formula_box.top + formula_box.bottom) / 2
            nearby = [
                line
                for line in text_lines
                if line.box.left >= max(formula_box.right + 4, image.width * 0.72)
                and abs((line.box.top + line.box.bottom) / 2 - center_y)
                <= max(16.0, formula_box.height * 0.9)
            ]
            nearby.sort(key=lambda line: (abs((line.box.top + line.box.bottom) / 2 - center_y), line.box.left))
            raw = " ".join(line.text for line in nearby[:2])
            number = _parse_equation_number(raw)
            if number:
                result.numbering = number
                label_boxes.extend(line.box for line in nearby[:2])
                events.append({"formula_box": result.box, "number": result.numbering, "source": "page OCR"})
                continue

            # If page OCR read the formula number as punctuation/noise, a small
            # high-resolution right-margin crop is much more reliable.  It is
            # still an OCR result, never a number inferred from equation order.
            possible_right_label = bool(nearby) or formula_box.right < 0.65 * image.width
            number = self._read_equation_number_crop(image, formula_box) if possible_right_label else None
            if number:
                result.numbering = number
                label_boxes.extend(line.box for line in nearby[:2])
                events.append({"formula_box": result.box, "number": number, "source": "label crop OCR"})
            elif nearby:
                result.review_flags.append("possible equation number could not be read")
                events.append({"formula_box": result.box, "number": None, "source": "unreadable page OCR"})

        self._equation_label_boxes = label_boxes
        self._last_math_audit["equation_numbers"] = events

    @staticmethod
    def _read_equation_number_crop(image: Image.Image, formula_box: Box) -> str | None:
        if importlib.util.find_spec("pytesseract") is None or find_tesseract_binary() is None:
            return None
        # The right margin is deliberately bounded: applying a text recognizer
        # to the entire row would merely repeat formula OCR's weak result.
        left = int(max(formula_box.right + 4, image.width * 0.72))
        right = int(image.width * 0.97)
        top = int(max(0, formula_box.top - max(10.0, formula_box.height * 0.35)))
        bottom = int(min(image.height, formula_box.bottom + max(10.0, formula_box.height * 0.35)))
        if right <= left + 8 or bottom <= top + 8:
            return None
        crop = image.crop((left, top, right, bottom)).convert("L")
        try:
            crop = crop.resize((crop.width * 4, crop.height * 4), Image.Resampling.LANCZOS)
            import pytesseract

            pytesseract.pytesseract.tesseract_cmd = find_tesseract_binary() or "tesseract"
            for psm in (7, 8, 11, 6):
                reading = pytesseract.image_to_string(crop, lang="eng", config=f"--psm {psm}")
                match = _parse_equation_number(reading)
                if match:
                    return match
        except Exception as error:
            logger.debug("Equation-number crop OCR failed: %s", error)
        finally:
            crop.close()
        return None

    def _assemble_document(
        self,
        image: Image.Image,
        regions: list[RegionResult],
        text_lines: list[TextLine],
        page_source: Any | None = None,
        audit: dict[str, Any] | None = None,
    ) -> PageOutcome:
        """Add page text, figures, and geometry around the recognized formulas to build a document."""

        # Suppress only a line substantially covered by an accepted *display*
        # formula.  The previous symmetric 45%/75% test could drop an entire
        # sentence because one small inline detector box crossed a word.
        math_boxes = [Box(*result.box) for result in regions if result.box is not None]
        display_boxes = [
            Box(*result.box)
            for result in regions
            if result.box is not None and result.kind != "embedded"
        ]
        equation_label_boxes = getattr(self, "_equation_label_boxes", [])
        kept_text: list[TextLine] = []
        suppressed_text: list[dict[str, Any]] = []
        for line in text_lines:
            if any(_overlap_fraction(line.box, label) >= 0.7 for label in equation_label_boxes):
                suppressed_text.append(
                    {"text": line.text, "box": _box_tuple(line.box), "reason": "equation number label"}
                )
                continue
            formula_overlap = max((_overlap_fraction(line.box, box) for box in display_boxes), default=0.0)
            if formula_overlap >= 0.60:
                suppressed_text.append(
                    {"text": line.text, "box": _box_tuple(line.box), "reason": "covered by display formula"}
                )
                continue
            kept_text.append(line)

        figures = []
        table_cell_rects = []
        page_num = 1
        if page_source is not None:
            raw_figures = list(getattr(page_source, "figures", []))
            table_cell_rects = list(getattr(page_source, "table_cell_rects", []))
            page_num = getattr(page_source, "page_number", 1)
            # Filter out figures that overlap with detected math regions (equations are not diagrams)
            for fig in raw_figures:
                math_overlap = max((_overlap_fraction(fig.box, mbox) for mbox in math_boxes), default=0.0)
                if math_overlap < 0.35:
                    figures.append(fig)
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
        document_audit = dict(audit or {})
        document_audit["kept_text_lines"] = [
            {
                "text": line.text,
                "confidence": round(line.confidence, 4),
                "engine": line.engine,
                "box": _box_tuple(line.box),
            }
            for line in kept_text
        ]
        document_audit["suppressed_text_lines"] = suppressed_text
        doc.metadata["ocr_audit"] = document_audit
        for result in regions:
            for flag in result.review_flags:
                doc.warnings.append(
                    f"Equation at {result.box or 'unknown region'} requires review: {flag}."
                )
        review_regions = document_audit.get("review_math_regions", [])
        if review_regions:
            doc.warnings.append(
                f"{len(review_regions)} math detector regions were retained in the OCR audit with source crops "
                "rather than exported as standalone equations."
            )
        markdown = doc.to_markdown()
        return PageOutcome(regions=regions, markdown=markdown, document=doc, audit=document_audit)

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

        # OMML validation fallback: if the elected winner fails Pandoc conversion,
        # fallback to the highest-scoring alternative that converts cleanly.
        if alternatives:
            from backend.omml import validate_equation

            winner_valid, _ = validate_equation(winner.latex)
            if not winner_valid:
                for alt in alternatives:
                    alt_valid, _ = validate_equation(alt.latex)
                    if alt_valid and structure_score(alt.latex) >= 0.5:
                        logger.info(
                            "Winner formula from %s failed OMML validation; promoted valid alternative from %s",
                            winner.engine,
                            alt.engine,
                        )
                        alternatives = [winner] + [a for a in alternatives if a.engine != alt.engine]
                        winner = alt
                        break
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
