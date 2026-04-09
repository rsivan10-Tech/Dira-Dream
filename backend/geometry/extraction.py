"""
PDF vector extraction for Israeli residential floor plans.

Agent: VG (Vector/Geometry Specialist)
Phase 1, Sprint 1 — raw extraction, legend cropping, stroke histogram.
"""

from __future__ import annotations

import math

import fitz  # PyMuPDF
import numpy as np


# --- Working parameters (configurable, never hardcoded per VG rule #2) ---
MIN_SEGMENT_LENGTH_PT = 2.0  # Filter noise below 2 PDF points
HAIRLINE_WIDTH = 0.1  # Zero-width strokes treated as hairline
BEZIER_SUBDIVISIONS = 10  # Points for cubic Bézier approximation
CROP_PADDING_RATIO = 0.10  # 10% padding around apartment bbox
THICK_PERCENTILE = 80  # Percentile threshold for "thick" segments


def _bezier_point(t: float, p0, p1, p2, p3) -> tuple[float, float]:
    """Evaluate cubic Bézier at parameter t."""
    u = 1.0 - t
    return (
        u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
    )


def _segment_length(seg: dict) -> float:
    """Euclidean length of a segment."""
    (x1, y1), (x2, y2) = seg["start"], seg["end"]
    return math.hypot(x2 - x1, y2 - y1)


def _flip_y(y: float, page_height: float) -> float:
    """Convert PDF bottom-left Y to screen top-left Y."""
    return page_height - y


def extract_vectors(pdf_path: str, page_num: int = 0) -> dict:
    """
    Extract vector segments and text from a PDF page.

    Returns dict with:
      - segments: list of {start, end, stroke_width, color, dash_pattern}
      - texts: list of {content, bbox, font_size}
      - page_size: (width, height)
      - page_num: int
    """
    doc = fitz.open(pdf_path)
    if page_num >= len(doc):
        raise ValueError(f"Page {page_num} does not exist (PDF has {len(doc)} pages)")

    page = doc[page_num]
    page_width = page.rect.width
    page_height = page.rect.height

    raw_segments = []
    paths = page.get_drawings()

    for path in paths:
        stroke_width = path.get("width", 0.0) or 0.0
        if stroke_width == 0.0:
            stroke_width = HAIRLINE_WIDTH

        color = path.get("color")  # (r, g, b) or None
        dash_pattern = path.get("dashes", "")

        for item in path["items"]:
            op = item[0]

            if op == "l":
                # lineto: item is ("l", Point_start, Point_end)
                p1, p2 = item[1], item[2]
                raw_segments.append({
                    "start": (p1.x, _flip_y(p1.y, page_height)),
                    "end": (p2.x, _flip_y(p2.y, page_height)),
                    "stroke_width": stroke_width,
                    "color": tuple(color) if color else (0.0, 0.0, 0.0),
                    "dash_pattern": dash_pattern,
                })

            elif op == "re":
                # rectangle: item is ("re", Rect)
                rect = item[1]
                x0, y0_pdf, x1, y1_pdf = rect.x0, rect.y0, rect.x1, rect.y1
                y0 = _flip_y(y0_pdf, page_height)
                y1 = _flip_y(y1_pdf, page_height)
                corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
                for i in range(4):
                    raw_segments.append({
                        "start": corners[i],
                        "end": corners[(i + 1) % 4],
                        "stroke_width": stroke_width,
                        "color": tuple(color) if color else (0.0, 0.0, 0.0),
                        "dash_pattern": dash_pattern,
                    })

            elif op == "c":
                # curveto: item is ("c", P1, P2, P3, P4)
                p0, p1, p2, p3 = item[1], item[2], item[3], item[4]
                pts = [
                    _bezier_point(
                        t / BEZIER_SUBDIVISIONS,
                        (p0.x, p0.y), (p1.x, p1.y),
                        (p2.x, p2.y), (p3.x, p3.y),
                    )
                    for t in range(BEZIER_SUBDIVISIONS + 1)
                ]
                for i in range(len(pts) - 1):
                    ax, ay = pts[i]
                    bx, by = pts[i + 1]
                    raw_segments.append({
                        "start": (ax, _flip_y(ay, page_height)),
                        "end": (bx, _flip_y(by, page_height)),
                        "stroke_width": stroke_width,
                        "color": tuple(color) if color else (0.0, 0.0, 0.0),
                        "dash_pattern": dash_pattern,
                    })

    # Filter noise: segments shorter than MIN_SEGMENT_LENGTH_PT
    segments = [s for s in raw_segments if _segment_length(s) >= MIN_SEGMENT_LENGTH_PT]

    # Extract text blocks
    texts = []
    text_dict = page.get_text("dict")
    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:  # type 0 = text block
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                content = span.get("text", "").strip()
                if not content:
                    continue
                bbox = span.get("bbox", (0, 0, 0, 0))
                texts.append({
                    "content": content,
                    "bbox": (
                        bbox[0],
                        _flip_y(bbox[1], page_height),
                        bbox[2],
                        _flip_y(bbox[3], page_height),
                    ),
                    "font_size": span.get("size", 0.0),
                })

    doc.close()

    return {
        "segments": segments,
        "texts": texts,
        "page_size": (page_width, page_height),
        "page_num": page_num,
    }
