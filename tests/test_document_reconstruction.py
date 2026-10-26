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


def test_reconcile_preserves_omitted_non_text_blocks() -> None:
    """Non-text blocks (images, tables, equations) must not be lost when a user edits text-only Markdown."""
    doc = Document(
        title="Omission Safety Test",
        elements=[
            Paragraph(
                runs=[TextRun("Introduction to physical constants.")],
                block_id="p1-para-intro",
            ),
            ImageBlock(
                asset_id="fig_const_1",
                caption="Figure 1: Fundamental Constants",
                box=(50, 100, 450, 300),
                block_id="p1-img-fig_const_1",
            ),
            Paragraph(
                runs=[TextRun("Table of observed values:")],
                block_id="p1-para-table-lead",
            ),
            Table(
                rows=[
                    [
                        TableCell(elements=[Paragraph(runs=[TextRun("Constant")])]),
                        TableCell(elements=[Paragraph(runs=[TextRun("Value")])]),
                    ],
                    [
                        TableCell(elements=[Paragraph(runs=[TextRun("c")])]),
                        TableCell(elements=[Paragraph(runs=[TextRun("3e8")])]),
                    ],
                ],
                block_id="p1-table-values",
            ),
            DisplayEquation(
                latex=r"E = mc^2",
                numbering="1",
                block_id="p1-eq-emc2",
            ),
            Paragraph(
                runs=[TextRun("Conclusion and final remarks.")],
                block_id="p1-para-conclusion",
            ),
        ],
    )

    # User edits only text paragraphs, omitting images, tables, and equations from the Markdown editor
    markdown_edited = (
        "Introduction to physical constants (edited).\n\n"
        "Table of observed values (edited):\n\n"
        "Conclusion and final remarks (edited)."
    )

    reconciled = reconcile_document_with_markdown(doc, markdown_edited)
    assert len(reconciled.elements) == 6

    # Verify order and intact metadata
    p1 = reconciled.elements[0]
    assert isinstance(p1, Paragraph)
    assert "Introduction to physical constants (edited)." in p1.text()

    img = reconciled.elements[1]
    assert isinstance(img, ImageBlock)
    assert img.asset_id == "fig_const_1"
    assert img.caption == "Figure 1: Fundamental Constants"
    assert img.box == (50, 100, 450, 300)
    assert img.block_id == "p1-img-fig_const_1"

    p2 = reconciled.elements[2]
    assert isinstance(p2, Paragraph)
    assert "Table of observed values (edited):" in p2.text()

    tbl = reconciled.elements[3]
    assert isinstance(tbl, Table)
    assert tbl.block_id == "p1-table-values"
    assert len(tbl.rows) == 2

    eq = reconciled.elements[4]
    assert isinstance(eq, DisplayEquation)
    assert eq.block_id == "p1-eq-emc2"
    assert eq.latex == r"E = mc^2"
    assert eq.numbering == "1"

    p3 = reconciled.elements[5]
    assert isinstance(p3, Paragraph)
    assert "Conclusion and final remarks (edited)." in p3.text()

    # Check that preservation warnings were generated
    assert any("p1-img-fig_const_1; preserved" in w for w in reconciled.warnings)
    assert any("p1-table-values; preserved" in w for w in reconciled.warnings)
    assert any("p1-eq-emc2; preserved" in w for w in reconciled.warnings)


def test_reconcile_preserves_leading_and_trailing_omitted_blocks() -> None:
    """Leading and trailing non-text blocks omitted in Markdown must be preserved at boundary positions."""
    doc = Document(
        elements=[
            ImageBlock(asset_id="lead_logo", caption="Logo", block_id="logo-1"),
            Paragraph(runs=[TextRun("Main body text")], block_id="body-1"),
            DisplayEquation(latex=r"\nabla \cdot \mathbf{B} = 0", block_id="eq-trailing"),
        ]
    )
    # User edited only body text
    md = "Main body text edited"
    reconciled = reconcile_document_with_markdown(doc, md)
    assert len(reconciled.elements) == 3
    assert isinstance(reconciled.elements[0], ImageBlock)
    assert reconciled.elements[0].asset_id == "lead_logo"
    assert isinstance(reconciled.elements[1], Paragraph)
    assert "Main body text edited" in reconciled.elements[1].text()
    assert isinstance(reconciled.elements[2], DisplayEquation)
    assert reconciled.elements[2].latex == r"\nabla \cdot \mathbf{B} = 0"


