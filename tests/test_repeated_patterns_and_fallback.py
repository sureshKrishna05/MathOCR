"""Regression tests for repeated-pattern equations, inline math notation, and image fallback."""

from io import BytesIO
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

import pytest
from PIL import Image

from backend.assets import default_asset_store
from backend.document import (
    DisplayEquation,
    Document,
    Heading,
    InlineEquation,
    Paragraph,
    TextRun,
    reconcile_document_with_markdown,
)
from backend.docx_export import (
    TemplateConfig,
    build_docx_from_document,
    get_template_config,
    should_fallback_to_image,
)
from backend.omml import _OMML_CACHE, latex_to_omml, sanitize_latex_for_pandoc
from starlette.testclient import TestClient
from backend.app import app


def _read_docx_xml(docx_path: Path) -> str:
    with zipfile.ZipFile(docx_path, "r") as archive:
        return archive.read("word/document.xml").decode("utf-8")


def _read_docx_media_files(docx_path: Path) -> list[str]:
    with zipfile.ZipFile(docx_path, "r") as archive:
        return [name for name in archive.namelist() if name.startswith("word/media/")]


# -------------------------------------------------------------------------
# Phase 2: Cache Identity and Repeated Pattern Equations
# -------------------------------------------------------------------------

CACHE_TEST_PAIRS = [
    # 1. Variable substitution
    ("x^{-1}", "y^{-1}"),
    # 2. Index substitution
    ("x_1", "x_2"),
    ("x_i", "x_j"),
    # 3. Exponent substitution
    ("x^2", "x^3"),
    ("x^2", "x^{-1}"),
    # 4. Sign and operator changes
    ("x + y", "x - y"),
    # 5. Coefficient changes
    ("2x", "3x"),
    # 6. Transposition and matrix index reversals
    ("A_{ij}", "A_{ji}"),
    ("A_{ij} = B_{ij}", "A_{ji} = B_{ji}"),
    # 7. Structurally identical equations with distinct symbols
    ("x_1 + x_2 = 0", "y_1 + y_2 = 0"),
    ("a_{11} x_1 + a_{12} x_2 = b_1", "a_{21} x_1 + a_{22} x_2 = b_2"),
]


@pytest.mark.parametrize("expr1,expr2", CACHE_TEST_PAIRS)
def test_repeated_pattern_cache_keys_are_distinct(expr1: str, expr2: str) -> None:
    """Distinct formulas must never produce identical sanitization or cache keys."""
    cleaned1 = sanitize_latex_for_pandoc(expr1)
    cleaned2 = sanitize_latex_for_pandoc(expr2)
    assert cleaned1 != cleaned2, f"Collision between '{expr1}' and '{expr2}': both cleaned to '{cleaned1}'"

    key1 = (cleaned1, False)
    key2 = (cleaned2, False)
    assert key1 != key2


@pytest.mark.parametrize("expr1,expr2", CACHE_TEST_PAIRS)
def test_repeated_pattern_conversion_results_are_isolated(expr1: str, expr2: str) -> None:
    """Converting expr1 and expr2 must produce distinct OMML outputs and not overwrite one another."""
    omml1, err1 = latex_to_omml(expr1, display=False)
    assert err1 is None and omml1 is not None

    omml2, err2 = latex_to_omml(expr2, display=False)
    assert err2 is None and omml2 is not None

    xml1 = ET.tostring(omml1, encoding="unicode")
    xml2 = ET.tostring(omml2, encoding="unicode")
    assert xml1 != xml2, f"OMML trees for '{expr1}' and '{expr2}' must be distinct"

    # Re-fetch from cache and confirm exact identity
    cached_omml1, _ = latex_to_omml(expr1, display=False)
    cached_omml2, _ = latex_to_omml(expr2, display=False)
    assert ET.tostring(cached_omml1, encoding="unicode") == xml1
    assert ET.tostring(cached_omml2, encoding="unicode") == xml2


