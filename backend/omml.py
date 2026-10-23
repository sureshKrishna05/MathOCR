"""Office Math Markup Language (OMML) conversion utilities for MathOCR.

Converts mathematical notation (LaTeX formulas) into native Word equations
represented as OMML XML (<m:oMath> and <m:oMathPara>) embedded in Microsoft
Word documents.

Runs 100% locally using Pandoc as the conversion engine; no external APIs or
Microsoft Office installation required.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
import threading
import zipfile
from pathlib import Path

from lxml import etree

from backend.latex import clean_latex

logger = logging.getLogger("mathocr.omml")

OMML_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
NAMESPACES = {"m": OMML_NS}

_CACHE_LOCK = threading.Lock()
_OMML_CACHE: dict[tuple[str, bool], tuple[str | None, str | None]] = {}


def find_pandoc_binary() -> str | None:
    """Find Pandoc executable via environment override, bundle, or PATH."""
    from backend.app import find_pandoc

    return find_pandoc()


def validate_equation(latex: str, pandoc_path: str | None = None) -> tuple[bool, str | None]:
    """Check if a LaTeX equation can be parsed into native MathML / OMML.

    Returns (True, None) if valid, or (False, error_detail) if unsupported or malformed.
    """
    elem, err = latex_to_omml(latex, display=False, pandoc_path=pandoc_path)
    if elem is not None:
        return True, None
    return False, err


def latex_to_omml(
    latex: str, display: bool = False, pandoc_path: str | None = None
) -> tuple[etree._Element | None, str | None]:
    """Convert a single LaTeX expression to a native OMML lxml element.

    Returns (etree._Element, None) on success, or (None, error_detail) on failure.
    Cached in memory to accelerate duplicate expressions.
    """
    cleaned = clean_latex(latex).strip()
    if not cleaned:
        return None, "Empty mathematical expression"

    cache_key = (cleaned, display)
    with _CACHE_LOCK:
        if cache_key in _OMML_CACHE:
            cached_xml, cached_err = _OMML_CACHE[cache_key]
            if cached_xml is not None:
                try:
                    return etree.fromstring(cached_xml.encode("utf-8")), None
                except Exception:
                    pass
            else:
                return None, cached_err

    binary = pandoc_path or find_pandoc_binary()
    if not binary:
        err = "Pandoc is not installed or not available on PATH"
        with _CACHE_LOCK:
            _OMML_CACHE[cache_key] = (None, err)
        return None, err

    temp_dir = tempfile.mkdtemp(prefix="mathocr-omml-")
    try:
        md_file = Path(temp_dir) / "math.md"
        docx_file = Path(temp_dir) / "math.docx"

        # Format with proper delimiters for Pandoc
        if display:
            content = f"$$\n{cleaned}\n$$\n"
        else:
            content = f"${cleaned}$"

        md_file.write_text(content, encoding="utf-8")
        cmd = [
            binary,
            "--from=markdown+tex_math_dollars",
            "--to=docx",
            "--standalone",
            str(md_file),
            "--output",
            str(docx_file),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)

        # Check for Pandoc texmath conversion warnings
        stderr = result.stderr or ""
        if "Could not convert TeX math" in stderr:
            error_line = [
                line.strip()
                for line in stderr.splitlines()
                if "Could not convert TeX math" in line or "unexpected" in line
            ]
            detail = "; ".join(error_line) if error_line else stderr.strip()
            with _CACHE_LOCK:
                _OMML_CACHE[cache_key] = (None, detail)
            return None, detail

        if result.returncode != 0 or not docx_file.exists():
            detail = stderr.strip() or f"Pandoc exited with code {result.returncode}"
            with _CACHE_LOCK:
                _OMML_CACHE[cache_key] = (None, detail)
            return None, detail

        with zipfile.ZipFile(docx_file) as zf:
            document_xml = zf.read("word/document.xml")

        root = etree.fromstring(document_xml)
        tag = "oMathPara" if display else "oMath"
        found = root.xpath(f".//m:{tag}", namespaces=NAMESPACES)
        if not found and display:
            found = root.xpath(".//m:oMath", namespaces=NAMESPACES)

        if not found:
            err = "Pandoc produced document without OMML elements"
            with _CACHE_LOCK:
                _OMML_CACHE[cache_key] = (None, err)
            return None, err

        elem = found[0]
        # Check that it is not empty
        xml_bytes = etree.tostring(elem, encoding="utf-8")
        xml_str = xml_bytes.decode("utf-8")
        with _CACHE_LOCK:
            _OMML_CACHE[cache_key] = (xml_str, None)
        return elem, None

    except subprocess.TimeoutExpired:
        err = "Equation conversion timed out"
        return None, err
    except Exception as exc:
        logger.warning("Equation conversion failed for %r: %s", cleaned, exc)
        return None, str(exc)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def batch_latex_to_omml(
    equations: list[tuple[str, bool]], pandoc_path: str | None = None
) -> list[tuple[etree._Element | None, str | None]]:
    """Convert multiple (latex, display) pairs, reusing cache and single calls."""
    results: list[tuple[etree._Element | None, str | None]] = []
    for latex, display in equations:
        results.append(latex_to_omml(latex, display=display, pandoc_path=pandoc_path))
    return results
