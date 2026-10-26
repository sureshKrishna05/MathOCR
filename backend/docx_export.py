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

import io
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

from backend.assets import default_asset_store

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
    equation_image_fallback_threshold: float = 0.8


def should_fallback_to_image(
    equation: DisplayEquation | InlineEquation,
    threshold: float = 0.8,
    omml_elem: Any | None = None,
) -> tuple[bool, str | None]:
    """Centralize the decision that determines whether an equation is exported as editable OMML
    or preserved as a source-image crop.

    Returns:
        (should_fallback: bool, reason: str | None)
    """
    if getattr(equation, "fallback_image", False):
        return True, "marked for image fallback"

    if getattr(equation, "error", None) is not None:
        return True, f"equation error: {equation.error}"

    conf = getattr(equation, "confidence", None)
    if conf is not None and conf < threshold:
        return True, f"confidence ({conf:.2f}) below threshold ({threshold:.2f})"

    if omml_elem is None and not getattr(equation, "omml", None) and not getattr(equation, "latex", None):
        return True, "empty formula content"

    return False, None


def get_template_config(
    preset: TemplatePreset = "academic_textbook",
    metadata: dict[str, Any] | None = None,
    equation_image_fallback_threshold: float = 0.8,
) -> TemplateConfig:
    meta = metadata or {}
    p = str(preset).lower()
    threshold = float(meta.get("equation_image_fallback_threshold", equation_image_fallback_threshold))

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
            equation_image_fallback_threshold=threshold,
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
            equation_image_fallback_threshold=threshold,
        )
    elif p == "preserve_layout":
        pw = float(meta.get("page_width", 8.5)) if meta.get("page_width") else 8.5
        ph = float(meta.get("page_height", 11.0)) if meta.get("page_height") else 11.0
        return TemplateConfig(
            preset="preserve_layout",
            page_width_in=pw if 4.0 <= pw <= 17.0 else 8.5,
            page_height_in=ph if 4.0 <= ph <= 22.0 else 11.0,
            top_margin_in=0.55,
            bottom_margin_in=0.55,
            left_margin_in=0.55,
            right_margin_in=0.55,
            body_font="Arial",
            heading_font="Arial",
            # Screenshot and book-page sources commonly use substantially
            # smaller type than the academic template.  Preserve mode keeps
            # their visual density and avoids moving a source page's final
            # worked line onto a new Word page.
            body_size_pt=8.5,
            body_line_spacing=1.0,
            body_space_after_pt=1.0,
            body_space_before_pt=0.0,
            heading1_size_pt=11.5,
            heading1_before_pt=4.0,
            heading1_after_pt=1.0,
            heading1_color=RGBColor(0, 0, 0),
            heading2_size_pt=10.0,
            heading2_before_pt=3.0,
            heading2_after_pt=1.0,
            heading2_color=RGBColor(0, 0, 0),
            heading3_size_pt=9.0,
            heading3_before_pt=2.0,
            heading3_after_pt=1.0,
            heading3_color=RGBColor(0, 0, 0),
            title_size_pt=14.0,
            title_color=RGBColor(0, 0, 0),
            table_border_color="9CA3AF",
            table_header_bg="E5E7EB",
            show_header=False,
            header_right=False,
            show_footer=True,
            footer_format="page_right",
            equation_image_fallback_threshold=threshold,
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
            equation_image_fallback_threshold=threshold,
        )


