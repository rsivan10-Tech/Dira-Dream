"""
PDF vector extraction for Israeli residential floor plans.

Agent: VG (Vector/Geometry Specialist)
Phase 1, Sprint 1 — raw extraction, legend cropping, stroke histogram.
Sprint 4 — pre-crop metadata extraction (scale, area annotations, fixture labels).
"""

from __future__ import annotations

import logging
import math
import re

import fitz  # PyMuPDF
import numpy as np
from scipy.ndimage import binary_closing, label as ndimage_label
from scipy.signal import find_peaks
from scipy.stats import gaussian_kde
from shapely.geometry import LineString, Point
from shapely.ops import polygonize, unary_union

logger = logging.getLogger(__name__)


# --- Working parameters (configurable, never hardcoded per VG rule #2) ---
MIN_SEGMENT_LENGTH_PT = 2.0  # Filter noise below 2 PDF points
HAIRLINE_WIDTH = 0.1  # Zero-width strokes treated as hairline
BEZIER_SUBDIVISIONS = 10  # Points for cubic Bézier approximation
CROP_PADDING_RATIO = 0.10  # 10% padding around apartment bbox
THICK_PERCENTILE = 80  # Percentile threshold for "thick" segments
ISOLATION_MARGIN = 0.40  # Expand seed polygon bbox by 40% of max dimension
ISOLATION_PERCENTILE = 90  # Percentile for thick-wall polygonize
MIN_POLYGON_AREA = 500  # Minimum polygon area to consider (in pt²)


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


# ---------------------------------------------------------------------------
# Pre-crop metadata extraction
# ---------------------------------------------------------------------------

# Scale notation patterns: "1:50", "1:100", "קנ״מ 1:50", "קנה מידה 1:50"
_SCALE_PATTERN = re.compile(r'1\s*:\s*(50|100|200|25|75|150)')
# Area patterns: digits (with optional decimal) followed by sqm unit
_AREA_SQM_PATTERN = re.compile(
    r'(\d+(?:\.\d+)?)\s*(?:מ"ר|מ״ר|m²|sqm|מ\.ר\.)',
)
# Fixture / room label keywords in Hebrew
_FIXTURE_LABELS = {
    'סלון', 'חדר שינה', 'חדר שינה הורים', 'חדר ילדים',
    'מטבח', 'שירותים', 'אמבטיה', 'מקלחת', 'ממ"ד', 'ממ״ד',
    'מרפסת', 'מרפסת שירות', 'מחסן', 'מסדרון', 'כניסה',
    'פרוזדור', 'חדר עבודה', 'חדר כביסה',
    # Abbreviations
    'ח. שינה', 'ח. רחצה', 'ח. עבודה', 'חד. שינה', 'מרפ.',
    # Fixtures
    'כיור', 'אמבט', 'מקלחון', 'אסלה', 'כיריים', 'תנור',
    'מכונת כביסה', 'מייבש', 'מדיח',
}
# Total area keywords: "שטח דירה", "שטח עיקרי", "שטח כולל"
_TOTAL_AREA_CONTEXT = re.compile(
    r'(?:שטח\s*(?:דירה|עיקרי|כולל|נטו|ברוטו))',
)
# Balcony area keywords
_BALCONY_AREA_CONTEXT = re.compile(
    r'(?:שטח\s*(?:מרפסת|מרפסות))',
)


def detect_scale_from_text(texts: list[dict]) -> dict:
    """
    Search ALL text annotations for scale notation before cropping.

    Looks for patterns like "1:50", "1:100", "קנ״מ 1:50".

    Returns
    -------
    dict
        {scale_notation: str | None, scale_value: int | None}
        scale_value is the denominator (50, 100, etc.)
    """
    for t in texts:
        content = t["content"]
        match = _SCALE_PATTERN.search(content)
        if match:
            denominator = int(match.group(1))
            notation = f"1:{denominator}"
            logger.info("Scale detected from text: %s (source: %r)", notation, content)
            return {"scale_notation": notation, "scale_value": denominator}

    return {"scale_notation": None, "scale_value": None}


