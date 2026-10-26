"""General document layout analysis and geometry-based reconstruction for MathOCR.

Reconstructs reading order, headings, multi-column flow, tables, figures,
captions, and filters headers/footers without subject-specific heuristics.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Literal

import cv2
import numpy as np
from PIL import Image

from backend.assets import AssetStore, default_asset_store
from backend.geometry import Box
from backend.pdf_source import ExtractedFigure


@dataclass
class LayoutBlock:
    """A classified layout region on a page with geometry and reading order."""

    id: str
    category: Literal[
        "paragraph",
        "heading",
        "display_equation",
        "inline_equation",
        "table",
        "figure",
        "caption",
        "list_item",
        "header",
        "footer",
        "page_number",
    ]
    box: Box
    page: int = 1
    reading_order: int = 0
    text: str = ""
    latex: str = ""
    asset_id: str | None = None
    caption: str | None = None
    level: int = 1  # For headings (1-6)
    alignment: str = "left"  # left | center | right | justify
    runs: list[Any] = field(default_factory=list)
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


CAPTION_PATTERN = re.compile(
    r"^(Figure|Fig\.|Illustration|Diagram|Plot|Graph|Chart|Table|Plate)\s*(\d+(\.\d+)*)?[:.\s-]*(.*)$",
    re.IGNORECASE,
)

HEADING_NUMBER_PATTERN = re.compile(
    r"^(\d+(?:\s*\.\s*\d+)*)\.?\s+([A-Z\u0370-\u03ff].*)$"
)

ACADEMIC_SECTION_KEYWORDS = re.compile(
    r"^(Abstract|Introduction|Theoretical Background|Methods|Methodology|Experimental|Results|"
    r"Discussion|Conclusion|References|Bibliography|Appendix|Exercises|Problems|"
    r"Overview|Preliminaries)\b",
    re.IGNORECASE,
)


def detect_scanned_figures(
    image: Image.Image,
    occupied_boxes: list[Box],
    asset_store: AssetStore | None = None,
    page_num: int = 1,
) -> list[ExtractedFigure]:
    """Detect figures, plots, and diagrams from raster/scanned pages using computer vision."""
    store = asset_store or default_asset_store
    w, h = image.size
    figures: list[ExtractedFigure] = []

    try:
        cv_img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

        # Mask out known text and math regions with padding
        mask = np.zeros((h, w), dtype=np.uint8)
        for box in occupied_boxes:
            x0 = max(0, int(box.left) - 4)
            y0 = max(0, int(box.top) - 4)
            x1 = min(w, int(box.right) + 4)
            y1 = min(h, int(box.bottom) + 4)
            cv2.rectangle(mask, (x0, y0), (x1, y1), 255, -1)

        # Invert gray and threshold
        _, thresh = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)
        thresh[mask == 255] = 0  # Remove text/math pixels

        # Morphological close to connect diagram strokes
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for c in contours:
            x, y, cw, ch = cv2.boundingRect(c)
            area = cw * ch
            # Filter noise and page margins/borders
            if cw < 60 or ch < 60 or area < 4000:
                continue
            if cw > 0.98 * w or ch > 0.95 * h:
                continue
            # Aspect ratio check (avoid thin lines/dividers)
            aspect = max(cw / ch, ch / cw)
            if aspect > 12.0:
                continue

            crop_box = (x, y, x + cw, y + ch)
            crop = image.crop(crop_box)
            buf = io.BytesIO()
            crop.save(buf, format="PNG")
            crop_bytes = buf.getvalue()
            crop.close()

            box_px = Box(float(x), float(y), float(x + cw), float(y + ch))
            asset = store.store_image(
                crop_bytes,
                mime_type="image/png",
                source_page=page_num,
                bbox=crop_box,
                metadata={"is_scanned_crop": True},
            )
            figures.append(
                ExtractedFigure(
                    asset_id=asset.asset_id,
                    box=box_px,
                    box_pt=(float(x) / 2.5, float(y) / 2.5, float(x + cw) / 2.5, float(y + ch) / 2.5),
                    mime_type="image/png",
                    source_page=page_num,
                    is_vector=False,
                )
            )
    except Exception:
        pass

    return figures


def filter_headers_footers(
    blocks: list[tuple[Box, str, Any]], page_height: float
) -> tuple[list[tuple[Box, str, Any]], list[tuple[Box, str, Any]], list[tuple[Box, str, Any]]]:
    """Separate running headers and footers/page numbers from main content."""
    body: list[tuple[Box, str, Any]] = []
    headers: list[tuple[Box, str, Any]] = []
    footers: list[tuple[Box, str, Any]] = []

    # Treat only the extreme top edge as a possible running header.  A tight
    # crop can begin within a paragraph, and a larger header zone was removing
    # valid opening lines from screenshots.
    top_margin = 0.05 * page_height
    bottom_margin = 0.92 * page_height
    header_zone = 0.09 * page_height

    # 1. Identify running header cues in the top zone to group all elements on the running header row
    cue_centers: list[float] = []
    for item in blocks:
        box, kind, payload = item
        if kind != "text":
            continue
        center_y = (box.top + box.bottom) / 2
        if center_y < header_zone:
            text = payload.text.strip()
            is_cue = bool(
                re.search(r"\b(?:Chap\.|Chapter)\s*\d+\b", text, re.I)
                or re.match(r"^Sec\.\s*\d+(?:\.\d+)*\b", text, re.I)
                or re.match(r"^[—–-]?\s*\d+\s*[—–-]?$", text)
                or re.search(r"\b(?:Running Header|Header)\b", text, re.I)
            ) and not re.match(r"^\s*(?:Theorem|Lemma|Proposition|Definition|Example|Exercise|Problem)\b", text, re.I)
            if is_cue:
                cue_centers.append(center_y)

    for item in blocks:
        box, kind, payload = item
        center_y = (box.top + box.bottom) / 2
        text = payload.text.strip() if kind == "text" else getattr(payload, "latex", "")

        # Header check (top 9% of page)
        if center_y < header_zone and kind == "text":
            is_row_peer = any(abs(center_y - cue_y) <= 18.0 for cue_y in cue_centers)
            words = re.findall(r"[A-Za-zÀ-ÿΑ-ω]+", text)
            looks_like_prose = len(words) >= 8 and any(word[:1].islower() for word in words[1:])
            not_prose_block = not re.match(r"^\s*(?:Theorem|Lemma|Proposition|Definition|Example|Exercise|Problem)\b", text, re.I)
            if (is_row_peer or (center_y < top_margin and len(text) < 100 and not looks_like_prose)) and not_prose_block:
                headers.append(item)
                continue

        # Footer check (bottom 8% of page)
        if center_y > bottom_margin:
            # Page number pattern: e.g. "— 1 —", "1", "Page 2"
            if re.match(r"^[—–-]?\s*\d+\s*[—–-]?$", text) or re.match(r"^Page\s+\d+", text, re.I):
                footers.append(item)
                continue
            # Copyright / publisher / metadata lines
            if (
                re.search(r"\b(copyright|isbn|doi|all rights reserved|printed in|published by|issn)\b", text, re.I)
                or text.startswith("©")
            ):
                footers.append(item)
                continue

        body.append(item)

    return body, headers, footers


def associate_captions(
    figures: list[ExtractedFigure],
    text_blocks: list[tuple[Box, str, Any]],
    line_height: float,
) -> tuple[list[ExtractedFigure], list[tuple[Box, str, Any]]]:
    """Associate adjacent caption text lines with their respective figures."""
    remaining_text: list[tuple[Box, str, Any]] = []
    claimed_text_indices: set[int] = set()

    for fig in figures:
        best_match_idx: int | None = None
        best_caption_text: str | None = None
        min_dist = float("inf")

        for idx, (tbox, kind, payload) in enumerate(text_blocks):
            if kind != "text":
                continue
            text = payload.text.strip()
            # Proximity: immediately below (preferable) or immediately above
            dist_below = tbox.top - fig.box.bottom
            dist_above = fig.box.top - tbox.bottom

            # Match explicit pattern
            m = CAPTION_PATTERN.match(text)
            if m:
                # If below within 3 line heights
                if 0 <= dist_below <= 3.5 * line_height:
                    best_match_idx = idx
                    best_caption_text = text
                    break
                # Or above within 2.5 line heights
                if 0 <= dist_above <= 2.5 * line_height:
                    best_match_idx = idx
                    best_caption_text = text
                    break

            # Only accept implicit captions if short, title-cased, non-numbered, and non-prose
            looks_like_short_title = (
                len(text) < 35
                and not re.match(r"^\s*\d", text)
                and not text.endswith((".", "!", "?", ",", ";", ":"))
                and (text.istitle() or text.isupper())
                and not any(w in text.lower().split() for w in ("in", "which", "where", "we", "call", "is", "are", "let", "the", "that", "this", "and"))
            )
            if looks_like_short_title and 0 <= dist_below <= 1.5 * line_height and dist_below < min_dist:
                fig_center = (fig.box.left + fig.box.right) / 2
                text_center = (tbox.left + tbox.right) / 2
                if abs(fig_center - text_center) < (fig.box.right - fig.box.left) * 0.4:
                    min_dist = dist_below
                    best_match_idx = idx
                    best_caption_text = text

        if best_match_idx is not None and best_caption_text:
            fig.caption = best_caption_text
            claimed_text_indices.add(best_match_idx)

    for idx, item in enumerate(text_blocks):
        if idx not in claimed_text_indices:
            remaining_text.append(item)

    return figures, remaining_text


def classify_heading_semantic(
    text: str,
    box: Box,
    page_width: float,
    median_h: float,
) -> tuple[bool, int, str]:
    """Classify headings based on numbering, keywords, and typography without domain hardcoding."""
    plain = text.strip()
    if not plain or len(plain) > 100:
        return False, 1, "left"

    box_width = box.right - box.left
    box_center = (box.left + box.right) / 2
    page_center = page_width / 2 if page_width > 0 else 0
    is_centered = (
        page_width > 0
        and abs(box_center - page_center) < 0.08 * page_width
        and abs(box.left - (page_width - box.right)) < 0.08 * page_width
        and box_width < 0.85 * page_width
    )
    align = "center" if is_centered else "left"

    # Titled theorems in research papers e.g. "Theorem 3.4 (Uniqueness of Solutions)" are headings
    if re.match(r"^\s*(?:Theorem|Lemma|Proposition|Definition|Corollary)\s+\d+(?:\.\d+)*\s*\([A-Z]", plain, re.I):
        return True, 2, align

    # Other theorem / lemma / definition / axiom statements are body theorem blocks, not headings
    if re.match(r"^\s*(?:Theorem|Lemma|Proposition|Definition|Corollary|Axiom|Proof|Example)\b", plain, re.I):
        return False, 1, "left"

    # Section title "Exercises" / "Problems" is centered
    if re.match(r"^\s*(?:exercises|problems)\b", plain, re.I) and len(plain) < 30:
        return True, 2, "center"

    # Avoid trailing sentence punctuation (headings never end in comma, semicolon, or colon)
    if plain.endswith((",", ";", ":")):
        return False, 1, "left"
    if plain.endswith(".") and not re.match(r"^\d+(?:\s*\.\s*\d+)*\.?\s+[A-Za-z0-9]", plain):
        return False, 1, "left"

    # 1. Explicit numbering: e.g. "1. Introduction", "2.1 Methods", "3.1.2 Analysis"
    m_num = HEADING_NUMBER_PATTERN.match(plain)
    if m_num:
        num_part = re.sub(r"\s+", "", m_num.group(1))
        after_num = m_num.group(2).strip()
        dots = num_part.count(".")
        if dots == 0:
            # Single-integer numbered line: check if it is an exercise problem, axiom, list item, or sentence
            is_exercise_or_problem = bool(
                re.match(
                    r"^(?:Verify|Prove|Show|Find|Solve|Let|Test|Determine|Calculate|Evaluate|"
                    r"State|Construct|Describe|Give|Check|Compute|Consider|Suppose|Assume|"
                    r"Demonstrate|Explain|Is|Are|If|Given|Recall|In\s+Exercise)\b",
                    after_num,
                    re.I,
                )
            )
            has_predicate = bool(re.search(r"\b(is|are|was|were|has|have)\b", after_num, re.I))
            if is_exercise_or_problem or has_predicate or len(after_num.split()) > 4 or plain.endswith((".", "?", "!", ",", ";", ":")):
                return False, 1, "left"
        level = min(6, 1 + dots if dots > 0 else 2)
        return True, level, align

    # 2. Academic section keywords: e.g. "Abstract", "Theoretical Background", "References"
    if ACADEMIC_SECTION_KEYWORDS.match(plain):
        return True, 2, align

    # 3. Typography: text significantly taller than median line height
    if median_h > 0 and (box.bottom - box.top) >= 1.35 * median_h:
        return True, 1 if is_centered else 2, align

    # 4. Short standalone centered title (all caps or title case) with no punctuation
    if is_centered and len(plain) < 70 and (plain.isupper() or plain.istitle()):
        return True, 1, "center"

    return False, 1, "left"


def detect_table_groups_geometry(
    rows: list[list[tuple[Box, str, Any]]],
    table_cell_rects: list[Box],
    page_width: float,
) -> list[tuple[int, int, list[float]]]:
    """Identify contiguous rows that form a genuine table using geometric column alignment.

    Returns:
        list of (start_row_idx, end_row_idx, column_boundaries)
    """
    num_rows = len(rows)
    tables: list[tuple[int, int, list[float]]] = []
    r_idx = 0

    while r_idx < num_rows:
        # Check if rows starting at r_idx form a table
        # Criterion 1: Visual ruling rectangles from vector drawings
        # Criterion 2: Multi-row column alignment (>=2 rows with >=2 items, aligning X boundaries)
        curr_row = rows[r_idx]

        # Check drawing table rects overlapping curr_row
        row_top = min(b.top for b, _k, _p in curr_row)
        row_bottom = max(b.bottom for b, _k, _p in curr_row)
        has_cell_rect = any(
            (rect.top <= row_bottom and rect.bottom >= row_top)
            for rect in table_cell_rects
        )

        # Check column count and ensure it is not already an equation block
        col_count = len(curr_row)
        if (col_count < 2 and not has_cell_rect) or any(k == "display" for _b, k, _p in curr_row):
            r_idx += 1
            continue

        # Look ahead for consecutive rows with matching column alignment
        consecutive = 1
        aligned_col_xs = [b.left for b, _k, _p in sorted(curr_row, key=lambda x: x[0].left)]

        while r_idx + consecutive < num_rows:
            next_row = rows[r_idx + consecutive]
            # If display math is in this row, not a standard table row
            if any(k == "display" for _b, k, _p in next_row):
                break

            # If drawing rect exists for this row, strong evidence of table continuation
            n_top = min(b.top for b, _k, _p in next_row)
            n_bot = max(b.bottom for b, _k, _p in next_row)
            next_has_cell = any(
                (rect.top <= n_bot and rect.bottom >= n_top)
                for rect in table_cell_rects
            )

            next_col_count = len(next_row)
            if next_has_cell:
                consecutive += 1
                continue

            # Check alignment with aligned_col_xs
            next_xs = [b.left for b, _k, _p in sorted(next_row, key=lambda x: x[0].left)]
            if next_col_count >= 2:
                # Check if at least 2 column boundaries align within 0.06 * page_width
                matches = sum(
                    any(abs(nx - ax) < 0.06 * page_width for ax in aligned_col_xs)
                    for nx in next_xs
                )
                if matches >= min(2, min(len(next_xs), len(aligned_col_xs))):
                    consecutive += 1
                    continue

            break

        # A valid table requires:
        # Either at least 2 consecutive multi-column rows with geometric alignment
        # Or presence of vector cell rects
        if (consecutive >= 2 and col_count >= 2) or (has_cell_rect and consecutive >= 1):
            # Compute common column boundaries
            all_lefts: list[float] = []
            for i in range(consecutive):
                all_lefts.extend(b.left for b, _k, _p in rows[r_idx + i])
            all_lefts.sort()

            # Cluster column lefts
            clusters: list[float] = []
            for x in all_lefts:
                if not clusters or abs(x - clusters[-1]) > 0.08 * page_width:
                    clusters.append(x)

            tables.append((r_idx, r_idx + consecutive, clusters))
            r_idx += consecutive
        else:
            r_idx += 1

    return tables

