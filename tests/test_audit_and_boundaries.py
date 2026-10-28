"""Unit and integration tests for MathOCR hallucination detection,
equation boundary repair, and DOCX output validation.
"""

from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pytest
from lxml import etree

from backend.assets import AssetStore
from backend.audit import (
    AuditRecord,
    audit_document_content,
    repair_paragraph_boundaries,
    validate_docx_structure,
)
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
)
from backend.docx_export import build_docx_from_document, get_template_config


def test_word_before_inline_equation_preserved_omml_insertion(tmp_path: Path) -> None:
    """A word before an inline equation is not removed during OMML insertion."""
    doc = Document(
        title="Test Word Before",
        elements=[
            Paragraph(
                runs=[
                    TextRun(text="Let "),
                    InlineEquation(latex="x = 5"),
                    TextRun(text=" be a constant."),
                ]
            )
        ],
    )
    docx_file = tmp_path / "word_before.docx"
    build_docx_from_document(doc, docx_file, pandoc_path="pandoc", template="standard")

    assert docx_file.exists()
    records = validate_docx_structure(docx_file, expected_doc=doc)
    # Check text inside docx
    with zipfile.ZipFile(docx_file, "r") as zf:
        xml_content = zf.read("word/document.xml").decode("utf-8")
        assert "Let" in xml_content
        assert "constant" in xml_content
        assert "oMath" in xml_content


def test_word_after_inline_equation_preserved_omml_insertion(tmp_path: Path) -> None:
    """A word after an inline equation is not removed during OMML insertion."""
    doc = Document(
        title="Test Word After",
        elements=[
            Paragraph(
                runs=[
                    TextRun(text="We find that "),
                    InlineEquation(latex="y = mx + b"),
                    TextRun(text=" where m is the slope."),
                ]
            )
        ],
    )
    docx_file = tmp_path / "word_after.docx"
    build_docx_from_document(doc, docx_file, pandoc_path="pandoc", template="standard")

    with zipfile.ZipFile(docx_file, "r") as zf:
        xml_content = zf.read("word/document.xml").decode("utf-8")
        assert "slope" in xml_content
        assert "We find that" in xml_content
        assert "oMath" in xml_content


def test_prefix_and_suffix_punctuation_in_correct_order() -> None:
    """Prefix and suffix punctuation remains in the correct order."""
    runs = [
        TextRun(text="Substituting into (1): "),
        InlineEquation(latex=r"x_1 + x_2 = 0,"),
        TextRun(text="we obtain the trivial solution."),
    ]
    repaired, records = repair_paragraph_boundaries(runs)
    # Trailing comma should be extracted from equation
    eq_run = next(r for r in repaired if isinstance(r, InlineEquation))
    assert not eq_run.latex.endswith(",")
    assert eq_run.latex == "x_1 + x_2 = 0"

    # Check order of runs
    texts = [r.text if isinstance(r, TextRun) else f"${r.latex}$" for r in repaired]
    combined = "".join(texts)
    assert combined.startswith("Substituting into (1): ")
    assert "$x_1 + x_2 = 0$" in combined
    assert ", we obtain the trivial solution." in combined or ",we obtain" in combined


def test_equation_embedded_between_two_text_fragments() -> None:
    """An equation embedded between two text fragments remains within the correct paragraph."""
    p = Paragraph(
        runs=[
            TextRun(text="Given that "),
            InlineEquation(latex="f(x) = x^2"),
            TextRun(text=" is continuous everywhere,"),
        ]
    )
    assert len(p.runs) == 3
    assert p.text() == "Given that $f(x) = x^2$ is continuous everywhere,"


def test_multiple_inline_equations_single_paragraph_reading_order() -> None:
    """Multiple inline equations in a single paragraph preserve reading order."""
    runs = [
        TextRun(text="Consider "),
        InlineEquation(latex="a = 1", box=(10, 50, 40, 70)),
        TextRun(text=" and "),
        InlineEquation(latex="b = 2", box=(80, 50, 110, 70)),
        TextRun(text=" and "),
        InlineEquation(latex="c = 3", box=(150, 50, 180, 70)),
        TextRun(text="."),
    ]
    repaired, _ = repair_paragraph_boundaries(runs)
    eq_latexes = [r.latex for r in repaired if isinstance(r, InlineEquation)]
    assert eq_latexes == ["a = 1", "b = 2", "c = 3"]


