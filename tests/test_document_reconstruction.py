"""Comprehensive test suite for document reconstruction, PDF source retention,
figure extraction, geometry-based tables, semantic headings, and secure asset flow.
"""

import io
import tempfile
import zipfile
from pathlib import Path

import fitz
import pytest
from PIL import Image

from backend.assets import AssetStore, default_asset_store
from backend.document import (
    DisplayEquation,
    Document,
    Heading,
    ImageBlock,
    InlineEquation,
    Paragraph,
    Table,
    TableCell,
    TableRow,
    TextRun,
    reconcile_document_with_markdown,
)
from backend.docx_export import build_docx_from_document, verify_docx_file
from backend.engines import TextLine
from backend.geometry import Box
from backend.layout import (
    associate_captions,
    classify_heading_semantic,
    detect_scanned_figures,
    detect_table_groups_geometry,
    filter_headers_footers,
)
from backend.pdf_source import ExtractedFigure, extract_pdf_pages


def test_document_from_layout_with_figures_and_captions() -> None:
    """Test that Document.from_layout produces ImageBlock with captions and asset IDs."""
    text_lines = [
        TextLine(Box(50, 50, 400, 80), "1. Introduction to Optics", 0.95),
        TextLine(Box(50, 90, 500, 120), "The ray diagram illustrates thin-lens refraction.", 0.92),
        TextLine(Box(50, 310, 350, 330), "Figure 1: Thin-lens focal geometry.", 0.90),
        TextLine(Box(50, 360, 500, 390), "Subsequent analysis confirms focal length invariance.", 0.91),
    ]

    fig_box = Box(50, 130, 350, 300)
    figures = [
        ExtractedFigure(
            asset_id="asset_lens_001",
            box=fig_box,
            box_pt=(20, 52, 140, 120),
            mime_type="image/png",
            caption=None,
            source_page=1,
        )
    ]

    doc = Document.from_layout(
        text_lines=text_lines,
        math_results=[],
        page_height=800,
        page_width=600,
        figures=figures,
    )

    types = [e.type for e in doc.elements]
    assert "heading" in types
    assert "image" in types

    img_elem = next(e for e in doc.elements if isinstance(e, ImageBlock))
    assert img_elem.asset_id == "asset_lens_001"
    assert img_elem.caption == "Figure 1: Thin-lens focal geometry."

    # Verify that the caption was not also duplicated as a standalone body paragraph
    body_texts = [e.text() for e in doc.elements if isinstance(e, Paragraph)]
    assert not any("Figure 1: Thin-lens focal geometry." in txt for txt in body_texts)


def test_caption_above_figure_associated_correctly() -> None:
    """Test caption association when caption appears above the figure."""
    text_lines = [
        TextLine(Box(50, 100, 300, 120), "Fig. 2. Circuit Diagram", 0.92),
    ]
    fig_box = Box(50, 125, 400, 350)
    figures = [
        ExtractedFigure(
            asset_id="asset_circuit_002",
            box=fig_box,
            box_pt=(20, 50, 160, 140),
            caption=None,
        )
    ]

    kept_figs, remaining_text = associate_captions(figures, [(t.box, "text", t) for t in text_lines], 20.0)
    assert len(kept_figs) == 1
    assert kept_figs[0].caption == "Fig. 2. Circuit Diagram"
    assert len(remaining_text) == 0


def test_no_quantum_keywords_dependency_for_tables() -> None:
    """Test that table detection works on general academic tables without quantum keywords."""
    rows = [
        # Table Header
        [
            (Box(50, 100, 150, 120), "text", TextLine(Box(50, 100, 150, 120), "Sample", 0.9)),
            (Box(160, 100, 260, 120), "text", TextLine(Box(160, 100, 260, 120), "Density (g/cm3)", 0.9)),
            (Box(270, 100, 370, 120), "text", TextLine(Box(270, 100, 370, 120), "Porosity (%)", 0.9)),
        ],
        # Table Row 1
        [
            (Box(50, 125, 150, 145), "text", TextLine(Box(50, 125, 150, 145), "Limestone A", 0.9)),
            (Box(160, 125, 260, 145), "text", TextLine(Box(160, 125, 260, 145), "2.71", 0.9)),
            (Box(270, 125, 370, 145), "text", TextLine(Box(270, 125, 370, 145), "14.2", 0.9)),
        ],
        # Table Row 2
        [
            (Box(50, 150, 150, 170), "text", TextLine(Box(50, 150, 150, 170), "Sandstone B", 0.9)),
            (Box(160, 150, 260, 170), "text", TextLine(Box(160, 150, 260, 170), "2.35", 0.9)),
            (Box(270, 150, 370, 170), "text", TextLine(Box(270, 150, 370, 170), "22.8", 0.9)),
        ],
    ]

    table_groups = detect_table_groups_geometry(rows, [], page_width=500.0)
    assert len(table_groups) == 1
    start, end, cols = table_groups[0]
    assert start == 0
    assert end == 3
    assert len(cols) == 3


