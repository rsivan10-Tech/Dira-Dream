"""
Geometry healing pipeline for Israeli residential floor plan segments.

Agent: VG (Vector/Geometry Specialist)
Phase 1, Sprint 2 — snap, merge, deduplicate, extend, split, validate.

Each function is independently testable, configurable, and produces statistics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import networkx as nx
import numpy as np
from scipy.spatial import KDTree
from shapely.geometry import LineString, Point


# ---------------------------------------------------------------------------
# Configuration (all tolerances configurable per VG rule #2)
# ---------------------------------------------------------------------------

@dataclass
class HealingConfig:
    """Configurable parameters for the healing pipeline."""
    snap_tolerance: float = 3.0          # PDF points
    collinear_angle: float = 2.0         # degrees
    collinear_distance: float = 2.0      # PDF points
    overlap_threshold: float = 0.9       # fraction
    extend_tolerance: float = 10.0       # PDF points
    door_width_min: float = 60.0         # cm
    door_width_max: float = 120.0        # cm
    scale_factor: float = 1.0            # PDF pts → cm conversion


DEFAULT_CONFIG = HealingConfig()

# Dash patterns that indicate dimension / annotation lines
_DASHED_PATTERNS = {"[]", "[] 0", ""}  # empty string is NOT dashed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seg_length(seg: dict) -> float:
    """Euclidean length of a segment."""
    (x1, y1), (x2, y2) = seg["start"], seg["end"]
    return math.hypot(x2 - x1, y2 - y1)


def _angle_between(seg_a: dict, seg_b: dict) -> float:
    """
    Angle in degrees between two segments' direction vectors.
    Returns value in [0, 180].
    """
    dx1 = seg_a["end"][0] - seg_a["start"][0]
    dy1 = seg_a["end"][1] - seg_a["start"][1]
    dx2 = seg_b["end"][0] - seg_b["start"][0]
    dy2 = seg_b["end"][1] - seg_b["start"][1]

    len1 = math.hypot(dx1, dy1)
    len2 = math.hypot(dx2, dy2)
    if len1 < 1e-9 or len2 < 1e-9:
        return 180.0  # degenerate

    dot = dx1 * dx2 + dy1 * dy2
    cos_val = max(-1.0, min(1.0, dot / (len1 * len2)))
    angle = math.degrees(math.acos(cos_val))
    return angle


def _point_key(pt: tuple, decimals: int = 4) -> tuple:
    """Round a point for use as a dict key."""
    return (round(pt[0], decimals), round(pt[1], decimals))


def _copy_seg(seg: dict, start: tuple, end: tuple) -> dict:
    """Create a copy of seg with new start/end, preserving metadata."""
    return {
        "start": start,
        "end": end,
        "stroke_width": seg["stroke_width"],
        "color": seg.get("color", (0.0, 0.0, 0.0)),
        "dash_pattern": seg.get("dash_pattern", ""),
    }


# ---------------------------------------------------------------------------
# PRE-FILTER: remove non-wall segments before healing
# ---------------------------------------------------------------------------

def filter_non_wall_segments(
    segments: list[dict],
    histogram_peaks: Optional[list[float]] = None,
    suggested_thresholds: Optional[list[float]] = None,
) -> tuple[list[dict], dict]:
    """
    Filter out dimension lines, grid lines, and furniture before healing.

    Classification strategy (relative, per VG rule — never absolute thresholds):
    - Dashed/dotted segments → DIMENSION_LINE (always removed)
    - ≥4 histogram peaks: below threshold[1] → non-wall (dimension + furniture)
    - 3 peaks: below threshold[0] → DIMENSION_LINE only
    - <3 peaks: no width-based filter (insufficient data)

    Args:
        segments: all extracted segments
        histogram_peaks: stroke-width peaks from compute_stroke_histogram
        suggested_thresholds: midpoints between peaks

    Returns:
        (wall_segments, report)
    """
    if not segments:
        return [], {"original": 0, "kept": 0, "removed_dashed": 0,
                    "removed_thin": 0, "wall_threshold": None}

    original = len(segments)

    # Step 1: Remove dashed/dotted segments (dimension lines, regardless of width)
    non_dashed = []
    removed_dashed = 0
    for seg in segments:
        dash = seg.get("dash_pattern", "")
        # Non-dashed: empty string or "[] 0" (solid line encoding varies)
        if dash and dash != "[] 0":
            removed_dashed += 1
        else:
            non_dashed.append(seg)

    # Step 2: Width-based filter using histogram thresholds
    wall_threshold = None
    if suggested_thresholds:
        if len(suggested_thresholds) >= 2:
            # ≥4 peaks → threshold[1] separates furniture from walls
            wall_threshold = suggested_thresholds[1]
        elif len(suggested_thresholds) >= 1:
            # 3 peaks → threshold[0] separates dimension from rest
            wall_threshold = suggested_thresholds[0]

    removed_thin = 0
    if wall_threshold is not None:
        kept = []
        for seg in non_dashed:
            if seg["stroke_width"] < wall_threshold:
                removed_thin += 1
            else:
                kept.append(seg)
        result = kept
    else:
        result = non_dashed

    return result, {
        "original": original,
        "kept": len(result),
        "removed_dashed": removed_dashed,
        "removed_thin": removed_thin,
        "wall_threshold": wall_threshold,
    }


# ---------------------------------------------------------------------------
# FUNCTION 1: snap_endpoints
# ---------------------------------------------------------------------------

def snap_endpoints(
    segments: list[dict],
    tolerance: Optional[float] = None,
    auto_tune: bool = False,
    histogram_peaks: Optional[list[float]] = None,
) -> tuple[list[dict], dict]:
    """
    Merge nearby endpoints into single averaged points.

    Uses KDTree + Union-Find for O(n log n) clustering.

    Args:
        segments: list of segment dicts
        tolerance: snap radius in PDF points (default 3.0)
        auto_tune: if True and tolerance is None, compute tolerance as
                   50% of minimum detected wall thickness
        histogram_peaks: stroke-width peaks for auto-tune

    Returns:
        (healed_segments, report)
    """
    if tolerance is None:
        if auto_tune and histogram_peaks and len(histogram_peaks) >= 1:
            tolerance = histogram_peaks[0] * 0.5
        else:
            tolerance = DEFAULT_CONFIG.snap_tolerance

    if not segments:
        return [], {
            "clusters_found": 0, "points_merged": 0,
            "tolerance_used": tolerance, "avg_cluster_size": 0.0,
        }

    # 1. Collect all endpoints
    points = []
    point_indices = []  # (seg_idx, 'start'|'end')
    for i, seg in enumerate(segments):
        points.append(seg["start"])
        point_indices.append((i, "start"))
        points.append(seg["end"])
        point_indices.append((i, "end"))

    coords = np.array(points)

    # 2. Build KDTree
    tree = KDTree(coords)

    # 3. Find neighbor pairs within tolerance
    pairs = tree.query_pairs(tolerance)

    # 4. Union-Find to build clusters
    parent = list(range(len(points)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for a, b in pairs:
        union(a, b)

    # 5. Build clusters and compute centroids
    clusters: dict[int, list[int]] = {}
    for i in range(len(points)):
        root = find(i)
        clusters.setdefault(root, []).append(i)

    centroid_map: dict[int, tuple[float, float]] = {}
    total_merged = 0
    for root, members in clusters.items():
        cx = float(np.mean([coords[m][0] for m in members]))
        cy = float(np.mean([coords[m][1] for m in members]))
        centroid_map[root] = (cx, cy)
        if len(members) > 1:
            total_merged += len(members)

    multi_clusters = sum(1 for m in clusters.values() if len(m) > 1)
    avg_size = (
        np.mean([len(m) for m in clusters.values() if len(m) > 1])
        if multi_clusters > 0 else 0.0
    )

    # 6. Update segments
    result = []
    for i, seg in enumerate(segments):
        start_idx = i * 2
        end_idx = i * 2 + 1
        new_start = centroid_map[find(start_idx)]
        new_end = centroid_map[find(end_idx)]

        # Skip zero-length segments created by snapping
        if math.hypot(new_end[0] - new_start[0],
                      new_end[1] - new_start[1]) < 1e-6:
            continue

        result.append(_copy_seg(seg, new_start, new_end))

    report = {
        "clusters_found": multi_clusters,
        "points_merged": total_merged,
        "tolerance_used": tolerance,
        "avg_cluster_size": float(avg_size),
    }
    return result, report


# ---------------------------------------------------------------------------
# FUNCTION 2: merge_collinear
# ---------------------------------------------------------------------------

def merge_collinear(
    segments: list[dict],
    angle_tol: float = 2.0,
    dist_tol: float = 2.0,
) -> tuple[list[dict], dict]:
    """
    Merge collinear fragments of the same wall into single segments.

    Iterates until no more merges occur. Preserves segments of different
    widths even if collinear (different wall types).

    Args:
        segments: list of segment dicts
        angle_tol: max angle deviation in degrees
        dist_tol: max perpendicular distance in PDF points

    Returns:
        (merged_segments, report)
    """
    if not segments:
        return [], {"merges_performed": 0, "passes_needed": 0}

    total_merges = 0
    passes = 0
    current = list(segments)

    while True:
        passes += 1
        merged_any = False

        # Build endpoint -> segment index lookup
        ep_map: dict[tuple, list[int]] = {}
        for i, seg in enumerate(current):
            for pt in (seg["start"], seg["end"]):
                key = _point_key(pt)
                ep_map.setdefault(key, []).append(i)

        used = set()
        result = []

        for i, seg_a in enumerate(current):
            if i in used:
                continue

            # Find segments sharing an endpoint with seg_a
            neighbors = set()
            for pt in (seg_a["start"], seg_a["end"]):
                key = _point_key(pt)
                for j in ep_map.get(key, []):
                    if j != i and j not in used:
                        neighbors.add(j)

            merged = False
            for j in neighbors:
                seg_b = current[j]

                # Different widths → don't merge (different wall types)
                width_ratio = (
                    min(seg_a["stroke_width"], seg_b["stroke_width"])
                    / max(seg_a["stroke_width"], seg_b["stroke_width"])
                    if max(seg_a["stroke_width"], seg_b["stroke_width"]) > 1e-9
                    else 1.0
                )
                if width_ratio < 0.7:
                    continue

                # Check angle
                angle = _angle_between(seg_a, seg_b)
                # Collinear means angle near 0° or near 180°
                if angle > angle_tol and (180.0 - angle) > angle_tol:
                    continue

                # Check perpendicular distance between lines
                perp_dist = _perpendicular_distance(seg_a, seg_b)
                if perp_dist > dist_tol:
                    continue

                # Merge: find the farthest endpoints
                pts_a = [seg_a["start"], seg_a["end"]]
                pts_b = [seg_b["start"], seg_b["end"]]
                all_pts = pts_a + pts_b

                # Direction vector from seg_a
                dx = seg_a["end"][0] - seg_a["start"][0]
                dy = seg_a["end"][1] - seg_a["start"][1]
                length = math.hypot(dx, dy)
                if length < 1e-9:
                    continue
                ux, uy = dx / length, dy / length

                # Project all points onto the direction axis
                projections = [
                    (p[0] * ux + p[1] * uy, p) for p in all_pts
                ]
                projections.sort(key=lambda x: x[0])

                new_start = projections[0][1]
                new_end = projections[-1][1]
                new_width = max(seg_a["stroke_width"], seg_b["stroke_width"])

                merged_seg = _copy_seg(seg_a, new_start, new_end)
                merged_seg["stroke_width"] = new_width

                result.append(merged_seg)
                used.add(i)
                used.add(j)
                merged = True
                merged_any = True
                total_merges += 1
                break

            if not merged and i not in used:
                result.append(seg_a)
                used.add(i)

        # Add any remaining segments
        for i, seg in enumerate(current):
            if i not in used:
                result.append(seg)

        current = result

        if not merged_any:
            break

    return current, {"merges_performed": total_merges, "passes_needed": passes}


def _perpendicular_distance(seg_a: dict, seg_b: dict) -> float:
    """
    Compute the perpendicular distance between two line segments' infinite lines.
    Uses the midpoint of seg_b projected onto the line of seg_a.
    """
    ax, ay = seg_a["start"]
    bx, by = seg_a["end"]
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return float("inf")

    # Midpoint of seg_b
    mx = (seg_b["start"][0] + seg_b["end"][0]) / 2
    my = (seg_b["start"][1] + seg_b["end"][1]) / 2

    # Signed distance from midpoint to line of seg_a
    dist = abs(dy * mx - dx * my + bx * ay - by * ax) / length
    return dist


# ---------------------------------------------------------------------------
# FUNCTION 3: remove_duplicates
# ---------------------------------------------------------------------------

def remove_duplicates(
    segments: list[dict],
    overlap_threshold: float = 0.9,
) -> tuple[list[dict], dict]:
    """
    Remove overlapping duplicate segments.

    For each pair with high overlap ratio, keeps the one with greater
    stroke width (more structural information).

    Args:
        segments: list of segment dicts
        overlap_threshold: min overlap fraction to consider duplicate

    Returns:
        (deduplicated_segments, report)
    """
    if not segments:
        return [], {"duplicates_removed": 0}

    n = len(segments)
    removed = set()

    # Precompute directions and lengths
    seg_info = []
    for seg in segments:
        dx = seg["end"][0] - seg["start"][0]
        dy = seg["end"][1] - seg["start"][1]
        length = math.hypot(dx, dy)
        seg_info.append((dx, dy, length))

    for i in range(n):
        if i in removed:
            continue
        for j in range(i + 1, n):
            if j in removed:
                continue

            # Quick angle check — must be nearly parallel
            angle = _angle_between(segments[i], segments[j])
            if angle > 5.0 and (180.0 - angle) > 5.0:
                continue

            # Check perpendicular distance (must be very close)
            perp = _perpendicular_distance(segments[i], segments[j])
            if perp > 2.0:
                continue

            # Compute overlap ratio via projection
            overlap = _overlap_ratio(segments[i], segments[j])
            if overlap >= overlap_threshold:
                # Remove the shorter / thinner one
                if segments[i]["stroke_width"] >= segments[j]["stroke_width"]:
                    removed.add(j)
                else:
                    removed.add(i)
                    break  # i is removed, move to next i

    result = [seg for i, seg in enumerate(segments) if i not in removed]
    return result, {"duplicates_removed": len(removed)}


def _overlap_ratio(seg_a: dict, seg_b: dict) -> float:
    """
    Compute overlap ratio between two nearly-parallel segments.
    Projects both onto a common axis and computes overlap / min_length.
    """
    # Use seg_a's direction as projection axis
    dx = seg_a["end"][0] - seg_a["start"][0]
    dy = seg_a["end"][1] - seg_a["start"][1]
    length_a = math.hypot(dx, dy)
    if length_a < 1e-9:
        return 0.0

    ux, uy = dx / length_a, dy / length_a

    # Project all 4 endpoints
    proj_a_start = seg_a["start"][0] * ux + seg_a["start"][1] * uy
    proj_a_end = seg_a["end"][0] * ux + seg_a["end"][1] * uy
    proj_b_start = seg_b["start"][0] * ux + seg_b["start"][1] * uy
    proj_b_end = seg_b["end"][0] * ux + seg_b["end"][1] * uy

    a_min, a_max = min(proj_a_start, proj_a_end), max(proj_a_start, proj_a_end)
    b_min, b_max = min(proj_b_start, proj_b_end), max(proj_b_start, proj_b_end)

    overlap_start = max(a_min, b_min)
    overlap_end = min(a_max, b_max)

    if overlap_end <= overlap_start:
        return 0.0

    overlap_len = overlap_end - overlap_start
    min_len = min(a_max - a_min, b_max - b_min)
    if min_len < 1e-9:
        return 0.0

    return overlap_len / min_len


# ---------------------------------------------------------------------------
# FUNCTION 4: extend_to_intersect
# ---------------------------------------------------------------------------

def extend_to_intersect(
    segments: list[dict],
    tolerance: float = 10.0,
    door_width_min_cm: float = 60.0,
    door_width_max_cm: float = 120.0,
    scale_factor: float = 1.0,
    arc_segments: Optional[list[dict]] = None,
) -> tuple[list[dict], dict]:
    """
    Extend dangling endpoints to close L-corners and T-junctions.

    Does NOT extend across door openings (60-120cm gaps with nearby arcs).

    Args:
        segments: list of segment dicts
        tolerance: max extension distance in PDF points
        door_width_min_cm: min door width in cm
        door_width_max_cm: max door width in cm
        scale_factor: PDF points to cm conversion
        arc_segments: curved segments (from Bézier) for door detection

    Returns:
        (extended_segments, report)
    """
    if not segments:
        return [], {"extensions_made": 0, "doors_preserved": 0}

    # Convert door widths to PDF points
    if scale_factor > 0:
        door_min_pt = door_width_min_cm / scale_factor if scale_factor > 1e-9 else 0
        door_max_pt = door_width_max_cm / scale_factor if scale_factor > 1e-9 else float("inf")
    else:
        door_min_pt = 0
        door_max_pt = float("inf")

    # Build endpoint connectivity: count how many segments share each endpoint
    ep_count: dict[tuple, int] = {}
    for seg in segments:
        for pt in (seg["start"], seg["end"]):
            key = _point_key(pt)
            ep_count[key] = ep_count.get(key, 0) + 1

    # Identify dangling endpoints (degree 1)
    dangling: set[tuple] = {k for k, v in ep_count.items() if v == 1}

    # Build arc midpoints for door detection
    arc_pts = []
    if arc_segments:
        for arc in arc_segments:
            mx = (arc["start"][0] + arc["end"][0]) / 2
            my = (arc["start"][1] + arc["end"][1]) / 2
            arc_pts.append((mx, my))
    arc_tree = KDTree(np.array(arc_pts)) if arc_pts else None

    extensions_made = 0
    doors_preserved = 0
    result = list(segments)  # work on a copy

    for i, seg in enumerate(result):
        for which in ("start", "end"):
            pt = seg[which]
            key = _point_key(pt)
            if key not in dangling:
                continue

            # Direction to extend: outward from the dangling end
            if which == "end":
                dx = seg["end"][0] - seg["start"][0]
                dy = seg["end"][1] - seg["start"][1]
            else:
                dx = seg["start"][0] - seg["end"][0]
                dy = seg["start"][1] - seg["end"][1]

            length = math.hypot(dx, dy)
            if length < 1e-9:
                continue
            ux, uy = dx / length, dy / length

            # Extended endpoint
            ext_pt = (pt[0] + ux * tolerance, pt[1] + uy * tolerance)

            # Build extended line and check intersection with all other segments
            ext_line = LineString([pt, ext_pt])
            best_dist = float("inf")
            best_pt = None
            best_j = -1

            for j, other in enumerate(result):
                if j == i:
                    continue
                other_line = LineString([other["start"], other["end"]])
                ix = ext_line.intersection(other_line)
                if ix.is_empty or not isinstance(ix, Point):
                    continue

                dist = math.hypot(ix.x - pt[0], ix.y - pt[1])
                if dist < best_dist and dist > 1e-6:
                    best_dist = dist
                    best_pt = (ix.x, ix.y)
                    best_j = j

            if best_pt is None:
                continue

            # Door check: is the gap door-sized with a nearby arc?
            gap_cm = best_dist * scale_factor
            if door_min_pt <= best_dist <= door_max_pt or (
                scale_factor > 1e-9 and door_width_min_cm <= gap_cm <= door_width_max_cm
            ):
                if arc_tree is not None:
                    mid = ((pt[0] + best_pt[0]) / 2, (pt[1] + best_pt[1]) / 2)
                    arc_dist, _ = arc_tree.query(mid)
                    if arc_dist < tolerance * 3:
                        doors_preserved += 1
                        continue

            # Extend the segment to the intersection point
            if which == "end":
                result[i] = _copy_seg(seg, seg["start"], best_pt)
            else:
                result[i] = _copy_seg(seg, best_pt, seg["end"])
            extensions_made += 1

    return result, {"extensions_made": extensions_made, "doors_preserved": doors_preserved}


# ---------------------------------------------------------------------------
# FUNCTION 5: split_at_intersections
# ---------------------------------------------------------------------------

def split_at_intersections(
    segments: list[dict],
) -> tuple[list[dict], dict]:
    """
    Split segments at all interior crossing points to create proper graph nodes.

    For each pair of segments that cross (not at endpoints), splits both
    at the intersection point.

    Returns:
        (split_segments, report)
    """
    if not segments:
        return [], {"intersections_found": 0, "splits_made": 0}

    intersections_found = 0
    # Map: seg_index -> list of split parameter t values
    split_points: dict[int, list[tuple[float, float]]] = {
        i: [] for i in range(len(segments))
    }

    for i in range(len(segments)):
        line_i = LineString([segments[i]["start"], segments[i]["end"]])
        for j in range(i + 1, len(segments)):
            line_j = LineString([segments[j]["start"], segments[j]["end"]])

            ix = line_i.intersection(line_j)
            if ix.is_empty or not isinstance(ix, Point):
                continue

            ip = (ix.x, ix.y)

            # Skip if intersection is at an existing endpoint of both segments
            eps_i = {_point_key(segments[i]["start"]), _point_key(segments[i]["end"])}
            eps_j = {_point_key(segments[j]["start"]), _point_key(segments[j]["end"])}
            ip_key = _point_key(ip)

            if ip_key in eps_i and ip_key in eps_j:
                continue

            intersections_found += 1

            if ip_key not in eps_i:
                split_points[i].append(ip)
            if ip_key not in eps_j:
                split_points[j].append(ip)

    # Perform splits
    result = []
    splits_made = 0

    for i, seg in enumerate(segments):
        pts = split_points[i]
        if not pts:
            result.append(seg)
            continue

        # Sort split points along the segment direction
        sx, sy = seg["start"]
        ex, ey = seg["end"]
        dx, dy = ex - sx, ey - sy
        length = math.hypot(dx, dy)
        if length < 1e-9:
            result.append(seg)
            continue

        ux, uy = dx / length, dy / length

        # Compute t parameter for each split point
        t_pts = []
        for p in pts:
            t = ((p[0] - sx) * ux + (p[1] - sy) * uy) / length
            if 0.001 < t < 0.999:  # skip near-endpoint splits
                t_pts.append((t, p))

        if not t_pts:
            result.append(seg)
            continue

        t_pts.sort(key=lambda x: x[0])

        # Create sub-segments
        chain = [seg["start"]] + [p for _, p in t_pts] + [seg["end"]]
        for k in range(len(chain) - 1):
            sub = _copy_seg(seg, chain[k], chain[k + 1])
            sub_len = math.hypot(
                chain[k + 1][0] - chain[k][0],
                chain[k + 1][1] - chain[k][1],
            )
            if sub_len > 1e-6:
                result.append(sub)
                splits_made += 1

        # We created splits_made sub-segments but the original was 1,
        # so net splits = sub_segments - 1 (already counted above, adjust later)

    # Adjust: splits_made counts sub-segments; actual splits = sub_segs - original_segs
    net_splits = len(result) - len(segments)

    return result, {
        "intersections_found": intersections_found,
        "splits_made": max(0, net_splits),
    }


# ---------------------------------------------------------------------------
# FUNCTION 6: validate_healed
# ---------------------------------------------------------------------------

def validate_healed(segments: list[dict]) -> dict:
    """
    Validate healing quality by building a temporary graph.

    Reports orphans (degree 0), dead ends (degree 1), connected components,
    and degree distribution.

    Returns:
        report dict with validation metrics
    """
    if not segments:
        return {
            "total_segments": 0, "orphan_count": 0, "dead_end_count": 0,
            "degree_distribution": {}, "connected_components": 0,
            "largest_component_ratio": 0.0,
        }

    G = nx.Graph()
    for seg in segments:
        p1 = _point_key(seg["start"])
        p2 = _point_key(seg["end"])
        G.add_edge(p1, p2, width=seg["stroke_width"])

    # Degree analysis
    degrees = dict(G.degree())
    dead_end_count = sum(1 for d in degrees.values() if d == 1)

    degree_dist: dict[int, int] = {}
    for d in degrees.values():
        degree_dist[d] = degree_dist.get(d, 0) + 1

    # Connected components
    components = list(nx.connected_components(G))
    num_components = len(components)
    largest_ratio = (
        max(len(c) for c in components) / len(G.nodes())
        if G.nodes() else 0.0
    )

    # Orphans: segments whose both endpoints have degree 1 and are in a
    # component of size 2 (just one edge)
    orphan_count = 0
    small_components = [c for c in components if len(c) <= 2]
    for comp in small_components:
        subgraph = G.subgraph(comp)
        if subgraph.number_of_edges() == 1:
            nodes = list(comp)
            if all(G.degree(n) == 1 for n in nodes):
                orphan_count += 1

    return {
        "total_segments": len(segments),
        "orphan_count": orphan_count,
        "dead_end_count": dead_end_count,
        "degree_distribution": degree_dist,
        "connected_components": num_components,
        "largest_component_ratio": round(largest_ratio, 4),
    }


def filter_largest_component(segments: list[dict]) -> list[dict]:
    """
    Keep only segments that belong to the largest connected component.

    The apartment is the largest connected component in the healed graph.
    Legend elements, neighbor outlines, and disconnected fragments are in
    smaller components and get discarded.
    """
    if len(segments) <= 1:
        return segments

    import logging
    logger = logging.getLogger(__name__)

    G = nx.Graph()
    for seg in segments:
        p1 = _point_key(seg["start"])
        p2 = _point_key(seg["end"])
        if p1 != p2:
            G.add_edge(p1, p2)

    if G.number_of_nodes() == 0:
        return segments

    components = list(nx.connected_components(G))
    if len(components) <= 1:
        return segments

    largest = max(components, key=len)

    kept = []
    removed = 0
    for seg in segments:
        p1 = _point_key(seg["start"])
        p2 = _point_key(seg["end"])
        if p1 in largest or p2 in largest:
            kept.append(seg)
        else:
            removed += 1

    logger.info(
        "filter_largest_component: %d components, kept %d segments "
        "(largest component), removed %d",
        len(components), len(kept), removed,
    )
    return kept


# ---------------------------------------------------------------------------
# POST-HEAL: second-pass gap fill for remaining dead ends
# ---------------------------------------------------------------------------

def _second_pass_gap_fill(
    segments: list[dict],
    tolerance: float,
) -> tuple[list[dict], dict]:
    """
    Re-snap only degree-1 (dead-end) nodes at an expanded tolerance.

    After the main pipeline, some near-miss endpoints remain because they
    were beyond the original snap tolerance. This pass targets only those
    dangling endpoints with 1.5x the original tolerance.

    Args:
        segments: healed segments (post-split)
        tolerance: the ORIGINAL snap tolerance (will be multiplied by 1.5)

    Returns:
        (segments, report)
    """
    if not segments:
        return [], {"dead_ends_snapped": 0, "tolerance_used": tolerance * 1.5}

    expanded_tol = tolerance * 1.5

    # Build graph to find degree-1 nodes
    ep_count: dict[tuple, list[tuple[int, str]]] = {}
    for i, seg in enumerate(segments):
        for which in ("start", "end"):
            key = _point_key(seg[which])
            ep_count.setdefault(key, []).append((i, which))

    degree: dict[tuple, int] = {}
    for key, entries in ep_count.items():
        degree[key] = len(entries)

    # Collect only degree-1 endpoint coordinates
    dangling_keys = [k for k, d in degree.items() if d == 1]
    if len(dangling_keys) < 2:
        return segments, {"dead_ends_snapped": 0, "tolerance_used": expanded_tol}

    dangling_coords = np.array(dangling_keys)
    tree = KDTree(dangling_coords)
    pairs = tree.query_pairs(expanded_tol)

    if not pairs:
        return segments, {"dead_ends_snapped": 0, "tolerance_used": expanded_tol}

    # Union-Find over dangling points only
    parent = list(range(len(dangling_keys)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for a, b in pairs:
        union(a, b)

    # Build clusters and compute centroids
    clusters: dict[int, list[int]] = {}
    for i in range(len(dangling_keys)):
        root = find(i)
        clusters.setdefault(root, []).append(i)

    # Map: dangling key → new centroid
    remap: dict[tuple, tuple[float, float]] = {}
    dead_ends_snapped = 0
    for root, members in clusters.items():
        if len(members) < 2:
            continue
        cx = float(np.mean([dangling_coords[m][0] for m in members]))
        cy = float(np.mean([dangling_coords[m][1] for m in members]))
        centroid = (cx, cy)
        for m in members:
            remap[dangling_keys[m]] = centroid
        dead_ends_snapped += len(members)

    if not remap:
        return segments, {"dead_ends_snapped": 0, "tolerance_used": expanded_tol}

    # Apply remapping to segments
    result = []
    for seg in segments:
        s_key = _point_key(seg["start"])
        e_key = _point_key(seg["end"])
        new_start = remap.get(s_key, seg["start"])
        new_end = remap.get(e_key, seg["end"])

        # Skip zero-length segments
        if math.hypot(new_end[0] - new_start[0],
                      new_end[1] - new_start[1]) < 1e-6:
            continue

        result.append(_copy_seg(seg, new_start, new_end))

    return result, {
        "dead_ends_snapped": dead_ends_snapped,
        "tolerance_used": expanded_tol,
    }


# ---------------------------------------------------------------------------
# POST-HEAL: reconnect disconnected components via bridge segments
# ---------------------------------------------------------------------------

def reconnect_components(
    segments: list[dict],
    tolerance: float = 6.0,
    max_bridges: int = 200,
) -> tuple[list[dict], dict]:
    """
    Bridge disconnected graph components by connecting nearby dead-end nodes.

    After healing, the wall graph may split into many disconnected components
    (e.g. 41 components on Sample 0). This step finds degree-1 (dead-end)
    nodes in the largest component and searches for the nearest node in ANY
    other component within `tolerance`. If found, a bridge segment is created
    to merge the components.

    The process iterates: after each round of bridging, components are
    recomputed and the next round targets the updated largest component.

    Parameters
    ----------
    segments : list[dict]
        Healed wall segments.
    tolerance : float
        Maximum distance (PDF points) to bridge between components.
        Default 6.0 = 2× SNAP_TOLERANCE.
    max_bridges : int
        Safety limit on total bridge segments created.

    Returns
    -------
    segments : list[dict]
        Segments with bridge segments appended.
    report : dict
        Statistics: bridges_created, components_before, components_after,
        largest_component_ratio_before, largest_component_ratio_after.
    """
    if not segments:
        return [], {
            "bridges_created": 0,
            "components_before": 0, "components_after": 0,
            "largest_component_ratio_before": 0.0,
            "largest_component_ratio_after": 0.0,
        }

    # Build initial graph
    G = nx.Graph()
    for seg in segments:
        p1 = _point_key(seg["start"])
        p2 = _point_key(seg["end"])
        if p1 != p2:
            G.add_edge(p1, p2, width=seg.get("stroke_width", 0.0))

    components_before = nx.number_connected_components(G)
    if components_before <= 1:
        ratio = 1.0 if G.number_of_nodes() > 0 else 0.0
        return segments, {
            "bridges_created": 0,
            "components_before": 1, "components_after": 1,
            "largest_component_ratio_before": ratio,
            "largest_component_ratio_after": ratio,
        }

    largest_before = max(len(c) for c in nx.connected_components(G)) / len(G.nodes())

    # Compute median stroke width for bridge segments
    widths = [s.get("stroke_width", 0.0) for s in segments if s.get("stroke_width", 0.0) > 0]
    median_width = sorted(widths)[len(widths) // 2] if widths else 1.0

    bridges_created = 0
    new_segments = list(segments)

    # Iterate: each round may merge multiple components
    for _round in range(10):  # max 10 rounds
        # Rebuild graph with current segments
        G = nx.Graph()
        for seg in new_segments:
            p1 = _point_key(seg["start"])
            p2 = _point_key(seg["end"])
            if p1 != p2:
                G.add_edge(p1, p2, width=seg.get("stroke_width", 0.0))

        components = list(nx.connected_components(G))
        if len(components) <= 1:
            break

        # Identify the largest component
        largest_comp = max(components, key=len)
        other_comps = [c for c in components if c is not largest_comp]

        # Collect all nodes in the largest component
        largest_nodes = list(largest_comp)
        largest_coords = np.array(largest_nodes)
        largest_tree = KDTree(largest_coords)

        # Collect all nodes in other components
        other_nodes = []
        other_comp_id = {}  # node -> component index
        for ci, comp in enumerate(other_comps):
            for node in comp:
                other_nodes.append(node)
                other_comp_id[node] = ci

        if not other_nodes:
            break

        other_coords = np.array(other_nodes)

        # For each node in other components, find nearest in largest
        distances, indices = largest_tree.query(other_coords)

        # Build candidate bridges: (distance, other_node, largest_node)
        candidates = []
        for i, (dist, idx) in enumerate(zip(distances, indices)):
            if dist <= tolerance:
                candidates.append((dist, other_nodes[i], largest_nodes[idx]))

        # Sort by distance (closest first)
        candidates.sort(key=lambda x: x[0])

        # Bridge one node per other-component (the closest candidate)
        bridged_comps: set[int] = set()
        round_bridges = 0

        for dist, other_node, largest_node in candidates:
            if bridges_created >= max_bridges:
                break

            comp_id = other_comp_id[other_node]
            if comp_id in bridged_comps:
                continue

            # Create bridge segment
            bridge = {
                "start": other_node,
                "end": largest_node,
                "stroke_width": median_width,
                "color": (0.0, 0.0, 0.0),
                "dash_pattern": "",
            }
            new_segments.append(bridge)
            bridges_created += 1
            round_bridges += 1
            bridged_comps.add(comp_id)

        if round_bridges == 0:
            break  # No more bridges possible within tolerance

    # Final validation
    G_final = nx.Graph()
    for seg in new_segments:
        p1 = _point_key(seg["start"])
        p2 = _point_key(seg["end"])
        if p1 != p2:
            G_final.add_edge(p1, p2)

    components_after = nx.number_connected_components(G_final)
    largest_after = (
        max(len(c) for c in nx.connected_components(G_final)) / len(G_final.nodes())
        if G_final.number_of_nodes() > 0 else 0.0
    )

    report = {
        "bridges_created": bridges_created,
        "components_before": components_before,
        "components_after": components_after,
        "largest_component_ratio_before": round(largest_before, 4),
        "largest_component_ratio_after": round(largest_after, 4),
    }

    return new_segments, report


# ---------------------------------------------------------------------------
# FUNCTION 7: heal_geometry (pipeline)
# ---------------------------------------------------------------------------

def heal_geometry(
    segments: list[dict],
    config: Optional[HealingConfig] = None,
    arc_segments: Optional[list[dict]] = None,
    histogram_peaks: Optional[list[float]] = None,
    suggested_thresholds: Optional[list[float]] = None,
) -> tuple[list[dict], dict]:
    """
    Run the full healing pipeline.

    Steps:
      0. filter_non_wall_segments (pre-filter dimension/grid/furniture)
      1. snap_endpoints
      2. merge_collinear
      3. remove_duplicates
      4. extend_to_intersect
      5. split_at_intersections
      6. second_pass_gap_fill (re-snap dead ends at 1.5x tolerance)
      7. validate_healed

    Args:
        segments: raw segment dicts from extraction
        config: healing parameters (uses DEFAULT_CONFIG if None)
        arc_segments: curved segments for door detection
        histogram_peaks: stroke width peaks for auto-tune
        suggested_thresholds: midpoints between histogram peaks for filtering

    Returns:
        (healed_segments, full_report)
    """
    if config is None:
        config = DEFAULT_CONFIG

    full_report: dict = {"segments_before": len(segments)}

    # Step 0: Pre-filter non-wall segments
    segs, filter_report = filter_non_wall_segments(
        segments,
        histogram_peaks=histogram_peaks,
        suggested_thresholds=suggested_thresholds,
    )
    full_report["filter"] = filter_report

    # Step 1: Snap endpoints
    segs, snap_report = snap_endpoints(
        segs,
        tolerance=config.snap_tolerance,
        histogram_peaks=histogram_peaks,
    )
    full_report["snap"] = snap_report

    # Step 2: Merge collinear
    segs, merge_report = merge_collinear(
        segs,
        angle_tol=config.collinear_angle,
        dist_tol=config.collinear_distance,
    )
    full_report["merge_collinear"] = merge_report

    # Step 3: Remove duplicates
    segs, dup_report = remove_duplicates(
        segs,
        overlap_threshold=config.overlap_threshold,
    )
    full_report["remove_duplicates"] = dup_report

    # Step 4: Extend to intersect
    segs, ext_report = extend_to_intersect(
        segs,
        tolerance=config.extend_tolerance,
        door_width_min_cm=config.door_width_min,
        door_width_max_cm=config.door_width_max,
        scale_factor=config.scale_factor,
        arc_segments=arc_segments,
    )
    full_report["extend_to_intersect"] = ext_report

    # Step 5: Split at intersections
    segs, split_report = split_at_intersections(segs)
    full_report["split_at_intersections"] = split_report

    # Step 6: Second-pass gap fill (re-snap dead ends at 1.5x tolerance)
    segs, gap_report = _second_pass_gap_fill(segs, config.snap_tolerance)
    full_report["gap_fill"] = gap_report

    # Step 7: Reconnect disconnected components (bridge nearby fragments)
    # Use 5× snap tolerance — real Israeli PDFs have 8-20pt gaps between
    # wall fragments after pre-filter removes connecting non-wall segments.
    segs, reconnect_report = reconnect_components(
        segs, tolerance=config.snap_tolerance * 5,
    )
    full_report["reconnect"] = reconnect_report

    # Step 8: Validate
    validation = validate_healed(segs)
    full_report["validation"] = validation

    full_report["segments_after"] = len(segs)

    return segs, full_report
