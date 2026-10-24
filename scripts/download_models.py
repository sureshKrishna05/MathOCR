#!/usr/bin/env python3
"""Pre-download all required MathOCR models into the cache directory."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.model_store import (
    configure_model_environment,
    ensure_pix2text_models,
    ensure_pix2tex_weights,
    ensure_rapid_latex_weights,
    ensure_tesseract_langs,
    default_cache_root,
)


def main():
    root = configure_model_environment()
    print(f"Downloading MathOCR models into: {root}")

    print("\n[1/4] Downloading Pix2Text (MFR + MFD) models (~190 MB)...")
    try:
        ensure_pix2text_models()
        print("  ✓ Pix2Text models ready.")
    except Exception as e:
        print(f"  ✗ Error downloading Pix2Text: {e}")

    print("\n[2/4] Downloading pix2tex (LaTeX-OCR) weights (~115 MB)...")
    try:
        ensure_pix2tex_weights()
        print("  ✓ pix2tex weights ready.")
    except Exception as e:
        print(f"  ✗ Error downloading pix2tex: {e}")

    print("\n[3/4] Downloading RapidLaTeXOCR ONNX models (~170 MB)...")
    try:
        ensure_rapid_latex_weights()
        print("  ✓ RapidLaTeXOCR models ready.")
    except Exception as e:
        print(f"  ✗ Error downloading RapidLaTeXOCR: {e}")

    print("\n[4/4] Downloading Tesseract language data (~5 MB)...")
    try:
        ensure_tesseract_langs()
        print("  ✓ Tesseract data ready.")
    except Exception as e:
        print(f"  ✗ Error downloading Tesseract data: {e}")

    print("\nAll model downloads complete!")


if __name__ == "__main__":
    main()