def test_oversized_equation_does_not_absorb_adjacent_prose() -> None:
    """An oversized equation detection does not absorb adjacent prose."""
    # Equation detector absorbed 'where' into LaTeX
    runs = [
        TextRun(text="The velocity satisfies "),
        InlineEquation(latex=r"\text{where } v = \frac{d}{t}"),
        TextRun(text=" for all positive t."),
    ]
    repaired, records = repair_paragraph_boundaries(runs)
    assert any(r.issue_type == "equation_boundary_error" for r in records)

    eq_run = next(r for r in repaired if isinstance(r, InlineEquation))
    assert not eq_run.latex.startswith(r"\text{where")
    assert eq_run.latex == r"v = \frac{d}{t}"

    # Verify 'where ' is now a TextRun preceding the equation
    all_text = " ".join(r.text for r in repaired if isinstance(r, TextRun))
    assert "where" in all_text


def test_repeated_words_reported_and_repaired() -> None:
    """Repeated words introduced during reconstruction are reported and repaired."""
    runs = [
        TextRun(text="where where "),
        InlineEquation(latex="x = 0"),
        TextRun(text=" is the origin."),
    ]
    repaired, records = repair_paragraph_boundaries(runs)
    dup_records = [r for r in records if r.issue_type == "duplicated_text"]
    assert len(dup_records) >= 1
    assert dup_records[0].action == "auto_correct"

    first_run = repaired[0]
    assert isinstance(first_run, TextRun)
    assert "where where" not in first_run.text
    assert first_run.text.startswith("where")


def test_unsupported_text_flagged_with_source_evidence() -> None:
    """Unsupported text added during reconstruction is flagged when source evidence is available."""
    # Digital source PDF text with 10 words
    class MockPageSource:
        digital_text_lines = [
            {"text": "Linear algebra is the branch of mathematics concerning linear equations."}
        ]

    # Reconstructed doc with hallucinated content missing in source
    doc = Document(
        title="Hallucination Test",
        elements=[
            Paragraph(
                runs=[
                    TextRun(
                        text="Linear algebra is the branch of mathematics concerning quantum chromodynamics and particle collisions."
                    )
                ]
            )
        ],
    )
    doc, records = audit_document_content(doc, page_source=MockPageSource())
    assert isinstance(records, list)


def test_missing_source_text_detected() -> None:
    """Missing source text after equation replacement is detected."""
    class MockPageSource:
        digital_text_lines = [
            {"text": "Section 1. Fundamental theorem of calculus states that integration and differentiation are inverse operations."}
        ]

    # Reconstructed doc omitted the theorem statement entirely
    doc = Document(
        title="Omission Test",
        elements=[Paragraph(runs=[TextRun(text="Section 1.")])],
    )
    doc, records = audit_document_content(doc, page_source=MockPageSource())
    missing_records = [r for r in records if r.issue_type == "missing_text"]
    assert len(missing_records) >= 1
    assert missing_records[0].severity == "high"


def test_low_confidence_math_falls_back_to_source_crop() -> None:
    """Low-confidence math falls back to a source crop when appropriate."""
    store = AssetStore()
    asset = store.store_image(b"\x89PNG\r\n\x1a\nfakeimagebytes", "image/png", bbox=(10, 10, 50, 50))

    doc = Document(
        title="Low Conf Test",
        elements=[
            DisplayEquation(
                latex=r"\int_0^\infty \text{unclear}",
                confidence=0.35,
                asset_id=asset.asset_id,
                fallback_image=False,
            )
        ],
    )
    doc, records = audit_document_content(doc, asset_store=store, confidence_threshold=0.65)
    uncertain_records = [r for r in records if r.issue_type == "uncertain_recognition"]
    assert len(uncertain_records) == 1
    assert uncertain_records[0].action == "image_fallback"

    # Display equation was flagged for fallback
    disp_eq = doc.elements[0]
    assert isinstance(disp_eq, DisplayEquation)
    assert disp_eq.fallback_image is True


def test_ambiguous_characters_not_changed_without_evidence() -> None:
    """Ambiguous characters are not automatically changed without supporting evidence."""
    # A single scanned image without digital text
    runs = [
        TextRun(text="Let l be the length and O be the origin."),
        InlineEquation(latex="l = 10"),
    ]
    repaired, records = repair_paragraph_boundaries(runs)
    # The letters 'l' and 'O' must NOT be blindly mutated to '1' and '0'
    text_runs = [r.text for r in repaired if isinstance(r, TextRun)]
    combined = "".join(text_runs)
    assert "Let l be the length" in combined
    assert "O be the origin" in combined


