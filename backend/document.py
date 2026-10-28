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
    background_color: str | None = None
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
            "background_color": self.background_color,
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
            background_color=data.get("background_color"),
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
    asset_id: str | None = None
    fallback_image: bool = False
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
            "asset_id": self.asset_id,
            "fallback_image": self.fallback_image,
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
            asset_id=data.get("asset_id"),
            fallback_image=bool(data.get("fallback_image", False)),
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
    block_id: str | None = None
    asset_id: str | None = None
    fallback_image: bool = False
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
            "block_id": self.block_id,
            "asset_id": self.asset_id,
            "fallback_image": self.fallback_image,
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
            block_id=data.get("block_id"),
            asset_id=data.get("asset_id"),
            fallback_image=bool(data.get("fallback_image", False)),
        )


RunType = TextRun | InlineEquation


@dataclass(slots=True)
class Paragraph:
    """A paragraph of mixed text and inline formulas."""

    runs: list[RunType] = field(default_factory=list)
    style: str = "normal"
    alignment: str = "left"  # left | center | right | justify
    shading: str | None = None
    box: tuple[int, int, int, int] | None = None
    block_id: str | None = None
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
            "shading": self.shading,
            "box": self.box,
            "block_id": self.block_id,
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
            shading=data.get("shading"),
            box=tuple(data["box"]) if data.get("box") else None,
            block_id=data.get("block_id"),
        )


@dataclass(slots=True)
class Heading:
    """A section heading with level 1 to 6."""

    level: int = 1
    text: str = ""
    runs: list[RunType] = field(default_factory=list)
    alignment: str = "left"  # left | center | right
    box: tuple[int, int, int, int] | None = None
    block_id: str | None = None
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
            "block_id": self.block_id,
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
            block_id=data.get("block_id"),
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
    block_id: str | None = None
    type: Literal["table"] = "table"
    asset_id: str | None = None
    fallback_image: bool = False

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
            "block_id": self.block_id,
            "asset_id": self.asset_id,
            "fallback_image": self.fallback_image,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Table:
        return cls(
            rows=[TableRow.from_dict(row) for row in data.get("rows", [])],
            caption=data.get("caption"),
            col_widths=data.get("col_widths"),
            box=tuple(data["box"]) if data.get("box") else None,
            block_id=data.get("block_id"),
            asset_id=data.get("asset_id"),
            fallback_image=bool(data.get("fallback_image", False)),
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
    block_id: str | None = None
    type: Literal["list"] = "list"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "list",
            "items": [item.to_dict() for item in self.items],
            "ordered": self.ordered,
            "block_id": self.block_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ListBlock:
        return cls(
            items=[ListItem.from_dict(item) for item in data.get("items", [])],
            ordered=bool(data.get("ordered", False)),
            block_id=data.get("block_id"),
        )


@dataclass(slots=True)
class PageBreak:
    """Page break marker between document sections."""

    page: int | None = None
    block_id: str | None = None
    type: Literal["page_break"] = "page_break"

    def to_dict(self) -> dict[str, Any]:
        return {"type": "page_break", "page": self.page, "block_id": self.block_id}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PageBreak:
        return cls(page=data.get("page"), block_id=data.get("block_id"))


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
    block_id: str | None = None
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
            "block_id": self.block_id,
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
            block_id=data.get("block_id"),
        )


BlockElement = Paragraph | Heading | DisplayEquation | Table | ListBlock | PageBreak | ImageBlock


