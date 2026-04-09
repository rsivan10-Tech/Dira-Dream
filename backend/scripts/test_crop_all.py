#!/usr/bin/env python3
"""Diagnostic: run crop_legend on all test PDFs, show before/after results."""

import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from geometry.extraction import extract_vectors, crop_legend, isolate_apartment, compute_stroke_histogram

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
                isolated = isolate_apartment(cropped)
                report = cropped["crop_report"]

                orig = report["original_segments"]
                after_crop = report["kept_segments"]
                after_iso = len(isolated["segments"])
                total_pct = ((orig - after_iso) / orig * 100) if orig > 0 else 0.0

                iso_report = isolated.get("isolation_report")
                iso_str = ""
                if iso_report:
                    iso_str = f" iso:{after_crop}->{after_iso}"

                crop_bbox = report.get("crop_bbox")
                bbox_str = (
                    f"({crop_bbox[0]:.0f},{crop_bbox[1]:.0f},{crop_bbox[2]:.0f},{crop_bbox[3]:.0f})"
                    if crop_bbox else "None"
                )

                orig_texts = len(raw.get("texts", []))
                kept_texts = len(isolated.get("texts", []))

                print(f"{page_label:<12} {orig:>6} {after_iso:>6} {total_pct:>5.1f}% "
                      f"{orig_texts:>6} {kept_texts:>6} {bbox_str}{iso_str}")
            except Exception as e:
                print(f"{page_label:<12} ERROR: {e}")


if __name__ == "__main__":
    run()