def test_markdown_reconciliation_preserves_source_equation_labels_and_example_style() -> None:
    """Markdown edits must not flatten source-derived blocks before DOCX export."""
    doc = Document(
        elements=[
            Heading(
                level=2,
                text="2.4 Rest Mass",
                alignment="left",
                box=(10, 20, 300, 40),
                block_id="p1-heading-10-20-300-40",
            ),
            Paragraph(
                runs=[TextRun("Example 1. Original statement", italic=True)],
                style="example",
                shading="F0D0E0",
                box=(10, 50, 400, 75),
                block_id="p1-paragraph-10-50-400-75",
            ),
            DisplayEquation(
                latex=r"p = h / \lambda",
                numbering="2",
                alignment="center",
                box=(100, 80, 350, 110),
                block_id="p1-display_equation-100-80-350-110",
            ),
        ]
    )

    edited = doc.to_markdown().replace("Original statement", "Edited statement")
    reconciled = reconcile_document_with_markdown(doc, edited)

    heading, example, equation = reconciled.elements
    assert isinstance(heading, Heading)
    assert heading.block_id == "p1-heading-10-20-300-40"
    assert isinstance(example, Paragraph)
    assert "Edited statement" in example.text()
    assert example.style == "example"
    assert example.shading == "F0D0E0"
    assert example.block_id == "p1-paragraph-10-50-400-75"
    assert isinstance(equation, DisplayEquation)
    assert equation.numbering == "2"
    assert equation.block_id == "p1-display_equation-100-80-350-110"


def test_modern_physics_baseline_fixtures_are_preserved() -> None:
    """Keep the supplied page and its pre-fix DOCX as immutable regression inputs."""
    root = Path(__file__).resolve().parents[1]
    source = root / "test-docs" / "Screenshot_20261026_073950.png"
    baseline = root / "test-docs" / "Qryptex Document by Bouronikos Christos.docx"

    assert source.is_file()
    assert baseline.is_file()
    with Image.open(source) as page:
        assert page.size == (684, 665)
    with zipfile.ZipFile(baseline, "r") as archive:
        assert "word/document.xml" in archive.namelist()


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


def test_modern_physics_screenshot_pipeline_regression(tmp_path: Path) -> None:
    """Verify that the Modern Physics page reconstructs heading 2.4, numbered equations (1)-(3), and pink example blocks."""
    from backend.engines import EngineRegistry, MathPipeline

    root = Path(__file__).resolve().parents[1]
    source_path = root / "test-docs" / "Screenshot_20261026_073950.png"
    if not source_path.is_file():
        pytest.skip("Regression image not available")

    with Image.open(source_path) as page:
        img = page.convert("RGB")

    registry = EngineRegistry()
    pipeline = MathPipeline(registry)
    outcome = pipeline.process(img, mode="document", engine="pix2text-mfr")

    assert outcome.document is not None
    elements = outcome.document.elements

    # Check heading 2.4
    headings = [e for e in elements if isinstance(e, Heading)]
    assert any("2.4" in h.text and "Rest Mass" in h.text for h in headings)

    # Check numbered equations (1), (2), (3)
    display_eqs = [e for e in elements if isinstance(e, DisplayEquation)]
    numbers = {eq.numbering for eq in display_eqs if eq.numbering}
    assert {"1", "2", "3"}.issubset(numbers)

    # Check pink-shaded example blocks
    examples = [e for e in elements if isinstance(e, Paragraph) and e.style == "example"]
    assert len(examples) >= 2
    assert any("EXAMPLE 1" in e.text().upper() for e in examples)
    assert any("EXAMPLE 2" in e.text().upper() for e in examples)
    assert all(e.shading == "F0D0E0" for e in examples)

    # Verify export to DOCX
    out_docx = tmp_path / "modern_physics_test.docx"
    warnings = build_docx_from_document(outcome.document, out_docx, template="preserve_layout")
    assert out_docx.is_file()
    v_errors = verify_docx_file(out_docx)
    assert len(v_errors) == 0