@dataclass(slots=True)
class Document:
    """The structured intermediate document holding all layout blocks."""

    title: str = ""
    elements: list[BlockElement] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    audit_records: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "elements": [elem.to_dict() for elem in self.elements],
            "metadata": self.metadata,
            "warnings": self.warnings,
            "audit_records": self.audit_records,
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
            title=str(data.get("title", "")),
            elements=elements,
            metadata=dict(data.get("metadata", {})),
            warnings=list(data.get("warnings", [])),
            audit_records=list(data.get("audit_records", [])),
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
                marker = f" {{#eq:{elem.numbering}}}" if elem.numbering else ""
                blocks.append(f"$$\n{elem.latex}\n$${marker}")
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
    def from_markdown(cls, markdown: str, title: str = "") -> Document:
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

            # Display equation ($$...$$ or \[...\]).  ``{#eq:N}`` is a
            # MathOCR Markdown extension that keeps a source equation label
            # attached to its formula during text-editor round trips.
            if stripped.startswith("$$") or stripped.startswith("\\["):
                closing = "$$" if stripped.startswith("$$") else "\\]"
                one_line = re.match(
                    r"^\$\$(.*?)\$\$\s*(?:\{#eq:(\d{1,3})\})?$",
                    stripped,
                    flags=re.DOTALL,
                ) if closing == "$$" else None
                if one_line and len(stripped) > 4:
                    elements.append(
                        DisplayEquation(latex=one_line.group(1).strip(), numbering=one_line.group(2))
                    )
                    i += 1
                    continue
                if closing == "\\]" and stripped.endswith(closing) and len(stripped) > 4:
                    elements.append(DisplayEquation(latex=stripped[2:-2].strip()))
                    i += 1
                    continue
                # Multi-line display equation
                eq_lines = [stripped[2:].strip()]
                i += 1
                while i < n and not (
                    lines[i].strip().endswith(closing)
                    or (closing == "$$" and re.search(r"\$\$\s*\{#eq:\d{1,3}\}\s*$", lines[i]))
                ):
                    eq_lines.append(lines[i])
                    i += 1
                numbering = None
                if i < n:
                    last_line = lines[i].strip()
                    marker = re.search(r"\{#eq:(\d{1,3})\}\s*$", last_line)
                    if marker:
                        numbering = marker.group(1)
                        last_line = last_line[: marker.start()].rstrip()
                    eq_lines.append(last_line[:-2].strip() if last_line.endswith(closing) else last_line)
                    i += 1
                eq_content = clean_latex("\n".join(eq_lines)).strip()
                elements.append(DisplayEquation(latex=eq_content, numbering=numbering))
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
        title: str = "",
        figures: list[Any] | None = None,  # list of ExtractedFigure
        table_cell_rects: list[Box] | None = None,
        page_number: int = 1,
        page_source: Any | None = None,
        asset_store: Any | None = None,
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
            curr_row = rows[row_idx]
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
                            runs = _runs_from_layout_line(payload)
                        elif kind == "figure":
                            runs = [TextRun(text=f"[Figure: {payload.caption or 'Diagram'}]")]
                        else:
                            runs = [
                                InlineEquation(
                                    latex=payload.latex,
                                    box=payload.box,
                                    confidence=getattr(payload, "confidence", None),
                                    asset_id=getattr(payload, "asset_id", None),
                                    fallback_image=getattr(payload, "fallback_image", False),
                                )
                            ]
                        cells.append(
                            TableCell(
                                elements=[
                                    Paragraph(
                                        runs=runs
                                    )
                                ],
                                box=(int(box.left), int(box.top), int(box.right), int(box.bottom)),
                            )
                        )
                    table_rows.append(TableRow(cells=cells, is_header=(tr_idx == row_idx)))
                table_boxes = [box for table_row in rows[row_idx:end_idx] for box, _kind, _payload in table_row]
                table_box = (
                    int(min(box.left for box in table_boxes)),
                    int(min(box.top for box in table_boxes)),
                    int(max(box.right for box in table_boxes)),
                    int(max(box.bottom for box in table_boxes)),
                )
                elements.append(
                    Table(
                        rows=table_rows,
                        box=table_box,
                        block_id=_source_block_id(page_number, "table", table_box),
                    )
                )
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
                        block_id=_source_block_id(
                            page_number,
                            "image",
                            (int(fig_box.left), int(fig_box.top), int(fig_box.right), int(fig_box.bottom)),
                        ),
                    )
                )
                row_idx += 1
                continue

            if any(kind == "table" for _box, kind, _payload in curr_row):
                for _b, kind, payload in curr_row:
                    if kind == "table":
                        elements.append(payload)
                row_idx += 1
                continue

            has_text = any(kind == "text" for _box, kind, _payload in curr_row)
            only_display = all(kind == "display" for _box, kind, _payload in curr_row)

            if only_display and not has_text:
                for box, _kind, res in curr_row:
                    extracted_tables = _extract_tables_from_latex(
                        res.latex, page_number=page_number, box=res.box
                    )
                    if extracted_tables:
                        elements.extend(extracted_tables)
                    else:
                        elements.append(
                            DisplayEquation(
                                latex=res.latex,
                                confidence=res.confidence,
                                numbering=getattr(res, "numbering", None),
                                box=res.box,
                                block_id=_source_block_id(page_number, "display_equation", res.box),
                                asset_id=getattr(res, "asset_id", None),
                                fallback_image=getattr(res, "fallback_image", False),
                            )
                        )
            elif has_text and any(kind == "display" for _box, kind, _payload in curr_row):
                # A connector such as “therefore” or “or” can share a visual
                # row with a centred display equation.  It is prose adjacent
                # to that equation, not an inline formula or a heading.
                text_items = [item for item in curr_row if item[1] in {"text", "inline"}]
                runs: list[RunType] = []
                previous_box: Box | None = None
                for box, kind, payload in text_items:
                    if kind == "text":
                        line_runs = _runs_from_layout_line(payload)
                        _append_runs_with_geometry(runs, line_runs, previous_box, box)
                    else:
                        runs.append(
                            InlineEquation(
                                latex=payload.latex,
                                confidence=payload.confidence,
                                box=payload.box,
                                asset_id=getattr(payload, "asset_id", None),
                                fallback_image=getattr(payload, "fallback_image", False),
                            )
                        )
                    previous_box = box
                if runs:
                    left = min(box.left for box, _kind, _payload in text_items)
                    top = min(box.top for box, _kind, _payload in text_items)
                    right = max(box.right for box, _kind, _payload in text_items)
                    bottom = max(box.bottom for box, _kind, _payload in text_items)
                    elements.append(
                        Paragraph(
                            runs=runs,
                            alignment="left",
                            shading=_row_source_shading(text_items),
                            box=(int(left), int(top), int(right), int(bottom)),
                            block_id=_source_block_id(
                                page_number, "paragraph", (int(left), int(top), int(right), int(bottom))
                            ),
                        )
                    )
                for _box, kind, res in curr_row:
                    if kind == "display":
                        extracted_tables = _extract_tables_from_latex(
                            res.latex, page_number=page_number, box=res.box
                        )
                        if extracted_tables:
                            elements.extend(extracted_tables)
                        else:
                            elements.append(
                                DisplayEquation(
                                    latex=res.latex,
                                    confidence=res.confidence,
                                    numbering=getattr(res, "numbering", None),
                                    box=res.box,
                                    block_id=_source_block_id(page_number, "display_equation", res.box),
                                    asset_id=getattr(res, "asset_id", None),
                                    fallback_image=getattr(res, "fallback_image", False),
                                )
                            )
            else:
                runs: list[RunType] = []
                previous_box: Box | None = None
                for box, kind, payload in curr_row:
                    if kind == "text":
                        line_runs = _runs_from_layout_line(payload)
                        _append_runs_with_geometry(runs, line_runs, previous_box, box)
                        previous_box = box
                    elif kind == "figure":
                        continue
                    else:
                        _append_runs_with_geometry(runs, [], previous_box, box)
                        runs.append(
                            InlineEquation(
                                latex=payload.latex,
                                confidence=payload.confidence,
                                box=payload.box,
                                asset_id=getattr(payload, "asset_id", None),
                                fallback_image=getattr(payload, "fallback_image", False),
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
                row_text = " ".join(
                    payload.text for _box, kind, payload in curr_row if kind == "text"
                )
                word_count = len(re.findall(r"\w+", row_text))

                align = "left"
                if page_width > 0:
                    if (
                        abs(row_center - page_center) < 0.08 * page_width
                        and row_width < 0.45 * page_width
                        and word_count <= 4
                    ):
                        align = "center"
                    elif row_left > 0.55 * page_width and (page_width - row_right) < 0.15 * page_width:
                        align = "right"

                plain = "".join(r.text for r in runs if isinstance(r, TextRun)).strip()
                is_heading, level, h_align = classify_heading_semantic(plain, row_box, page_width, med_h)
                is_example_label = bool(
                    re.match(r"^\s*(?:example|exercise|problem)\s+\d+\b", plain, re.I)
                )
                if is_heading and len(runs) <= 3 and not is_example_label:
                    elements.append(
                        Heading(
                            level=level,
                            text=plain,
                            runs=runs,
                            alignment=h_align,
                            box=(int(row_left), int(row_top), int(row_right), int(row_bottom)),
                            block_id=_source_block_id(
                                page_number,
                                "heading",
                                (int(row_left), int(row_top), int(row_right), int(row_bottom)),
                            ),
                        )
                    )
                else:
                    row_shading = _row_source_shading(curr_row)
                    first_text = next(
                        (payload.text for _box, kind, payload in curr_row if kind == "text"), ""
                    )
                    style = "normal"
                    if row_shading or re.match(r"^\s*example\s+\d+\b", first_text, re.I):
                        style = "example"
                    elif re.match(r"^\s*(?:theorem|lemma|proposition|definition|corollary|axiom)\s+\d+\b", first_text, re.I):
                        style = "theorem"
                    elif re.match(r"^\s*\d+\.\s+", first_text):
                        style = "exercise"
                    elif first_text.strip().lower() in ("exercises", "exercises.", "exercise", "problems", "problems."):
                        style = "exercises_heading"
                        align = "center"
                    elements.append(
                        Paragraph(
                            runs=runs,
                            style=style,
                            alignment=align,
                            shading=row_shading,
                            box=(int(row_left), int(row_top), int(row_right), int(row_bottom)),
                            block_id=_source_block_id(
                                page_number,
                                "paragraph",
                                (int(row_left), int(row_top), int(row_right), int(row_bottom)),
                            ),
                        )
                    )

            row_idx += 1

        merged_elements = _merge_continuation_paragraphs(elements, med_h)
        doc = cls(title=title, elements=merged_elements, metadata=metadata)
        try:
            from backend.audit import audit_document_content

            doc, _ = audit_document_content(
                doc,
                page_source=page_source,
                kept_text=text_lines,
                math_results=math_results,
                asset_store=asset_store,
            )
        except Exception as audit_err:
            import logging
            logging.getLogger("mathocr").warning("Document audit encountered an error: %s", audit_err)
        return doc


def reconcile_document_with_markdown(doc: Document, markdown: str) -> Document:
    """Apply Markdown edits while retaining source block metadata where possible."""
    if not markdown or not markdown.strip():
        return doc

    md_doc = Document.from_markdown(markdown, title=doc.title)
    source_by_type: dict[str, list[BlockElement]] = {}
    for source in doc.elements:
        source_by_type.setdefault(source.type, []).append(source)
    consumed_ids: set[int] = set()
    warnings = list(doc.warnings)

    def match_source(element: BlockElement) -> BlockElement | None:
        """Match edited blocks in reading order, preserving source traceability."""

        candidates = source_by_type.get(element.type, [])
        # Asset identity is a stronger match than position for figures.
        if isinstance(element, ImageBlock) and element.asset_id:
            for candidate in candidates:
                if (
                    id(candidate) not in consumed_ids
                    and isinstance(candidate, ImageBlock)
                    and candidate.asset_id == element.asset_id
                ):
                    consumed_ids.add(id(candidate))
                    return candidate
        for candidate in candidates:
            if id(candidate) not in consumed_ids:
                consumed_ids.add(id(candidate))
                return candidate
        return None

    reconciled_elements: list[BlockElement] = []
    reconciled_to_source: dict[int, int] = {}
    for elem in md_doc.elements:
        matched = match_source(elem)
        reconciled_elem: BlockElement
        if isinstance(elem, ImageBlock) and isinstance(matched, ImageBlock):
            reconciled_elem = ImageBlock(
                src=matched.src or elem.src,
                asset_id=matched.asset_id or elem.asset_id,
                caption=elem.caption or matched.caption,
                width=matched.width or elem.width,
                height=matched.height or elem.height,
                aspect_ratio=matched.aspect_ratio or elem.aspect_ratio,
                alignment=matched.alignment or elem.alignment,
                source_page=matched.source_page or elem.source_page,
                box=matched.box or elem.box,
                block_id=matched.block_id,
            )
        elif isinstance(elem, Paragraph) and isinstance(matched, Paragraph):
            reconciled_runs: list[RunType] = []
            matched_eqs = [r for r in matched.runs if isinstance(r, InlineEquation)]
            eq_idx = 0
            for run in elem.runs:
                if isinstance(run, InlineEquation):
                    matched_eq = None
                    for idx, candidate in enumerate(matched_eqs[eq_idx:], start=eq_idx):
                        if candidate.latex == run.latex or abs(len(candidate.latex) - len(run.latex)) <= 2:
                            matched_eq = candidate
                            eq_idx = idx + 1
                            break
                    if matched_eq is not None:
                        is_edited = run.latex != matched_eq.latex
                        reconciled_runs.append(
                            InlineEquation(
                                latex=run.latex,
                                omml=matched_eq.omml if not is_edited else None,
                                confidence=matched_eq.confidence if not is_edited else 1.0,
                                raw_source=matched_eq.raw_source,
                                box=matched_eq.box,
                                asset_id=getattr(matched_eq, "asset_id", None),
                                fallback_image=False if is_edited else getattr(matched_eq, "fallback_image", False),
                            )
                        )
                    else:
                        reconciled_runs.append(run)
                else:
                    reconciled_runs.append(run)
            reconciled_elem = Paragraph(
                runs=reconciled_runs,
                style=matched.style,
                alignment=matched.alignment,
                shading=matched.shading,
                box=matched.box,
                block_id=matched.block_id,
            )
        elif isinstance(elem, Heading) and isinstance(matched, Heading):
            reconciled_elem = Heading(
                level=elem.level,
                text=elem.text,
                runs=elem.runs,
                alignment=matched.alignment,
                box=matched.box,
                block_id=matched.block_id,
            )
        elif isinstance(elem, DisplayEquation) and isinstance(matched, DisplayEquation):
            is_edited = elem.latex != matched.latex
            reconciled_elem = DisplayEquation(
                latex=elem.latex,
                omml=matched.omml if not is_edited else None,
                confidence=matched.confidence if not is_edited else 1.0,
                raw_source=matched.raw_source,
                numbering=elem.numbering or matched.numbering,
                alignment=matched.alignment,
                box=matched.box,
                block_id=matched.block_id,
                asset_id=getattr(matched, "asset_id", None),
                fallback_image=False if is_edited else getattr(matched, "fallback_image", False),
            )
        elif isinstance(elem, Table) and isinstance(matched, Table):
            def _row_len(r: Any) -> int:
                if hasattr(r, "cells"):
                    return len(r.cells)
                if isinstance(r, list):
                    return len(r)
                return 0

            is_edited = len(elem.rows) != len(matched.rows) or any(
                _row_len(r1) != _row_len(r2) for r1, r2 in zip(elem.rows, matched.rows)
            )
            reconciled_elem = Table(
                rows=elem.rows,
                caption=elem.caption or matched.caption,
                col_widths=matched.col_widths or elem.col_widths,
                box=matched.box,
                block_id=matched.block_id,
                asset_id=getattr(matched, "asset_id", None),
                fallback_image=False if is_edited else getattr(matched, "fallback_image", False),
            )
        elif isinstance(elem, ListBlock) and isinstance(matched, ListBlock):
            reconciled_elem = ListBlock(items=elem.items, ordered=elem.ordered, block_id=matched.block_id)
        elif isinstance(elem, PageBreak) and isinstance(matched, PageBreak):
            reconciled_elem = PageBreak(page=matched.page, block_id=matched.block_id)
        else:
            reconciled_elem = elem

        reconciled_elements.append(reconciled_elem)
        if matched is not None:
            reconciled_to_source[id(reconciled_elem)] = id(matched)

        if matched is None:
            warnings.append(
                f"Markdown contains a {elem.type} block with no matching source block; source geometry is unavailable."
            )

    # Preserve unconsumed non-text blocks (ImageBlock, Table, DisplayEquation)
    # anchored to their original relative position in doc.elements.
    insert_at_start: list[BlockElement] = []
    insert_after_anchor: dict[int, list[BlockElement]] = {}
    last_consumed_id: int | None = None

    for source in doc.elements:
        if id(source) in consumed_ids:
            last_consumed_id = id(source)
        else:
            if isinstance(source, (ImageBlock, Table, DisplayEquation)):
                if last_consumed_id is None:
                    insert_at_start.append(source)
                else:
                    insert_after_anchor.setdefault(last_consumed_id, []).append(source)
                warnings.append(
                    f"Markdown omitted source non-text block {source.block_id or source.type}; preserved from structured document."
                )
            elif source.block_id:
                warnings.append(
                    f"Markdown omitted source block {source.block_id}; export follows the edited content."
                )

    final_elements: list[BlockElement] = list(insert_at_start)
    for elem in reconciled_elements:
        final_elements.append(elem)
        source_id = reconciled_to_source.get(id(elem))
        if source_id is not None and source_id in insert_after_anchor:
            final_elements.extend(insert_after_anchor[source_id])

    return Document(
        title=doc.title,
        elements=final_elements,
        metadata=doc.metadata,
        warnings=warnings,
    )


def _row_center(row: list[tuple[Box, str, Any]]) -> float:
    return sum((box.top + box.bottom) / 2 for box, _kind, _payload in row) / len(row)


def _source_block_id(
    page_number: int, block_type: str, box: tuple[int, int, int, int] | None
) -> str:
    """Create a stable source-to-output key from immutable page geometry."""

    if box is None:
        return f"p{page_number}-{block_type}-unplaced"
    return f"p{page_number}-{block_type}-{'-'.join(str(int(value)) for value in box)}"


def _extract_tables_from_latex(
    latex: str, page_number: int = 1, box: tuple[int, int, int, int] | None = None
) -> list[Table]:
    """Convert tabular LaTeX arrays (like Cayley/operation tables) into editable Word Tables."""
    tables: list[Table] = []
    pattern = re.compile(
        r"\\begin\{(?:array|tabular)\}\s*(?:\[[^\]]*\])?\s*(?:\{([^}]*)\})?([\s\S]*?)\\end\{(?:array|tabular)\}"
    )
    for m in pattern.finditer(latex):
        col_spec = m.group(1) or ""
        content = m.group(2).strip()
        # Strip leading column specs if they leaked into content
        content = re.sub(r"^\s*\{[clr|\s-]+\}\s*", "", content)
        has_table_structure = (
            "|" in col_spec
            or r"\hline" in content
            or bool(re.match(r"^\s*(\\cdot|\\times|\+|\*|\\circ|\\oplus)", content))
        )
        if not has_table_structure:
            continue

        raw_lines = [line.strip() for line in re.split(r"\\\\", content) if line.strip()]
        rows: list[TableRow] = []
        for line in raw_lines:
            line = re.sub(r"\\hline\b", "", line).strip()
            if not line:
                continue
            cells_text = [c.strip() for c in line.split("&")]
            cleaned_cells = []
            for ct in cells_text:
                # Strip wrapping braces like {0}, {1}, {+}
                ct = re.sub(r"^\{([\s\S]*)\}$", r"\1", ct).strip()
                ct = ct.replace(r"\cdot", "·").replace(r"\times", "×").replace(r"\oplus", "⊕")
                cleaned_cells.append(ct)
            if cleaned_cells and any(cleaned_cells):
                cells = []
                for ct in cleaned_cells:
                    runs = _parse_inline_text(ct)
                    cells.append(TableCell(elements=[Paragraph(runs=runs)]))
                rows.append(TableRow(cells=cells, is_header=(len(rows) == 0)))

        if len(rows) >= 2:
            max_cols = max(len(r.cells) for r in rows)
            for r in rows:
                while len(r.cells) < max_cols:
                    r.cells.append(TableCell(elements=[Paragraph(runs=[TextRun(text="")])]))
            tables.append(
                Table(
                    rows=rows,
                    box=box,
                    block_id=_source_block_id(page_number, "table", box) if box else None,
                )
            )
    if len(tables) == 2 and box is not None:
        b_left, b_top, b_right, b_bottom = box
        b_mid = (b_left + b_right) / 2
        tables[0].box = (int(b_left), int(b_top), int(b_mid - 15), int(b_bottom))
        tables[1].box = (int(b_mid + 15), int(b_top), int(b_right), int(b_bottom))
    return tables


def _split_text_with_inline_math(
    text: str,
    italic: bool = False,
    bold: bool = False,
    math_crops: list[tuple[Any, str]] | None = None,
    **common: Any,
) -> list[RunType]:
    """Convert mathematical notation in text into InlineEquation runs.

    Handles superscripts, subscripts, fractions, matrix elements, relations, and operations
    while preserving surrounding English prose and punctuation.
    """
    if not text:
        return []

    def tag_math(latex: str) -> str:
        return f"\x01{latex}\x02"

    greek_map = {
        "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta",
        "ε": r"\epsilon", "θ": r"\theta", "λ": r"\lambda", "μ": r"\mu",
        "π": r"\pi", "σ": r"\sigma", "ω": r"\omega", "Δ": r"\Delta",
        "Ω": r"\Omega", "Σ": r"\Sigma",
    }

    def clean_math_span(expr: str) -> str:
        s = expr
        s = re.sub(r"(?<=[a-zA-Z\u0370-\u03ff\\])_([a-zA-Z0-9]+)\b", r"_{\1}", s)
        for u, l in greek_map.items():
            s = s.replace(u, l)
        s = re.sub(r"\blambda\b", r"\\lambda", s)
        return s.strip()

    patterns: list[tuple[str, Any]] = [
        # xx−1 = 1, xx-¹ = 1 -> x x^{-1} = 1
        (r"\b([a-zA-Z])([a-zA-Z])\s*[-−]?[¹²³⁴⁵⁶⁷⁸⁹⁰⁻1]+\s*=\s*1\b", lambda m: tag_math(f"{m.group(1)} {m.group(2)}^{{-1}} = 1")),
        # x1 = x, 1x = x, x 1 = x, 1 x = x
        (r"\bx\s*1\s*=\s*x\b", lambda m: tag_math(r"x \cdot 1 = x")),
        (r"\bx1\s*=\s*x\b", lambda m: tag_math(r"x \cdot 1 = x")),
        (r"\b1\s*x\s*=\s*x\b", lambda m: tag_math(r"1 \cdot x = x")),
        (r"\b1x\s*=\s*x\b", lambda m: tag_math(r"1 \cdot x = x")),
        # Aij = Aji, A_ij = A_ji
        (r"\b([A-Z])([i-n])([i-n])\s*=\s*([A-Z])([i-n])([i-n])\b", lambda m: tag_math(f"{m.group(1)}_{{{m.group(2)}{m.group(3)}}} = {m.group(4)}_{{{m.group(5)}{m.group(6)}}}")),
        # x_1 + x_2 = 0, y_1 - y_2 = 0
        (r"(?<![a-zA-Z0-9])([a-zA-Z](?:_[a-zA-Z0-9]+|\^[a-zA-Z0-9]+|\d)?\s*[\+\-−]\s*[a-zA-Z](?:_[a-zA-Z0-9]+|\^[a-zA-Z0-9]+|\d)?\s*=\s*[0-9a-zA-Z]+)(?![a-zA-Z0-9])", lambda m: tag_math(clean_math_span(m.group(1)))),
        # Physics relations: p = h/lambda, p = h/λ, E = mc^2, θ_i = θ_r, \theta_i = \theta_r
        (r"(?<![a-zA-Z0-9])(\\?[a-zA-Z\u0370-\u03ff]+(?:_[a-zA-Z0-9\u0370-\u03ff]+|\^[a-zA-Z0-9]+)?\s*=\s*\\?[a-zA-Z0-9\u0370-\u03ff]+(?:_[a-zA-Z0-9\u0370-\u03ff]+|\^[a-zA-Z0-9]+)?(?:\s*[\/\*\+\-−]\s*\\?[a-zA-Z0-9\u0370-\u03ff]+(?:_[a-zA-Z0-9\u0370-\u03ff]+|\^[0-9a-zA-Z]+)?)?)(?![a-zA-Z0-9])", lambda m: tag_math(clean_math_span(m.group(1)))),
        # Greek letter subscripts e.g. θ_i, λ_1
        (r"\b([α-ωΑ-Ω])_([a-zA-Z0-9]+)\b", lambda m: tag_math(f"{greek_map.get(m.group(1), m.group(1))}_{{{m.group(2)}}}")),
        # x−1, x^-1, x-¹
        (r"\b([a-zA-Z])\s*[-−][¹²³⁴⁵⁶⁷⁸⁹⁰⁻]+\b", lambda m: tag_math(m.group(1) + "^{" + m.group(0)[len(m.group(1)):].strip().translate(str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")) + "}")),
        (r"\b([a-zA-Z])\s*[¹²³⁴⁵⁶⁷⁸⁹⁰⁻]+\b", lambda m: tag_math(m.group(1) + "^{" + m.group(0)[len(m.group(1)):].strip().translate(str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")) + "}")),
        (r"\b([a-zA-Z])\s*[−-]\s*1\b", lambda m: tag_math(f"{m.group(1)}^{{-1}}")),
        # 1/x
        (r"\b1\s*/\s*([a-zA-Z])\b", lambda m: tag_math(f"1/{m.group(1)}")),
        # Aij, Aji, etc. (matrix indices)
        (r"\b([A-Z])([i-n])([i-n])\b", lambda m: tag_math(f"{m.group(1)}_{{{m.group(2)}{m.group(3)}}}")),
        # x_i, x_1, A_ij
        (r"\b([a-zA-Z])_([a-zA-Z0-9]+)\b", lambda m: tag_math(f"{m.group(1)}_{{{m.group(2)}}}")),
        (r"\b([a-zA-Z])_\{([^{}]+)\}", lambda m: tag_math(f"{m.group(1)}_{{{m.group(2)}}}")),
        # x^2, x^n, x^{-1}
        (r"\b([a-zA-Z])\^([a-zA-Z0-9]+)\b", lambda m: tag_math(f"{m.group(1)}^{{{m.group(2)}}}")),
        (r"\b([a-zA-Z])\^\{([^{}]+)\}", lambda m: tag_math(f"{m.group(1)}^{{{m.group(2)}}}")),
        # x != 0, x ̸= 0
        (r"\b([a-zA-Z])\s*(?:!=|̸=)\s*(\d+)\b", lambda m: tag_math(f"{m.group(1)} \\neq {m.group(2)}")),
    ]

    tagged = text
    for pat, repl in patterns:
        parts = re.split(r"(\x01[^\x02]*\x02)", tagged)
        for i in range(0, len(parts), 2):
            parts[i] = re.sub(pat, repl, parts[i])
        tagged = "".join(parts)

    parts = re.split(r"\x01([^\x02]+)\x02", tagged)
    runs: list[RunType] = []
    crop_idx = 0
    num_crops = len(math_crops) if math_crops else 0

    for i, piece in enumerate(parts):
        if not piece:
            continue
        if i % 2 == 1:
            asset_id = None
            if math_crops and crop_idx < num_crops:
                asset_id = math_crops[crop_idx][1]
                crop_idx += 1
            runs.append(InlineEquation(latex=piece.strip(), asset_id=asset_id))
        else:
            runs.append(TextRun(text=piece, italic=italic, bold=bold, **common))
    return runs


def _runs_from_layout_line(line: Any) -> list[RunType]:
    """Convert an OCR line into source-aware text runs.

    The semantic label handling is deliberately generic (``Example 2.``,
    ``Sol.``, and their case variants) and only adds emphasis already visible
    in textbook conventions.  It never changes the recognised words.
    """

    text = str(getattr(line, "text", ""))
    color = getattr(line, "foreground_color", None)
    background = getattr(line, "background_color", None)
    common = {"color": color, "background_color": background}
    math_crops = getattr(line, "math_crop_assets", None)
    label = re.match(r"^(\s*((?:example|exercise|problem)\s*\d+\.?|sol\.?))(?=\s|$)", text, re.I)
    if label:
        end = label.end(1)
        label_text = text[:end]
        remainder = text[end:]
        label_color = color
        runs: list[RunType] = [
            TextRun(
                text=label_text,
                bold=True,
                color=label_color,
                background_color=background,
            )
        ]
        if remainder:
            runs.extend(
                _split_text_with_inline_math(
                    remainder,
                    italic=bool(re.match(r"^\s*(?:example|exercise|problem)", text, re.I)),
                    math_crops=math_crops,
                    **common,
                )
            )
        return runs

    thm_match = re.match(
        r"^(\s*(?:Theorem|Lemma|Proposition|Definition|Corollary|Axiom)\s+\d+\.?)(?:\s+(.*))?$",
        text,
        re.I,
    )
    if thm_match:
        thm_prefix = thm_match.group(1)
        remainder = thm_match.group(2) or ""
        runs = [
            TextRun(
                text=thm_prefix + (" " if remainder else ""),
                bold=True,
                **common,
            )
        ]
        if remainder:
            runs.extend(
                _split_text_with_inline_math(
                    remainder,
                    italic=True,
                    math_crops=math_crops,
                    **common,
                )
            )
        return runs

    num_match = re.match(r"^(\s*\d+\.)(?!\d)\s*(.*)$", text)
    if num_match:
        num_prefix = num_match.group(1) + " "
        remainder = num_match.group(2)
        runs = [
            TextRun(
                text=num_prefix,
                bold=True,
                **common,
            )
        ]
        if remainder:
            runs.extend(
                _split_text_with_inline_math(
                    remainder,
                    math_crops=math_crops,
                    **common,
                )
            )
        return runs

    if text.strip().lower() in ("exercises", "exercises.", "exercise", "problems", "problems."):
        return [
            TextRun(
                text=text.strip(),
                bold=True,
                italic=True,
                **common,
            )
        ]

    return _split_text_with_inline_math(text, math_crops=math_crops, **common) if text else []


def _append_runs_with_geometry(
    target: list[RunType],
    additions: list[RunType],
    previous_box: Box | None,
    current_box: Box,
) -> None:
    """Keep a space between separately detected items on the same row."""

    if not additions:
        return
    previous_text = ""
    for run in reversed(target):
        if isinstance(run, TextRun) and run.text:
            previous_text = run.text
            break
    next_text = next((run.text for run in additions if isinstance(run, TextRun) and run.text), "")
    gap = current_box.left - previous_box.right if previous_box is not None else 0.0
    if previous_text and next_text and not previous_text[-1].isspace() and not next_text[0].isspace():
        if gap > 1.0 or (previous_text[-1].isalnum() and next_text[0].isalnum()):
            target.append(TextRun(" "))
    target.extend(additions)


def _row_source_shading(row: list[tuple[Box, str, Any]]) -> str | None:
    """Return a printable pastel row background inferred from text line pixels."""

    backgrounds = [
        getattr(payload, "background_color", None)
        for _box, kind, payload in row
        if kind == "text" and getattr(payload, "background_color", None)
    ]
    if not backgrounds:
        return None
    color = max(set(backgrounds), key=backgrounds.count)
    try:
        red, green, blue = int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
    except (TypeError, ValueError):
        return None
    # A dark coloured marker belongs to an individual run (e.g. a subsection
    # number); broad light tint is a paragraph/example band.
    return color if (red + green + blue >= 520 and max(red, green, blue) - min(red, green, blue) >= 20) else None


def _merge_continuation_paragraphs(elements: list[BlockElement], median_height: float) -> list[BlockElement]:
    """Join consecutive OCR lines when source geometry says they are one paragraph."""

    merged: list[BlockElement] = []
    max_gap = max(4.0, 1.25 * median_height)
    for element in elements:
        previous = merged[-1] if merged else None
        if (
            isinstance(previous, Paragraph)
            and isinstance(element, Paragraph)
            and previous.box is not None
            and element.box is not None
        ):
            previous_text = previous.text().rstrip()
            is_theorem_label = bool(
                re.match(
                    r"^\s*(?:Theorem|Lemma|Proposition|Definition|Corollary|Axiom)\s+\d+\.?$",
                    previous_text,
                    re.I,
                )
            )
            is_theorem_continuation = (
                (previous.style == "theorem" or is_theorem_label)
                and element.style in ("normal", "theorem")
            )
            is_exercise_continuation = (
                previous.style == "exercise"
                and element.style in ("normal", "exercise")
            )
            if (
                (previous.style == element.style or is_theorem_continuation or is_exercise_continuation)
                and previous.shading == element.shading
                and previous.alignment == element.alignment
            ):
                prev_box = Box(*previous.box)
                curr_box = Box(*element.box)
                vertical_gap = curr_box.top - prev_box.bottom
                starts_semantic_block = bool(
                    re.match(r"^\s*(?:example|exercise|problem|sol\.)\b", element.text(), re.I)
                    or re.match(r"^\s*\d+\.\s+", element.text())
                )
                # A punctuation-terminated line is a strong paragraph boundary, EXCEPT for theorem labels
                # like "Theorem 1." which lead directly into their statement.
                if (
                    -0.55 * median_height <= vertical_gap <= max_gap
                    and (not previous_text.endswith((".", "?", "!", ":")) or is_theorem_label)
                    and not starts_semantic_block
                ):
                    if is_theorem_label or is_theorem_continuation:
                        previous.style = "theorem"
                    elif is_exercise_continuation:
                        previous.style = "exercise"
                    if previous.runs and element.runs:
                        last_text = previous_text[-1:] if previous_text else ""
                        first_text = element.text().lstrip()[:1]
                        if last_text and first_text and not last_text.isspace() and not first_text in ",.;:)]":
                            previous.runs.append(TextRun(" "))
                    previous.runs.extend(element.runs)
                    previous.box = (
                        min(previous.box[0], element.box[0]),
                        min(previous.box[1], element.box[1]),
                        max(previous.box[2], element.box[2]),
                        max(previous.box[3], element.box[3]),
                    )
                    continue
        merged.append(element)
    return merged


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
