"""
PDF vector extraction for Israeli residential floor plans.

Agent: VG (Vector/Geometry Specialist)
Phase 1, Sprint 1 — raw extraction, legend cropping, stroke histogram.
"""

from __future__ import annotations

import math

import fitz  # PyMuPDF
import numpy as np
from scipy.ndimage import binary_closing, label as ndimage_label
from scipy.signal import find_peaks
from scipy.stats import gaussian_kde


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


def _seg_bbox(seg: dict) -> tuple[float, float, float, float]:
    """Return (min_x, min_y, max_x, max_y) for a segment."""
    (x1, y1), (x2, y2) = seg["start"], seg["end"]
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def _bbox_intersects(a: tuple, b: tuple) -> bool:
    """Check if two (min_x, min_y, max_x, max_y) bboxes overlap."""
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _no_crop_report(total: int) -> dict:
    """Return a crop_report that indicates no cropping was applied."""
    return {"original_segments": total, "kept_segments": total, "crop_bbox": None}


def crop_legend(data: dict) -> dict:
    """
    Crop kartisiyyah (title block / legend) using density-grid clustering.

    Strategy:
    1. Divide the page into a grid of cells.
    2. Accumulate segment length per cell (weighted by stroke width).
    3. Threshold at median of non-zero cells.
    4. Find connected components of above-threshold cells (scipy.ndimage.label).
    5. The largest component (by total density) is the apartment region.
    6. Filter segments/texts outside that region's bbox + padding.

    This replaces the old approach (thick-segment bbox) which failed when
    kartisiyyah borders had similar stroke widths to apartment walls.
    """
    segments = data["segments"]
    texts = data.get("texts", [])
    page_w, page_h = data["page_size"]

    if len(segments) < 20:
        return {**data, "crop_report": _no_crop_report(len(segments))}

    original_count = len(segments)

    # --- Build density grid ---
    GRID = 30
    cell_w = page_w / GRID
    cell_h = page_h / GRID
    density = np.zeros((GRID, GRID))

    for s in segments:
        seg_len = _segment_length(s)
        weight = seg_len * max(s["stroke_width"], HAIRLINE_WIDTH)
        for px, py in [s["start"], s["end"]]:
            ci = int(np.clip(px / cell_w, 0, GRID - 1))
            ri = int(np.clip(py / cell_h, 0, GRID - 1))
            density[ri, ci] += weight / 2

    nonzero = density[density > 0]
    if len(nonzero) < 4:
        return {**data, "crop_report": _no_crop_report(original_count)}

    # --- Adaptive threshold: find the level that separates apartment from legend ---
    # Try progressively higher thresholds until the largest component covers
    # a reasonable fraction of the grid (15-85%), indicating clean separation.
    labeled = None
    best_label = None
    for pct in (40, 50, 60, 70, 80):
        thresh = float(np.percentile(nonzero, pct))
        mask = (density >= thresh).astype(np.int32)
        # Light closing (2x2) to bridge immediate neighbors without merging
        # distant regions.
        closed = binary_closing(mask, structure=np.ones((2, 2))).astype(np.int32)
        lab, n_labels = ndimage_label(closed)

        if n_labels < 2:
            continue  # everything merged — try higher threshold

        sizes = {lb: int(np.sum(lab == lb)) for lb in range(1, n_labels + 1)}
        top_label = max(sizes, key=sizes.get)
        ratio = sizes[top_label] / (GRID * GRID)

        if 0.15 <= ratio <= 0.85:
            labeled = lab
            best_label = top_label
            break

    if labeled is None or best_label is None:
        return {**data, "crop_report": _no_crop_report(original_count)}

    rows, cols = np.where(labeled == best_label)
    min_x = float(cols.min()) * cell_w
    max_x = float(cols.max() + 1) * cell_w
    min_y = float(rows.min()) * cell_h
    max_y = float(rows.max() + 1) * cell_h

    # Skip if bbox already covers >92% of page (no meaningful crop)
    bbox_area = (max_x - min_x) * (max_y - min_y)
    if bbox_area > 0.92 * page_w * page_h:
        return {**data, "crop_report": _no_crop_report(original_count)}

    # Pad and clamp
    pad_x = (max_x - min_x) * CROP_PADDING_RATIO
    pad_y = (max_y - min_y) * CROP_PADDING_RATIO
    crop_bbox = (
        max(0.0, min_x - pad_x),
        max(0.0, min_y - pad_y),
        min(page_w, max_x + pad_x),
        min(page_h, max_y + pad_y),
    )

    # Filter segments
    kept_segments = [s for s in segments if _bbox_intersects(_seg_bbox(s), crop_bbox)]

    # Safety: if we'd remove >70% of segments, something is wrong — skip crop
    if len(kept_segments) < original_count * 0.3:
        return {**data, "crop_report": _no_crop_report(original_count)}

    # Filter texts
    kept_texts = []
    for t in texts:
        bx0, by0, bx1, by1 = t["bbox"]
        text_bb = (min(bx0, bx1), min(by0, by1), max(bx0, bx1), max(by0, by1))
        if _bbox_intersects(text_bb, crop_bbox):
            kept_texts.append(t)

    return {
        "segments": kept_segments,
        "texts": kept_texts,
        "page_size": data["page_size"],
        "page_num": data["page_num"],
        "crop_report": {
            "original_segments": original_count,
            "kept_segments": len(kept_segments),
            "crop_bbox": crop_bbox,
        },
    }


def compute_stroke_histogram(segments: list[dict]) -> dict:
    """
    Analyze stroke width distribution to find natural clusters.

    Uses Gaussian KDE to find density peaks, then computes midpoint
    thresholds between adjacent peaks for wall classification.

    Returns:
      - widths: sorted unique stroke widths
      - peaks: detected peak values
      - suggested_thresholds: midpoints between adjacent peaks
    """
    if not segments:
        return {"widths": [], "peaks": [], "suggested_thresholds": []}

    raw_widths = [s["stroke_width"] for s in segments]
    # Filter out hairline/zero-width — they're noise, not walls
    widths = [w for w in raw_widths if w > HAIRLINE_WIDTH]

    if not widths:
        return {"widths": [], "peaks": [], "suggested_thresholds": []}

    unique_widths = sorted(set(widths))

    # KDE needs variance — if fewer than 3 unique values, return them as peaks
    if len(unique_widths) < 3:
        return {
            "widths": unique_widths,
            "peaks": unique_widths,
            "suggested_thresholds": (
                [(unique_widths[0] + unique_widths[1]) / 2]
                if len(unique_widths) == 2
                else []
            ),
        }

    arr = np.array(widths)
    # Use narrow bandwidth — stroke widths cluster tightly (0.2 vs 1.0 vs 3.0)
    kde = gaussian_kde(arr, bw_method=0.15)

    # Evaluate KDE over a fine grid
    x_min, x_max = arr.min(), arr.max()
    margin = (x_max - x_min) * 0.1
    x_grid = np.linspace(x_min - margin, x_max + margin, 500)
    density = kde(x_grid)

    # Find peaks in the density curve
    peak_indices, _ = find_peaks(density)

    if len(peak_indices) == 0:
        # Fallback: use the mode
        return {
            "widths": unique_widths,
            "peaks": [float(arr.mean())],
            "suggested_thresholds": [],
        }

    peaks = sorted(float(x_grid[i]) for i in peak_indices)
    thresholds = [(peaks[i] + peaks[i + 1]) / 2 for i in range(len(peaks) - 1)]

    return {
        "widths": unique_widths,
        "peaks": peaks,
        "suggested_thresholds": thresholds,
    }
