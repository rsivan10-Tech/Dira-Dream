"""
Diagnose whether test PDFs are vector-based, raster, or hybrid.

Usage:
    python scripts/diagnose_pdfs.py [pdf_dir]

Default pdf_dir: ../docs/test-pdfs/
"""

import fitz  # PyMuPDF
import os
import re
import sys
import glob


def diagnose_pdf(pdf_path: str) -> list[dict]:
    """Diagnose each page: vector drawing count, image count, text, full-page image check."""
    doc = fitz.open(pdf_path)
    results = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        page_area = page.rect.width * page.rect.height

        drawings = page.get_drawings()
        images = page.get_images(full=True)
        text_dict = page.get_text("dict")
        text_blocks = text_dict.get("blocks", [])

        text_spans = 0
        for block in text_blocks:
            if block.get("type") == 0:
                for line in block.get("lines", []):
                    text_spans += len(line.get("spans", []))

        has_full_page_image = False
        largest_image_coverage = 0.0
        for img in images:
            for rect in page.get_image_rects(img[0]):
                coverage = (rect.width * rect.height) / page_area if page_area else 0
                largest_image_coverage = max(largest_image_coverage, coverage)
                if coverage > 0.5:
                    has_full_page_image = True

        if has_full_page_image:
            verdict = "hybrid" if len(drawings) > 50 else "raster"
        elif len(drawings) > 50:
            verdict = "vector"
        elif len(images) > 0:
            verdict = "hybrid" if len(drawings) > 0 else "raster"
        else:
            verdict = "vector"

        results.append({
            "page_num": page_num,
            "drawing_count": len(drawings),
            "image_count": len(images),
            "text_blocks": len(text_blocks),
            "text_spans": text_spans,
            "has_full_page_image": has_full_page_image,
            "largest_image_coverage": largest_image_coverage,
            "verdict": verdict,
        })

    doc.close()
    return results


def sample_key(path: str) -> float:
    m = re.search(r"Sample (\d+\.?\d*)", os.path.basename(path))
    return float(m.group(1)) if m else 999


def main():
    pdf_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "..", "..", "docs", "test-pdfs"
    )
    pdf_dir = os.path.abspath(pdf_dir)
    pdf_files = sorted(glob.glob(os.path.join(pdf_dir, "*.pdf")), key=sample_key)

    if not pdf_files:
        print(f"No PDFs found in {pdf_dir}")
        sys.exit(1)

    print(f"{'Sample':<10} {'Page':>4} {'Drawings':>9} {'Images':>7} {'TxtBlks':>8} "
          f"{'TxtSpans':>9} {'FullPgImg':>10} {'Coverage':>9} {'Verdict':<8}")
    print("-" * 85)

    summaries = []
    for pdf_path in pdf_files:
        m = re.search(r"Sample (\d+\.?\d*)", os.path.basename(pdf_path))
        label = f"S{m.group(1)}" if m else os.path.basename(pdf_path)[:8]

        try:
            pages = diagnose_pdf(pdf_path)
            for p in pages:
                print(f"{label:<10} {p['page_num']:>4} {p['drawing_count']:>9,} "
                      f"{p['image_count']:>7} {p['text_blocks']:>8} {p['text_spans']:>9} "
                      f"{str(p['has_full_page_image']):>10} {p['largest_image_coverage']:>8.1%} "
                      f"{p['verdict']:<8}")
            summaries.append((label, pages))
        except Exception as e:
            print(f"{label:<10}  ERROR: {e}")

    print("\n=== SUMMARY ===\n")
    print(f"{'Sample':<10} {'Pages':>5} {'Type':<8} {'Notes'}")
    print("-" * 70)

    for label, pages in summaries:
        total_drawings = sum(p["drawing_count"] for p in pages)
        total_images = sum(p["image_count"] for p in pages)
        any_fullpage = any(p["has_full_page_image"] for p in pages)
        verdicts = set(p["verdict"] for p in pages)

        if all(v == "vector" for v in verdicts):
            overall = "VECTOR"
            note = f"{total_drawings:,} drawings, {total_images} images"
        elif all(v == "raster" for v in verdicts):
            overall = "RASTER"
            note = f"NOT suitable for vector pipeline! {total_images} images"
        elif "raster" in verdicts:
            overall = "MIXED"
            raster_pages = [p["page_num"] for p in pages if p["verdict"] == "raster"]
            note = f"Raster pages: {raster_pages}"
        else:
            overall = "HYBRID"
            note = f"{total_drawings:,} drawings + {total_images} images"

        if any_fullpage:
            note += " | HAS FULL-PAGE IMAGE"

        print(f"{label:<10} {len(pages):>5} {overall:<8} {note}")


if __name__ == "__main__":
    main()
