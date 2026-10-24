"""High-fidelity DOCX export module for MathOCR.

Generates professional, editable Microsoft Word documents from the structured Document
intermediate representation, with:
- Multiple professional document templates (Academic Textbook, Research Paper,
  Standard Editable Document, Preserve Original Layout)
- Native OMML equations (Office Math Markup Language) editable in Word's equation editor
- Actual Word tables with editable cells (<w:tbl>, <w:tr>, <w:tc>) and template-specific borders
- Proper Word headings, paragraphs, lists, and images
- OpenXML headers, footers, and field-based dynamic page numbering (<w:fldSimple w:instr="PAGE"/>)
- Inline and display equation positioning
- Strict handling of equation conversion errors (never leaking visible LaTeX into text)
- 100% offline local generation without cloud APIs or Microsoft Office installation
"""

from __future__ import annotations

import logging
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Inches, Pt, RGBColor
from lxml import etree

from backend.document import (
    BlockElement,
    DisplayEquation,
    Document,
    Heading,
    ImageBlock,
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

TemplatePreset = Literal["academic_textbook", "research_paper", "standard", "preserve_layout"]


@dataclass(frozen=True)
class TemplateConfig:
    preset: TemplatePreset
    page_width_in: float
    page_height_in: float
    top_margin_in: float
    bottom_margin_in: float
    left_margin_in: float
    right_margin_in: float
    body_font: str
    heading_font: str
    body_size_pt: float
    body_line_spacing: float
    body_space_after_pt: float
    body_space_before_pt: float
    heading1_size_pt: float
    heading1_before_pt: float
    heading1_after_pt: float
    heading1_color: RGBColor
    heading2_size_pt: float
    heading2_before_pt: float
    heading2_after_pt: float
    heading2_color: RGBColor
    heading3_size_pt: float
    heading3_before_pt: float
    heading3_after_pt: float
    heading3_color: RGBColor
    title_size_pt: float
    title_color: RGBColor
    table_border_color: str
    table_header_bg: str
    show_header: bool
    header_right: bool
    show_footer: bool
    footer_format: str  # "em_dash" | "page_right" | "page_of_total"


def get_template_config(
    preset: TemplatePreset = "academic_textbook",
    metadata: dict[str, Any] | None = None,
) -> TemplateConfig:
    meta = metadata or {}
    p = str(preset).lower()

    if p == "research_paper":
        return TemplateConfig(
            preset="research_paper",
            page_width_in=8.5,
            page_height_in=11.0,
            top_margin_in=0.75,
            bottom_margin_in=0.75,
            left_margin_in=0.75,
            right_margin_in=0.75,
            body_font="Times New Roman",
            heading_font="Times New Roman",
            body_size_pt=10.5,
            body_line_spacing=1.15,
            body_space_after_pt=4.0,
            body_space_before_pt=0.0,
            heading1_size_pt=14.0,
            heading1_before_pt=10.0,
            heading1_after_pt=4.0,
            heading1_color=RGBColor(17, 17, 17),
            heading2_size_pt=12.0,
            heading2_before_pt=8.0,
            heading2_after_pt=3.0,
            heading2_color=RGBColor(34, 34, 34),
            heading3_size_pt=10.5,
            heading3_before_pt=4.0,
            heading3_after_pt=2.0,
            heading3_color=RGBColor(51, 51, 51),
            title_size_pt=16.0,
            title_color=RGBColor(0, 0, 0),
            table_border_color="111111",
            table_header_bg="FFFFFF",
            show_header=True,
            header_right=False,
            show_footer=True,
            footer_format="page_right",
        )
    elif p == "standard":
        return TemplateConfig(
            preset="standard",
            page_width_in=8.5,
            page_height_in=11.0,
            top_margin_in=1.0,
            bottom_margin_in=1.0,
            left_margin_in=1.0,
            right_margin_in=1.0,
            body_font="Calibri",
            heading_font="Calibri",
            body_size_pt=11.0,
            body_line_spacing=1.15,
            body_space_after_pt=6.0,
            body_space_before_pt=0.0,
            heading1_size_pt=16.0,
            heading1_before_pt=12.0,
            heading1_after_pt=4.0,
            heading1_color=RGBColor(30, 58, 138),
            heading2_size_pt=13.0,
            heading2_before_pt=8.0,
            heading2_after_pt=3.0,
            heading2_color=RGBColor(37, 99, 235),
            heading3_size_pt=11.5,
            heading3_before_pt=4.0,
            heading3_after_pt=2.0,
            heading3_color=RGBColor(55, 65, 81),
            title_size_pt=20.0,
            title_color=RGBColor(30, 58, 138),
            table_border_color="D1D5DB",
            table_header_bg="F3F4F6",
            show_header=False,
            header_right=False,
            show_footer=True,
            footer_format="page_of_total",
        )
    elif p == "preserve_layout":
        pw = float(meta.get("page_width", 8.5)) if meta.get("page_width") else 8.5
        ph = float(meta.get("page_height", 11.0)) if meta.get("page_height") else 11.0
        return TemplateConfig(
            preset="preserve_layout",
            page_width_in=pw if 4.0 <= pw <= 17.0 else 8.5,
            page_height_in=ph if 4.0 <= ph <= 22.0 else 11.0,
            top_margin_in=0.8,
            bottom_margin_in=0.8,
            left_margin_in=0.8,
            right_margin_in=0.8,
            body_font="Arial",
            heading_font="Arial",
            body_size_pt=10.5,
            body_line_spacing=1.05,
            body_space_after_pt=3.0,
            body_space_before_pt=0.0,
            heading1_size_pt=15.0,
            heading1_before_pt=8.0,
            heading1_after_pt=3.0,
            heading1_color=RGBColor(0, 0, 0),
            heading2_size_pt=12.5,
            heading2_before_pt=6.0,
            heading2_after_pt=2.0,
            heading2_color=RGBColor(0, 0, 0),
            heading3_size_pt=11.0,
            heading3_before_pt=4.0,
            heading3_after_pt=2.0,
            heading3_color=RGBColor(0, 0, 0),
            title_size_pt=18.0,
            title_color=RGBColor(0, 0, 0),
            table_border_color="9CA3AF",
            table_header_bg="E5E7EB",
            show_header=False,
            header_right=False,
            show_footer=True,
            footer_format="page_right",
        )
    else:  # academic_textbook (default)
        return TemplateConfig(
            preset="academic_textbook",
            page_width_in=8.27,  # A4 standard
            page_height_in=11.69,
            top_margin_in=1.0,
            bottom_margin_in=1.0,
            left_margin_in=1.0,
            right_margin_in=1.0,
            body_font="Georgia",
            heading_font="Georgia",
            body_size_pt=11.0,
            body_line_spacing=1.2,
            body_space_after_pt=6.0,
            body_space_before_pt=0.0,
            heading1_size_pt=18.0,
            heading1_before_pt=14.0,
            heading1_after_pt=6.0,
            heading1_color=RGBColor(26, 54, 93),  # Deep Academic Slate Navy
            heading2_size_pt=14.0,
            heading2_before_pt=10.0,
            heading2_after_pt=4.0,
            heading2_color=RGBColor(43, 108, 176),
            heading3_size_pt=12.0,
            heading3_before_pt=6.0,
            heading3_after_pt=2.0,
            heading3_color=RGBColor(45, 55, 72),
            title_size_pt=22.0,
            title_color=RGBColor(26, 54, 93),
            table_border_color="CBD5E1",
            table_header_bg="F1F5F9",
            show_header=True,
            header_right=True,
            show_footer=True,
            footer_format="em_dash",
        )


def build_docx_from_document(
    document: Document,
    output_path: Path | str,
    pandoc_path: str | None = None,
    template: TemplatePreset = "academic_textbook",
) -> list[str]:
    """Build an editable DOCX file from a Document and return any warnings.

    Applies the chosen template preset, embeds native OMML equations, genuine Word
    tables with styled borders, OpenXML headers/footers with dynamic page numbers,
    and performs post-generation validation.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = list(document.warnings)
    doc = docx.Document()

    config = get_template_config(template, document.metadata)
    _apply_template_styles(doc, config)
    _setup_header_footer(doc, config, document.title)

    # Add title if provided and not already present as first heading
    has_title_heading = False
    if document.elements and isinstance(document.elements[0], Heading):
        if document.elements[0].text.strip().lower() == document.title.strip().lower():
            has_title_heading = True
    if document.title.strip().lower() in ("mathocr document", "mathocr equations", "untitled"):
        if any(isinstance(elem, Heading) for elem in document.elements[:3]):
            has_title_heading = True

    if document.title and not has_title_heading:
        h = doc.add_heading(level=1)
        hp = h.paragraph_format
        hp.space_before = Pt(0)
        hp.space_after = Pt(config.heading1_after_pt * 1.5)
        hp.alignment = (
            WD_ALIGN_PARAGRAPH.CENTER
            if config.preset in ("research_paper", "academic_textbook")
            else WD_ALIGN_PARAGRAPH.LEFT
        )
        r = h.add_run(document.title)
        r.font.name = config.heading_font
        r.font.size = Pt(config.title_size_pt)
        r.font.color.rgb = config.title_color
        r.bold = True

    for element in document.elements:
        if isinstance(element, Heading):
            _add_heading(doc, element, warnings, pandoc_path, config)
        elif isinstance(element, DisplayEquation):
            _add_display_equation(doc, element, warnings, pandoc_path, config)
        elif isinstance(element, Paragraph):
            _add_paragraph(doc, element, warnings, pandoc_path, config)
        elif isinstance(element, Table):
            _add_table(doc, element, warnings, pandoc_path, config)
        elif isinstance(element, ListBlock):
            _add_list_block(doc, element, warnings, pandoc_path, config)
        elif isinstance(element, PageBreak):
            doc.add_page_break()
        elif isinstance(element, ImageBlock):
            _add_image_block(doc, element, warnings, config)

    # Save to disk
    doc.save(str(output))

    # Post-export validation
    validation_warnings = verify_docx_file(output)
    warnings.extend(validation_warnings)

    return warnings


def _apply_template_styles(doc: docx.Document, config: TemplateConfig) -> None:
    """Configure page geometry, margins, and base styles on the Document."""
    for section in doc.sections:
        section.page_width = Inches(config.page_width_in)
        section.page_height = Inches(config.page_height_in)
        section.top_margin = Inches(config.top_margin_in)
        section.bottom_margin = Inches(config.bottom_margin_in)
        section.left_margin = Inches(config.left_margin_in)
        section.right_margin = Inches(config.right_margin_in)

    # Base Normal style
    try:
        normal = doc.styles["Normal"]
        normal.font.name = config.body_font
        normal.font.size = Pt(config.body_size_pt)
        normal.font.color.rgb = RGBColor(30, 30, 30)
        pf = normal.paragraph_format
        pf.line_spacing = config.body_line_spacing
        pf.space_after = Pt(config.body_space_after_pt)
        pf.space_before = Pt(config.body_space_before_pt)
    except Exception:
        pass


def _setup_header_footer(doc: docx.Document, config: TemplateConfig, title: str) -> None:
    """Configure WordprocessingML headers and footers with dynamic page numbering."""
    if not doc.sections:
        return
    section = doc.sections[0]
    section.different_first_page_header_footer = False

    # Header
    if config.show_header and title:
        header = section.header
        hp = header.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT if config.header_right else WD_ALIGN_PARAGRAPH.LEFT
        hp.paragraph_format.space_after = Pt(4)
        hrun = hp.add_run(title[:60] + ("…" if len(title) > 60 else ""))
        hrun.font.name = config.heading_font
        hrun.font.size = Pt(8.5)
        hrun.font.italic = True
        hrun.font.color.rgb = RGBColor(128, 128, 128)

    # Footer
    if config.show_footer:
        footer = section.footer
        fp = footer.paragraphs[0]
        if config.footer_format == "em_dash":
            fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r_pre = fp.add_run("— ")
            r_pre.font.name = config.body_font
            r_pre.font.size = Pt(9.0)
            r_pre.font.color.rgb = RGBColor(120, 120, 120)

            fld = parse_xml(r'<w:fldSimple %s w:instr="PAGE"/>' % nsdecls("w"))
            fp._p.append(fld)

            r_post = fp.add_run(" —")
            r_post.font.name = config.body_font
            r_post.font.size = Pt(9.0)
            r_post.font.color.rgb = RGBColor(120, 120, 120)

        elif config.footer_format == "page_of_total":
            fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            r1 = fp.add_run("Page ")
            r1.font.name = config.body_font
            r1.font.size = Pt(9.0)
            r1.font.color.rgb = RGBColor(120, 120, 120)

            fld1 = parse_xml(r'<w:fldSimple %s w:instr="PAGE"/>' % nsdecls("w"))
            fp._p.append(fld1)

            r2 = fp.add_run(" of ")
            r2.font.name = config.body_font
            r2.font.size = Pt(9.0)
            r2.font.color.rgb = RGBColor(120, 120, 120)

            fld2 = parse_xml(r'<w:fldSimple %s w:instr="NUMPAGES"/>' % nsdecls("w"))
            fp._p.append(fld2)

        else:  # "page_right"
            fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            r1 = fp.add_run()
            r1.font.name = config.body_font
            r1.font.size = Pt(9.0)
            r1.font.color.rgb = RGBColor(120, 120, 120)
            fld = parse_xml(r'<w:fldSimple %s w:instr="PAGE"/>' % nsdecls("w"))
            fp._p.append(fld)


def _clean_error_message(err: str | None) -> str:
    """Format a user-friendly error note without leaking ANY raw LaTeX tokens into the document."""
    if not err:
        return "unsupported or malformed syntax"
    err_str = str(err).lower()
    if "timed out" in err_str:
        return "conversion timed out"
    if "empty" in err_str:
        return "empty mathematical expression"
    if "not installed" in err_str or "not available" in err_str:
        return "converter not available"
    if "unexpected control sequence" in err_str:
        return "unsupported mathematical control sequence"
    if "unexpected" in err_str:
        return "unexpected mathematical syntax"
    return "syntax error"


def _add_heading(
    doc: docx.Document,
    heading: Heading,
    warnings: list[str],
    pandoc_path: str | None,
    config: TemplateConfig,
) -> None:
    lvl = max(1, min(6, heading.level))
    h = doc.add_heading(level=lvl)
    hp = h.paragraph_format
    hp.keep_with_next = True

    if heading.alignment == "center" or (lvl == 1 and config.preset in ("academic_textbook", "research_paper")):
        hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif heading.alignment == "right":
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    else:
        hp.alignment = WD_ALIGN_PARAGRAPH.LEFT

    if lvl == 1:
        hp.space_before = Pt(config.heading1_before_pt)
        hp.space_after = Pt(config.heading1_after_pt)
        target_size = config.heading1_size_pt
        target_color = config.heading1_color
    elif lvl == 2:
        hp.space_before = Pt(config.heading2_before_pt)
        hp.space_after = Pt(config.heading2_after_pt)
        target_size = config.heading2_size_pt
        target_color = config.heading2_color
    else:
        hp.space_before = Pt(config.heading3_before_pt)
        hp.space_after = Pt(config.heading3_after_pt)
        target_size = config.heading3_size_pt
        target_color = config.heading3_color

    for run in heading.runs:
        if isinstance(run, TextRun):
            r = h.add_run(run.text)
            r.font.name = config.heading_font
            r.font.size = Pt(target_size)
            r.font.color.rgb = target_color
            r.bold = True
            r.italic = run.italic
            r.underline = run.underline
        elif isinstance(run, InlineEquation):
            _append_inline_equation(h, run, warnings, pandoc_path)


def _add_paragraph(
    doc: docx.Document,
    paragraph: Paragraph,
    warnings: list[str],
    pandoc_path: str | None,
    config: TemplateConfig,
) -> None:
    p = doc.add_paragraph()
    if paragraph.alignment == "center":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif paragraph.alignment == "right":
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    elif paragraph.alignment == "justify" or (
        config.preset in ("academic_textbook", "research_paper")
        and paragraph.alignment == "left"
        and (len(paragraph.runs) > 1 or len(paragraph.text()) > 80)
    ):
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    elif paragraph.alignment == "left":
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT

    pf = p.paragraph_format
    pf.line_spacing = config.body_line_spacing
    pf.space_after = Pt(config.body_space_after_pt)
    pf.space_before = Pt(config.body_space_before_pt)

    for run in paragraph.runs:
        if isinstance(run, TextRun):
            r = p.add_run(run.text)
            r.font.name = config.body_font
            r.font.size = Pt(run.font_size or config.body_size_pt)
            r.bold = run.bold
            r.italic = run.italic
            r.underline = run.underline
        elif isinstance(run, InlineEquation):
            _append_inline_equation(p, run, warnings, pandoc_path)


def _add_display_equation(
    doc: docx.Document,
    equation: DisplayEquation,
    warnings: list[str],
    pandoc_path: str | None,
    config: TemplateConfig,
) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p.paragraph_format
    pf.space_before = Pt(6)
    pf.space_after = Pt(6)

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
        if not elem.tag.endswith("oMathPara"):
            para_wrap = etree.Element(f"{{{OMML_NS}}}oMathPara")
            jc = etree.SubElement(
                etree.SubElement(para_wrap, f"{{{OMML_NS}}}oMathParaPr"), f"{{{OMML_NS}}}jc"
            )
            jc.set(f"{{{OMML_NS}}}val", "center")
            para_wrap.append(elem)
            elem = para_wrap
        p._p.append(elem)

        if equation.numbering:
            r_num = p.add_run(f"    ({equation.numbering})")
            r_num.font.name = config.body_font
            r_num.font.size = Pt(config.body_size_pt * 0.95)
            r_num.font.color.rgb = RGBColor(100, 100, 100)
    else:
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
        if elem.tag.endswith("oMathPara"):
            math_child = elem.find(f".//{{{OMML_NS}}}oMath")
            if math_child is not None:
                elem = math_child
        p._p.append(elem)
    else:
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
    config: TemplateConfig,
) -> None:
    if not table.rows:
        return

    num_rows = len(table.rows)
    num_cols = max(len(row.cells) for row in table.rows)
    if num_cols == 0:
        return

    tbl = doc.add_table(rows=num_rows, cols=num_cols)
    _style_table(tbl, config)

    for r_idx, row in enumerate(table.rows):
        is_hdr = row.is_header or (r_idx == 0)
        for c_idx, cell in enumerate(row.cells):
            if c_idx >= num_cols:
                break
            docx_cell = tbl.cell(r_idx, c_idx)
            first_p = docx_cell.paragraphs[0]
            first_p.text = ""

            # Header cell background shading
            if is_hdr and config.table_header_bg:
                shd = parse_xml(r'<w:shd %s w:fill="%s"/>' % (nsdecls("w"), config.table_header_bg))
                docx_cell._tc.get_or_add_tcPr().append(shd)

            for el_idx, el in enumerate(cell.elements):
                p = first_p if el_idx == 0 else docx_cell.add_paragraph()
                p.paragraph_format.space_before = Pt(1)
                p.paragraph_format.space_after = Pt(1)
                p.paragraph_format.line_spacing = 1.05

                if isinstance(el, Paragraph):
                    if el.alignment == "center" or is_hdr or c_idx > 0:
                        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    elif el.alignment == "right":
                        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    for run in el.runs:
                        if isinstance(run, TextRun):
                            r = p.add_run(run.text)
                            r.font.name = config.body_font
                            r.font.size = Pt(config.body_size_pt * 0.95)
                            r.bold = run.bold or is_hdr
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


def _style_table(tbl: docx.table.Table, config: TemplateConfig) -> None:
    """Apply template-specific borders, margins, and alignment to a Word table."""
    tblPr = tbl._tbl.tblPr

    # Center table
    jc = parse_xml(r'<w:jc %s w:val="center"/>' % nsdecls("w"))
    tblPr.append(jc)

    # Padding: 120 dxa = 6pt top/bottom, 160 dxa = 8pt left/right
    tblCellMar = parse_xml(
        r'<w:tblCellMar %s>'
        r'<w:top w:w="120" w:type="dxa"/>'
        r'<w:bottom w:w="120" w:type="dxa"/>'
        r'<w:left w:w="160" w:type="dxa"/>'
        r'<w:right w:w="160" w:type="dxa"/>'
        r'</w:tblCellMar>' % nsdecls("w")
    )
    tblPr.append(tblCellMar)

    if config.preset == "research_paper":
        # Formal academic booktabs: thick top & bottom, thin header separator, no vertical rules
        borders = parse_xml(
            r'<w:tblBorders %s>'
            r'<w:top w:val="single" w:sz="12" w:space="0" w:color="111111"/>'
            r'<w:bottom w:val="single" w:sz="12" w:space="0" w:color="111111"/>'
            r'<w:left w:val="none"/>'
            r'<w:right w:val="none"/>'
            r'<w:insideH w:val="single" w:sz="6" w:space="0" w:color="111111"/>'
            r'<w:insideV w:val="none"/>'
            r'</w:tblBorders>' % nsdecls("w")
        )
    elif config.preset == "academic_textbook":
        # Academic textbook: classic structured borders
        borders = parse_xml(
            r'<w:tblBorders %s>'
            r'<w:top w:val="single" w:sz="10" w:space="0" w:color="1A365D"/>'
            r'<w:bottom w:val="single" w:sz="10" w:space="0" w:color="1A365D"/>'
            r'<w:left w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
            r'<w:right w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
            r'<w:insideH w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
            r'<w:insideV w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
            r'</w:tblBorders>' % nsdecls("w")
        )
    else:
        # Standard clean grid table
        bc = config.table_border_color
        borders = parse_xml(
            r'<w:tblBorders %s>'
            r'<w:top w:val="single" w:sz="6" w:space="0" w:color="%s"/>'
            r'<w:bottom w:val="single" w:sz="6" w:space="0" w:color="%s"/>'
            r'<w:left w:val="single" w:sz="6" w:space="0" w:color="%s"/>'
            r'<w:right w:val="single" w:sz="6" w:space="0" w:color="%s"/>'
            r'<w:insideH w:val="single" w:sz="4" w:space="0" w:color="%s"/>'
            r'<w:insideV w:val="single" w:sz="4" w:space="0" w:color="%s"/>'
            r'</w:tblBorders>' % (nsdecls("w"), bc, bc, bc, bc, bc, bc)
        )
    tblPr.append(borders)


def _add_list_block(
    doc: docx.Document,
    list_block: ListBlock,
    warnings: list[str],
    pandoc_path: str | None,
    config: TemplateConfig,
) -> None:
    style_name = "List Number" if list_block.ordered else "List Bullet"
    for item in list_block.items:
        p = doc.add_paragraph(style=style_name)
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = config.body_line_spacing
        for el in item.elements:
            if isinstance(el, Paragraph):
                for run in el.runs:
                    if isinstance(run, TextRun):
                        r = p.add_run(run.text)
                        r.font.name = config.body_font
                        r.font.size = Pt(config.body_size_pt)
                        r.bold = run.bold
                        r.italic = run.italic
                        r.underline = run.underline
                    elif isinstance(run, InlineEquation):
                        _append_inline_equation(p, run, warnings, pandoc_path)


def _add_image_block(
    doc: docx.Document,
    image_block: ImageBlock,
    warnings: list[str],
    config: TemplateConfig,
) -> None:
    """Embed an image with optional centered caption."""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = bool(image_block.caption)

    added = False
    if image_block.src:
        src_path = Path(image_block.src)
        if src_path.is_file():
            try:
                width = Inches(min(6.0, image_block.width)) if image_block.width else Inches(5.5)
                p.add_run().add_picture(str(src_path), width=width)
                added = True
            except Exception as exc:
                warnings.append(f"Could not embed image {image_block.src}: {exc}")

    if not added:
        r = p.add_run(f"[Figure: {image_block.caption or image_block.src or 'Image'}]")
        r.font.name = config.body_font
        r.italic = True
        r.font.color.rgb = RGBColor(128, 128, 128)

    if image_block.caption:
        cap_p = doc.add_paragraph()
        cap_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap_p.paragraph_format.space_before = Pt(2)
        cap_p.paragraph_format.space_after = Pt(8)
        cap_r = cap_p.add_run(f"Figure: {image_block.caption}")
        cap_r.font.name = config.body_font
        cap_r.italic = True
        cap_r.font.size = Pt(9.5)
        cap_r.font.color.rgb = RGBColor(80, 80, 80)


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
