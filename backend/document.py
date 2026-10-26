"""Structured intermediate document representation for MathOCR.

Serves as the high-fidelity representation between OCR/Layout recognition and
document export (DOCX, Markdown, etc.). Preserves reading order, paragraphs,
headings, inline/display equations, tables, lists, and formatting.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from statistics import median
from typing import Any, Literal

from backend.geometry import Box
from backend.latex import clean_latex


@dataclass(slots=True)
class TextRun:
    """One run of styled text within a paragraph, heading, or table cell."""

    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    font_size: float | None = None
    color: str | None = None
    type: Literal["text_run"] = "text_run"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "text_run",
            "text": self.text,
            "bold": self.bold,
            "italic": self.italic,
            "underline": self.underline,
            "font_size": self.font_size,
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TextRun:
        return cls(
            text=str(data.get("text", "")),
            bold=bool(data.get("bold", False)),
            italic=bool(data.get("italic", False)),
            underline=bool(data.get("underline", False)),
            font_size=data.get("font_size"),
            color=data.get("color"),
        )


@dataclass(slots=True)
class InlineEquation:
    """An inline mathematical formula positioned within a text paragraph or cell."""

    latex: str
    omml: str | None = None
    confidence: float | None = None
    raw_source: str | None = None
    error: str | None = None
    box: tuple[int, int, int, int] | None = None
    type: Literal["inline_equation"] = "inline_equation"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "inline_equation",
            "latex": self.latex,
            "omml": self.omml,
            "confidence": self.confidence,
            "raw_source": self.raw_source,
            "error": self.error,
            "box": self.box,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InlineEquation:
        return cls(
            latex=str(data.get("latex", "")),
            omml=data.get("omml"),
            confidence=data.get("confidence"),
            raw_source=data.get("raw_source"),
            error=data.get("error"),
            box=tuple(data["box"]) if data.get("box") else None,
        )


@dataclass(slots=True)
class DisplayEquation:
    """A standalone display equation on its own line/block."""

    latex: str
    omml: str | None = None
    confidence: float | None = None
    raw_source: str | None = None
    error: str | None = None
    numbering: str | None = None
    alignment: str = "center"  # center | left | right
    box: tuple[int, int, int, int] | None = None
    type: Literal["display_equation"] = "display_equation"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "display_equation",
            "latex": self.latex,
            "omml": self.omml,
            "confidence": self.confidence,
            "raw_source": self.raw_source,
            "error": self.error,
            "numbering": self.numbering,
            "alignment": self.alignment,
            "box": self.box,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DisplayEquation:
        return cls(
            latex=str(data.get("latex", "")),
            omml=data.get("omml"),
            confidence=data.get("confidence"),
            raw_source=data.get("raw_source"),
            error=data.get("error"),
            numbering=data.get("numbering"),
            alignment=str(data.get("alignment", "center")),
            box=tuple(data["box"]) if data.get("box") else None,
        )


RunType = TextRun | InlineEquation


@dataclass(slots=True)
class Paragraph:
    """A paragraph of mixed text and inline formulas."""

    runs: list[RunType] = field(default_factory=list)
    style: str = "normal"
    alignment: str = "left"  # left | center | right | justify
    box: tuple[int, int, int, int] | None = None
    type: Literal["paragraph"] = "paragraph"

    def text(self) -> str:
        parts = []
        for run in self.runs:
            if isinstance(run, TextRun):
                parts.append(run.text)
            elif isinstance(run, InlineEquation):
                parts.append(f"${run.latex}$")
        return "".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "paragraph",
            "runs": [run.to_dict() for run in self.runs],
            "style": self.style,
            "alignment": self.alignment,
            "box": self.box,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Paragraph:
        runs = []
        for item in data.get("runs", []):
            if item.get("type") == "inline_equation":
                runs.append(InlineEquation.from_dict(item))
            else:
                runs.append(TextRun.from_dict(item))
        return cls(
            runs=runs,
            style=str(data.get("style", "normal")),
            alignment=str(data.get("alignment", "left")),
            box=tuple(data["box"]) if data.get("box") else None,
        )


@dataclass(slots=True)
class Heading:
    """A section heading with level 1 to 6."""

    level: int = 1
    text: str = ""
    runs: list[RunType] = field(default_factory=list)
    alignment: str = "left"  # left | center | right
    box: tuple[int, int, int, int] | None = None
    type: Literal["heading"] = "heading"

    def __post_init__(self) -> None:
        if not self.runs and self.text:
            self.runs = [TextRun(text=self.text, bold=True)]
        elif self.runs and not self.text:
            self.text = "".join(r.text if isinstance(r, TextRun) else f"${r.latex}$" for r in self.runs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "heading",
            "level": self.level,
            "text": self.text,
            "runs": [run.to_dict() for run in self.runs],
            "alignment": self.alignment,
            "box": self.box,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Heading:
        runs = []
        for item in data.get("runs", []):
            if item.get("type") == "inline_equation":
                runs.append(InlineEquation.from_dict(item))
            else:
                runs.append(TextRun.from_dict(item))
        return cls(
            level=int(data.get("level", 1)),
            text=str(data.get("text", "")),
            runs=runs,
            alignment=str(data.get("alignment", "left")),
            box=tuple(data["box"]) if data.get("box") else None,
        )


@dataclass(slots=True)
class TableCell:
    """One cell in a table, containing paragraphs or equations."""

    elements: list[Paragraph | DisplayEquation] = field(default_factory=list)
    col_span: int = 1
    row_span: int = 1
    box: tuple[int, int, int, int] | None = None

    def text(self) -> str:
        return " ".join(
            elem.text() if isinstance(elem, Paragraph) else f"$${elem.latex}$$"
            for elem in self.elements
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "elements": [elem.to_dict() for elem in self.elements],
            "col_span": self.col_span,
            "row_span": self.row_span,
            "box": self.box,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TableCell:
        elements: list[Paragraph | DisplayEquation] = []
        for item in data.get("elements", []):
            if item.get("type") == "display_equation":
                elements.append(DisplayEquation.from_dict(item))
            else:
                elements.append(Paragraph.from_dict(item))
        return cls(
            elements=elements,
            col_span=int(data.get("col_span", 1)),
            row_span=int(data.get("row_span", 1)),
            box=tuple(data["box"]) if data.get("box") else None,
        )


@dataclass(slots=True)
class TableRow:
    """One row of cells in a table."""

    cells: list[TableCell] = field(default_factory=list)
    is_header: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "cells": [cell.to_dict() for cell in self.cells],
            "is_header": self.is_header,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TableRow:
        return cls(
            cells=[TableCell.from_dict(cell) for cell in data.get("cells", [])],
            is_header=bool(data.get("is_header", False)),
        )


@dataclass(slots=True)
class Table:
    """An editable table containing rows and cells."""

    rows: list[TableRow] = field(default_factory=list)
    caption: str | None = None
    col_widths: list[float] | None = None
    box: tuple[int, int, int, int] | None = None
    type: Literal["table"] = "table"

    def num_columns(self) -> int:
        if not self.rows:
            return 0
        return max(len(row.cells) for row in self.rows)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "table",
            "rows": [row.to_dict() for row in self.rows],
            "caption": self.caption,
            "col_widths": self.col_widths,
            "box": self.box,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Table:
        return cls(
            rows=[TableRow.from_dict(row) for row in data.get("rows", [])],
            caption=data.get("caption"),
            col_widths=data.get("col_widths"),
            box=tuple(data["box"]) if data.get("box") else None,
        )


@dataclass(slots=True)
class ListItem:
    """An individual list item."""

    elements: list[Paragraph | DisplayEquation | Table] = field(default_factory=list)
    level: int = 0
    ordered: bool = False
    number: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "elements": [elem.to_dict() for elem in self.elements],
            "level": self.level,
            "ordered": self.ordered,
            "number": self.number,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ListItem:
        elements = []
        for item in data.get("elements", []):
            t = item.get("type")
            if t == "display_equation":
                elements.append(DisplayEquation.from_dict(item))
            elif t == "table":
                elements.append(Table.from_dict(item))
            else:
                elements.append(Paragraph.from_dict(item))
        return cls(
            elements=elements,
            level=int(data.get("level", 0)),
            ordered=bool(data.get("ordered", False)),
            number=data.get("number"),
        )


@dataclass(slots=True)
class ListBlock:
    """A bulleted or numbered list."""

    items: list[ListItem] = field(default_factory=list)
    ordered: bool = False
    type: Literal["list"] = "list"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "list",
            "items": [item.to_dict() for item in self.items],
            "ordered": self.ordered,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ListBlock:
        return cls(
            items=[ListItem.from_dict(item) for item in data.get("items", [])],
            ordered=bool(data.get("ordered", False)),
        )


@dataclass(slots=True)
class PageBreak:
    """Page break marker between document sections."""

    page: int | None = None
    type: Literal["page_break"] = "page_break"

    def to_dict(self) -> dict[str, Any]:
        return {"type": "page_break", "page": self.page}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PageBreak:
        return cls(page=data.get("page"))


@dataclass(slots=True)
class ImageBlock:
    """An embedded image or figure reference with optional caption and layout geometry."""

    src: str = ""
    asset_id: str | None = None
    caption: str | None = None
    width: float | None = None
    height: float | None = None
    aspect_ratio: float | None = None
    alignment: str = "center"  # center | left | right
    source_page: int | None = None
    box: tuple[int, int, int, int] | None = None
    type: Literal["image"] = "image"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "image",
            "src": self.src,
            "asset_id": self.asset_id,
            "caption": self.caption,
            "width": self.width,
            "height": self.height,
            "aspect_ratio": self.aspect_ratio,
            "alignment": self.alignment,
            "source_page": self.source_page,
            "box": self.box,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ImageBlock:
        return cls(
            src=str(data.get("src", "")),
            asset_id=data.get("asset_id"),
            caption=data.get("caption"),
            width=data.get("width"),
            height=data.get("height"),
            aspect_ratio=data.get("aspect_ratio"),
            alignment=str(data.get("alignment", "center")),
            source_page=data.get("source_page"),
            box=tuple(data["box"]) if data.get("box") else None,
        )


BlockElement = Paragraph | Heading | DisplayEquation | Table | ListBlock | PageBreak | ImageBlock


@dataclass(slots=True)
class Document:
    """The structured intermediate document holding all layout blocks."""

    title: str = "MathOCR document"
    elements: list[BlockElement] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "elements": [elem.to_dict() for elem in self.elements],
            "metadata": self.metadata,
            "warnings": self.warnings,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Document:
        elements: list[BlockElement] = []
        for item in data.get("elements", []):
            t = item.get("type")
            if t == "heading":
                elements.append(Heading.from_dict(item))
            elif t == "display_equation":
                elements.append(DisplayEquation.from_dict(item))
            elif t == "table":
                elements.append(Table.from_dict(item))
            elif t == "list":
                elements.append(ListBlock.from_dict(item))
            elif t == "page_break":
                elements.append(PageBreak.from_dict(item))
            elif t == "image":
                elements.append(ImageBlock.from_dict(item))
            else:
                elements.append(Paragraph.from_dict(item))
        return cls(
            title=str(data.get("title", "MathOCR document")),
            elements=elements,
            metadata=dict(data.get("metadata", {})),
            warnings=list(data.get("warnings", [])),
        )

    def to_markdown(self) -> str:
        """Render this structured document as standard Markdown with TeX math."""
        blocks: list[str] = []
        for elem in self.elements:
            if isinstance(elem, Heading):
                hashes = "#" * max(1, min(6, elem.level))
                if elem.alignment == "center":
                    blocks.append(f'<p align="center">{hashes} {elem.text}</p>')
                elif elem.alignment == "right":
                    blocks.append(f'<p align="right">{hashes} {elem.text}</p>')
                else:
                    blocks.append(f"{hashes} {elem.text}")
            elif isinstance(elem, DisplayEquation):
                blocks.append(f"$$\n{elem.latex}\n$$")
            elif isinstance(elem, Paragraph):
                pieces = []
                for run in elem.runs:
                    if isinstance(run, InlineEquation):
                        if pieces and not pieces[-1].endswith((" ", "\n", "\t", "$", "(", "[")):
                            pieces.append(" ")
                        pieces.append(f"${run.latex}$")
                    elif isinstance(run, TextRun):
                        text = run.text
                        if run.bold and run.italic:
                            text = f"***{text}***"
                        elif run.bold:
                            text = f"**{text}**"
                        elif run.italic:
                            text = f"*{text}*"
                        if pieces and pieces[-1].endswith("$") and not text.startswith((" ", "\n", "\t", ".", ",", ";", ":", ")", "]")):
                            pieces.append(" ")
                        pieces.append(text)
                para_text = "".join(pieces).strip()
                if para_text:
                    if elem.alignment == "center":
                        para_text = f"<p align=\"center\">{para_text}</p>"
                    elif elem.alignment == "right":
                        para_text = f"<p align=\"right\">{para_text}</p>"
                    elif elem.alignment == "justify":
                        para_text = f"<p align=\"justify\">{para_text}</p>"
                    blocks.append(para_text)
            elif isinstance(elem, Table):
                table_lines = _render_table_markdown(elem)
                if table_lines:
                    blocks.append("\n".join(table_lines))
            elif isinstance(elem, ListBlock):
                list_lines = []
                for i, item in enumerate(elem.items, start=1):
                    prefix = f"{i}. " if elem.ordered else "- "
                    item_text = " ".join(
                        e.text() if isinstance(e, Paragraph) else "" for e in item.elements
                    ).strip()
                    list_lines.append(f"{prefix}{item_text}")
                if list_lines:
                    blocks.append("\n".join(list_lines))
            elif isinstance(elem, PageBreak):
                blocks.append("\n---\n")
            elif isinstance(elem, ImageBlock):
                cap = elem.caption or ""
                src_ref = f"asset:{elem.asset_id}" if elem.asset_id else (elem.src or "image")
                blocks.append(f"![{cap}]({src_ref})")

        return "\n\n".join(b for b in blocks if b)

    @classmethod
    def from_markdown(cls, markdown: str, title: str = "MathOCR document") -> Document:
        """Parse Markdown text (headings, math, tables, lists, text) into Document."""
        elements: list[BlockElement] = []
        lines = markdown.splitlines()
        i = 0
        n = len(lines)

        while i < n:
            line = lines[i]
            stripped = line.strip()

            if not stripped:
                i += 1
                continue

            # Page break (--- or ***)
            if re.match(r"^---+$", stripped) or re.match(r"^\*\*\*+$", stripped):
                elements.append(PageBreak())
                i += 1
                continue

            # Image (![caption](src))
            m_img = re.match(r"^!\[(.*?)\]\((.*?)\)$", stripped)
            if m_img:
                caption = m_img.group(1).strip() or None
                src = m_img.group(2).strip()
                asset_id = None
                if src.startswith("asset:"):
                    asset_id = src[6:].strip()
                elif re.match(r"^[0-9a-fA-F]{16,64}$", src):
                    asset_id = src
                elements.append(ImageBlock(src=src, asset_id=asset_id, caption=caption))
                i += 1
                continue

            # Heading (# ...)
            raw_h_line = stripped
            h_align = "left"
            m_outer_align = re.match(
                r"^<(?:p\s+align=[\"'](center|right|justify)[\"']|center)>(.*?)(?:</(?:p|center)>)?$",
                raw_h_line,
                flags=re.IGNORECASE,
            )
            if m_outer_align:
                h_align = m_outer_align.group(1).lower() if m_outer_align.group(1) else "center"
                raw_h_line = m_outer_align.group(2).strip()

            m_heading = re.match(r"^(#{1,6})\s+(.*)$", raw_h_line)
            if m_heading:
                level = len(m_heading.group(1))
                h_text = m_heading.group(2).strip()
                m_inner_align = re.match(
                    r"^<(?:p\s+align=[\"'](center|right|justify)[\"']|center)>(.*?)(?:</(?:p|center)>)?$",
                    h_text,
                    flags=re.IGNORECASE,
                )
                if m_inner_align:
                    h_align = m_inner_align.group(1).lower() if m_inner_align.group(1) else "center"
                    h_text = m_inner_align.group(2).strip()
                elif h_text.startswith("->") and h_text.endswith("<-") and len(h_text) > 4:
                    h_align = "center"
                    h_text = h_text[2:-2].strip()
                elif h_text.startswith("->") and len(h_text) > 2:
                    h_align = "right"
                    h_text = h_text[2:].strip()

                runs = _parse_inline_text(h_text)
                elements.append(Heading(level=level, text=h_text, runs=runs, alignment=h_align))
                i += 1
                continue

            # Display equation ($$...$$ or \[...\])
            if stripped.startswith("$$") or stripped.startswith("\\["):
                closing = "$$" if stripped.startswith("$$") else "\\]"
                if stripped.endswith(closing) and len(stripped) > 4:
                    eq_content = stripped[2:-2].strip()
                    elements.append(DisplayEquation(latex=eq_content))
                    i += 1
                    continue
                # Multi-line display equation
                eq_lines = [stripped[2:].strip()]
                i += 1
                while i < n and not lines[i].strip().endswith(closing):
                    eq_lines.append(lines[i])
                    i += 1
                if i < n:
                    last_line = lines[i].strip()
                    eq_lines.append(last_line[:-2].strip() if last_line.endswith(closing) else last_line)
                    i += 1
                eq_content = clean_latex("\n".join(eq_lines)).strip()
                elements.append(DisplayEquation(latex=eq_content))
                continue

            # Table (lines starting with '|' and having multiple rows or separator)
            if stripped.startswith("|") and not stripped.startswith("$$"):
                table_lines = [line]
                i += 1
                while i < n and lines[i].strip().startswith("|"):
                    table_lines.append(lines[i])
                    i += 1
                table_elem = _parse_table_markdown(table_lines)
                if table_elem is not None:
                    elements.append(table_elem)
                    continue
                # If table parsing failed, roll back lines and treat as text
                i -= len(table_lines) - 1

            # List block (- or * or 1.)
            m_bullet = re.match(r"^([-*+]|\d+\.)\s+(.*)$", stripped)
            if m_bullet:
                ordered = m_bullet.group(1).endswith(".")
                items: list[ListItem] = []
                while i < n:
                    item_strip = lines[i].strip()
                    item_match = re.match(r"^([-*+]|\d+\.)\s+(.*)$", item_strip)
                    if not item_match:
                        break
                    item_text = item_match.group(2).strip()
                    item_runs = _parse_inline_text(item_text)
                    items.append(
                        ListItem(
                            elements=[Paragraph(runs=item_runs)],
                            ordered=ordered,
                        )
                    )
                    i += 1

                # Disambiguate single-item numbered lines that are actually section headings:
                # e.g. "1. Introduction and Theoretical Foundation" or "2. Experimental Measurements"
                if len(items) == 1 and ordered:
                    single_text = m_bullet.group(2).strip()
                    looks_like_heading = (
                        bool(re.match(r"^[A-Z][A-Za-z0-9\s,:;'-]+$", single_text))
                        and not single_text.endswith((".", ",", ";", ":"))
                        and len(single_text) < 100
                    )
                    if looks_like_heading:
                        heading_text = f"{m_bullet.group(1)} {single_text}"
                        runs = _parse_inline_text(heading_text)
                        elements.append(Heading(level=2, text=heading_text, runs=runs))
                        continue

                elements.append(ListBlock(items=items, ordered=ordered))
                continue

            # Regular paragraph
            para_lines = [stripped]
            i += 1
            while i < n:
                next_strip = lines[i].strip()
                if not next_strip:
                    break
                # Stop if next line is a heading, display equation, table, list, page break, or image
                if (
                    re.match(r"^#{1,6}\s+", next_strip)
                    or next_strip.startswith("$$")
                    or next_strip.startswith("\\[")
                    or "|" in next_strip
                    or re.match(r"^([-*+]|\d+\.)\s+", next_strip)
                    or re.match(r"^---+$", next_strip)
                    or re.match(r"^\*\*\*+$", next_strip)
                    or next_strip.startswith("![")
                ):
                    break
                para_lines.append(next_strip)
                i += 1

            combined = " ".join(para_lines).strip()
            # Check for alignment tags: <p align="center">...</p>, <center>...</center>, <p align="right">...</p>
            align = "left"
            m_align = re.match(
                r"^<(?:p\s+align=[\"'](center|right|justify)[\"']|center)>(.*?)(?:</(?:p|center)>)?$",
                combined,
                flags=re.DOTALL | re.IGNORECASE,
            )
            if m_align:
                align = m_align.group(1).lower() if m_align.group(1) else "center"
                combined = m_align.group(2).strip()
            elif combined.startswith("->") and combined.endswith("<-") and len(combined) > 4:
                align = "center"
                combined = combined[2:-2].strip()
            elif combined.startswith("->") and len(combined) > 2:
                align = "right"
                combined = combined[2:].strip()

            runs = _parse_inline_text(combined)
            elements.append(Paragraph(runs=runs, alignment=align))

        return cls(title=title, elements=elements)

    @classmethod
    def from_layout(
        cls,
        text_lines: list[Any],  # list of TextLine
        math_results: list[Any],  # list of RegionResult
        page_height: float,
        page_width: float,
        title: str = "MathOCR document",
        figures: list[Any] | None = None,  # list of ExtractedFigure
        table_cell_rects: list[Box] | None = None,
        page_number: int = 1,
    ) -> Document:
        """Construct structured Document from OCR geometry, detecting tables, math, and figures."""
        from backend.layout import (
            associate_captions,
            classify_heading_semantic,
            detect_table_groups_geometry,
            filter_headers_footers,
        )

        metadata: dict[str, Any] = {
            "page": page_number,
            "page_width": page_width,
            "page_height": page_height,
        }

        # 1. Separate running headers and footers/page numbers
        raw_text_blocks = [(line.box, "text", line) for line in text_lines]
        body_text_blocks, header_blocks, footer_blocks = filter_headers_footers(
            raw_text_blocks, page_height
        )
        if header_blocks:
            metadata["headers"] = [p.text for _b, _k, p in header_blocks]
        if footer_blocks:
            metadata["footers"] = [p.text for _b, _k, p in footer_blocks]

        # 2. Process figures and associate captions
        fig_items: list[tuple[Box, str, Any]] = []
        if figures:
            heights = [b.height for b, _k, _p in body_text_blocks if b.height > 0]
            med_line_h = median(heights) if heights else 0.02 * page_height
            kept_figs, body_text_blocks = associate_captions(figures, body_text_blocks, med_line_h)
            for fig in kept_figs:
                fig_items.append((fig.box, "figure", fig))

        # 3. Process math results
        math_blocks: list[tuple[Box, str, Any]] = []
        for result in math_results:
            if not result.latex or result.box is None:
                continue
            box = Box(*result.box)
            kind = "inline" if result.kind == "embedded" else "display"
            math_blocks.append((box, kind, result))

        blocks: list[tuple[Box, str, Any]] = body_text_blocks + fig_items + math_blocks
        if not blocks:
            return cls(title=title, elements=[], metadata=metadata)

        blocks.sort(key=lambda item: (item[0].top, item[0].left))
        heights = [box.height for box, kind, _payload in blocks if box.height > 0 and kind == "text"]
        tolerance = 0.55 * (median(heights) if heights else 0.02 * page_height)

        rows: list[list[tuple[Box, str, Any]]] = []
        for block in blocks:
            center = (block[0].top + block[0].bottom) / 2
            if rows and abs(center - _row_center(rows[-1])) <= tolerance:
                rows[-1].append(block)
            else:
                rows.append([block])

        # 4. Geometry-driven table detection
        table_ranges = detect_table_groups_geometry(rows, table_cell_rects or [], page_width)
        table_map = {start: (end, cols) for start, end, cols in table_ranges}

        elements: list[BlockElement] = []
        row_idx = 0
        num_rows = len(rows)
        med_h = median(heights) if heights else 0.02 * page_height

        while row_idx < num_rows:
            # Check if current row starts a table
            if row_idx in table_map:
                end_idx, col_clusters = table_map[row_idx]
                table_rows: list[TableRow] = []
                for tr_idx in range(row_idx, end_idx):
                    curr_tr = sorted(rows[tr_idx], key=lambda x: x[0].left)
                    # If we have column clusters, bin cells into columns
                    num_cols = max(len(curr_tr), len(col_clusters))
                    cells: list[TableCell] = []
                    for box, kind, payload in curr_tr:
                        if kind == "text":
                            runs = _parse_inline_text(payload.text)
                        elif kind == "figure":
                            runs = [TextRun(text=f"[Figure: {payload.caption or 'Diagram'}]")]
                        else:
                            runs = [InlineEquation(latex=payload.latex, box=payload.box)]
                        cells.append(
                            TableCell(
                                elements=[Paragraph(runs=runs)],
                                box=(int(box.left), int(box.top), int(box.right), int(box.bottom)),
                            )
                        )
                    table_rows.append(TableRow(cells=cells, is_header=(tr_idx == row_idx)))
                elements.append(Table(rows=table_rows))
                row_idx = end_idx
                continue

            curr_row = sorted(rows[row_idx], key=lambda x: x[0].left)

            # Check for figure in this row
            fig_item = next((payload for _box, kind, payload in curr_row if kind == "figure"), None)
            if fig_item:
                fig_box = fig_item.box
                width_in = None
                if page_width > 0:
                    fraction = (fig_box.right - fig_box.left) / page_width
                    width_in = round(max(2.0, min(6.0, 6.5 * fraction)), 2)
                fig_align = "center"
                fig_center = (fig_box.left + fig_box.right) / 2
                if page_width > 0:
                    if fig_center < 0.35 * page_width:
                        fig_align = "left"
                    elif fig_center > 0.65 * page_width:
                        fig_align = "right"

                elements.append(
                    ImageBlock(
                        asset_id=fig_item.asset_id,
                        caption=fig_item.caption,
                        width=width_in,
                        alignment=fig_align,
                        source_page=page_number,
                        box=(int(fig_box.left), int(fig_box.top), int(fig_box.right), int(fig_box.bottom)),
                    )
                )
                row_idx += 1
                continue

            has_text = any(kind == "text" for _box, kind, _payload in curr_row)
            only_display = all(kind == "display" for _box, kind, _payload in curr_row)

            if only_display and not has_text:
                for box, _kind, res in curr_row:
                    elements.append(
                        DisplayEquation(
                            latex=res.latex,
                            confidence=res.confidence,
                            box=res.box,
                        )
                    )
            else:
                runs: list[RunType] = []
                for box, kind, payload in curr_row:
                    if kind == "text":
                        runs.extend(_parse_inline_text(payload.text))
                    elif kind == "figure":
                        continue
                    else:
                        runs.append(
                            InlineEquation(
                                latex=payload.latex,
                                confidence=payload.confidence,
                                box=payload.box,
                            )
                        )

                row_left = min(b.left for b, _k, _p in curr_row)
                row_right = max(b.right for b, _k, _p in curr_row)
                row_top = min(b.top for b, _k, _p in curr_row)
                row_bottom = max(b.bottom for b, _k, _p in curr_row)
                row_box = Box(row_left, row_top, row_right, row_bottom)
                row_width = row_right - row_left
                row_center = (row_left + row_right) / 2
                page_center = page_width / 2

                align = "left"
                if page_width > 0:
                    if abs(row_center - page_center) < 0.08 * page_width and row_width < 0.78 * page_width:
                        align = "center"
                    elif row_left > 0.55 * page_width and (page_width - row_right) < 0.15 * page_width:
                        align = "right"

                plain = "".join(r.text for r in runs if isinstance(r, TextRun)).strip()
                is_heading, level, h_align = classify_heading_semantic(plain, row_box, page_width, med_h)
                if is_heading and len(runs) <= 3:
                    elements.append(
                        Heading(
                            level=level,
                            text=plain,
                            runs=runs,
                            alignment=h_align,
                            box=(int(row_left), int(row_top), int(row_right), int(row_bottom)),
                        )
                    )
                else:
                    elements.append(
                        Paragraph(
                            runs=runs,
                            alignment=align,
                            box=(int(row_left), int(row_top), int(row_right), int(row_bottom)),
                        )
                    )

            row_idx += 1

        return cls(title=title, elements=elements, metadata=metadata)


def reconcile_document_with_markdown(doc: Document, markdown: str) -> Document:
    """Reconcile user edits from Markdown while preserving structured elements and image assets."""
    if not markdown or not markdown.strip():
        return doc

    md_doc = Document.from_markdown(markdown, title=doc.title)
    existing_images = [e for e in doc.elements if isinstance(e, ImageBlock)]
    img_idx = 0

    reconciled_elements: list[BlockElement] = []
    for elem in md_doc.elements:
        if isinstance(elem, ImageBlock):
            matched = None
            if elem.asset_id:
                matched = next((img for img in existing_images if img.asset_id == elem.asset_id), None)
            if not matched and img_idx < len(existing_images):
                matched = existing_images[img_idx]
                img_idx += 1
            if matched:
                reconciled_elements.append(
                    ImageBlock(
                        src=matched.src or elem.src,
                        asset_id=matched.asset_id or elem.asset_id,
                        caption=elem.caption or matched.caption,
                        width=matched.width or elem.width,
                        height=matched.height or elem.height,
                        aspect_ratio=matched.aspect_ratio or elem.aspect_ratio,
                        alignment=matched.alignment or elem.alignment,
                        source_page=matched.source_page or elem.source_page,
                        box=matched.box or elem.box,
                    )
                )
            else:
                reconciled_elements.append(elem)
        else:
            reconciled_elements.append(elem)

    return Document(
        title=doc.title,
        elements=reconciled_elements,
        metadata=doc.metadata,
        warnings=doc.warnings,
    )


def _row_center(row: list[tuple[Box, str, Any]]) -> float:
    return sum((box.top + box.bottom) / 2 for box, _kind, _payload in row) / len(row)


def _parse_inline_text(text: str) -> list[RunType]:
    """Parse text into TextRun and InlineEquation objects, preserving bold/italic."""
    math_pattern = re.compile(r"(\$(?!\$)[^\$]+(?<!\\)\$|\\\([^\\]+\\\))")
    tokens = math_pattern.split(text)
    runs: list[RunType] = []

    format_pattern = re.compile(
        r"(\*\*\*[^*]+\*\*\*|\*\*[^*]+\*\*|\*[^*]+\*|___[^_]+___|__[^_]+__|_[^_]+_)"
    )

    for token in tokens:
        if not token:
            continue
        if (token.startswith("$") and token.endswith("$") and len(token) > 1) or (
            token.startswith("\\(") and token.endswith("\\)")
        ):
            clean_eq = token[1:-1] if token.startswith("$") else token[2:-2]
            runs.append(InlineEquation(latex=clean_eq.strip()))
        else:
            chunks = format_pattern.split(token)
            for chunk in chunks:
                if not chunk:
                    continue
                if (chunk.startswith("***") and chunk.endswith("***")) or (
                    chunk.startswith("___") and chunk.endswith("___")
                ):
                    runs.append(TextRun(text=chunk[3:-3], bold=True, italic=True))
                elif (chunk.startswith("**") and chunk.endswith("**")) or (
                    chunk.startswith("__") and chunk.endswith("__")
                ):
                    runs.append(TextRun(text=chunk[2:-2], bold=True))
                elif (chunk.startswith("*") and chunk.endswith("*")) or (
                    chunk.startswith("_") and chunk.endswith("_")
                ):
                    runs.append(TextRun(text=chunk[1:-1], italic=True))
                else:
                    runs.append(TextRun(text=chunk))
    return runs


def _parse_table_markdown(lines: list[str]) -> Table | None:
    """Parse markdown table lines into a Table object."""
    raw_rows: list[list[str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip markdown separator row |:---|:---|
        if re.match(r"^\|?[\s:-|-]+\|?$", stripped) and "-" in stripped:
            continue
        if stripped.startswith("|"):
            stripped = stripped[1:]
        if stripped.endswith("|"):
            stripped = stripped[:-1]
        cells = [c.strip() for c in stripped.split("|")]
        if cells:
            raw_rows.append(cells)

    if not raw_rows or len(raw_rows) < 2:
        return None

    table_rows: list[TableRow] = []
    for idx, row in enumerate(raw_rows):
        cells = []
        for cell_text in row:
            runs = _parse_inline_text(cell_text)
            cells.append(TableCell(elements=[Paragraph(runs=runs)]))
        table_rows.append(TableRow(cells=cells, is_header=(idx == 0)))

    return Table(rows=table_rows)


def _render_table_markdown(table: Table) -> list[str]:
    """Render Table object into GitHub-flavored Markdown table lines."""
    if not table.rows:
        return []

    lines: list[str] = []
    # Header row
    header_row = table.rows[0]
    header_cells = [cell.text().replace("|", "\\|") for cell in header_row.cells]
    lines.append("| " + " | ".join(header_cells) + " |")

    # Separator
    lines.append("| " + " | ".join(["---"] * len(header_cells)) + " |")

    # Data rows
    for row in table.rows[1:]:
        row_cells = [cell.text().replace("|", "\\|") for cell in row.cells]
        # Pad if needed
        while len(row_cells) < len(header_cells):
            row_cells.append("")
        lines.append("| " + " | ".join(row_cells) + " |")

    return lines