def test_equation_numbers_remain_separate_from_cache_keys() -> None:
    """Equation numbers (1) vs (2) belong to DisplayEquation metadata, not formula OMML cache keys."""
    eq1 = DisplayEquation(latex="x + y = 0", numbering="1")
    eq2 = DisplayEquation(latex="x + y = 0", numbering="2")

    # Formula itself can safely share OMML conversion
    clean1 = sanitize_latex_for_pandoc(eq1.latex)
    clean2 = sanitize_latex_for_pandoc(eq2.latex)
    assert clean1 == clean2

    # Numbering stays distinct on the block objects
    assert eq1.numbering != eq2.numbering


# -------------------------------------------------------------------------
# Phase 3: Inline Mathematical Notation and Run Splitting
# -------------------------------------------------------------------------

def test_inline_math_splitting_in_layout_lines() -> None:
    """Prose lines containing textbook mathematical notations split into TextRun and InlineEquation runs."""
    from backend.document import _runs_from_layout_line

    class MockLine:
        def __init__(self, text: str) -> None:
            self.text = text
            self.box = None
            self.foreground_color = None
            self.background_color = None

    # Case 1: Field Axiom 7
    line7 = MockLine("7. There is a unique non-zero element 1 (one) in F' such that x1 = x,")
    runs7 = _runs_from_layout_line(line7)
    inline_eqs7 = [r for r in runs7 if isinstance(r, InlineEquation)]
    assert len(inline_eqs7) == 1
    assert r"x \cdot 1 = x" in inline_eqs7[0].latex or "x1 = x" in inline_eqs7[0].latex
    # Number label run is bold
    assert any(isinstance(r, TextRun) and r.bold and "7." in r.text for r in runs7)

    # Case 2: Field Axiom 8
    line8 = MockLine("8. To each non-zero x in F there corresponds a unique element x−1 (or 1/x) such that xx−1 = 1.")
    runs8 = _runs_from_layout_line(line8)
    inline_eqs8 = [r for r in runs8 if isinstance(r, InlineEquation)]
    assert len(inline_eqs8) >= 2
    eq_latexs8 = [eq.latex for eq in inline_eqs8]
    assert any("x^{-1}" in eq for eq in eq_latexs8)
    assert any("1/x" in eq for eq in eq_latexs8) or any("x x^{-1} = 1" in eq for eq in eq_latexs8)

    # Case 3: Matrix transposition Aij = Aji
    line_mat = MockLine("Let Aij = Aji for all i, j.")
    runs_mat = _runs_from_layout_line(line_mat)
    inline_eqs_mat = [r for r in runs_mat if isinstance(r, InlineEquation)]
    assert len(inline_eqs_mat) >= 1
    mat_latexs = [eq.latex for eq in inline_eqs_mat]
    assert any("A_{ij}" in eq for eq in mat_latexs)


def test_markdown_reconciliation_preserves_inline_equation_metadata() -> None:
    """Markdown reconciliation preserves InlineEquation asset_id, confidence, and box."""
    initial_p = Paragraph(
        runs=[
            TextRun(text="Let "),
            InlineEquation(latex="x^{-1}", confidence=0.98, asset_id="crop-asset-123", box=(10, 20, 50, 40)),
            TextRun(text=" be the inverse."),
        ]
    )
    doc = Document(elements=[initial_p])

    # User modifies markdown text slightly
    edited_md = "Let $x^{-1}$ be the inverse element."
    reconciled = reconcile_document_with_markdown(doc, edited_md)

    assert len(reconciled.elements) == 1
    rec_p = reconciled.elements[0]
    assert isinstance(rec_p, Paragraph)
    rec_eq = next((r for r in rec_p.runs if isinstance(r, InlineEquation)), None)
    assert rec_eq is not None
    assert rec_eq.latex == "x^{-1}"
    assert rec_eq.asset_id == "crop-asset-123"
    assert rec_eq.confidence == 0.98
    assert rec_eq.box == (10, 20, 50, 40)


# -------------------------------------------------------------------------
# Phase 4: Reliable Source-Crop Image Fallback
# -------------------------------------------------------------------------

