#!/usr/bin/env python3
"""Diagnostic: run crop_legend on all test PDFs, show before/after results."""

import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from geometry.extraction import extract_vectors, crop_legend, compute_stroke_histogram

PDF_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "test-pdfs")


def run():
    pdfs = sorted(glob.glob(os.path.join(PDF_DIR, "*.pdf")))
    if not pdfs:
        print(f"No PDFs found in {PDF_DIR}")
        return

    print(f"{'Sample':<12} {'Segs':>6} {'After':>6} {'Crop%':>6} "
          f"{'Texts':>6} {'TxAftr':>6} {'BBox'}")
    print("-" * 80)

    for pdf_path in pdfs:
        name = os.path.basename(pdf_path)
        # Extract sample number from filename
        label = name.split(" ")[2] if len(name.split(" ")) > 2 else name[:12]

        # Handle multi-page PDFs
        import fitz
        doc = fitz.open(pdf_path)
        num_pages = len(doc)
        doc.close()

        for page_num in range(num_pages):
            page_label = f"{label}" if num_pages == 1 else f"{label}.{page_num}"

            try:
                raw = extract_vectors(pdf_path, page_num=page_num)
                cropped = crop_legend(raw)
                report = cropped["crop_report"]

                orig = report["original_segments"]
                kept = report["kept_segments"]
                crop_pct = ((orig - kept) / orig * 100) if orig > 0 else 0.0
                bbox = report.get("crop_bbox")
                bbox_str = (
                    f"({bbox[0]:.0f},{bbox[1]:.0f},{bbox[2]:.0f},{bbox[3]:.0f})"
                    if bbox else "None"
                )

                orig_texts = len(raw.get("texts", []))
                kept_texts = len(cropped.get("texts", []))

                print(f"{page_label:<12} {orig:>6} {kept:>6} {crop_pct:>5.1f}% "
                      f"{orig_texts:>6} {kept_texts:>6} {bbox_str}")
            except Exception as e:
                print(f"{page_label:<12} ERROR: {e}")


if __name__ == "__main__":
    run()