def detect_area_annotations(texts: list[dict]) -> dict:
    """
    Search ALL text annotations for area values (sqm) before cropping.

    Identifies total apartment area and balcony area from contextual text.
    Also collects all standalone area values found on the page.

    Returns
    -------
    dict
        {total_area_sqm: float | None, balcony_area_sqm: float | None,
         area_values: list[{value: float, context: str, bbox: tuple}]}
    """
    total_area: float | None = None
    balcony_area: float | None = None
    area_values: list[dict] = []

    # First pass: collect all area values with their textual context
    for i, t in enumerate(texts):
        content = t["content"]
        match = _AREA_SQM_PATTERN.search(content)
        if not match:
            continue

        value = float(match.group(1))
        area_values.append({
            "value": value,
            "context": content,
            "bbox": t["bbox"],
        })

    # Second pass: look for contextual keywords near area values.
    # Check current text first; only fall back to adjacent spans if no
    # context keyword is found in the current span itself.
    for i, t in enumerate(texts):
        content = t["content"]

        area_match = _AREA_SQM_PATTERN.search(content)
        if not area_match:
            continue

        value = float(area_match.group(1))

        # Priority 1: context keyword in the SAME text span
        has_total_ctx = _TOTAL_AREA_CONTEXT.search(content)
        has_balcony_ctx = _BALCONY_AREA_CONTEXT.search(content)

        if not has_total_ctx and not has_balcony_ctx:
            # Priority 2: context keyword in an adjacent span only
            prev = texts[i - 1]["content"] if i > 0 else ""
            nxt = texts[i + 1]["content"] if i < len(texts) - 1 else ""
            has_total_ctx = _TOTAL_AREA_CONTEXT.search(prev) or _TOTAL_AREA_CONTEXT.search(nxt)
            has_balcony_ctx = _BALCONY_AREA_CONTEXT.search(prev) or _BALCONY_AREA_CONTEXT.search(nxt)

        if has_total_ctx and total_area is None:
            total_area = value
            logger.info("Total area detected: %.1f sqm (source: %r)", value, content)

        if has_balcony_ctx and balcony_area is None:
            balcony_area = value
            logger.info("Balcony area detected: %.1f sqm (source: %r)", value, content)

    return {
        "total_area_sqm": total_area,
        "balcony_area_sqm": balcony_area,
        "area_values": area_values,
    }


def detect_fixture_labels(texts: list[dict]) -> list[dict]:
    """
    Find all fixture and room labels on the page before cropping.

    Returns
    -------
    list[dict]
        [{label: str, bbox: tuple, font_size: float}, ...]
    """
    found: list[dict] = []

    for t in texts:
        content = t["content"].strip()
        if not content:
            continue

        # Exact match against known fixture/room labels
        for label in _FIXTURE_LABELS:
            if label in content:
                found.append({
                    "label": label,
                    "bbox": t["bbox"],
                    "font_size": t["font_size"],
                })
                break

    logger.info("Fixture labels found: %d", len(found))
    return found