def build_docx_from_document(
    document: Document,
    output_path: Path | str,
    pandoc_path: str | None = None,
    template: TemplatePreset = "academic_textbook",
    asset_store: Any | None = None,
) -> list[str]:
    """Build an editable DOCX file from a Document and return any warnings.

    Applies the chosen template preset, embeds native OMML equations, genuine Word
    tables with styled borders, OpenXML headers/footers with dynamic page numbers,
    and performs post-generation validation.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = list(document.warnings)
    stats: dict[str, int] = {"native_omml": 0, "image_fallback": 0, "unresolved": 0}
    doc = docx.Document()

    config = (
        template
        if isinstance(template, TemplateConfig)
        else get_template_config(template, metadata=document.metadata)
    )
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

    elem_idx = 0
    total_elems = len(document.elements)
    while elem_idx < total_elems:
        element = document.elements[elem_idx]
        if (
            isinstance(element, Table)
            and elem_idx + 1 < total_elems
            and isinstance(document.elements[elem_idx + 1], Table)
            and _should_place_tables_side_by_side(element, document.elements[elem_idx + 1])
        ):
            _add_side_by_side_tables(
                doc,
                element,
                document.elements[elem_idx + 1],
                warnings,
                pandoc_path,
                config,
                asset_store=asset_store,
                stats=stats,
            )
            elem_idx += 2
            continue

        if isinstance(element, Heading):
            _add_heading(
                doc, element, warnings, pandoc_path, config, asset_store=asset_store, stats=stats
            )
        elif isinstance(element, DisplayEquation):
            _add_display_equation(
                doc, element, warnings, pandoc_path, config, asset_store=asset_store, stats=stats
            )
        elif isinstance(element, Paragraph):
            _add_paragraph(
                doc, element, warnings, pandoc_path, config, asset_store=asset_store, stats=stats
            )
        elif isinstance(element, Table):
            _add_table(
                doc, element, warnings, pandoc_path, config, asset_store=asset_store, stats=stats
            )
        elif isinstance(element, ListBlock):
            _add_list_block(
                doc, element, warnings, pandoc_path, config, asset_store=asset_store, stats=stats
            )
        elif isinstance(element, PageBreak):
            doc.add_page_break()
        elif isinstance(element, ImageBlock):
            _add_image_block(doc, element, warnings, config, asset_store=asset_store)
        elem_idx += 1

    document.metadata["export_stats"] = dict(stats)
    if stats["image_fallback"] > 0 or stats["unresolved"] > 0:
        summary = (
            f"Export summary: {stats['native_omml']} native OMML equations, "
            f"{stats['image_fallback']} image fallback equations, "
            f"{stats['unresolved']} unresolved equations"
        )
        warnings.append(summary)

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


def _source_rgb(value: str | None) -> RGBColor | None:
    """Parse a source-derived six-digit RGB value defensively."""

    if not value or not re.fullmatch(r"[0-9A-Fa-f]{6}", value):
        return None
    return RGBColor(int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def _apply_shading(paragraph: docx.text.paragraph.Paragraph, color: str | None) -> None:
    if not color or not re.fullmatch(r"[0-9A-Fa-f]{6}", color):
        return
    p_pr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), color.upper())
    p_pr.append(shd)


def _apply_run_background(run: Any, color: str | None) -> None:
    if not color or not re.fullmatch(r"[0-9A-Fa-f]{6}", color):
        return
    r_pr = run._r.get_or_add_rPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), color.upper())
    r_pr.append(shd)


def _add_heading(
    doc: docx.Document,
    heading: Heading,
    warnings: list[str],
    pandoc_path: str | None,
    config: TemplateConfig,
    asset_store: Any | None = None,
    stats: dict[str, int] | None = None,
) -> None:
    lvl = max(1, min(6, heading.level))
    h = doc.add_heading(level=lvl)
    hp = h.paragraph_format
    hp.keep_with_next = True

    is_exercises_header = heading.text.strip().lower() in (
        "exercises",
        "exercises.",
        "exercise",
        "problems",
        "problems.",
    )
    if heading.alignment == "center" or is_exercises_header or (
        lvl == 1 and config.preset in ("academic_textbook", "research_paper")
    ):
        hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif heading.alignment == "right":
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    else:
        hp.alignment = WD_ALIGN_PARAGRAPH.LEFT

    if is_exercises_header:
        hp.space_before = Pt(8.0)
        hp.space_after = Pt(4.0)
        target_size = config.heading2_size_pt
        target_color = RGBColor(0, 0, 0)
    elif lvl == 1:
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
            r.font.color.rgb = _source_rgb(run.color) or target_color
            r.bold = True
            r.italic = True if is_exercises_header else run.italic
            r.underline = run.underline
            _apply_run_background(r, run.background_color)
        elif isinstance(run, InlineEquation):
            _append_inline_equation(
                h, run, warnings, pandoc_path, config=config, asset_store=asset_store, stats=stats
            )


def _add_paragraph(
    doc: docx.Document,
    paragraph: Paragraph,
    warnings: list[str],
    pandoc_path: str | None,
    config: TemplateConfig,
    asset_store: Any | None = None,
    stats: dict[str, int] | None = None,
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
    if paragraph.style == "exercises_heading":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pf.space_before = Pt(8.0)
        pf.space_after = Pt(4.0)
        pf.keep_with_next = True
    elif paragraph.style == "theorem":
        pf.space_before = Pt(4.0)
        pf.space_after = Pt(4.0)
        pf.keep_with_next = True
    elif paragraph.style == "exercise":
        pf.space_before = Pt(2.0)
        pf.space_after = Pt(2.0)
    else:
        pf.space_after = Pt(config.body_space_after_pt)
        pf.space_before = Pt(config.body_space_before_pt)
    _apply_shading(p, paragraph.shading)

    for run in paragraph.runs:
        if isinstance(run, TextRun):
            r = p.add_run(run.text)
            r.font.name = config.body_font
            r.font.size = Pt(run.font_size or config.body_size_pt)
            r.font.color.rgb = _source_rgb(run.color) or RGBColor(30, 30, 30)
            r.bold = run.bold
            r.italic = run.italic
            r.underline = run.underline
            _apply_run_background(r, run.background_color)
        elif isinstance(run, InlineEquation):
            _append_inline_equation(
                p, run, warnings, pandoc_path, config=config, asset_store=asset_store, stats=stats
            )


def _add_display_equation(
    doc: docx.Document,
    equation: DisplayEquation,
    warnings: list[str],
    pandoc_path: str | None,
    config: TemplateConfig,
    asset_store: Any | None = None,
    stats: dict[str, int] | None = None,
) -> None:
    number_paragraph: docx.text.paragraph.Paragraph | None = None
    if equation.numbering:
        # A borderless three-cell table keeps the formula centred in the usable
        # line while anchoring its source label at the right edge.  Unlike
        # spaces or a text box, both objects remain editable in Word.
        table = doc.add_table(rows=1, cols=3)
        table.autofit = False
        table._tbl.tblPr.append(
            parse_xml(
                r'<w:tblBorders %s><w:top w:val="nil"/><w:left w:val="nil"/>'
                r'<w:bottom w:val="nil"/><w:right w:val="nil"/>'
                r'<w:insideH w:val="nil"/><w:insideV w:val="nil"/></w:tblBorders>'
                % nsdecls("w")
            )
        )
        usable_width = config.page_width_in - config.left_margin_in - config.right_margin_in
        widths = (0.15 * usable_width, 0.70 * usable_width, 0.15 * usable_width)
        for cell, width in zip(table.rows[0].cells, widths):
            cell.width = Inches(width)
        p = table.cell(0, 1).paragraphs[0]
        number_paragraph = table.cell(0, 2).paragraphs[0]
        number_paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    else:
        p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p.paragraph_format
    equation_spacing = 1 if config.preset == "preserve_layout" else 6
    pf.space_before = Pt(equation_spacing)
    pf.space_after = Pt(equation_spacing)

    threshold = getattr(config, "equation_image_fallback_threshold", 0.8)
    needs_fallback, fallback_reason = should_fallback_to_image(equation, threshold=threshold)

    elem: etree._Element | None = None
    err: str | None = None

    if not needs_fallback:
        if equation.omml:
            try:
                elem = etree.fromstring(equation.omml.encode("utf-8"))
            except Exception as exc:
                err = str(exc)

        if elem is None and equation.latex:
            elem, err = latex_to_omml(equation.latex, display=True, pandoc_path=pandoc_path)

        if elem is None:
            needs_fallback = True
            fallback_reason = f"OMML conversion failed: {_clean_error_message(err)}"

    if elem is not None and not needs_fallback:
        if not elem.tag.endswith("oMathPara"):
            para_wrap = etree.Element(f"{{{OMML_NS}}}oMathPara")
            jc = etree.SubElement(
                etree.SubElement(para_wrap, f"{{{OMML_NS}}}oMathParaPr"), f"{{{OMML_NS}}}jc"
            )
            jc.set(f"{{{OMML_NS}}}val", "center")
            para_wrap.append(elem)
            elem = para_wrap
        p._p.append(elem)

        if equation.numbering and number_paragraph is not None:
            r_num = number_paragraph.add_run(f"({equation.numbering})")
            r_num.font.name = config.body_font
            r_num.font.size = Pt(config.body_size_pt * 0.95)
            r_num.font.color.rgb = RGBColor(100, 100, 100)
        if stats is not None:
            stats["native_omml"] += 1
    else:
        store = asset_store or default_asset_store
        img_stream: io.BytesIO | None = None
        if equation.asset_id:
            asset = store.get(equation.asset_id)
            if asset and asset.data:
                img_stream = io.BytesIO(asset.data)

        if img_stream is not None:
            try:
                max_w_in = max(
                    1.5, config.page_width_in - (config.left_margin_in + config.right_margin_in)
                )
                if equation.box:
                    box_w = equation.box[2] - equation.box[0]
                    width_in = min(max_w_in, max(1.5, box_w / 160.0))
                else:
                    width_in = min(max_w_in, 4.5)
                r_img = p.add_run()
                r_img.add_picture(img_stream, width=Inches(width_in))
                if equation.numbering and number_paragraph is not None:
                    r_num = number_paragraph.add_run(f"({equation.numbering})")
                    r_num.font.name = config.body_font
                    r_num.font.size = Pt(config.body_size_pt * 0.95)
                    r_num.font.color.rgb = RGBColor(100, 100, 100)
                warnings.append(
                    f"Display equation fallback to source image (asset: {equation.asset_id}, reason: {fallback_reason})"
                )
                if stats is not None:
                    stats["image_fallback"] += 1
                return
            except Exception as pic_err:
                warnings.append(f"Could not embed display fallback image: {pic_err}")

        equation.error = err or fallback_reason
        equation.raw_source = equation.latex
        clean_err = _clean_error_message(err or fallback_reason)
        msg = f"Display equation could not be converted: {clean_err}"
        warnings.append(f"{msg} (equation: {equation.latex[:40]}...)")
        r = p.add_run(f"[{msg}]")
        r.italic = True
        r.font.color.rgb = RGBColor(128, 128, 128)
        if stats is not None:
            stats["unresolved"] += 1


def _append_inline_equation(
    p: docx.text.paragraph.Paragraph,
    equation: InlineEquation,
    warnings: list[str],
    pandoc_path: str | None,
    config: TemplateConfig | None = None,
    asset_store: Any | None = None,
    stats: dict[str, int] | None = None,
) -> None:
    threshold = getattr(config, "equation_image_fallback_threshold", 0.8) if config else 0.8
    needs_fallback, fallback_reason = should_fallback_to_image(equation, threshold=threshold)

    elem: etree._Element | None = None
    err: str | None = None

    if not needs_fallback:
        if equation.omml:
            try:
                elem = etree.fromstring(equation.omml.encode("utf-8"))
            except Exception as exc:
                err = str(exc)

        if elem is None and equation.latex:
            elem, err = latex_to_omml(equation.latex, display=False, pandoc_path=pandoc_path)

        if elem is None:
            needs_fallback = True
            fallback_reason = f"OMML conversion failed: {_clean_error_message(err)}"

    if elem is not None and not needs_fallback:
        if elem.tag.endswith("oMathPara"):
            math_child = elem.find(f".//{{{OMML_NS}}}oMath")
            if math_child is not None:
                elem = math_child
        p._p.append(elem)
        if stats is not None:
            stats["native_omml"] += 1
    else:
        store = asset_store or default_asset_store
        img_stream: io.BytesIO | None = None
        if equation.asset_id:
            asset = store.get(equation.asset_id)
            if asset and asset.data:
                img_stream = io.BytesIO(asset.data)

        if img_stream is not None:
            try:
                run = p.add_run()
                font_size = config.body_size_pt if config else 11.0
                run.add_picture(img_stream, height=Pt(font_size * 1.35))
                warnings.append(
                    f"Inline equation fallback to source image (asset: {equation.asset_id}, reason: {fallback_reason})"
                )
                if stats is not None:
                    stats["image_fallback"] += 1
                return
            except Exception as pic_err:
                warnings.append(f"Could not embed fallback image: {pic_err}")

        equation.error = err or fallback_reason
        equation.raw_source = equation.latex
        clean_err = _clean_error_message(err or fallback_reason)
        msg = f"Inline equation could not be converted: {clean_err}"
        warnings.append(f"{msg} (equation: {equation.latex[:30]}...)")
        r = p.add_run(f"[{msg}]")
        r.italic = True
        r.font.color.rgb = RGBColor(128, 128, 128)
        if stats is not None:
            stats["unresolved"] += 1


def _populate_table_cells(
    tbl: docx.table.Table,
    table: Table,
    warnings: list[str],
    pandoc_path: str | None,
    config: TemplateConfig,
    asset_store: Any | None = None,
    stats: dict[str, int] | None = None,
) -> None:
    num_cols = max(len(row.cells) for row in table.rows) if table.rows else 0
    threshold = getattr(config, "equation_image_fallback_threshold", 0.8)
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
                    _apply_shading(p, el.shading)
                    for run in el.runs:
                        if isinstance(run, TextRun):
                            r = p.add_run(run.text)
                            r.font.name = config.body_font
                            r.font.size = Pt(config.body_size_pt * 0.95)
                            r.font.color.rgb = _source_rgb(run.color) or RGBColor(30, 30, 30)
                            r.bold = run.bold or is_hdr
                            r.italic = run.italic
                            r.underline = run.underline
                            _apply_run_background(r, run.background_color)
                        elif isinstance(run, InlineEquation):
                            _append_inline_equation(
                                p,
                                run,
                                warnings,
                                pandoc_path,
                                config=config,
                                asset_store=asset_store,
                                stats=stats,
                            )
                elif isinstance(el, DisplayEquation):
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    needs_fallback, fallback_reason = should_fallback_to_image(
                        el, threshold=threshold
                    )
                    elem: etree._Element | None = None
                    err: str | None = None
                    if not needs_fallback:
                        if el.omml:
                            try:
                                elem = etree.fromstring(el.omml.encode("utf-8"))
                            except Exception as exc:
                                err = str(exc)
                        if elem is None and el.latex:
                            elem, err = latex_to_omml(el.latex, display=True, pandoc_path=pandoc_path)
                        if elem is None:
                            needs_fallback = True
                            fallback_reason = f"OMML conversion failed: {_clean_error_message(err)}"
                    if elem is not None and not needs_fallback:
                        p._p.append(elem)
                        if stats is not None:
                            stats["native_omml"] += 1
                    else:
                        store = asset_store or default_asset_store
                        img_stream = None
                        if el.asset_id:
                            asset = store.get(el.asset_id)
                            if asset and asset.data:
                                img_stream = io.BytesIO(asset.data)
                        if img_stream is not None:
                            try:
                                r_img = p.add_run()
                                r_img.add_picture(img_stream, width=Inches(2.0))
                                warnings.append(
                                    f"Table equation fallback to source image (asset: {el.asset_id}, reason: {fallback_reason})"
                                )
                                if stats is not None:
                                    stats["image_fallback"] += 1
                                continue
                            except Exception:
                                pass
                        el.error = err or fallback_reason
                        clean_err = _clean_error_message(err or fallback_reason)
                        warnings.append(f"Table equation conversion failed: {clean_err}")
                        r = p.add_run(f"[Equation conversion failed: {clean_err}]")
                        r.italic = True
                        if stats is not None:
                            stats["unresolved"] += 1


def _should_place_tables_side_by_side(t1: Table, t2: Table) -> bool:
    """Check if two consecutive tables should be placed side-by-side."""
    if not t1.rows or not t2.rows:
        return False
    cols1 = max(len(r.cells) for r in t1.rows)
    cols2 = max(len(r.cells) for r in t2.rows)
    if cols1 > 5 or cols2 > 5 or len(t1.rows) > 6 or len(t2.rows) > 6:
        return False
    if t1.box and t2.box:
        same_box = (t1.box == t2.box)
        vert_overlap = not (t1.box[3] < t2.box[1] or t2.box[3] < t1.box[1])
        return same_box or vert_overlap
    return True


def _remove_table_borders(tbl: docx.table.Table) -> None:
    tblPr = tbl._tbl.tblPr
    borders = parse_xml(
        r'<w:tblBorders %s>'
        r'<w:top w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        r'<w:left w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        r'<w:bottom w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        r'<w:right w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        r'<w:insideH w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        r'<w:insideV w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        r'</w:tblBorders>' % nsdecls("w")
    )
    tblPr.append(borders)


def _add_side_by_side_tables(
    doc: docx.Document,
    table1: Table,
    table2: Table,
    warnings: list[str],
    pandoc_path: str | None,
    config: TemplateConfig,
    asset_store: Any | None = None,
    stats: dict[str, int] | None = None,
) -> None:
    """Render two compact tables side-by-side inside a borderless layout container."""
    container = doc.add_table(rows=1, cols=3)
    _remove_table_borders(container)
    jc = parse_xml(r'<w:jc %s w:val="center"/>' % nsdecls("w"))
    container._tbl.tblPr.append(jc)

    container.columns[0].width = Inches(2.7)
    container.columns[1].width = Inches(0.5)
    container.columns[2].width = Inches(2.7)

    # Table 1
    c1 = container.cell(0, 0)
    store = asset_store or default_asset_store
    asset1 = store.get(table1.asset_id) if getattr(table1, "fallback_image", False) and getattr(table1, "asset_id", None) else None
    if asset1 and asset1.data:
        img_s1 = io.BytesIO(asset1.data)
        c1.paragraphs[0].add_run().add_picture(img_s1, width=Inches(2.7))
        warnings.append("Table structure could not be reliably recovered; embedded original table crop as fallback image.")
        if stats is not None:
            stats["image_fallback"] += 1
    elif table1.rows:
        p_before1 = c1.paragraphs[0]._p
        t1 = c1.add_table(rows=len(table1.rows), cols=max(len(r.cells) for r in table1.rows))
        c1._tc.remove(p_before1)
        if c1.paragraphs:
            c1.paragraphs[-1].paragraph_format.space_before = Pt(0)
            c1.paragraphs[-1].paragraph_format.space_after = Pt(0)
        _style_table(t1, config)
        _populate_table_cells(
            t1, table1, warnings, pandoc_path, config, asset_store=asset_store, stats=stats
        )

    # Spacer
    c_spacer = container.cell(0, 1)
    c_spacer.paragraphs[0].text = ""

    # Table 2
    c2 = container.cell(0, 2)
    asset2 = store.get(table2.asset_id) if getattr(table2, "fallback_image", False) and getattr(table2, "asset_id", None) else None
    if asset2 and asset2.data:
        img_s2 = io.BytesIO(asset2.data)
        c2.paragraphs[0].add_run().add_picture(img_s2, width=Inches(2.7))
        warnings.append("Table structure could not be reliably recovered; embedded original table crop as fallback image.")
        if stats is not None:
            stats["image_fallback"] += 1
    elif table2.rows:
        p_before2 = c2.paragraphs[0]._p
        t2 = c2.add_table(rows=len(table2.rows), cols=max(len(r.cells) for r in table2.rows))
        c2._tc.remove(p_before2)
        if c2.paragraphs:
            c2.paragraphs[-1].paragraph_format.space_before = Pt(0)
            c2.paragraphs[-1].paragraph_format.space_after = Pt(0)
        _style_table(t2, config)
        _populate_table_cells(
            t2, table2, warnings, pandoc_path, config, asset_store=asset_store, stats=stats
        )


def _add_table(
    doc: docx.Document,
    table: Table,
    warnings: list[str],
    pandoc_path: str | None,
    config: TemplateConfig,
    asset_store: Any | None = None,
    stats: dict[str, int] | None = None,
) -> None:
    if getattr(table, "fallback_image", False) and getattr(table, "asset_id", None):
        store = asset_store or default_asset_store
        asset = store.get(table.asset_id)
        if asset and asset.data:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(8)
            p.paragraph_format.space_after = Pt(4)
            img_stream = io.BytesIO(asset.data)
            max_w_in = max(1.5, config.page_width_in - (config.left_margin_in + config.right_margin_in))
            if table.box:
                box_w = table.box[2] - table.box[0]
                frac = min(1.0, max(0.25, box_w / 1400.0))
                w = Inches(min(max_w_in, max(2.0, max_w_in * frac)))
            else:
                w = Inches(min(max_w_in, 5.0))
            p.add_run().add_picture(img_stream, width=w)
            warnings.append("Table structure could not be reliably recovered; embedded original table crop as fallback image.")
            if stats is not None:
                stats["image_fallback"] += 1
            return

    if not table.rows:
        return

    num_rows = len(table.rows)
    num_cols = max(len(row.cells) for row in table.rows)
    if num_cols == 0:
        return

    tbl = doc.add_table(rows=num_rows, cols=num_cols)
    _style_table(tbl, config)
    _populate_table_cells(
        tbl, table, warnings, pandoc_path, config, asset_store=asset_store, stats=stats
    )


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
    asset_store: Any | None = None,
    stats: dict[str, int] | None = None,
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
                        _append_inline_equation(
                            p,
                            run,
                            warnings,
                            pandoc_path,
                            config=config,
                            asset_store=asset_store,
                            stats=stats,
                        )


def _add_image_block(
    doc: docx.Document,
    image_block: ImageBlock,
    warnings: list[str],
    config: TemplateConfig,
    asset_store: Any | None = None,
) -> None:
    """Embed an image with source layout alignment, derived width, and optional caption."""
    p = doc.add_paragraph()

    align_map = {
        "left": WD_ALIGN_PARAGRAPH.LEFT,
        "right": WD_ALIGN_PARAGRAPH.RIGHT,
        "center": WD_ALIGN_PARAGRAPH.CENTER,
    }
    p.alignment = align_map.get(image_block.alignment, WD_ALIGN_PARAGRAPH.CENTER)
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = bool(image_block.caption)

    # Calculate derived width within printable margins
    max_w_in = max(1.5, config.page_width_in - (config.left_margin_in + config.right_margin_in))
    if image_block.width is not None and image_block.width > 0:
        width = Inches(min(max_w_in, max(1.5, image_block.width)))
    elif image_block.box is not None:
        box_w = image_block.box[2] - image_block.box[0]
        frac = min(1.0, max(0.25, box_w / 1400.0))
        width = Inches(min(max_w_in, max(2.0, max_w_in * frac)))
    else:
        width = Inches(min(max_w_in, 5.2))

    added = False
    img_stream: io.BytesIO | None = None

    # 1. Resolve from asset_store
    store = asset_store or default_asset_store
    asset_id = image_block.asset_id
    if not asset_id and image_block.src and image_block.src.startswith("asset:"):
        asset_id = image_block.src[6:].strip()
    elif not asset_id and image_block.src and re.match(r"^[0-9a-fA-F]{16,64}$", image_block.src):
        asset_id = image_block.src

    if asset_id:
        asset = store.get(asset_id)
        if asset and asset.data:
            img_stream = io.BytesIO(asset.data)

    # 2. Resolve from local file path if valid
    if img_stream is None and image_block.src and not image_block.src.startswith("asset:"):
        src_path = Path(image_block.src)
        if src_path.is_file():
            try:
                img_stream = io.BytesIO(src_path.read_bytes())
            except Exception as read_err:
                warnings.append(f"Could not read image file {image_block.src}: {read_err}")

    if img_stream is not None:
        try:
            p.add_run().add_picture(img_stream, width=width)
            added = True
        except Exception as exc:
            warnings.append(f"Could not embed image: {exc}")

    if not added:
        r = p.add_run(f"[Figure: {image_block.caption or 'Image'}]")
        r.font.name = config.body_font
        r.italic = True
        r.font.color.rgb = RGBColor(128, 128, 128)

    if image_block.caption:
        cap_p = doc.add_paragraph()
        cap_p.alignment = p.alignment
        cap_p.paragraph_format.space_before = Pt(2)
        cap_p.paragraph_format.space_after = Pt(8)
        cap_p.paragraph_format.keep_with_next = False
        cap_clean = image_block.caption.strip()
        if cap_clean.lower().startswith(("figure", "fig.", "illustration", "diagram", "chart")):
            label = cap_clean
        else:
            label = f"Figure: {cap_clean}"
        cap_r = cap_p.add_run(label)
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

            # Verify image relationships
            if "word/_rels/document.xml.rels" in namelist:
                rels_xml = zf.read("word/_rels/document.xml.rels").decode("utf-8")
                for target in re.findall(r'Target="(media/[^"]+)"', rels_xml):
                    full_target = f"word/{target}"
                    if full_target not in namelist:
                        warnings.append(f"Referenced image {target} missing from DOCX package")

            # Verify no raw LaTeX commands leak into body text outside OMML
            text_runs = re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml_content)
            for t_text in text_runs:
                if re.search(r"\\(begin|frac|dfrac|sqrt|int|sum)\b", t_text):
                    warnings.append(f"Raw LaTeX detected in text run: {t_text[:40]}")
                    break

    except zipfile.BadZipFile:
        return ["Generated file is not a valid ZIP/DOCX archive"]
    except Exception as exc:
        return [f"Verification error: {exc}"]

    return warnings