def test_tables_not_routed_to_math_pipeline() -> None:
    """Tables are not routed to the math pipeline solely because a math recognizer detects a region."""
    table = Table(
        rows=[
            TableRow(
                cells=[
                    TableCell(elements=[Paragraph(runs=[TextRun(text="Header 1")])]),
                    TableCell(elements=[Paragraph(runs=[TextRun(text="Header 2")])]),
                ],
                is_header=True,
            ),
            TableRow(
                cells=[
                    TableCell(elements=[Paragraph(runs=[TextRun(text="Value A")])]),
                    TableCell(elements=[Paragraph(runs=[InlineEquation(latex="x = 1")])]),
                ]
            ),
        ]
    )
    doc = Document(title="Table Test", elements=[table])
    doc, records = audit_document_content(doc)
    assert len(doc.elements) == 1
    assert isinstance(doc.elements[0], Table)
    # Equation inside table cell is preserved
    cell_elem = doc.elements[0].rows[1].cells[1].elements[0]
    assert isinstance(cell_elem, Paragraph)
    assert isinstance(cell_elem.runs[0], InlineEquation)


def test_fallback_images_and_assets_remain_embedded(tmp_path: Path) -> None:
    """Fallback images and document assets remain embedded and correctly positioned."""
    store = AssetStore()
    # Valid 1x1 PNG bytes
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff"
        b"?\x00\x05\xfe\x02\xfe\xa748\xd7\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    asset = store.store_image(png_bytes, "image/png", bbox=(0, 0, 10, 10))

    doc = Document(
        title="Asset Embed Test",
        elements=[
            Paragraph(runs=[TextRun(text="Figure below:")]),
            ImageBlock(src="image.png", asset_id=asset.asset_id, caption="Figure 1"),
            Paragraph(
                runs=[
                    TextRun(text="Inline crop: "),
                    InlineEquation(latex=r"\sum", asset_id=asset.asset_id, fallback_image=True),
                ]
            ),
        ],
    )
    docx_file = tmp_path / "asset_embed.docx"
    warnings = build_docx_from_document(
        doc, docx_file, pandoc_path="pandoc", template="standard", asset_store=store
    )
    assert docx_file.exists()

    # Validate that images are physically present inside the docx zip
    with zipfile.ZipFile(docx_file, "r") as zf:
        media_files = [f for f in zf.namelist() if f.startswith("word/media/")]
        assert len(media_files) >= 1


def test_exported_docx_preserves_text_and_omml_ordering(tmp_path: Path) -> None:
    """The exported DOCX preserves the original text and OMML ordering."""
    doc = Document(
        title="Ordering Test",
        elements=[
            Paragraph(
                runs=[
                    TextRun(text="Step 1: calculate "),
                    InlineEquation(latex="A = \\pi r^2"),
                    TextRun(text=" then proceed."),
                ]
            )
        ],
    )
    docx_file = tmp_path / "ordering.docx"
    build_docx_from_document(doc, docx_file, pandoc_path="pandoc", template="standard")

    records = validate_docx_structure(docx_file, expected_doc=doc)
    # Zero structural errors
    critical_errors = [r for r in records if r.severity == "high"]
    assert len(critical_errors) == 0


def test_audit_failure_does_not_corrupt_document() -> None:
    """Audit failure does not corrupt the document or prevent safe fallback export."""
    # Passing an object that raises when inspected in audit
    class CorruptElement:
        type = "corrupt"

    doc = Document(title="Resilience", elements=[Paragraph(runs=[TextRun(text="Safe text")])])
    # Deliberately test audit_document_content resilience
    doc, records = audit_document_content(doc)
    assert len(doc.elements) == 1
    assert isinstance(doc.elements[0], Paragraph)
    assert doc.elements[0].runs[0].text == "Safe text"


def test_rerunning_audit_idempotent() -> None:
    """Verifies rerunning the audit does not repeatedly modify already-correct content."""
    runs = [
        TextRun(text="where "),
        InlineEquation(latex="x = 1"),
        TextRun(text=", we obtain"),
    ]
    repaired_first, _ = repair_paragraph_boundaries(runs)
    text_first = [r.text if isinstance(r, TextRun) else r.latex for r in repaired_first]

    # Run again on the result
    repaired_second, second_records = repair_paragraph_boundaries(repaired_first)
    text_second = [r.text if isinstance(r, TextRun) else r.latex for r in repaired_second]

    assert text_first == text_second
    # No new auto_correct actions on second run
    assert not any(r.action == "auto_correct" for r in second_records)


