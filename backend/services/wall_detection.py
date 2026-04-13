"""Parallel-line wall detection with centerline extraction.

Quality Sprint Step 1 — replaces stroke-width wall classification with
measurement-based classification from parallel line pairs. Real Israeli PDFs
draw each wall as two parallel strokes (inner + outer face); this module
collapses them into a single centerline carrying the measured thickness.

Algorithm:
  1. Pre-filter to wall-width candidates (drop dashed, hairlines, very short)
  2. STRtree proximity search → candidate pairs
  3. Validate pair: angle <5°, perpendicular distance ∈ [6cm, 40cm],
     projected overlap ≥50% of shorter segment
  4. Build centerline: project all 4 endpoints onto average direction,
     take min/max for span; thickness = perp distance between midpoints
  5. Greedy assignment: highest-overlap pairs win, each segment used once
  6. Classify by thickness using relative ranking (mamad ≥ exterior ≥
     partition) with spec bands as fallback floors
  7. Unpaired thick segments → single-line wall fallback (lower confidence)

Agent: VG | Quality Sprint Step 1
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from shapely.geometry import LineString
from shapely.strtree import STRtree


# --- Working parameters (configurable per VG rule #2) ---
MAX_PARALLEL_ANGLE_DEG = 5.0
MIN_OVERLAP_RATIO = 0.5
MIN_WALL_THICKNESS_CM = 6.0       # below this = furniture/annotation
MAX_WALL_THICKNESS_CM = 40.0      # above this = double wall, flag
MIN_SEGMENT_LENGTH_PT = 5.0       # filter short noise pre-pairing
MIN_WALL_LENGTH_CM = 50.0         # real walls ≥ 50cm; shorter pairs = furniture
SINGLE_LINE_THICKNESS_CM = 10.0   # default thickness for unpaired thick lines
ENABLE_SINGLE_LINE_FALLBACK = False  # off by default — furniture outlines pollute it

# Spec thickness bands — used as floors in the relative classifier
PARTITION_MAX_CM = 12.0
EXTERIOR_MAX_CM = 18.0
MAMAD_MIN_CM = 18.0  # mamad must be clearly thicker than partition

# Mamad detection: only the top fraction of the population, and only if
# substantially thicker than the median (mamad ≥ exterior ≥ partition rule).
MAMAD_TOP_PERCENTILE = 90
MAMAD_MIN_DELTA_OVER_MEDIAN_CM = 4.0


@dataclass
class CenterlineWall:
    """A single wall represented by its centerline and measured thickness.

    Coordinates in PDF points. Thickness in real-world cm. Source segment
    indices retained so the opening detector can inspect the original
    parallel pair for gaps.
    """

    id: str
    p1: tuple[float, float]
    p2: tuple[float, float]
    thickness_cm: float
    wall_type: str = "unknown"  # exterior | mamad | partition | unknown
    confidence: float = 0.0
    source_segment_ids: list[int] = field(default_factory=list)
    # (start_pos, end_pos) in PDF points along the centerline, for gap hosting
    gaps: list[tuple[float, float]] = field(default_factory=list)

    @property
    def length_pt(self) -> float:
        return math.hypot(self.p2[0] - self.p1[0], self.p2[1] - self.p1[1])


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _seg_length(seg: dict) -> float:
    (x1, y1), (x2, y2) = seg["start"], seg["end"]
    return math.hypot(x2 - x1, y2 - y1)


def _seg_dir(seg: dict) -> tuple[float, float]:
    (x1, y1), (x2, y2) = seg["start"], seg["end"]
    L = math.hypot(x2 - x1, y2 - y1)
    if L < 1e-9:
        return (1.0, 0.0)
    return ((x2 - x1) / L, (y2 - y1) / L)


def _angle_diff_deg(d1: tuple, d2: tuple) -> float:
    """Smallest angle (degrees) between two unit vectors, treating them as undirected lines."""
    dot = abs(d1[0] * d2[0] + d1[1] * d2[1])
    dot = min(1.0, max(-1.0, dot))
    return math.degrees(math.acos(dot))


def _perp_distance(seg_a: dict, seg_b: dict, dir_a: tuple) -> float:
    """Perpendicular distance from b's midpoint to a's infinite line."""
    amx = (seg_a["start"][0] + seg_a["end"][0]) / 2
    amy = (seg_a["start"][1] + seg_a["end"][1]) / 2
    bmx = (seg_b["start"][0] + seg_b["end"][0]) / 2
    bmy = (seg_b["start"][1] + seg_b["end"][1]) / 2
    dx, dy = bmx - amx, bmy - amy
    perp_x, perp_y = -dir_a[1], dir_a[0]
    return abs(dx * perp_x + dy * perp_y)


def _projected_overlap_ratio(seg_a: dict, seg_b: dict, axis: tuple) -> float:
    """Overlap of A and B projected onto a shared axis, as fraction of shorter length."""
    def proj(p, origin, ax):
        return (p[0] - origin[0]) * ax[0] + (p[1] - origin[1]) * ax[1]

    origin = seg_a["start"]
    ta = sorted([proj(seg_a["start"], origin, axis), proj(seg_a["end"], origin, axis)])
    tb = sorted([proj(seg_b["start"], origin, axis), proj(seg_b["end"], origin, axis)])
    overlap = max(0.0, min(ta[1], tb[1]) - max(ta[0], tb[0]))
    min_len = min(ta[1] - ta[0], tb[1] - tb[0])
    return overlap / min_len if min_len > 1e-9 else 0.0


def _build_centerline(seg_a: dict, seg_b: dict, scale_factor: float):
    """Return (p1, p2, thickness_cm) for a parallel pair."""
    dir_a = _seg_dir(seg_a)
    dir_b = _seg_dir(seg_b)
    if dir_a[0] * dir_b[0] + dir_a[1] * dir_b[1] < 0:
        dir_b = (-dir_b[0], -dir_b[1])
    avg_x = (dir_a[0] + dir_b[0]) / 2
    avg_y = (dir_a[1] + dir_b[1]) / 2
    L = math.hypot(avg_x, avg_y)
    d = (avg_x / L, avg_y / L) if L > 1e-9 else dir_a
    perp = (-d[1], d[0])

    pts = [seg_a["start"], seg_a["end"], seg_b["start"], seg_b["end"]]
    cx = sum(p[0] for p in pts) / 4
    cy = sum(p[1] for p in pts) / 4

    # Project onto centerline direction → take min/max for span
    ts = [(p[0] - cx) * d[0] + (p[1] - cy) * d[1] for p in pts]
    t_min, t_max = min(ts), max(ts)
    p1 = (cx + d[0] * t_min, cy + d[1] * t_min)
    p2 = (cx + d[0] * t_max, cy + d[1] * t_max)

    # Thickness = perp distance between segment midpoints
    pa_mid = ((seg_a["start"][0] + seg_a["end"][0]) / 2 - cx,
              (seg_a["start"][1] + seg_a["end"][1]) / 2 - cy)
    pb_mid = ((seg_b["start"][0] + seg_b["end"][0]) / 2 - cx,
              (seg_b["start"][1] + seg_b["end"][1]) / 2 - cy)
    thick_pt = abs((pa_mid[0] - pb_mid[0]) * perp[0]
                   + (pa_mid[1] - pb_mid[1]) * perp[1])
    thickness_cm = thick_pt * scale_factor * 100.0
    return p1, p2, thickness_cm


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def _classify_thickness(thickness_cm: float, all_thicknesses: list) -> tuple[str, float]:
    """Classify a wall by thickness using relative ranking + spec bands.

    Mamad ≥ exterior ≥ partition is the authoritative ordering. The mamad
    label is only granted when a wall is in the top decile AND substantially
    thicker than the population median — most apartments have at most one
    mamad, so percentile cuts alone over-classify.
    """
    if thickness_cm > MAX_WALL_THICKNESS_CM:
        return "unknown", 0.4

    if all_thicknesses and len(all_thicknesses) >= 4:
        arr = np.array(all_thicknesses)
        median = float(np.median(arr))
        mamad_cut = float(np.percentile(arr, MAMAD_TOP_PERCENTILE))
        # Mamad: top decile AND > median + delta AND ≥ absolute floor
        if (thickness_cm >= mamad_cut
                and thickness_cm >= median + MAMAD_MIN_DELTA_OVER_MEDIAN_CM
                and thickness_cm >= MAMAD_MIN_CM):
            return "mamad", 0.80
        # Exterior: above median, below mamad cut
        if thickness_cm >= median:
            return "exterior", 0.75
        # Below median → partition
        return "partition", 0.85

    # Population too small for relative ranking — use spec bands
    if thickness_cm >= MAMAD_MIN_CM:
        return "mamad", 0.60
    if thickness_cm > PARTITION_MAX_CM:
        return "exterior", 0.70
    return "partition", 0.80


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_centerline_walls(
    segments: list,
    scale_factor: float,
    histogram: Optional[dict] = None,
) -> tuple:
    """Collapse parallel line pairs into centerline walls.

    Args:
        segments: extracted PDF segments — each a dict with start, end,
            stroke_width, color, dash_pattern.
        scale_factor: metres per PDF point (e.g. 0.0176 at scale 1:50).
        histogram: optional output of compute_stroke_histogram for pre-filter.

    Returns:
        (walls, stats) where walls is list[CenterlineWall] and stats is a
        dict with raw_segments, wall_candidates, pairs_found, centerlines,
        single_line_walls.
    """
    stats = {
        "raw_segments": len(segments),
        "wall_candidates": 0,
        "pairs_found": 0,
        "centerlines": 0,
        "single_line_walls": 0,
    }

    # 1. Pre-filter
    if histogram and histogram.get("suggested_thresholds"):
        wall_thresh = histogram["suggested_thresholds"][0]
    else:
        wall_thresh = 0.5

    candidates = []
    for s in segments:
        if _seg_length(s) < MIN_SEGMENT_LENGTH_PT:
            continue
        dash = s.get("dash_pattern")
        if dash and str(dash) not in ("None", "[] 0", "()", "[] 0.0"):
            continue
        if s.get("stroke_width", 0) < wall_thresh:
            continue
        candidates.append(s)
    stats["pre_merge"] = len(candidates)

    if not candidates:
        return [], stats

    # 1b. Pre-merge fragments. Israeli PDFs break long walls into many
    # collinear pieces; without merging, each piece pairs separately and
    # produces dozens of "walls" for a single physical wall. We only call
    # snap → merge_collinear → remove_duplicates (NOT extend/split, which
    # would re-fragment).
    from geometry.healing import merge_collinear, remove_duplicates, snap_endpoints

    # Snap tolerance MUST be < MIN_WALL_THICKNESS in PDF points or parallel
    # wall faces collapse into each other. At scale 1:50, 6cm = 3.4pt, so we
    # cap snap at 3.0pt. Repeated merge passes catch more after snap aligns
    # endpoints.
    min_thick_pt = (MIN_WALL_THICKNESS_CM / 100.0) / scale_factor
    snap_tol = min(3.0, max(1.0, min_thick_pt * 0.7))
    candidates, _ = snap_endpoints(candidates, tolerance=snap_tol)
    for _ in range(3):
        before = len(candidates)
        candidates, _ = merge_collinear(candidates, angle_tol=3.0, dist_tol=4.0)
        if len(candidates) >= before:
            break
    candidates, _ = remove_duplicates(candidates)
    stats["wall_candidates"] = len(candidates)

    # 2. STRtree on LineStrings
    lines = [LineString([s["start"], s["end"]]) for s in candidates]
    tree = STRtree(lines)
    max_d_pt = (MAX_WALL_THICKNESS_CM / 100.0) / scale_factor
    min_d_pt = (MIN_WALL_THICKNESS_CM / 100.0) / scale_factor

    # 3. Find candidate pairs by proximity
    pair_records = []
    for i, line in enumerate(lines):
        seg_a = candidates[i]
        dir_a = _seg_dir(seg_a)
        buf = line.buffer(max_d_pt + 1.0)
        idxs = tree.query(buf)
        for j in idxs:
            j = int(j)
            if j <= i:
                continue
            seg_b = candidates[j]
            dir_b = _seg_dir(seg_b)
            if _angle_diff_deg(dir_a, dir_b) > MAX_PARALLEL_ANGLE_DEG:
                continue
            d_perp = _perp_distance(seg_a, seg_b, dir_a)
            if d_perp < min_d_pt or d_perp > max_d_pt:
                continue
            overlap = _projected_overlap_ratio(seg_a, seg_b, dir_a)
            if overlap < MIN_OVERLAP_RATIO:
                continue
            p1, p2, thickness_cm = _build_centerline(seg_a, seg_b, scale_factor)
            # Drop short pairs — real walls are ≥ MIN_WALL_LENGTH_CM (50cm).
            # Most rejections here are furniture (cabinets, fridges, vanities).
            length_cm = math.hypot(p2[0] - p1[0], p2[1] - p1[1]) * scale_factor * 100.0
            if length_cm < MIN_WALL_LENGTH_CM:
                continue
            pair_records.append((overlap, i, j, p1, p2, thickness_cm))

    stats["pairs_found"] = len(pair_records)

    # 4. Greedy selection — highest overlap first, each seg used once
    pair_records.sort(key=lambda r: -r[0])
    used: set = set()
    selected = []
    for rec in pair_records:
        _, i, j, _, _, _ = rec
        if i in used or j in used:
            continue
        used.add(i)
        used.add(j)
        selected.append(rec)

    # 5. Classify by thickness
    all_thicks = [r[5] for r in selected]
    walls = []
    for k, (_, i, j, p1, p2, thick_cm) in enumerate(selected):
        wall_type, conf = _classify_thickness(thick_cm, all_thicks)
        walls.append(CenterlineWall(
            id=f"cw_{k}",
            p1=p1, p2=p2,
            thickness_cm=thick_cm,
            wall_type=wall_type,
            confidence=conf * 100,
            source_segment_ids=[i, j],
        ))
    stats["centerlines"] = len(walls)

    # 6. Unpaired thick segments → single-line wall fallback (off by default).
    # Furniture outlines (cabinet edges, fridge boxes) overwhelm this signal
    # in real PDFs. Re-enable per-sample once we can distinguish wall stroke
    # from furniture stroke.
    if ENABLE_SINGLE_LINE_FALLBACK:
        fallback_pop = all_thicks if all_thicks else [SINGLE_LINE_THICKNESS_CM]
        min_single_length_pt = (MIN_WALL_LENGTH_CM / 100.0) / scale_factor
        for i, s in enumerate(candidates):
            if i in used:
                continue
            if s.get("stroke_width", 0) < wall_thresh * 1.5:
                continue
            if _seg_length(s) < min_single_length_pt:
                continue
            wall_type, conf = _classify_thickness(SINGLE_LINE_THICKNESS_CM, fallback_pop)
            walls.append(CenterlineWall(
                id=f"cw_s{i}",
                p1=s["start"], p2=s["end"],
                thickness_cm=SINGLE_LINE_THICKNESS_CM,
                wall_type=wall_type,
                confidence=conf * 50,
                source_segment_ids=[i],
            ))
            stats["single_line_walls"] += 1

    return walls, stats


# ---------------------------------------------------------------------------
# Diagnostic CLI: report wall counts on a few samples
# ---------------------------------------------------------------------------

def _diagnostic_run():
    from pathlib import Path

    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    samples = [
        ("Sample 2", "- Sample 2 vector pdf תכניות-מכר-דירתי-מגרש-130-בניינים-A-ו-B.pdf", 0),
        ("Sample 5", "- Sample 5 4-Rooms-Newer2.pdf", 0),
        ("Sample 9", "- Sample 9 vector sample.pdf", 0),
    ]
    from geometry.extraction import (
        compute_stroke_histogram, crop_legend, extract_metadata, extract_vectors,
    )

    print("\n=== Wall detection diagnostic (Step 1) ===\n")
    print(f"{'Sample':<12} {'raw':>6} {'cands':>6} {'pairs':>6} "
          f"{'walls':>6} {'single':>7}  thickness(cm)")
    for name, pdf_name, page in samples:
        pdf = PROJECT_ROOT / "docs" / "test-pdfs" / pdf_name
        if not pdf.exists():
            print(f"{name}: PDF missing")
            continue
        raw = extract_vectors(str(pdf), page_num=page)
        meta = extract_metadata(raw["texts"])
        cropped = crop_legend(raw)
        hist = compute_stroke_histogram(cropped["segments"])
        scale_value = meta.get("scale_value") or 50
        scale_factor = (0.0254 / 72) * scale_value
        walls, stats = find_centerline_walls(cropped["segments"], scale_factor, hist)
        ths = [w.thickness_cm for w in walls if len(w.source_segment_ids) == 2]
        rng = f"{min(ths):.1f}-{max(ths):.1f}" if ths else "n/a"
        from collections import Counter
        types = Counter(w.wall_type for w in walls)
        print(f"{name:<12} {stats['raw_segments']:>6} {stats['wall_candidates']:>6} "
              f"{stats['pairs_found']:>6} {stats['centerlines']:>6} "
              f"{stats['single_line_walls']:>7}  {rng}   {dict(types)}")


if __name__ == "__main__":
    _diagnostic_run()