def test_display_equation_image_fallback(tmp_path: Path) -> None:
    """When a display equation fails OMML conversion, it falls back to its source crop without error text."""
    # Create a small dummy image in AssetStore
    img = Image.new("RGB", (120, 40), color=(240, 240, 240))
    asset = default_asset_store.store_image(img, mime_type="image/png")

    # Formula with invalid LaTeX that Pandoc cannot parse
    doc = Document(
        elements=[
            Paragraph(runs=[TextRun(text="Below is an unparseable formula:")]),
            DisplayEquation(
                latex=r"\unsupportedSpecialControlSequence{123",
                asset_id=asset.asset_id,
                box=(100, 100, 300, 160),
                numbering="4",
            ),
        ]
    )

    output = tmp_path / "fallback_display.docx"
    warnings = build_docx_from_document(doc, output)

    # 1. Fallback warning logged
    assert any("Display equation fallback to source image" in w for w in warnings)
    # 2. No ugly literal failure string in document
    xml = _read_docx_xml(output)
    assert "[Display equation could not be converted:" not in xml
    assert r"\unsupportedSpecialControlSequence" not in xml
    # 3. Media file embedded in docx
    media_files = _read_docx_media_files(output)
    assert len(media_files) >= 1
    # 4. Equation number preserved
    assert "(4)" in xml


def test_inline_equation_image_fallback(tmp_path: Path) -> None:
    """When an inline equation fails OMML conversion, it embeds an inline source crop."""
    img = Image.new("RGB", (60, 20), color=(250, 250, 250))
    asset = default_asset_store.store_image(img, mime_type="image/png")

    doc = Document(
        elements=[
            Paragraph(
                runs=[
                    TextRun(text="The variable "),
                    InlineEquation(
                        latex=r"\unsupportedMacro{inline}",
                        asset_id=asset.asset_id,
                    ),
                    TextRun(text=" is well-defined."),
                ]
            )
        ]
    )

    output = tmp_path / "fallback_inline.docx"
    warnings = build_docx_from_document(doc, output)

    assert any("Inline equation fallback to source image" in w for w in warnings)
    xml = _read_docx_xml(output)
    assert "[Inline equation could not be converted:" not in xml
    assert "The variable " in xml
    assert " is well-defined." in xml
    # Embedded drawing exists
    assert "<w:drawing>" in xml
    media_files = _read_docx_media_files(output)
    assert len(media_files) >= 1


def test_equation_serialization_preserves_asset_id_and_fallback_image() -> None:
    """InlineEquation and DisplayEquation to_dict / from_dict preserve asset_id and fallback_image."""
    inline = InlineEquation(
        latex=r"x^{-1}",
        asset_id="asset-inline-99",
        fallback_image=True,
        confidence=0.95,
        box=(1, 2, 3, 4),
    )
    d_inline = inline.to_dict()
    assert d_inline["asset_id"] == "asset-inline-99"
    assert d_inline["fallback_image"] is True
    reconstructed_inline = InlineEquation.from_dict(d_inline)
    assert reconstructed_inline.asset_id == "asset-inline-99"
    assert reconstructed_inline.fallback_image is True

    display = DisplayEquation(
        latex=r"A_{ij} = A_{ji}",
        numbering="7",
        asset_id="asset-display-88",
        fallback_image=False,
        box=(10, 20, 100, 80),
    )
    d_display = display.to_dict()
    assert d_display["asset_id"] == "asset-display-88"
    assert d_display["fallback_image"] is False
    reconstructed_display = DisplayEquation.from_dict(d_display)
    assert reconstructed_display.asset_id == "asset-display-88"
    assert reconstructed_display.fallback_image is False


# -------------------------------------------------------------------------
# Phase 6: Low-Confidence Image Fallback and Threshold Tests
# -------------------------------------------------------------------------