def test_prose_with_relative_error_remains_paragraph() -> None:
    """Regression test: Normal prose containing 'relative error' must not become a table."""
    text_lines = [
        TextLine(
            Box(50, 100, 480, 120),
            "The relative error of the numerical approximation was measured below 0.01 percent.",
            0.95,
        ),
        TextLine(
            Box(50, 130, 480, 150),
            "This confirms that the transition energy satisfies the convergence criterion.",
            0.94,
        ),
    ]

    doc = Document.from_layout(
        text_lines=text_lines,
        math_results=[],
        page_height=800,
        page_width=600,
    )

    types = [e.type for e in doc.elements]
    assert "table" not in types
    assert all(isinstance(e, Paragraph) for e in doc.elements)


def test_heading_classification_semantic() -> None:
    """Test heading classification against section numbers, theorems, and short prose."""
    # 1. Numbered section
    is_h, level, align = classify_heading_semantic(
        "2.1 Experimental Methods", Box(50, 100, 250, 120), 600, 15.0
    )
    assert is_h is True
    assert level == 2

    # 2. Academic keyword
    is_h, level, align = classify_heading_semantic(
        "Theorem 3.4 (Uniqueness of Solutions)", Box(50, 150, 320, 170), 600, 15.0
    )
    assert is_h is True

    # 3. Short sentence with period is NOT a heading
    is_h, level, align = classify_heading_semantic(
        "WE OBSERVED RAPID CONVERGENCE.", Box(50, 200, 260, 220), 600, 15.0
    )
    assert is_h is False

    # 4. Long prose sentence is NOT a heading
    is_h, level, align = classify_heading_semantic(
        "IN THIS SECTION WE DEMONSTRATE THAT THE HAMILTONIAN OPERATOR IS STRICTLY SELF-ADJOINT UNDER BOUNDARY CONDITIONS",
        Box(50, 250, 550, 270),
        600,
        15.0,
    )
    assert is_h is False


def test_structured_document_markdown_roundtrip() -> None:
    """Test that Markdown serialization and reconciliation preserves image assets and block order."""
    doc = Document(
        title="Roundtrip Test",
        elements=[
            Heading(level=1, text="Section 1"),
            Paragraph(runs=[TextRun("Paragraph before image with math "), InlineEquation(latex=r"E=mc^2")]),
            ImageBlock(
                asset_id="test_asset_uuid_9999",
                caption="Figure 1: Energy diagram",
                width=4.5,
                alignment="center",
            ),
            DisplayEquation(latex=r"\int_0^1 f(x) \, dx = 1"),
        ],
    )

    md = doc.to_markdown()
    assert "![Figure 1: Energy diagram](asset:test_asset_uuid_9999)" in md
    assert "$E=mc^2$" in md
    assert "$$\n\\int_0^1 f(x) \\, dx = 1\n$$" in md

    # User edits Markdown text slightly
    edited_md = md.replace("Paragraph before image", "Edited paragraph before image")

    # Reconcile back to structured document
    reconciled = reconcile_document_with_markdown(doc, edited_md)
    img_blocks = [e for e in reconciled.elements if isinstance(e, ImageBlock)]
    assert len(img_blocks) == 1
    assert img_blocks[0].asset_id == "test_asset_uuid_9999"
    assert img_blocks[0].caption == "Figure 1: Energy diagram"
    assert img_blocks[0].width == 4.5

    # Check updated paragraph text
    para_blocks = [e for e in reconciled.elements if isinstance(e, Paragraph)]
    assert any("Edited paragraph" in p.text() for p in para_blocks)


def test_docx_export_with_asset_store(tmp_path: Path) -> None:
    """Test that DOCX export embeds assets from AssetStore and verifies zip package integrity."""
    store = AssetStore()

    # Create dummy image bytes (red rectangle)
    img = Image.new("RGB", (200, 120), color="crimson")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    asset = store.store_image(img_bytes, mime_type="image/png", caption="Red plot")

    doc = Document(
        title="Asset Export Test",
        elements=[
            Heading(level=1, text="Figure Demonstration"),
            ImageBlock(
                asset_id=asset.asset_id,
                caption="Red plot showing resonance peak",
                width=4.0,
                alignment="center",
            ),
            Paragraph(runs=[TextRun("Follow-up discussion of the resonance plot.")]),
        ],
    )

    output = tmp_path / "test_asset_export.docx"
    warnings = build_docx_from_document(doc, output, asset_store=store)

    assert len(warnings) == 0
    assert output.is_file() and output.stat().st_size > 0

    # Verify that image was embedded into the DOCX zip package
    with zipfile.ZipFile(output, "r") as zf:
        namelist = zf.namelist()
        media_files = [name for name in namelist if name.startswith("word/media/")]
        assert len(media_files) == 1
        assert "word/document.xml" in namelist