def test_linear_equations_page5_reconstruction_regression(tmp_path: Path) -> None:
    """Verify Section 1.2 Linear Equations (Page 5) formatting and reconstruction.

    Ensures:
    1. Theorem 1 is formatted as a single theorem paragraph with bold label and italic body (not Heading 2).
    2. Exercises header is centered, bold, and italic.
    3. Exercise numbers 1-8 are body/exercise paragraphs with bold numbers (not large blue Heading 2).
    4. Saturated red artifacts and hardcoded B0005A are absent.
    5. Exercise 4 systems of equations convert cleanly to OMML without error placeholders.
    6. Exercise 5 addition and multiplication tables are reconstructed as real editable Table objects.
    7. Exercise 8 trailing phrase 'the rational number field.' is preserved and merged.
    8. Export to DOCX succeeds with valid structure.
    """
    from backend.engines import RegionResult

    text_lines = [
        TextLine(Box(50, 40, 180, 60), "Theorem 1.", 0.96),
        TextLine(Box(50, 65, 550, 85), "Equivalent systems of linear equations have exactly the same solutions.", 0.95),
        TextLine(Box(250, 110, 350, 130), "Exercises", 0.95),
        TextLine(Box(50, 150, 550, 170), "1. Verify that the set of complex numbers described in Example 4 is a subfield of the field of complex numbers, C.", 0.95),
        TextLine(Box(50, 190, 550, 210), "2. Let F be the field of complex numbers. Are the following two systems of linear equations equivalent?", 0.94),
        TextLine(Box(50, 270, 550, 290), "3. Test the following systems of equations as in Exercise 2:", 0.95),
        TextLine(Box(50, 350, 550, 370), "4. Test the following systems of equations as in Exercise 2:", 0.95),
        TextLine(Box(50, 440, 550, 460), "5. Let F be a set which contains exactly two elements, 0 and 1. Define an addition and multiplication by the tables:", 0.94),
        TextLine(Box(50, 540, 550, 560), "Verify that the set F, together with these two operations, is a field.", 0.95),
        TextLine(Box(50, 580, 550, 600), "6. Prove that if two homogeneous systems of linear equations in two unknowns have the same solutions, they are equivalent.", 0.95),
        TextLine(Box(50, 620, 550, 640), "7. Prove that each subfield of the field of complex numbers contains every rational number.", 0.95),
        TextLine(Box(50, 660, 550, 680), "8. Prove that each field of characteristic zero contains a copy of", 0.95),
        TextLine(Box(50, 685, 280, 705), "the rational number field.", 0.95),
    ]

    math_results = [
        RegionResult(
            box=(150, 220, 450, 250),
            latex=r"\begin{aligned} x_1 - x_2 &= 0 \\ 3x_1 + x_2 &= 0 \end{aligned}",
            confidence=0.95,
            kind="isolated",
            engine="rapid_latex_ocr",
        ),
        RegionResult(
            box=(150, 300, 450, 330),
            latex=r"\begin{aligned} -x_1 + x_2 + 4x_3 &= 0 \\ x_1 + 3x_2 + 8x_3 &= 0 \end{aligned}",
            confidence=0.95,
            kind="isolated",
            engine="rapid_latex_ocr",
        ),
        # Exercise 4 with non-standard \cases control sequence
        RegionResult(
            box=(150, 380, 450, 420),
            latex=r"\cases{x_1 + x_2 = 0 \cr 2x_1 + 3x_2 = 0 \cr x_1 - x_2 = 0}",
            confidence=0.95,
            kind="isolated",
            engine="rapid_latex_ocr",
        ),
        # Exercise 5 with addition and multiplication tables
        RegionResult(
            box=(150, 470, 450, 530),
            latex=r"\begin{array}{c|cc} + & 0 & 1 \\ \hline 0 & 0 & 1 \\ 1 & 1 & 0 \end{array} \qquad \begin{array}{c|cc} \cdot & 0 & 1 \\ \hline 0 & 0 & 0 \\ 1 & 0 & 1 \end{array}",
            confidence=0.95,
            kind="isolated",
            engine="rapid_latex_ocr",
        ),
    ]

    doc = Document.from_layout(
        text_lines=text_lines,
        math_results=math_results,
        page_height=800,
        page_width=600,
    )

    # 1. Theorem 1 verification:
    # Must NOT be Heading 2; must be a single paragraph containing both label and statement
    headings = [e for e in doc.elements if isinstance(e, Heading)]
    assert not any("Theorem 1" in h.text for h in headings), "Theorem 1 must not be classified as a Heading"

    paragraphs = [e for e in doc.elements if isinstance(e, Paragraph)]
    thm_paras = [p for p in paragraphs if "Theorem 1" in p.text()]
    assert len(thm_paras) == 1, "Theorem 1 statement must be in a single paragraph, not split"
    assert "Equivalent systems of linear equations" in thm_paras[0].text()
    assert thm_paras[0].style == "theorem"
    # First run must be bold "Theorem 1."
    assert thm_paras[0].runs[0].bold is True

    # 2. Exercises header verification:
    # Either a centered heading or paragraph, bold and italic
    ex_headers = [
        e for e in doc.elements
        if (isinstance(e, Heading) and "Exercises" in e.text)
        or (isinstance(e, Paragraph) and "Exercises" in e.text() and len(e.text().split()) == 1)
    ]
    assert len(ex_headers) >= 1
    ex_hdr = ex_headers[0]
    assert ex_hdr.alignment == "center"
    first_run = ex_hdr.runs[0]
    assert first_run.bold is True and first_run.italic is True

    # 3. Exercises 1 through 8 must NOT be Heading 2
    for i in range(1, 9):
        assert not any(h.text.startswith(f"{i}.") for h in headings), f"Exercise {i} must not be a Heading"

    # 4. Exercise numbers 1 through 8 are in paragraphs with bold number runs
    for i in range(1, 9):
        ex_p = next((p for p in paragraphs if p.text().startswith(f"{i}.")), None)
        assert ex_p is not None, f"Exercise {i} paragraph not found"
        assert ex_p.runs[0].bold is True, f"Exercise {i} number prefix must be bold"
        assert ex_p.runs[0].color is None or ex_p.runs[0].color != "B0005A", "No stray red color"

    # 5. Exercise 5 tables: Reconstructed as real editable Table objects
    tables = [e for e in doc.elements if isinstance(e, Table)]
    assert len(tables) >= 2, f"Expected at least 2 tables (addition and multiplication), got {len(tables)}"
    assert any("+" in tables[0].rows[0].cells[0].text() for _ in [1])
    assert any("0" in tables[0].rows[0].cells[1].text() for _ in [1])

    # 6. Exercise 8 completeness: Trailing phrase must be merged and preserved
    ex8 = next(p for p in paragraphs if p.text().startswith("8."))
    assert "the rational number field." in ex8.text()

    # 7. DOCX export verification
    out_docx = tmp_path / "linear_equations_test.docx"
    warnings = build_docx_from_document(doc, out_docx, template="preserve_layout")
    assert out_docx.is_file()

    # Verify no conversion failure messages in document
    import docx
    docx_doc = docx.Document(str(out_docx))
    full_docx_text = "\n".join(p.text for p in docx_doc.paragraphs)
    assert "could not be converted" not in full_docx_text
    assert "unexpected control sequence" not in full_docx_text
    assert "[Display equation" not in full_docx_text

    # Validation check
    v_errors = verify_docx_file(out_docx)
    assert len(v_errors) == 0

    # Verify side-by-side table container
    assert len(docx_doc.tables) >= 1
    container = docx_doc.tables[0]
    assert len(container.columns) == 3
    assert len(container.cell(0, 0).tables) == 1
    assert len(container.cell(0, 2).tables) == 1
    # Check cell contents of both tables
    t1 = container.cell(0, 0).tables[0]
    t2 = container.cell(0, 2).tables[0]
    assert "+" in t1.cell(0, 0).text
    assert "·" in t2.cell(0, 0).text or "*" in t2.cell(0, 0).text or "·" in t2.cell(0, 0).paragraphs[0].text