def test_high_confidence_equation_exports_native_omml(tmp_path: Path) -> None:
    """A high-confidence valid equation (AX = Y, 100%) remains native editable OMML."""
    doc = Document(
        elements=[
            DisplayEquation(
                latex="AX = Y",
                confidence=1.0,
                box=(50, 100, 200, 140),
            )
        ]
    )
    output = tmp_path / "high_conf_omml.docx"
    warnings = build_docx_from_document(doc, output)

    xml = _read_docx_xml(output)
    assert "oMath" in xml
    # No image fallback used
    media_files = _read_docx_media_files(output)
    assert len(media_files) == 0
    assert len(warnings) == 0
    assert doc.metadata["export_stats"]["native_omml"] == 1
    assert doc.metadata["export_stats"]["image_fallback"] == 0


def test_low_confidence_equation_exports_image_fallback(tmp_path: Path) -> None:
    """A low-confidence equation (56% confidence) exports as an embedded source crop image."""
    img = Image.new("RGB", (200, 80), color=(220, 230, 240))
    asset = default_asset_store.store_image(
        img,
        mime_type="image/png",
        bbox=(50, 200, 250, 280),
        metadata={"purpose": "math-region-crop"},
    )

    doc = Document(
        elements=[
            DisplayEquation(
                latex=r"\begin{aligned} x_1 + 2x_2 &= 3 \\ 4x_1 + 5x_2 &= 6 \end{aligned}",
                confidence=0.56,  # Below default 0.80 threshold
                asset_id=asset.asset_id,
                box=(50, 200, 250, 280),
            )
        ]
    )
    output = tmp_path / "low_conf_fallback.docx"
    warnings = build_docx_from_document(doc, output)

    assert any("Display equation fallback to source image" in w for w in warnings)
    assert any("Export summary: 0 native OMML equations, 1 image fallback equations, 0 unresolved equations" in w for w in warnings)

    # Word document contains drawing and media package contains the image
    xml = _read_docx_xml(output)
    assert "<w:drawing>" in xml
    media_files = _read_docx_media_files(output)
    assert len(media_files) == 1

    # Verify image bytes in media package match original asset
    with zipfile.ZipFile(output, "r") as archive:
        pkg_img_bytes = archive.read(media_files[0])
    assert pkg_img_bytes == asset.data


def test_high_confidence_failed_omml_falls_back_to_image(tmp_path: Path) -> None:
    """A high-confidence equation (95%) with failed OMML conversion falls back to the source crop."""
    img = Image.new("RGB", (150, 50), color=(255, 250, 240))
    asset = default_asset_store.store_image(img, mime_type="image/png")

    doc = Document(
        elements=[
            DisplayEquation(
                latex=r"\unsupportedNonExistentLatexMacro{xyz}",
                confidence=0.95,
                asset_id=asset.asset_id,
            )
        ]
    )
    output = tmp_path / "failed_omml_fallback.docx"
    warnings = build_docx_from_document(doc, output)

    assert any("Display equation fallback to source image" in w for w in warnings)
    media_files = _read_docx_media_files(output)
    assert len(media_files) == 1


def test_fallback_decision_per_equation_isolated(tmp_path: Path) -> None:
    """Fallback for one equation (56% matrix) does NOT affect neighboring native OMML equations (100% AX=Y)."""
    img = Image.new("RGB", (180, 60), color=(240, 240, 240))
    asset = default_asset_store.store_image(img, mime_type="image/png")

    doc = Document(
        elements=[
            Paragraph(runs=[TextRun(text="First equation is simple and high confidence:")]),
            DisplayEquation(
                latex="AX = Y",
                confidence=1.0,
                numbering="1",
            ),
            Paragraph(runs=[TextRun(text="Second equation is complex and low confidence:")]),
            DisplayEquation(
                latex=r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}",
                confidence=0.56,
                asset_id=asset.asset_id,
                numbering="2",
            ),
        ]
    )
    output = tmp_path / "mixed_fallback_isolated.docx"
    warnings = build_docx_from_document(doc, output)

    xml = _read_docx_xml(output)
    # AX = Y is native OMML
    assert "oMath" in xml
    # Matrix is embedded drawing
    assert "<w:drawing>" in xml
    # Both equation numbers are preserved
    assert "(1)" in xml
    assert "(2)" in xml
    # Exactly 1 media file for the 1 fallback equation
    media_files = _read_docx_media_files(output)
    assert len(media_files) == 1
    assert any("Export summary: 1 native OMML equations, 1 image fallback equations, 0 unresolved equations" in w for w in warnings)


