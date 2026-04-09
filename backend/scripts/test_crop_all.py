#!/usr/bin/env python3
"""Diagnostic: run crop_legend on all test PDFs (page 0 only), show results."""

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

    print(f"{'#':<6} {'Segs':>6} {'After':>6} {'Crop%':>6} "
          f"{'Texts':>6} {'TxAft':>6} {'Peaks':>5} {'BBox':<36} {'Notes'}")
    print("-" * 120)

    for pdf_path in pdfs:
        name = os.path.basename(pdf_path)
        # Extract sample number
        parts = name.split(" ")
        label = parts[2] if len(parts) > 2 else name[:6]

        # Skip multi-page — only do page 0 (matching inventory)
        # Exception: Sample 5 has known page split
        try:
            raw = extract_vectors(pdf_path, page_num=0)
            cropped = crop_legend(raw)
            hist = compute_stroke_histogram(cropped["segments"])
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
            n_peaks = len(hist.get("peaks", []))

            # Assess quality
            notes = ""
            if crop_pct > 30:
                notes = "GOOD crop"
            elif crop_pct > 10:
                notes = "moderate crop"
            elif crop_pct > 2:
                notes = "light crop"
            else:
                notes = "no separation"

            print(f"{label:<6} {orig:>6} {kept:>6} {crop_pct:>5.1f}% "
                  f"{orig_texts:>6} {kept_texts:>6} {n_peaks:>5} {bbox_str:<36} {notes}")

        except Exception as e:
            print(f"{label:<6} ERROR: {e}")


if __name__ == "__main__":
    run()
