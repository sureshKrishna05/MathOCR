"""High-fidelity PDF source extraction and geometry preservation for MathOCR.

Extracts page dimensions, embedded images, vector drawing bounds, and high-res
page bitmaps using PyMuPDF (fitz) while keeping memory bounded.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from typing import Any, Generator

try:
    import pymupdf as fitz
except ImportError:
    import fitz  # PyMuPDF fallback
from PIL import Image

from backend.assets import Asset, AssetStore, default_asset_store
from backend.geometry import Box

logger = logging.getLogger("mathocr")


@dataclass
class ExtractedFigure:
    """A figure or image extracted from the PDF or cropped from a page."""

    asset_id: str
    box: Box  # In rendered pixel coordinates
    box_pt: tuple[float, float, float, float]  # In PDF points (left, top, right, bottom)
    mime_type: str = "image/png"
    caption: str | None = None
    is_vector: bool = False
    source_page: int = 1


@dataclass
class PageSource:
    """Rich representation of a source page preserving geometry and extracted objects."""

    page_number: int  # 1-based
    image: Image.Image  # Rendered PIL Image (RGB)
    width_pt: float  # Original page width in PDF points
    height_pt: float  # Original page height in PDF points
    scale: float  # Scale factor from points to pixels (e.g. 2.5 for 180 DPI)
    figures: list[ExtractedFigure] = field(default_factory=list)
    table_cell_rects: list[Box] = field(default_factory=list)  # Table border/cell boxes in px
    digital_text_lines: list[dict[str, Any]] = field(default_factory=list)
    is_scanned: bool = False
    asset_store: AssetStore | None = None

    @property
    def width_px(self) -> int:
        return self.image.width

    @property
    def height_px(self) -> int:
        return self.image.height

    def close(self) -> None:
        """Release rendered image resources."""
        try:
            self.image.close()
        except Exception:
            pass


def extract_pdf_pages(
    data: bytes,
    page_limit: int,
    asset_store: AssetStore | None = None,
    dpi: int = 180,
) -> tuple[list[PageSource], bool]:
    """Process PDF pages one by one, preserving original objects and coordinates.

    Returns:
        (pages, truncated): list of PageSource objects and whether total pages exceeded page_limit.
    """
    store = asset_store or default_asset_store
    scale = dpi / 72.0

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        logger.warning("PyMuPDF failed to open PDF: %s", exc)
        raise ValueError("The uploaded PDF could not be opened") from exc

    total_pages = len(doc)
    page_sources: list[PageSource] = []
    truncated = total_pages > page_limit

    try:
        for page_idx in range(min(total_pages, page_limit)):
            page = doc[page_idx]
            page_num = page_idx + 1
            rect = page.rect
            width_pt = rect.width
            height_pt = rect.height

            # Render bitmap at desired DPI
            pix = page.get_pixmap(dpi=dpi)
            pil_image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            pix = None  # Free pixmap immediately

            # Extract digital text if present
            digital_words = page.get_text("words")  # (x0, y0, x1, y1, word, block_no, line_no, word_no)
            is_scanned = len(digital_words) == 0

            # 1. Extract embedded raster images
            figures: list[ExtractedFigure] = []
            seen_xrefs: set[int] = set()
            try:
                raw_images = page.get_images(full=True)
                for img_info in raw_images:
                    xref = img_info[0]
                    if xref in seen_xrefs:
                        continue
                    seen_xrefs.add(xref)

                    rects = page.get_image_rects(xref)
                    if not rects:
                        continue

                    # Filter out tiny decorative icons / 1x1 spacers
                    for img_rect in rects:
                        w_pt = img_rect.width
                        h_pt = img_rect.height
                        if w_pt < 15 or h_pt < 15 or (w_pt * h_pt) < 400:
                            continue

                        # Extract image bytes
                        try:
                            base_img = doc.extract_image(xref)
                            img_bytes = base_img.get("image")
                            img_ext = base_img.get("ext", "png").lower()
                            mime = f"image/{img_ext}" if img_ext != "jpg" else "image/jpeg"
                        except Exception:
                            # Fallback: crop from rendered page image
                            crop_box = (
                                max(0, int(img_rect.x0 * scale)),
                                max(0, int(img_rect.y0 * scale)),
                                min(pil_image.width, int(img_rect.x1 * scale)),
                                min(pil_image.height, int(img_rect.y1 * scale)),
                            )
                            crop = pil_image.crop(crop_box)
                            buf = io.BytesIO()
                            crop.save(buf, format="PNG")
                            img_bytes = buf.getvalue()
                            mime = "image/png"
                            crop.close()

                        if not img_bytes:
                            continue

                        box_px = Box(
                            img_rect.x0 * scale,
                            img_rect.y0 * scale,
                            img_rect.x1 * scale,
                            img_rect.y1 * scale,
                        )
                        box_pt = (img_rect.x0, img_rect.y0, img_rect.x1, img_rect.y1)

                        asset = store.store_image(
                            img_bytes,
                            mime_type=mime,
                            source_page=page_num,
                            bbox=(int(box_px.left), int(box_px.top), int(box_px.right), int(box_px.bottom)),
                            metadata={"xref": xref, "width_pt": w_pt, "height_pt": h_pt},
                        )

                        figures.append(
                            ExtractedFigure(
                                asset_id=asset.asset_id,
                                box=box_px,
                                box_pt=box_pt,
                                mime_type=mime,
                                source_page=page_num,
                                is_vector=False,
                            )
                        )
            except Exception as img_err:
                logger.warning("Error extracting embedded images on page %d: %s", page_num, img_err)

            # 2. Extract vector drawings (table borders, diagrams)
            table_cell_rects: list[Box] = []
            try:
                drawings = page.get_drawings()
                diag_rects: list[fitz.Rect] = []
                for d in drawings:
                    d_rect = d.get("rect")
                    if not d_rect or d_rect.is_empty:
                        continue
                    w = d_rect.width
                    h = d_rect.height

                    # If it's a rectangle of a table cell or line
                    if w > 40 and h > 10 and (w < width_pt * 0.95 or h < height_pt * 0.8):
                        if (d_rect.y0 > height_pt * 0.08) and (d_rect.y1 < height_pt * 0.92):
                            table_cell_rects.append(
                                Box(
                                    d_rect.x0 * scale,
                                    d_rect.y0 * scale,
                                    d_rect.x1 * scale,
                                    d_rect.y1 * scale,
                                )
                            )

                    # If it's a standalone drawing (diagram / plot)
                    if len(d.get("items", [])) > 4 and w > 60 and h > 60:
                        diag_rects.append(d_rect)

                # Cluster and crop standalone vector diagrams not overlapping text
                if diag_rects:
                    for d_rect in diag_rects:
                        # Check it doesn't overlap existing figures
                        b_px = Box(d_rect.x0 * scale, d_rect.y0 * scale, d_rect.x1 * scale, d_rect.y1 * scale)
                        if any(_overlap(b_px, f.box) > 0.3 for f in figures):
                            continue
                        # Crop from rendered page
                        crop_box = (
                            max(0, int(b_px.left)),
                            max(0, int(b_px.top)),
                            min(pil_image.width, int(b_px.right)),
                            min(pil_image.height, int(b_px.bottom)),
                        )
                        if crop_box[2] > crop_box[0] + 40 and crop_box[3] > crop_box[1] + 40:
                            crop = pil_image.crop(crop_box)
                            buf = io.BytesIO()
                            crop.save(buf, format="PNG")
                            crop_bytes = buf.getvalue()
                            crop.close()
                            asset = store.store_image(
                                crop_bytes,
                                mime_type="image/png",
                                source_page=page_num,
                                bbox=crop_box,
                                metadata={"is_vector": True},
                            )
                            figures.append(
                                ExtractedFigure(
                                    asset_id=asset.asset_id,
                                    box=b_px,
                                    box_pt=(d_rect.x0, d_rect.y0, d_rect.x1, d_rect.y1),
                                    mime_type="image/png",
                                    source_page=page_num,
                                    is_vector=True,
                                )
                            )
            except Exception as draw_err:
                logger.warning("Error processing drawings on page %d: %s", page_num, draw_err)

            page_source = PageSource(
                page_number=page_num,
                image=pil_image,
                width_pt=width_pt,
                height_pt=height_pt,
                scale=scale,
                figures=figures,
                table_cell_rects=table_cell_rects,
                is_scanned=is_scanned,
                asset_store=store,
            )
            page_sources.append(page_source)

    finally:
        doc.close()

    return page_sources, truncated


def _overlap(box1: Box, box2: Box) -> float:
    """Return intersection area over min area of two boxes."""
    x_left = max(box1.left, box2.left)
    y_top = max(box1.top, box2.top)
    x_right = min(box1.right, box2.right)
    y_bottom = min(box1.bottom, box2.bottom)

    if x_right <= x_left or y_bottom <= y_top:
        return 0.0

    inter = (x_right - x_left) * (y_bottom - y_top)
    area1 = max(1.0, (box1.right - box1.left) * (box1.bottom - box1.top))
    area2 = max(1.0, (box2.right - box2.left) * (box2.bottom - box2.top))
    return inter / min(area1, area2)