def test_security_asset_store_path_traversal() -> None:
    """Test that invalid or path-traversal asset IDs are rejected."""
    store = AssetStore()

    # Malicious asset IDs attempting path traversal
    assert store.get("../../../../etc/passwd") is None
    assert store.get("/etc/shadow") is None
    assert store.get("..\\..\\Windows\\System32") is None
    assert store.get("invalid_characters!") is None


def test_pdf_source_retention_end_to_end(tmp_path: Path) -> None:
    """Test that extract_pdf_pages extracts embedded images with exact bounding boxes and points geometry."""
    pdf_doc = fitz.open()
    page = pdf_doc.new_page(width=612, height=792)  # Letter size
    page.insert_text((72, 72), "Figure 1. Test Diagram", fontsize=14)

    # Insert an image
    test_img = Image.new("RGB", (150, 100), color="forestgreen")
    buf = io.BytesIO()
    test_img.save(buf, format="PNG")
    img_bytes = buf.getvalue()
    rect = fitz.Rect(72, 100, 222, 200)
    page.insert_image(rect, stream=img_bytes)

    pdf_bytes = pdf_doc.tobytes()
    pdf_doc.close()

    store = AssetStore()
    page_sources, truncated = extract_pdf_pages(pdf_bytes, page_limit=5, asset_store=store)

    assert truncated is False
    assert len(page_sources) == 1
    ps = page_sources[0]
    assert ps.width_pt == 612
    assert ps.height_pt == 792
    assert len(ps.figures) == 1

    fig = ps.figures[0]
    assert fig.asset_id is not None
    assert store.get(fig.asset_id) is not None
    assert fig.box.left > 0
    assert fig.box.top > 0


def test_scanned_figure_detection() -> None:
    """Test computer vision detection of diagrams on scanned/raster pages."""
    import numpy as np

    # Create a 600x800 page with a simulated diagram
    img = Image.new("RGB", (600, 800), color="white")
    arr = np.array(img)
    # Draw a diagram box with circle
    arr[200:350, 100:300] = [20, 20, 20]
    arr[205:345, 105:295] = [255, 255, 255]
    diag_img = Image.fromarray(arr)

    store = AssetStore()
    text_boxes = [Box(50, 50, 450, 80), Box(50, 400, 450, 430)]
    figures = detect_scanned_figures(diag_img, text_boxes, asset_store=store, page_num=1)

    assert len(figures) == 1
    assert figures[0].asset_id is not None
    assert store.get(figures[0].asset_id) is not None
    assert figures[0].box.top >= 180 and figures[0].box.bottom <= 370


def test_header_footer_filtering() -> None:
    """Test filtering of running headers and page numbers into document metadata."""
    lines = [
        (Box(100, 20, 500, 45), "text", TextLine(Box(100, 20, 500, 45), "Running Header: Optics Principles", 0.95)),
        (Box(50, 100, 550, 130), "text", TextLine(Box(50, 100, 550, 130), "Introduction to Geometric Optics", 0.95)),
        (Box(50, 140, 550, 170), "text", TextLine(Box(50, 140, 550, 170), "Light propagates in straight lines.", 0.95)),
        (Box(280, 770, 320, 795), "text", TextLine(Box(280, 770, 320, 795), "— 1 —", 0.95)),
    ]

    body, headers, footers = filter_headers_footers(lines, page_height=800)

    assert len(headers) == 1
    assert "Running Header" in headers[0][2].text
    assert len(footers) == 1
    assert "— 1 —" in footers[0][2].text
    assert len(body) == 2


def test_full_api_export_roundtrip() -> None:
    """Test the complete API export workflow with structured Document and ImageBlock."""
    from fastapi.testclient import TestClient
    from backend.app import app

    client = TestClient(app)

    # Store a test asset in default_asset_store
    img = Image.new("RGB", (160, 100), color="navy")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    asset = default_asset_store.store_image(buf.getvalue(), mime_type="image/png", caption="Test Figure")

    payload = {
        "title": "API Roundtrip Document",
        "document": {
            "title": "API Roundtrip Document",
            "elements": [
                {"type": "heading", "level": 1, "text": "Optical Reflection"},
                {"type": "paragraph", "runs": [{"type": "text_run", "text": "The angle of incidence equals reflection: "}, {"type": "inline_equation", "latex": r"\theta_i = \theta_r"}]},
                {"type": "image", "asset_id": asset.asset_id, "caption": "Figure 1: Law of reflection", "width": 4.5, "alignment": "center"},
                {"type": "display_equation", "latex": r"n_1 \sin\theta_1 = n_2 \sin\theta_2"},
            ],
            "metadata": {},
            "warnings": [],
        },
        "template": "academic_textbook",
        "save_to_downloads": False,
    }

    response = client.post("/api/export/docx", json=payload)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    with zipfile.ZipFile(io.BytesIO(response.content), "r") as zf:
        namelist = zf.namelist()
        assert "word/document.xml" in namelist
        media = [n for n in namelist if n.startswith("word/media/")]
        assert len(media) == 1