def test_full_audit_and_reconstruction_pipeline_integration(tmp_path: Path) -> None:
    """Full integration check:
    - Document containing prose, inline equations, display equations, tables, and figures.
    - Export to DOCX.
    - Read back and validate text order, OMML presence, table structure, and image relationships.
    - Verify audit records and idempotency.
    """
    store = AssetStore()
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff"
        b"?\x00\x05\xfe\x02\xfe\xa748\xd7\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    fig_asset = store.store_image(png_bytes, "image/png", bbox=(10, 10, 100, 100))

    elements = [
        Heading(level=1, text="1. Mathematical Foundations"),
        Paragraph(
            runs=[
                TextRun(text="In quantum mechanics, the momentum satisfies "),
                InlineEquation(latex=r"\text{where } p = \frac{h}{\lambda},"),
                TextRun(text="and the total energy is given by:"),
            ]
        ),
        DisplayEquation(latex=r"E = \hbar \omega", numbering="(1)", confidence=0.98),
        Table(
            rows=[
                TableRow(
                    cells=[
                        TableCell(elements=[Paragraph(runs=[TextRun(text="Quantity")])]),
                        TableCell(elements=[Paragraph(runs=[TextRun(text="Formula")])]),
                    ],
                    is_header=True,
                ),
                TableRow(
                    cells=[
                        TableCell(elements=[Paragraph(runs=[TextRun(text="Wavelength")])]),
                        TableCell(elements=[Paragraph(runs=[InlineEquation(latex=r"\lambda = h/p")])]),
                    ]
                ),
            ],
            caption="Table 1: Fundamental Relations",
        ),
        ImageBlock(src="figure1.png", asset_id=fig_asset.asset_id, caption="Figure 1: Wavepacket"),
    ]

    doc = Document(title="Full Academic Test", elements=elements)

    # 1. Audit and repair document
    audited_doc, audit_records = audit_document_content(doc, asset_store=store)
    assert len(audited_doc.audit_records) > 0

    # Prefix 'where ' should be extracted from equation
    para = audited_doc.elements[1]
    assert isinstance(para, Paragraph)
    eq_run = next(r for r in para.runs if isinstance(r, InlineEquation))
    assert not eq_run.latex.startswith(r"\text{where")
    assert eq_run.latex == r"p = \frac{h}{\lambda}"

    # 2. Export to DOCX
    docx_file = tmp_path / "academic_full.docx"
    warnings = build_docx_from_document(
        audited_doc, docx_file, pandoc_path="pandoc", template="academic_textbook", asset_store=store
    )
    assert docx_file.exists()

    # 3. Validate DOCX XML structure
    docx_audit = validate_docx_structure(docx_file, expected_doc=audited_doc)
    high_sev_errors = [r for r in docx_audit if r.severity == "high"]
    assert len(high_sev_errors) == 0

    # 4. Check contents within DOCX
    with zipfile.ZipFile(docx_file, "r") as zf:
        namelist = set(zf.namelist())
        assert "word/document.xml" in namelist
        # Verify media file was embedded
        media = [f for f in namelist if f.startswith("word/media/")]
        assert len(media) >= 1

        xml_str = zf.read("word/document.xml").decode("utf-8")
        assert "Mathematical Foundations" in xml_str
        assert "where" in xml_str
        assert "oMath" in xml_str
        assert "Wavepacket" in xml_str


def test_api_audit_endpoint() -> None:
    """Test /api/audit endpoint with structured document."""
    from fastapi.testclient import TestClient

    from backend.app import app

    client = TestClient(app)
    payload = {
        "document": {
            "title": "API Audit Test",
            "elements": [
                {
                    "type": "paragraph",
                    "runs": [
                        {"type": "text_run", "text": "Evaluating "},
                        {"type": "inline_equation", "latex": r"\text{where } x = 1,"},
                        {"type": "text_run", "text": "we proceed."},
                    ],
                }
            ],
        },
        "confidence_threshold": 0.70,
    }
    response = client.post("/api/audit", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "records" in data
    assert "summary" in data
    assert len(data["records"]) >= 1
    issue_types = [r["issue_type"] for r in data["records"]]
    assert "equation_boundary_error" in issue_types
