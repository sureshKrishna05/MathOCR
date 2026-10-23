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


BlockElement = Paragraph | Heading | DisplayEquation | Table | ListBlock | PageBreak


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

            # Heading (# ...)
            m_heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
            if m_heading:
                level = len(m_heading.group(1))
                h_text = m_heading.group(2).strip()
                runs = _parse_inline_text(h_text)
                elements.append(Heading(level=level, text=h_text, runs=runs))
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
                elements.append(ListBlock(items=items, ordered=ordered))
                continue

            # Regular paragraph
            para_lines = [stripped]
            i += 1
            while i < n:
                next_strip = lines[i].strip()
                if not next_strip:
                    break
                # Stop if next line is a heading, display equation, table, or list
                if (
                    re.match(r"^#{1,6}\s+", next_strip)
                    or next_strip.startswith("$$")
                    or next_strip.startswith("\\[")
                    or "|" in next_strip
                    or re.match(r"^([-*+]|\d+\.)\s+", next_strip)
                ):
                    break
                para_lines.append(next_strip)
                i += 1

            combined = " ".join(para_lines).strip()
            runs = _parse_inline_text(combined)
            elements.append(Paragraph(runs=runs))

        return cls(title=title, elements=elements)

    @classmethod
    def from_layout(
        cls,
        text_lines: list[Any],  # list of TextLine
        math_results: list[Any],  # list of RegionResult
        page_height: float,
        page_width: float,
        title: str = "MathOCR document",
    ) -> Document:
        """Construct structured Document from OCR geometry, detecting tables and math."""
        blocks: list[tuple[Box, str, Any]] = []

        for line in text_lines:
            blocks.append((line.box, "text", line))

        for result in math_results:
            if not result.latex or result.box is None:
                continue
            box = Box(*result.box)
            kind = "inline" if result.kind == "embedded" else "display"
            blocks.append((box, kind, result))

        if not blocks:
            return cls(title=title, elements=[])

        blocks.sort(key=lambda item: (item[0].top, item[0].left))
        heights = [box.height for box, _kind, _payload in blocks if box.height > 0]
        tolerance = 0.6 * (median(heights) if heights else 0.02 * page_height)

        rows: list[list[tuple[Box, str, Any]]] = []
        for block in blocks:
            center = (block[0].top + block[0].bottom) / 2
            if rows and abs(center - _row_center(rows[-1])) <= tolerance:
                rows[-1].append(block)
            else:
                rows.append([block])

        # Detect candidate table rows: consecutive rows that have multiple columns aligning
        elements: list[BlockElement] = []
        row_idx = 0
        num_rows = len(rows)

        while row_idx < num_rows:
            # Check if this row and following rows look like a table
            table_row_count = 0
            while (
                row_idx + table_row_count < num_rows
                and len(rows[row_idx + table_row_count]) >= 2
                and not any(k == "display" for _b, k, _p in rows[row_idx + table_row_count])
            ):
                table_row_count += 1

            if table_row_count >= 2:
                # Group these rows into a Table
                table_rows: list[TableRow] = []
                for tr_idx in range(table_row_count):
                    curr_row = sorted(rows[row_idx + tr_idx], key=lambda x: x[0].left)
                    cells: list[TableCell] = []
                    for box, kind, payload in curr_row:
                        if kind == "text":
                            runs = _parse_inline_text(payload.text)
                        else:
                            runs = [InlineEquation(latex=payload.latex, box=payload.box)]
                        cells.append(
                            TableCell(
                                elements=[Paragraph(runs=runs)],
                                box=(int(box.left), int(box.top), int(box.right), int(box.bottom)),
                            )
                        )
                    table_rows.append(TableRow(cells=cells, is_header=(tr_idx == 0)))
                elements.append(Table(rows=table_rows))
                row_idx += table_row_count
                continue

            # Process single row
            curr_row = sorted(rows[row_idx], key=lambda x: x[0].left)
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
                # Mixed row or text row
                runs: list[RunType] = []
                for box, kind, payload in curr_row:
                    if kind == "text":
                        runs.extend(_parse_inline_text(payload.text))
                    else:
                        runs.append(
                            InlineEquation(
                                latex=payload.latex,
                                confidence=payload.confidence,
                                box=payload.box,
                            )
                        )

                # Check if this line looks like a heading
                plain = "".join(r.text for r in runs if isinstance(r, TextRun)).strip()
                if (
                    len(runs) == 1
                    and isinstance(runs[0], TextRun)
                    and len(plain) < 60
                    and not plain.endswith((".", ",", ";", ":"))
                    and (plain.isupper() or plain.istitle())
                ):
                    elements.append(Heading(level=2, text=plain, runs=runs))
                else:
                    elements.append(Paragraph(runs=runs))

            row_idx += 1

        return cls(title=title, elements=elements)


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
