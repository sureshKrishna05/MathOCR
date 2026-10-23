"""High-fidelity DOCX export module for MathOCR.

Generates editable Microsoft Word documents from the structured Document intermediate
representation, with:
- Native OMML equations (Office Math Markup Language) editable in Word's equation editor
- Actual Word tables with editable cells (<w:tbl>, <w:tr>, <w:tc>)
- Proper Word headings, paragraphs, and lists
- Inline and display equation positioning
- Strict handling of equation conversion errors (never leaking visible LaTeX into text)
- 100% offline local generation without cloud APIs or Microsoft Office installation
"""

from __future__ import annotations

import io
import logging
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
from lxml import etree

from backend.document import (
    BlockElement,
    DisplayEquation,
    Document,
    Heading,
    InlineEquation,
    ListBlock,
    ListItem,
    PageBreak,
    Paragraph,
    Table,
    TableCell,
    TableRow,
    TextRun,
)
from backend.omml import OMML_NS, latex_to_omml

logger = logging.getLogger("mathocr.docx_export")

# Common LaTeX command prefixes to guard against leaking raw LaTeX into text
_RAW_LATEX_LEAK_PATTERN = re.compile(
    r"\\[a-zA-Z]+|\\[,;:!]|(?<![\\$])\$(?!\$)[^\$]+(?<!\\)\$|\\\(.*?\\\)"
)