def extract_metadata(texts: list[dict]) -> dict:
    """
    Run all pre-crop metadata extraction on the full text set.

    Called by the pipeline BEFORE crop_legend() so that legend-area text
    (scale notation, total area, balcony area, fixture labels) is captured
    before those texts are filtered out.

    Returns
    -------
    dict
        Combined metadata from scale, area, and fixture detection.
    """
    scale_info = detect_scale_from_text(texts)
    area_info = detect_area_annotations(texts)
    fixture_labels = detect_fixture_labels(texts)

    return {
        "scale_notation": scale_info["scale_notation"],
        "scale_value": scale_info["scale_value"],
        "total_area_sqm": area_info["total_area_sqm"],
        "balcony_area_sqm": area_info["balcony_area_sqm"],
        "area_values": area_info["area_values"],
        "fixture_labels": fixture_labels,
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


def isolate_apartment(data: dict) -> dict:
    """
    Isolate the target apartment from neighboring apartment outlines.

    Israeli contractor plans often show adjacent unit boundaries for context.
    This function finds the largest closed polygon formed by thick wall
    segments, then uses it as a seed to define the apartment boundary.

    Strategy:
    1. Polygonize thick wall segments (≥90th percentile width).
    2. Find the polygon with the most interior segments (the main room).
    3. Expand its bounding box by ISOLATION_MARGIN to capture adjacent rooms.
    4. Filter segments/texts to the expanded box.

    Skips isolation if no meaningful polygon is found or if the expansion
    would cover most of the page (no neighboring outline to remove).
    """
    segments = data["segments"]
    texts = data.get("texts", [])
    page_w, page_h = data["page_size"]
    original_count = len(segments)

    if original_count < 50:
        return data

    # --- Find thick wall segments and polygonize ---
    widths = [s["stroke_width"] for s in segments]
    w_thresh = float(np.percentile(widths, ISOLATION_PERCENTILE))
    thick = [s for s in segments if s["stroke_width"] >= w_thresh]

    if len(thick) < 10:
        return data

    lines = [
        LineString([(s["start"][0], s["start"][1]), (s["end"][0], s["end"][1])])
        for s in thick
    ]
    merged = unary_union(lines)
    polys = list(polygonize(merged))

    if not polys:
        return data

    # --- Find seed: polygon with the most interior segments ---
    best_poly = None
    best_inside = 0
    midpoints = [
        Point((s["start"][0] + s["end"][0]) / 2, (s["start"][1] + s["end"][1]) / 2)
        for s in segments
    ]
    for poly in polys:
        if poly.area < MIN_POLYGON_AREA:
            continue
        inside = sum(1 for pt in midpoints if poly.contains(pt))
        if inside > best_inside:
            best_inside = inside
            best_poly = poly

    if best_poly is None or best_inside < 20:
        return data

    # --- Expand seed bounds ---
    # Use uniform expansion based on the LARGER dimension so the short axis
    # gets adequate coverage (seed polygons are often wider than tall).
    bx0, by0, bx1, by1 = best_poly.bounds
    seed_w = bx1 - bx0
    seed_h = by1 - by0
    expansion = max(seed_w, seed_h) * ISOLATION_MARGIN

    exp_bbox = (
        max(0.0, bx0 - expansion),
        max(0.0, by0 - expansion),
        min(page_w, bx1 + expansion),
        min(page_h, by1 + expansion),
    )

    # Skip if expanded bbox covers >90% of the page (no neighbor to remove)
    exp_area = (exp_bbox[2] - exp_bbox[0]) * (exp_bbox[3] - exp_bbox[1])
    if exp_area > 0.90 * page_w * page_h:
        return data

    # --- Filter segments and texts ---
    kept_segments = [s for s in segments if _bbox_intersects(_seg_bbox(s), exp_bbox)]

    # Safety: don't remove more than 50% of segments
    if len(kept_segments) < original_count * 0.5:
        return data

    kept_texts = []
    for t in texts:
        bx0t, by0t, bx1t, by1t = t["bbox"]
        text_bb = (min(bx0t, bx1t), min(by0t, by1t), max(bx0t, bx1t), max(by0t, by1t))
        if _bbox_intersects(text_bb, exp_bbox):
            kept_texts.append(t)

    isolation_report = {
        "seed_bounds": (
            round(best_poly.bounds[0], 1),
            round(best_poly.bounds[1], 1),
            round(best_poly.bounds[2], 1),
            round(best_poly.bounds[3], 1),
        ),
        "seed_area": round(best_poly.area, 1),
        "seed_interior_segments": best_inside,
        "expanded_bbox": tuple(round(v, 1) for v in exp_bbox),
        "original_segments": original_count,
        "kept_segments": len(kept_segments),
    }

    result = {
        **data,
        "segments": kept_segments,
        "texts": kept_texts,
    }
    # Preserve existing crop_report and add isolation_report
    if "crop_report" in data:
        result["crop_report"] = data["crop_report"]
    result["isolation_report"] = isolation_report
    return result


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
