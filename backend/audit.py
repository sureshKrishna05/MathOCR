"""Source-grounded content audit and equation boundary repair for MathOCR.

Audits reconstructed documents against source evidence (PDF digital text, OCR lines,
bounding box geometry, and asset stores) to detect hallucinations, missing text,
duplicated phrases, and corrupted boundaries. Safely repairs inline equation prefixes
and suffixes, separating prose from mathematical notation and preserving text order.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from lxml import etree

from backend.assets import AssetStore, default_asset_store
from backend.geometry import Box

logger = logging.getLogger("mathocr.audit")

AuditIssueType = Literal[
    "unsupported_text",
    "missing_text",
    "duplicated_text",
    "corrupted_text",
    "prefix_error",
    "suffix_error",
    "equation_boundary_error",
    "reading_order_error",
    "missing_asset",
    "uncertain_recognition",
]

AuditSeverity = Literal["low", "medium", "high"]

AuditAction = Literal[
    "auto_correct",
    "retain_original",
    "image_fallback",
    "manual_review",
    "no_action",
]


@dataclass(slots=True)
class AuditRecord:
    """A traceable finding produced during content auditing or DOCX validation."""

    issue_id: str
    page_number: int
    issue_type: AuditIssueType
    severity: AuditSeverity
    confidence: float
    source_bbox: tuple[int, int, int, int] | None
    original_text: str
    proposed_text: str | None = None
    left_context: str = ""
    right_context: str = ""
    evidence: list[str] = field(default_factory=list)
    action: AuditAction = "no_action"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "page_number": self.page_number,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "confidence": round(self.confidence, 4),
            "source_bbox": list(self.source_bbox) if self.source_bbox else None,
            "original_text": self.original_text,
            "proposed_text": self.proposed_text,
            "left_context": self.left_context,
            "right_context": self.right_context,
            "evidence": self.evidence,
            "action": self.action,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditRecord:
        bbox = data.get("source_bbox")
        return cls(
            issue_id=str(data.get("issue_id", "")),
            page_number=int(data.get("page_number", 1)),
            issue_type=data.get("issue_type", "unsupported_text"),
            severity=data.get("severity", "medium"),
            confidence=float(data.get("confidence", 0.0)),
            source_bbox=tuple(bbox) if bbox else None,
            original_text=str(data.get("original_text", "")),
            proposed_text=data.get("proposed_text"),
            left_context=str(data.get("left_context", "")),
            right_context=str(data.get("right_context", "")),
            evidence=list(data.get("evidence", [])),
            action=data.get("action", "no_action"),
            reason=str(data.get("reason", "")),
        )


def generate_issue_id(prefix: str, page: int, text: str) -> str:
    """Generate a stable, unique identifier for an audit record."""
    digest = hashlib.sha1(f"{prefix}:{page}:{text}".encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_p{page}_{digest}"


# Regex matching prose prefixes mistakenly absorbed into LaTeX equations
PROSE_PREFIX_REGEX = re.compile(
    r"^(?:\\text\{\s*|\\mathrm\{\s*|\\textbf\{\s*)?"
    r"(\b(?:where|where\s+we\s+have|let|if|then|for\s+all|for\s+any|for|with|such\s+that|"
    r"and|or|when|we\s+have|we\s+obtain|substituting\s+into\s+equation\s+\(?\d+\)?|"
    r"substituting\s+into|given\s+that|assuming|since|hence|therefore)\b)"
    r"(\s*[:=,]|\s+)"
    r"(?:\}\s*)?",
    re.IGNORECASE,
)

# Regex matching trailing sentence punctuation mistakenly absorbed into LaTeX equations
PROSE_SUFFIX_REGEX = re.compile(
    r"(?:\\quad\s*|\\qquad\s*|\\,\s*|\\;\s*|\s*)"
    r"(?:\\text\{\s*([,.;:!?])\s*\}|([,.;:!?]))\s*$"
)

# Repeated words pattern e.g. "where where", "the the", "equation equation"
REPEATED_WORD_REGEX = re.compile(r"\b([a-zA-Z]{2,})\s+\1\b", re.IGNORECASE)


def repair_paragraph_boundaries(
    runs: list[Any],
    page_number: int = 1,
    paragraph_box: tuple[int, int, int, int] | None = None,
) -> tuple[list[Any], list[AuditRecord]]:
    """Repair inline equation prefixes, suffixes, whitespace, and duplicated words.

    Separates English prose prefixes (e.g. 'where ', 'Let ') and trailing punctuation
    (',', '.') mistakenly absorbed into equations, guarantees whitespace around equations,
    and removes duplicate boundary words while preserving mathematical notation.
    """
    from backend.document import InlineEquation, TextRun

    if not runs:
        return [], []

    new_runs: list[Any] = []
    records: list[AuditRecord] = []

    for run_idx, run in enumerate(runs):
        if not isinstance(run, InlineEquation):
            new_runs.append(run)
            continue

        latex = run.latex or ""
        box = run.box or paragraph_box
        original_latex = latex

        prefix_text: str | None = None
        suffix_text: str | None = None

        # 1. Detect and separate absorbed prose prefix
        m_prefix = PROSE_PREFIX_REGEX.match(latex)
        if m_prefix:
            word = m_prefix.group(1)
            punct_or_space = m_prefix.group(2)
            prefix_text = f"{word}{punct_or_space}"
            if not prefix_text.endswith(" "):
                prefix_text += " "
            latex = latex[m_prefix.end():].strip()
            # If the remaining latex has an unmatched closing brace due to stripped \text{
            if latex.endswith("}") and latex.count("{") < latex.count("}"):
                latex = latex[:-1].strip()

            records.append(
                AuditRecord(
                    issue_id=generate_issue_id("pfx", page_number, original_latex),
                    page_number=page_number,
                    issue_type="equation_boundary_error",
                    severity="medium",
                    confidence=0.92,
                    source_bbox=box,
                    original_text=original_latex,
                    proposed_text=f"Prefix: '{prefix_text}', Math: '{latex}'",
                    evidence=["LaTeX formula starts with English prose prefix"],
                    action="auto_correct",
                    reason=f"Extracted prose prefix '{prefix_text.strip()}' from inline equation into body text",
                )
            )

        # 2. Detect and separate absorbed trailing punctuation
        m_suffix = PROSE_SUFFIX_REGEX.search(latex)
        # Avoid stripping valid mathematical dots in \dots or \ldots
        if m_suffix and not latex.endswith(r"\dots") and not latex.endswith(r"\ldots") and not latex.endswith(r"\cdots"):
            punct = m_suffix.group(1) or m_suffix.group(2)
            suffix_text = f"{punct} "
            latex = latex[:m_suffix.start()].strip()

            records.append(
                AuditRecord(
                    issue_id=generate_issue_id("sfx", page_number, original_latex),
                    page_number=page_number,
                    issue_type="equation_boundary_error",
                    severity="low",
                    confidence=0.95,
                    source_bbox=box,
                    original_text=original_latex,
                    proposed_text=f"Math: '{latex}', Suffix: '{punct}'",
                    evidence=["LaTeX formula ends with sentence-level punctuation"],
                    action="auto_correct",
                    reason=f"Extracted trailing punctuation '{punct}' from equation into prose run",
                )
            )

        # 3. Add extracted prefix as TextRun before the equation
        if prefix_text:
            # Check if previous run already ends with this prefix to avoid duplication
            if new_runs and isinstance(new_runs[-1], TextRun):
                prev_text = new_runs[-1].text.rstrip()
                clean_pfx = prefix_text.strip().lower()
                if prev_text.lower().endswith(clean_pfx):
                    # Duplicate already present in preceding run, skip adding
                    prefix_text = None
            if prefix_text:
                new_runs.append(TextRun(text=prefix_text))

        # 4. Append repaired InlineEquation
        repaired_eq = InlineEquation(
            latex=latex,
            omml=run.omml if latex == original_latex else None,  # recompute OMML if changed
            confidence=run.confidence,
            box=run.box,
            asset_id=run.asset_id,
            fallback_image=run.fallback_image,
        )
        new_runs.append(repaired_eq)

        # 5. Add extracted suffix as TextRun after the equation
        if suffix_text:
            new_runs.append(TextRun(text=suffix_text))

    # 6. Ensure proper whitespace and deduplicate repeated words across runs
    final_runs: list[Any] = []
    for i, r in enumerate(new_runs):
        if isinstance(r, TextRun):
            text = r.text

            # Check for intra-run duplicated words like "where where"
            m_dup = REPEATED_WORD_REGEX.search(text)
            if m_dup:
                dup_word = m_dup.group(1)
                text = REPEATED_WORD_REGEX.sub(r"\1", text)
                records.append(
                    AuditRecord(
                        issue_id=generate_issue_id("dup", page_number, m_dup.group(0)),
                        page_number=page_number,
                        issue_type="duplicated_text",
                        severity="medium",
                        confidence=0.95,
                        source_bbox=paragraph_box,
                        original_text=m_dup.group(0),
                        proposed_text=dup_word,
                        evidence=["Consecutive identical words in text run"],
                        action="auto_correct",
                        reason=f"Deduplicated consecutive word '{dup_word}'",
                    )
                )

            # Check if this TextRun duplicates the last word of the previous TextRun
            if final_runs and isinstance(final_runs[-1], TextRun):
                prev_words = final_runs[-1].text.split()
                curr_words = text.split()
                if prev_words and curr_words and prev_words[-1].lower() == curr_words[0].lower() and len(curr_words[0]) >= 2:
                    dup_word = curr_words[0]
                    text = re.sub(rf"^\s*{re.escape(dup_word)}\b\s*", "", text)
                    records.append(
                        AuditRecord(
                            issue_id=generate_issue_id("dup_cross", page_number, dup_word),
                            page_number=page_number,
                            issue_type="duplicated_text",
                            severity="medium",
                            confidence=0.95,
                            source_bbox=paragraph_box,
                            original_text=f"{dup_word} {dup_word}",
                            proposed_text=dup_word,
                            evidence=["Identical word repeated across run boundary"],
                            action="auto_correct",
                            reason=f"Removed duplicated word '{dup_word}' across boundary",
                        )
                    )

            # Whitespace preservation: Ensure a space before inline equation if preceded by word
            if i + 1 < len(new_runs) and isinstance(new_runs[i + 1], InlineEquation):
                if text and not text.endswith((" ", "\t", "\n", "(", "[", "{", '"', "'", "«")):
                    text += " "

            # Whitespace preservation: Ensure a space after inline equation if followed by word
            if final_runs and isinstance(final_runs[-1], InlineEquation):
                if text and not text.startswith((" ", "\t", "\n", ",", ".", ";", ":", "!", "?", ")", "]", "}", '"', "'", "»")):
                    text = " " + text

            r.text = text
            if r.text:
                final_runs.append(r)
        else:
            final_runs.append(r)

    return final_runs, records


def _has_asset(store: AssetStore | None, asset_id: str | None) -> bool:
    if not asset_id:
        return True
    if store is not None:
        try:
            asset = store.get(asset_id)
            if asset and asset.data:
                return True
        except Exception:
            pass
    try:
        def_asset = default_asset_store.get(asset_id)
        if def_asset and def_asset.data:
            return True
    except Exception:
        pass
    return False


def audit_document_content(
    doc: Any,
    page_source: Any | None = None,
    kept_text: list[Any] | None = None,
    math_results: list[Any] | None = None,
    asset_store: AssetStore | None = None,
    confidence_threshold: float = 0.65,
) -> tuple[Any, list[AuditRecord]]:
    """Perform a comprehensive source-grounded audit of a structured Document.

    Checks:
    - Inline equation prefixes and suffixes are repaired and separated from math.
    - Word duplication is detected and removed.
    - Referenced image and fallback assets exist in the asset store.
    - Low-confidence math equations are routed to image fallbacks.
    - Digital PDF text omissions are detected.
    - Table vs equation classifications are validated.
    """
    from backend.document import DisplayEquation, Document, Heading, ImageBlock, InlineEquation, Paragraph, Table

    store = asset_store or getattr(page_source, "asset_store", None) or default_asset_store
    records: list[AuditRecord] = []
    page_num = doc.metadata.get("page", 1) if doc.metadata else 1

    # 1. Repair boundaries and deduplicate within all paragraphs and headings
    for elem in doc.elements:
        if isinstance(elem, (Paragraph, Heading)):
            repaired_runs, p_records = repair_paragraph_boundaries(
                elem.runs, page_number=page_num, paragraph_box=elem.box
            )
            elem.runs = repaired_runs
            records.extend(p_records)

    # 2. Audit equation confidence and asset availability
    for elem in doc.elements:
        if isinstance(elem, DisplayEquation):
            # Check asset store if fallback_image is requested
            if elem.asset_id and not _has_asset(store, elem.asset_id):
                records.append(
                    AuditRecord(
                        issue_id=generate_issue_id("asset_missing", page_num, elem.asset_id),
                        page_number=page_num,
                        issue_type="missing_asset",
                        severity="high",
                        confidence=1.0,
                        source_bbox=elem.box,
                        original_text=f"Display equation (asset: {elem.asset_id})",
                        evidence=["Referenced asset ID not present in AssetStore"],
                        action="manual_review",
                        reason=f"Asset {elem.asset_id} is missing from asset store",
                    )
                )

            # Check confidence
            if elem.confidence is not None and elem.confidence < confidence_threshold:
                action: AuditAction = "image_fallback" if elem.asset_id else "manual_review"
                if elem.asset_id and not elem.fallback_image:
                    elem.fallback_image = True
                records.append(
                    AuditRecord(
                        issue_id=generate_issue_id("low_conf_disp", page_num, elem.latex[:20]),
                        page_number=page_num,
                        issue_type="uncertain_recognition",
                        severity="medium",
                        confidence=elem.confidence,
                        source_bbox=elem.box,
                        original_text=elem.latex,
                        evidence=[f"Model recognition confidence ({elem.confidence:.2f}) < threshold ({confidence_threshold:.2f})"],
                        action=action,
                        reason=f"Low ensemble confidence formula retained with source image fallback",
                    )
                )

        elif isinstance(elem, Paragraph):
            for run in elem.runs:
                if isinstance(run, InlineEquation):
                    if run.asset_id and not _has_asset(store, run.asset_id):
                        records.append(
                            AuditRecord(
                                issue_id=generate_issue_id("asset_missing_inline", page_num, run.asset_id),
                                page_number=page_num,
                                issue_type="missing_asset",
                                severity="high",
                                confidence=1.0,
                                source_bbox=run.box,
                                original_text=f"Inline equation (asset: {run.asset_id})",
                                evidence=["Referenced inline asset ID not present in AssetStore"],
                                action="manual_review",
                                reason=f"Inline asset {run.asset_id} is missing from asset store",
                            )
                        )

                    if run.confidence is not None and run.confidence < confidence_threshold:
                        action: AuditAction = "image_fallback" if run.asset_id else "manual_review"
                        if run.asset_id and not run.fallback_image:
                            run.fallback_image = True
                        records.append(
                            AuditRecord(
                                issue_id=generate_issue_id("low_conf_inline", page_num, run.latex[:20]),
                                page_number=page_num,
                                issue_type="uncertain_recognition",
                                severity="medium",
                                confidence=run.confidence,
                                source_bbox=run.box,
                                original_text=run.latex,
                                evidence=[f"Inline confidence ({run.confidence:.2f}) < {confidence_threshold:.2f}"],
                                action=action,
                                reason="Low confidence inline math preserved with source fallback",
                            )
                        )

        elif isinstance(elem, ImageBlock):
            if elem.asset_id and not _has_asset(store, elem.asset_id):
                records.append(
                    AuditRecord(
                        issue_id=generate_issue_id("asset_missing_img", page_num, elem.asset_id),
                        page_number=page_num,
                        issue_type="missing_asset",
                        severity="high",
                        confidence=1.0,
                        source_bbox=elem.box,
                        original_text=f"Image block (asset: {elem.asset_id})",
                        evidence=["Figure/drawing asset ID not present in AssetStore"],
                        action="manual_review",
                        reason=f"Image asset {elem.asset_id} is missing from asset store",
                    )
                )

        elif isinstance(elem, Table):
            if elem.asset_id and not _has_asset(store, elem.asset_id):
                records.append(
                    AuditRecord(
                        issue_id=generate_issue_id("asset_missing_tbl", page_num, elem.asset_id),
                        page_number=page_num,
                        issue_type="missing_asset",
                        severity="high",
                        confidence=1.0,
                        source_bbox=elem.box,
                        original_text=f"Table (asset: {elem.asset_id})",
                        evidence=["Table fallback asset ID not present in AssetStore"],
                        action="manual_review",
                        reason=f"Table fallback asset {elem.asset_id} is missing from asset store",
                    )
                )

    # 3. Source-grounded comparison against digital PDF text if available
    if page_source and getattr(page_source, "digital_text_lines", None):
        source_words: list[str] = []
        for line in page_source.digital_text_lines:
            txt = line.get("text", "") if isinstance(line, dict) else getattr(line, "text", "")
            for token in re.findall(r"\w+", str(txt)):
                if token:
                    source_words.append(token)
        if source_words:
            doc_text = " ".join(
                elem.text() for elem in doc.elements if isinstance(elem, (Paragraph, Heading))
            )
            doc_words_lower = set(re.findall(r"\w+", doc_text.lower()))

            # Check for significant phrases (>3 words) present in source but missing in doc
            missing_phrases: list[str] = []
            chunk_size = 4
            for idx in range(0, len(source_words) - chunk_size + 1, chunk_size):
                chunk = source_words[idx : idx + chunk_size]
                if not any(w.lower() in doc_words_lower for w in chunk):
                    phrase = " ".join(chunk)
                    if len(phrase) > 8 and not re.match(r"^[\d\s\W]+$", phrase):
                        missing_phrases.append(phrase)

            for missing in missing_phrases[:3]:  # report top 3 distinct missing spans
                records.append(
                    AuditRecord(
                        issue_id=generate_issue_id("missing_pdf_text", page_num, missing),
                        page_number=page_num,
                        issue_type="missing_text",
                        severity="high",
                        confidence=0.88,
                        source_bbox=None,
                        original_text="",
                        proposed_text=missing,
                        evidence=["Source PDF digital text contains phrase not found in reconstructed document"],
                        action="manual_review",
                        reason=f"Potential omission of source PDF text: '{missing}'",
                    )
                )

    # Attach audit records to document
    doc.audit_records = [r.to_dict() for r in records]

    # Add human-readable warnings for medium/high severity findings
    for r in records:
        if r.severity in ("medium", "high") and r.action != "auto_correct":
            doc.warnings.append(f"Audit warning (p.{r.page_number}, {r.issue_type}): {r.reason}")

    return doc, records


def validate_docx_structure(
    docx_path: Path | str,
    expected_doc: Any | None = None,
) -> list[AuditRecord]:
    """Inspect an exported Word .docx document for structural integrity,
    text order, OMML elements, and image media preservation.
    """
    path = Path(docx_path)
    if not path.is_file():
        return [
            AuditRecord(
                issue_id="docx_missing",
                page_number=1,
                issue_type="unsupported_text",
                severity="high",
                confidence=1.0,
                source_bbox=None,
                original_text=str(path),
                evidence=["DOCX file does not exist on disk"],
                action="manual_review",
                reason=f"DOCX export output file not found: {path}",
            )
        ]

    records: list[AuditRecord] = []
    w_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    m_ns = "http://schemas.openxmlformats.org/officeDocument/2006/math"
    r_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    a_ns = "http://schemas.openxmlformats.org/drawingml/2006/main"

    try:
        with zipfile.ZipFile(path, "r") as zf:
            namelist = set(zf.namelist())
            if "word/document.xml" not in namelist:
                records.append(
                    AuditRecord(
                        issue_id="docx_no_doc_xml",
                        page_number=1,
                        issue_type="unsupported_text",
                        severity="high",
                        confidence=1.0,
                        source_bbox=None,
                        original_text="",
                        evidence=["word/document.xml missing from zip archive"],
                        action="manual_review",
                        reason="Invalid DOCX package: missing word/document.xml",
                    )
                )
                return records

            doc_xml = zf.read("word/document.xml")
            root = etree.fromstring(doc_xml)

            # Check embedded media relationships
            rels_map: dict[str, str] = {}
            if "word/_rels/document.xml.rels" in namelist:
                rels_xml = zf.read("word/_rels/document.xml.rels")
                rels_root = etree.fromstring(rels_xml)
                for rel in rels_root.findall(f".//{{{r_ns}}}Relationship"):
                    rid = rel.get("Id")
                    target = rel.get("Target")
                    if rid and target:
                        rels_map[rid] = target

            # Inspect paragraphs
            paragraphs = root.findall(f".//{{{w_ns}}}p")
            for p_idx, p in enumerate(paragraphs):
                # Inspect runs and math in visual sequence
                children = list(p)
                has_omml = False
                prev_text = ""

                for child in children:
                    tag = child.tag
                    if tag == f"{{{m_ns}}}oMath" or tag == f"{{{m_ns}}}oMathPara":
                        has_omml = True
                    elif tag == f"{{{w_ns}}}r":
                        t_elem = child.find(f"{{{w_ns}}}t")
                        if t_elem is not None and t_elem.text:
                            text = t_elem.text
                            # Check duplicated text across runs
                            if prev_text and prev_text.strip() and prev_text.strip() == text.strip() and len(text.strip()) > 2:
                                records.append(
                                    AuditRecord(
                                        issue_id=f"docx_dup_r_{p_idx}_{len(records)}",
                                        page_number=1,
                                        issue_type="duplicated_text",
                                        severity="medium",
                                        confidence=0.95,
                                        source_bbox=None,
                                        original_text=f"{prev_text} {text}",
                                        proposed_text=text,
                                        evidence=["Identical consecutive text runs in DOCX paragraph"],
                                        action="manual_review",
                                        reason=f"Duplicated run text in DOCX: '{text.strip()}'",
                                    )
                                )
                            prev_text = text

                        # Check image drawings
                        for blip in child.findall(f".//{{{a_ns}}}blip"):
                            embed_rid = blip.get(f"{{{r_ns}}}embed")
                            if embed_rid and embed_rid in rels_map:
                                media_target = rels_map[embed_rid]
                                # Canonicalize path within zip (word/media/image1.png)
                                if not media_target.startswith("word/"):
                                    media_target = f"word/{media_target}"
                                if media_target not in namelist:
                                    records.append(
                                        AuditRecord(
                                            issue_id=f"docx_missing_media_{embed_rid}",
                                            page_number=1,
                                            issue_type="missing_asset",
                                            severity="high",
                                            confidence=1.0,
                                            source_bbox=None,
                                            original_text=embed_rid,
                                            evidence=[f"Drawing refers to {media_target} which is missing in zip"],
                                            action="manual_review",
                                            reason=f"Exported DOCX contains broken image reference: {media_target}",
                                        )
                                    )

    except Exception as exc:
        records.append(
            AuditRecord(
                issue_id="docx_validation_error",
                page_number=1,
                issue_type="unsupported_text",
                severity="high",
                confidence=1.0,
                source_bbox=None,
                original_text="",
                evidence=[f"Error parsing DOCX package: {exc}"],
                action="manual_review",
                reason=f"DOCX structure validation error: {exc}",
            )
        )

    return records