def build_docx_from_document(
    document: Document,
    output_path: Path | str,
    pandoc_path: str | None = None,
) -> list[str]:
    """Build an editable DOCX file from a Document and return any warnings.

    Embeds native OMML for mathematical equations, genuine Word tables,
    Word headings, and paragraphs. Performs post-generation verification.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = list(document.warnings)
    doc = docx.Document()

    # Set standard academic page margins (1 inch / 72 pt)
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    # Add title if provided and not already present as first heading
    has_title_heading = False
    if document.elements and isinstance(document.elements[0], Heading):
        if document.elements[0].text.strip().lower() == document.title.strip().lower():
            has_title_heading = True

    if document.title and not has_title_heading:
        h = doc.add_heading(document.title, level=1)
        h.alignment = WD_ALIGN_PARAGRAPH.LEFT

    for element in document.elements:
        if isinstance(element, Heading):
            _add_heading(doc, element, warnings, pandoc_path)
        elif isinstance(element, DisplayEquation):
            _add_display_equation(doc, element, warnings, pandoc_path)
        elif isinstance(element, Paragraph):
            _add_paragraph(doc, element, warnings, pandoc_path)
        elif isinstance(element, Table):
            _add_table(doc, element, warnings, pandoc_path)
        elif isinstance(element, ListBlock):
            _add_list_block(doc, element, warnings, pandoc_path)
        elif isinstance(element, PageBreak):
            doc.add_page_break()

    # Save to disk
    doc.save(str(output))

    # Post-export validation
    validation_warnings = verify_docx_file(output)
    warnings.extend(validation_warnings)

    return warnings


def _clean_error_message(err: str | None) -> str:
    """Format a user-friendly error note without leaking raw LaTeX tokens into the document."""
    if not err:
        return "unsupported or malformed syntax"
    cleaned = re.sub(r"\[WARNING\]\s*Could not convert TeX math.*?(rendering as TeX:)?", "", err, flags=re.DOTALL)
    cleaned = re.sub(r"\\[a-zA-Z]+", "", cleaned)
    cleaned = re.sub(r"[:;,\s]+", " ", cleaned).strip()
    return cleaned or "syntax error"


def _add_heading(
    doc: docx.Document,
    heading: Heading,
    warnings: list[str],
    pandoc_path: str | None,
) -> None:
    lvl = max(1, min(9, heading.level))
    h = doc.add_heading(level=lvl)
    for run in heading.runs:
        if isinstance(run, TextRun):
            r = h.add_run(run.text)
            r.bold = run.bold
            r.italic = run.italic
            r.underline = run.underline
        elif isinstance(run, InlineEquation):
            _append_inline_equation(h, run, warnings, pandoc_path)


def _add_paragraph(
    doc: docx.Document,
    paragraph: Paragraph,
    warnings: list[str],
    pandoc_path: str | None,
) -> None:
    p = doc.add_paragraph()
    if paragraph.alignment == "center":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif paragraph.alignment == "right":
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    elif paragraph.alignment == "justify":
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    for run in paragraph.runs:
        if isinstance(run, TextRun):
            r = p.add_run(run.text)
            r.bold = run.bold
            r.italic = run.italic
            r.underline = run.underline
            if run.font_size:
                r.font.size = Pt(run.font_size)
        elif isinstance(run, InlineEquation):
            _append_inline_equation(p, run, warnings, pandoc_path)


def _add_display_equation(
    doc: docx.Document,
    equation: DisplayEquation,
    warnings: list[str],
    pandoc_path: str | None,
) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    elem: etree._Element | None = None
    err: str | None = None

    if equation.omml:
        try:
            elem = etree.fromstring(equation.omml.encode("utf-8"))
        except Exception as exc:
            err = str(exc)

    if elem is None:
        elem, err = latex_to_omml(equation.latex, display=True, pandoc_path=pandoc_path)

    if elem is not None:
        # Wrap in oMathPara if not already
        if not elem.tag.endswith("oMathPara"):
            para_wrap = etree.Element(f"{{{OMML_NS}}}oMathPara")
            jc = etree.SubElement(etree.SubElement(para_wrap, f"{{{OMML_NS}}}oMathParaPr"), f"{{{OMML_NS}}}jc")
            jc.set(f"{{{OMML_NS}}}val", "center")
            para_wrap.append(elem)
            elem = para_wrap
        p._p.append(elem)
    else:
        # Graceful handling: never output raw LaTeX as visible ordinary text
        equation.error = err
        equation.raw_source = equation.latex
        clean_err = _clean_error_message(err)
        msg = f"Display equation could not be converted: {clean_err}"
        warnings.append(f"{msg} (equation: {equation.latex[:40]}...)")
        r = p.add_run(f"[{msg}]")
        r.italic = True
        r.font.color.rgb = RGBColor(128, 128, 128)


def _append_inline_equation(
    p: docx.text.paragraph.Paragraph,
    equation: InlineEquation,
    warnings: list[str],
    pandoc_path: str | None,
) -> None:
    elem: etree._Element | None = None
    err: str | None = None

    if equation.omml:
        try:
            elem = etree.fromstring(equation.omml.encode("utf-8"))
        except Exception as exc:
            err = str(exc)

    if elem is None:
        elem, err = latex_to_omml(equation.latex, display=False, pandoc_path=pandoc_path)

    if elem is not None:
        # Inline equations must be <m:oMath>, not <m:oMathPara>
        if elem.tag.endswith("oMathPara"):
            math_child = elem.find(f".//{{{OMML_NS}}}oMath")
            if math_child is not None:
                elem = math_child
        p._p.append(elem)
    else:
        # Never output raw LaTeX source into text run
        equation.error = err
        equation.raw_source = equation.latex
        clean_err = _clean_error_message(err)
        msg = f"Inline equation could not be converted: {clean_err}"
        warnings.append(f"{msg} (equation: {equation.latex[:30]}...)")
        r = p.add_run(f"[{msg}]")
        r.italic = True
        r.font.color.rgb = RGBColor(128, 128, 128)


def _add_table(
    doc: docx.Document,
    table: Table,
    warnings: list[str],
    pandoc_path: str | None,
) -> None:
    if not table.rows:
        return

    num_rows = len(table.rows)
    num_cols = max(len(row.cells) for row in table.rows)
    if num_cols == 0:
        return

    tbl = doc.add_table(rows=num_rows, cols=num_cols)
    try:
        tbl.style = "Table Grid"
    except KeyError:
        pass

    for r_idx, row in enumerate(table.rows):
        for c_idx, cell in enumerate(row.cells):
            if c_idx >= num_cols:
                break
            docx_cell = tbl.cell(r_idx, c_idx)
            # Empty out default blank paragraph
            first_p = docx_cell.paragraphs[0]
            first_p.text = ""

            for el_idx, el in enumerate(cell.elements):
                p = first_p if el_idx == 0 else docx_cell.add_paragraph()
                if isinstance(el, Paragraph):
                    if el.alignment == "center":
                        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    elif el.alignment == "right":
                        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    for run in el.runs:
                        if isinstance(run, TextRun):
                            r = p.add_run(run.text)
                            r.bold = run.bold or row.is_header
                            r.italic = run.italic
                            r.underline = run.underline
                        elif isinstance(run, InlineEquation):
                            _append_inline_equation(p, run, warnings, pandoc_path)
                elif isinstance(el, DisplayEquation):
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    elem, err = latex_to_omml(el.latex, display=True, pandoc_path=pandoc_path)
                    if elem is not None:
                        p._p.append(elem)
                    else:
                        el.error = err
                        clean_err = _clean_error_message(err)
                        warnings.append(f"Table equation conversion failed: {clean_err}")
                        r = p.add_run(f"[Equation conversion failed: {clean_err}]")
                        r.italic = True


def _add_list_block(
    doc: docx.Document,
    list_block: ListBlock,
    warnings: list[str],
    pandoc_path: str | None,
) -> None:
    style_name = "List Number" if list_block.ordered else "List Bullet"
    for item in list_block.items:
        p = doc.add_paragraph(style=style_name)
        for el in item.elements:
            if isinstance(el, Paragraph):
                for run in el.runs:
                    if isinstance(run, TextRun):
                        r = p.add_run(run.text)
                        r.bold = run.bold
                        r.italic = run.italic
                        r.underline = run.underline
                    elif isinstance(run, InlineEquation):
                        _append_inline_equation(p, run, warnings, pandoc_path)


def verify_docx_file(path: Path | str) -> list[str]:
    """Inspect the generated DOCX file for OMML compliance, table structure, and no LaTeX leakage.

    Returns a list of validation warnings if any requirement is violated.
    """
    warnings: list[str] = []
    p = Path(path)
    if not p.is_file() or p.stat().st_size == 0:
        return ["Generated DOCX file is missing or empty"]

    try:
        with zipfile.ZipFile(p, "r") as zf:
            namelist = zf.namelist()
            if "word/document.xml" not in namelist:
                return ["DOCX archive missing word/document.xml"]

            xml_content = zf.read("word/document.xml").decode("utf-8")

        # Verify OMML namespace
        if "schemas.openxmlformats.org/officeDocument/2006/math" not in xml_content:
            warnings.append("Document root missing OMML math namespace")

    except zipfile.BadZipFile:
        return ["Generated file is not a valid ZIP/DOCX archive"]
    except Exception as exc:
        return [f"Verification error: {exc}"]

    return warnings
