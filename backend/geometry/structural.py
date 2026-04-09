"""
Structural wall classification, mamad detection, and door/window detection.

Agent: VG (Vector/Geometry Specialist)
Phase 1, Sprint 3 — Spec Step 6: exterior walls, mamad, structural
classification, doors, windows.

Every structural classification carries a mandatory disclaimer
(Israeli building code requirement).
"""

from __future__ import annotations

import logging
import math
from typing import Optional

import numpy as np
from scipy.spatial import KDTree
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import unary_union

try:
    from backend.geometry.models import (
        AREA_HEURISTICS, STRUCTURAL_DISCLAIMER, Opening, Room, WallInfo,
    )
except ModuleNotFoundError:
    from geometry.models import (
        AREA_HEURISTICS, STRUCTURAL_DISCLAIMER, Opening, Room, WallInfo,
    )

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants (configurable per VG rule #2)
# ---------------------------------------------------------------------------

EXTERIOR_DISTANCE_TOLERANCE = 5.0   # PDF points — max distance to envelope
MAMAD_AREA_MIN = 9.0                # sqm
MAMAD_AREA_MAX = 15.0               # sqm
MAMAD_THICKNESS_RATIO = 0.9         # Fraction of max thickness
STRUCTURAL_THICKNESS_RATIO = 1.5    # Interior wall is structural if > 1.5x avg
DOOR_WIDTH_MIN_CM = 60.0            # cm
DOOR_WIDTH_MAX_CM = 120.0           # cm
WINDOW_WIDTH_MIN_CM = 80.0          # cm
WINDOW_WIDTH_MAX_CM = 200.0         # cm
ARC_PROXIMITY_TOLERANCE = 15.0      # PDF points — arc near gap = door


# ---------------------------------------------------------------------------
# Exterior wall detection
# ---------------------------------------------------------------------------

def detect_exterior_walls(
    segments: list[dict],
    rooms: list[Room],
    tolerance: float = EXTERIOR_DISTANCE_TOLERANCE,
) -> list[WallInfo]:
    """
    Identify exterior (envelope) walls.

    Strategy: build the union of all room polygons to get the apartment
    envelope, then check which segments lie on or near the envelope boundary.

    Parameters
    ----------
    segments : list[dict]
        All wall segments.
    rooms : list[Room]
        Detected room polygons.
    tolerance : float
        Maximum distance from envelope boundary to count as exterior.

    Returns
    -------
    list[WallInfo]
        Segments classified as exterior walls.
    """
    if not rooms:
        return []

    # Build apartment envelope from union of all room polygons
    polys = [r.polygon for r in rooms if r.polygon.is_valid]
    if not polys:
        return []

    envelope = unary_union(polys)
    if isinstance(envelope, MultiPolygon):
        # Use the largest polygon as the main envelope
        envelope = max(envelope.geoms, key=lambda p: p.area)

    boundary = envelope.exterior

    exterior_walls: list[WallInfo] = []
    for seg in segments:
        seg_line = LineString([seg["start"], seg["end"]])
        dist = seg_line.distance(boundary)

        if dist <= tolerance:
            exterior_walls.append(WallInfo(
                segment=seg,
                wall_type="exterior",
                is_structural=True,
                is_modifiable=False,
                confidence=95.0,
            ))

    logger.info(
        "Exterior walls: %d / %d segments on envelope boundary",
        len(exterior_walls), len(segments),
    )

    return exterior_walls


# ---------------------------------------------------------------------------
# Mamad detection
# ---------------------------------------------------------------------------

def detect_mamad(
    rooms: list[Room],
    segments: list[dict],
    scale_factor: float = 1.0,
    thickness_ratio: float = MAMAD_THICKNESS_RATIO,
) -> Optional[Room]:
    """
    Detect the mamad (safe room) — enclosed by the thickest walls, 9-15 sqm.

    Parameters
    ----------
    rooms : list[Room]
        Detected rooms.
    segments : list[dict]
        All segments (for thickness analysis).
    scale_factor : float
        PDF points -> metres.
    thickness_ratio : float
        A wall is "mamad-thick" if width >= max_width * ratio.

    Returns
    -------
    Room or None
        The mamad room if found, else None.
    """
    if not segments or not rooms:
        return None

    # Find max stroke width
    widths = [s.get("stroke_width", 0.0) for s in segments]
    max_width = max(widths)
    if max_width <= 0:
        return None

    threshold = max_width * thickness_ratio

    # Find segments that qualify as mamad walls
    mamad_segs = [s for s in segments if s.get("stroke_width", 0.0) >= threshold]
    if not mamad_segs:
        return None

    # Build LineStrings from mamad-thick segments
    mamad_lines = [LineString([s["start"], s["end"]]) for s in mamad_segs]

    # For each room, check how much of its boundary is covered by thick walls
    best_room: Optional[Room] = None
    best_coverage = 0.0

    for room in rooms:
        if not (MAMAD_AREA_MIN <= room.area_sqm <= MAMAD_AREA_MAX):
            continue

        boundary = room.polygon.exterior
        covered_length = 0.0

        for ml in mamad_lines:
            # Check if mamad segment is near the room boundary
            if ml.distance(boundary) < 3.0:  # within snap tolerance
                covered_length += ml.length

        coverage = covered_length / boundary.length if boundary.length > 0 else 0.0

        if coverage > best_coverage:
            best_coverage = coverage
            best_room = room

    if best_room is not None and best_coverage > 0.3:
        best_room.room_type = "mamad"
        best_room.room_type_he = 'ממ"ד'
        best_room.is_modifiable = False
        best_room.confidence = min(95.0, 50.0 + best_coverage * 50.0)
        best_room.classification_strategy = "heuristic"
        best_room.needs_review = best_room.confidence < 70

        logger.info(
            "Mamad detected: %.1f sqm, %.0f%% thick-wall coverage, confidence=%.0f",
            best_room.area_sqm, best_coverage * 100, best_room.confidence,
        )
        return best_room

    return None


# ---------------------------------------------------------------------------
# Structural classification
# ---------------------------------------------------------------------------

def classify_structural(
    segments: list[dict],
    exterior_walls: list[WallInfo],
    mamad_room: Optional[Room],
    thickness_ratio: float = STRUCTURAL_THICKNESS_RATIO,
) -> list[WallInfo]:
    """
    Classify all wall segments as structural, partition, or unknown.

    Classification hierarchy:
    1. Mamad walls -> structural (99%)
    2. Exterior walls -> structural (95%)
    3. Thickness > avg * ratio -> likely structural (70%)
    4. Standard thickness -> partition (85%)

    Parameters
    ----------
    segments : list[dict]
        All wall segments.
    exterior_walls : list[WallInfo]
        Already-identified exterior walls.
    mamad_room : Room or None
        The mamad room, if detected.
    thickness_ratio : float
        A wall is "likely structural" if width > avg * ratio.

    Returns
    -------
    list[WallInfo]
        All segments with structural classification.
    """
    # Build lookup sets for exterior and mamad segment identities
    exterior_ids = set()
    for ew in exterior_walls:
        exterior_ids.add(_seg_id(ew.segment))

    mamad_ids = set()
    if mamad_room is not None:
        # Segments near the mamad boundary are mamad walls
        widths = [s.get("stroke_width", 0.0) for s in segments]
        max_width = max(widths) if widths else 0.0
        threshold = max_width * MAMAD_THICKNESS_RATIO
        for seg in segments:
            if seg.get("stroke_width", 0.0) < threshold:
                continue
            seg_line = LineString([seg["start"], seg["end"]])
            if seg_line.distance(mamad_room.polygon.exterior) < 3.0:
                mamad_ids.add(_seg_id(seg))

    # Compute average interior wall thickness (excluding exterior and mamad)
    interior_widths = [
        s.get("stroke_width", 0.0) for s in segments
        if _seg_id(s) not in exterior_ids and _seg_id(s) not in mamad_ids
    ]
    avg_interior = (sum(interior_widths) / len(interior_widths)) if interior_widths else 0.0

    classified: list[WallInfo] = []

    for seg in segments:
        sid = _seg_id(seg)
        width = seg.get("stroke_width", 0.0)

        if sid in mamad_ids:
            classified.append(WallInfo(
                segment=seg,
                wall_type="mamad",
                is_structural=True,
                is_modifiable=False,
                confidence=99.0,
            ))
        elif sid in exterior_ids:
            classified.append(WallInfo(
                segment=seg,
                wall_type="exterior",
                is_structural=True,
                is_modifiable=False,
                confidence=95.0,
            ))
        elif avg_interior > 0 and width > avg_interior * thickness_ratio:
            classified.append(WallInfo(
                segment=seg,
                wall_type="structural",
                is_structural=True,
                is_modifiable=False,
                confidence=70.0,
            ))
        else:
            classified.append(WallInfo(
                segment=seg,
                wall_type="partition",
                is_structural=False,
                is_modifiable=True,
                confidence=85.0,
            ))

    logger.info(
        "Structural classification: %d mamad, %d exterior, %d structural, %d partition",
        sum(1 for w in classified if w.wall_type == "mamad"),
        sum(1 for w in classified if w.wall_type == "exterior"),
        sum(1 for w in classified if w.wall_type == "structural"),
        sum(1 for w in classified if w.wall_type == "partition"),
    )

    return classified


def _seg_id(seg: dict) -> tuple:
    """Create a hashable identity for a segment (rounded endpoints)."""
    s = seg["start"]
    e = seg["end"]
    # Normalize direction so (A,B) == (B,A)
    p1 = (round(s[0], 2), round(s[1], 2))
    p2 = (round(e[0], 2), round(e[1], 2))
    return (min(p1, p2), max(p1, p2))


# ---------------------------------------------------------------------------
# Door and window detection
# ---------------------------------------------------------------------------

def detect_doors_and_windows(
    segments: list[dict],
    rooms: list[Room],
    arc_segments: Optional[list[dict]] = None,
    scale_factor: float = 1.0,
    door_min_cm: float = DOOR_WIDTH_MIN_CM,
    door_max_cm: float = DOOR_WIDTH_MAX_CM,
    window_min_cm: float = WINDOW_WIDTH_MIN_CM,
    window_max_cm: float = WINDOW_WIDTH_MAX_CM,
    arc_tolerance: float = ARC_PROXIMITY_TOLERANCE,
) -> tuple[list[Opening], dict]:
    """
    Detect door and window openings in the wall graph.

    Doors: gaps between degree-1 (dangling) endpoints of wall segments,
    with width in door range. Optionally confirmed by nearby arc segments.

    Windows: parallel line pairs within exterior wall segments.

    Parameters
    ----------
    segments : list[dict]
        Wall segments.
    rooms : list[Room]
        Detected rooms (for connecting rooms through openings).
    arc_segments : list[dict] or None
        Arc/curve segments indicating door swings.
    scale_factor : float
        PDF points -> metres.
    door_min_cm, door_max_cm : float
        Door width range in cm.
    window_min_cm, window_max_cm : float
        Window width range in cm.
    arc_tolerance : float
        Max distance from gap midpoint to arc to confirm as door.

    Returns
    -------
    openings : list[Opening]
        Detected doors and windows.
    report : dict
        Detection statistics.
    """
    if arc_segments is None:
        arc_segments = []

    # Convert door/window ranges to PDF points
    if scale_factor > 0:
        door_min_pt = door_min_cm / (scale_factor * 100)  # cm -> m -> pdf pts
        door_max_pt = door_max_cm / (scale_factor * 100)
        window_min_pt = window_min_cm / (scale_factor * 100)
        window_max_pt = window_max_cm / (scale_factor * 100)
    else:
        door_min_pt = door_min_cm
        door_max_pt = door_max_cm
        window_min_pt = window_min_cm
        window_max_pt = window_max_cm

    # Find degree-1 (dangling) endpoints
    endpoint_count: dict[tuple, int] = {}
    endpoint_to_seg: dict[tuple, list[int]] = {}

    for i, seg in enumerate(segments):
        for pt_raw in [seg["start"], seg["end"]]:
            pt = (round(pt_raw[0], 2), round(pt_raw[1], 2))
            endpoint_count[pt] = endpoint_count.get(pt, 0) + 1
            endpoint_to_seg.setdefault(pt, []).append(i)

    dangles = [pt for pt, count in endpoint_count.items() if count == 1]

    # Build KDTree of arc midpoints for proximity check
    arc_points = []
    if arc_segments:
        for arc in arc_segments:
            mid_x = (arc["start"][0] + arc["end"][0]) / 2
            mid_y = (arc["start"][1] + arc["end"][1]) / 2
            arc_points.append((mid_x, mid_y))

    arc_tree = KDTree(arc_points) if arc_points else None

    # Find door-sized gaps between dangling endpoints
    openings: list[Opening] = []
    used_dangles: set[tuple] = set()

    if len(dangles) >= 2:
        dangle_arr = np.array(dangles)
        dangle_tree = KDTree(dangle_arr)

        # Precompute which segments each dangle belongs to
        dangle_seg_ids: dict[int, set[int]] = {}
        for i, pt in enumerate(dangles):
            dangle_seg_ids[i] = set(endpoint_to_seg.get(pt, []))

        for i, pt in enumerate(dangles):
            if pt in used_dangles:
                continue

            # Query neighbors within door max distance, sorted by distance
            neighbors = dangle_tree.query_ball_point(pt, r=door_max_pt)
            # Sort by distance (closest first)
            neighbors = sorted(
                neighbors,
                key=lambda j: math.hypot(
                    dangles[j][0] - pt[0], dangles[j][1] - pt[1],
                ),
            )

            for j in neighbors:
                if j == i:
                    continue
                other = dangles[j]
                if other in used_dangles:
                    continue

                # Skip if both endpoints belong to the same segment
                if dangle_seg_ids[i] & dangle_seg_ids[j]:
                    continue

                gap = math.hypot(other[0] - pt[0], other[1] - pt[1])

                if door_min_pt <= gap <= door_max_pt:
                    mid = ((pt[0] + other[0]) / 2, (pt[1] + other[1]) / 2)
                    width_cm = gap * scale_factor * 100

                    # Check for nearby arc (door swing)
                    swing = None
                    if arc_tree is not None:
                        dist, idx = arc_tree.query(mid)
                        if dist <= arc_tolerance:
                            swing = "detected"

                    # Find which rooms this opening connects
                    room_pair = _find_connected_rooms(mid, rooms)

                    openings.append(Opening(
                        position=mid,
                        width_cm=width_cm,
                        opening_type="door",
                        swing_direction=swing,
                        connects_rooms=room_pair,
                        endpoints=(pt, other),
                    ))

                    used_dangles.add(pt)
                    used_dangles.add(other)
                    break  # Each dangle used once

    # Window detection: find parallel line pairs in exterior wall segments
    windows = _detect_windows(segments, scale_factor, window_min_pt, window_max_pt)
    openings.extend(windows)

    report = {
        "dangling_endpoints": len(dangles),
        "doors_detected": sum(1 for o in openings if o.opening_type == "door"),
        "doors_with_arc": sum(1 for o in openings
                              if o.opening_type == "door" and o.swing_direction is not None),
        "windows_detected": sum(1 for o in openings if o.opening_type == "window"),
    }

    logger.info(
        "Openings: %d doors (%d with arcs), %d windows",
        report["doors_detected"], report["doors_with_arc"], report["windows_detected"],
    )

    return openings, report


def _find_connected_rooms(
    midpoint: tuple[float, float],
    rooms: list[Room],
) -> Optional[tuple[int, int]]:
    """Find which two rooms an opening connects (indices)."""
    pt = Point(midpoint)
    nearby: list[int] = []

    for i, room in enumerate(rooms):
        # Check if midpoint is near the room boundary
        if room.polygon.exterior.distance(pt) < 5.0:
            nearby.append(i)

    if len(nearby) >= 2:
        return (nearby[0], nearby[1])
    return None


def _detect_windows(
    segments: list[dict],
    scale_factor: float,
    window_min_pt: float,
    window_max_pt: float,
) -> list[Opening]:
    """
    Detect windows as parallel double/triple lines within wall segments.

    Windows in Israeli plans appear as 2-3 parallel lines drawn within
    the wall thickness, spanning the window width.
    """
    windows: list[Opening] = []

    # Group segments by orientation (horizontal vs vertical, +-5 degrees)
    for i, seg_a in enumerate(segments):
        angle_a = math.atan2(
            seg_a["end"][1] - seg_a["start"][1],
            seg_a["end"][0] - seg_a["start"][0],
        )

        for j, seg_b in enumerate(segments):
            if j <= i:
                continue

            angle_b = math.atan2(
                seg_b["end"][1] - seg_b["start"][1],
                seg_b["end"][0] - seg_b["start"][0],
            )

            # Check parallel (angle difference < 5 degrees)
            angle_diff = abs(angle_a - angle_b) % math.pi
            if angle_diff > math.radians(5) and angle_diff < math.radians(175):
                continue

            # Check perpendicular distance (should be small, within wall thickness)
            perp_dist = _perpendicular_distance_lines(seg_a, seg_b)
            if perp_dist > 15.0:  # Max wall thickness in PDF points
                continue
            if perp_dist < 1.0:   # Too close, likely duplicate
                continue

            # Check overlap (parallel segments should overlap significantly)
            overlap = _segment_overlap(seg_a, seg_b)
            if overlap < 0.5:
                continue

            # Check if the overlapping length is in window range
            len_a = math.hypot(
                seg_a["end"][0] - seg_a["start"][0],
                seg_a["end"][1] - seg_a["start"][1],
            )

            if window_min_pt <= len_a <= window_max_pt:
                mid_x = (seg_a["start"][0] + seg_a["end"][0] +
                         seg_b["start"][0] + seg_b["end"][0]) / 4
                mid_y = (seg_a["start"][1] + seg_a["end"][1] +
                         seg_b["start"][1] + seg_b["end"][1]) / 4

                windows.append(Opening(
                    position=(mid_x, mid_y),
                    width_cm=len_a * scale_factor * 100,
                    opening_type="window",
                ))
                break  # Avoid duplicate matches for same window

    return windows


def _perpendicular_distance_lines(seg_a: dict, seg_b: dict) -> float:
    """Compute perpendicular distance between two line segments."""
    line_a = LineString([seg_a["start"], seg_a["end"]])
    mid_b = Point(
        (seg_b["start"][0] + seg_b["end"][0]) / 2,
        (seg_b["start"][1] + seg_b["end"][1]) / 2,
    )
    return line_a.distance(mid_b)


def _segment_overlap(seg_a: dict, seg_b: dict) -> float:
    """
    Compute overlap fraction between two parallel segments.

    Projects both onto the common direction axis and checks overlap.
    """
    # Direction of seg_a
    dx = seg_a["end"][0] - seg_a["start"][0]
    dy = seg_a["end"][1] - seg_a["start"][1]
    length = math.hypot(dx, dy)
    if length == 0:
        return 0.0

    ux, uy = dx / length, dy / length

    # Project all 4 endpoints onto this axis
    def proj(pt):
        return pt[0] * ux + pt[1] * uy

    a1, a2 = sorted([proj(seg_a["start"]), proj(seg_a["end"])])
    b1, b2 = sorted([proj(seg_b["start"]), proj(seg_b["end"])])

    overlap = max(0.0, min(a2, b2) - max(a1, b1))
    span_a = a2 - a1
    return overlap / span_a if span_a > 0 else 0.0