def test_figure_rich_pdf_end_to_end_regression(tmp_path: Path) -> None:
    """Validate figure detection, asset preservation, caption association, and media packaging."""
    from backend.assets import AssetStore
    from backend.pdf_source import extract_pdf_pages
    from backend.engines import EngineRegistry, MathPipeline

    root = Path(__file__).resolve().parents[1]
    source_pdf = root / "test-docs" / "figure_rich_sample.pdf"
    if not source_pdf.is_file():
        pytest.skip("Figure-rich test PDF fixture not found")

    store = AssetStore()
    page_sources, truncated = extract_pdf_pages(source_pdf.read_bytes(), page_limit=5, asset_store=store)
    assert len(page_sources) == 1
    ps = page_sources[0]
    assert len(ps.figures) == 2

    registry = EngineRegistry()
    pipeline = MathPipeline(registry)
    outcome = pipeline.process(ps.image, mode="document", engine="pix2text-mfr", page_source=ps)
    doc = outcome.document
    assert doc is not None

    image_blocks = [e for e in doc.elements if isinstance(e, ImageBlock)]
    assert len(image_blocks) == 2
    assert any("Figure 3.1" in (b.caption or "") for b in image_blocks)
    assert any("Figure 3.2" in (b.caption or "") for b in image_blocks)
    assert all(b.asset_id is not None and store.get(b.asset_id) is not None for b in image_blocks)

    out_docx = tmp_path / "figure_rich_output.docx"
    warnings = build_docx_from_document(doc, out_docx, template="academic_textbook", asset_store=store)
    assert out_docx.is_file() and out_docx.stat().st_size > 0
    assert len(warnings) == 0

    v_errors = verify_docx_file(out_docx)
    assert len(v_errors) == 0

    with zipfile.ZipFile(out_docx, "r") as zf:
        media_files = [n for n in zf.namelist() if n.startswith("word/media/")]
        assert len(media_files) == 2