def test_configurable_fallback_threshold(tmp_path: Path) -> None:
    """Configuring equation_image_fallback_threshold controls the fallback boundary."""
    img = Image.new("RGB", (100, 40), color=(230, 230, 230))
    asset = default_asset_store.store_image(img, mime_type="image/png")

    doc = Document(
        elements=[
            DisplayEquation(
                latex="x^2 + y^2 = r^2",
                confidence=0.70,
                asset_id=asset.asset_id,
            )
        ]
    )

    # At default threshold 0.80 -> 0.70 < 0.80, so image fallback triggers
    config_default = get_template_config("academic_textbook", equation_image_fallback_threshold=0.80)
    out_default = tmp_path / "thresh_080.docx"
    warnings_default = build_docx_from_document(doc, out_default, template=config_default)
    assert any("Display equation fallback to source image" in w for w in warnings_default)
    assert len(_read_docx_media_files(out_default)) == 1

    # At lower threshold 0.60 -> 0.70 >= 0.60, so native OMML is used!
    config_lower = get_template_config("academic_textbook", equation_image_fallback_threshold=0.60)
    out_lower = tmp_path / "thresh_060.docx"
    warnings_lower = build_docx_from_document(doc, out_lower, template=config_lower)
    assert not any("Display equation fallback to source image" in w for w in warnings_lower)
    assert len(_read_docx_media_files(out_lower)) == 0
    assert "oMath" in _read_docx_xml(out_lower)


def test_missing_asset_crop_produces_explicit_warning(tmp_path: Path) -> None:
    """When fallback is required but no asset exists, produce an explicit warning and do not omit content silently."""
    doc = Document(
        elements=[
            DisplayEquation(
                latex=r"\unsupportedBrokenMacro{bad}",
                confidence=0.50,
                asset_id=None,  # No asset!
            )
        ]
    )
    output = tmp_path / "unresolved_equation.docx"
    warnings = build_docx_from_document(doc, output)

    xml = _read_docx_xml(output)
    # Does not crash, exports placeholder
    assert "could not be converted" in xml
    assert any("could not be converted" in w for w in warnings)
    assert any("Export summary: 0 native OMML equations, 0 image fallback equations, 1 unresolved equations" in w for w in warnings)


def test_api_export_docx_with_document_and_threshold(tmp_path: Path) -> None:
    """Full HTTP API round-trip: /api/export/docx processes structured document with fallback threshold."""
    img = Image.new("RGB", (160, 60), color=(200, 210, 220))
    asset = default_asset_store.store_image(img, mime_type="image/png")

    client = TestClient(app)
    payload = {
        "title": "Systems of Linear Equations",
        "document": {
            "title": "Systems of Linear Equations",
            "elements": [
                {
                    "type": "display_equation",
                    "latex": "AX = Y",
                    "confidence": 1.0,
                    "numbering": "1",
                },
                {
                    "type": "display_equation",
                    "latex": r"\begin{bmatrix} 1 & 2 \\ 3 & 4 \end{bmatrix}",
                    "confidence": 0.56,
                    "asset_id": asset.asset_id,
                    "numbering": "2",
                },
            ],
            "metadata": {},
            "warnings": [],
        },
        "template": "academic_textbook",
        "equation_image_fallback_threshold": 0.80,
    }

    response = client.post("/api/export/docx", json=payload)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    docx_bytes = BytesIO(response.content)
    with zipfile.ZipFile(docx_bytes, "r") as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
        media = [name for name in archive.namelist() if name.startswith("word/media/")]

    # High-confidence equation has native OMML
    assert "oMath" in xml
    # Low-confidence equation has embedded media
    assert len(media) == 1
    # Both numbering labels present
    assert "(1)" in xml
    assert "(2)" in xml

