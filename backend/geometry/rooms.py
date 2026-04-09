"""
Room detection and classification from a planar wall graph.

Agent: VG (Vector/Geometry Specialist)
Phase 1, Sprint 3 — Spec Step 5: detect rooms, classify by text/fixture/area.

detect_rooms():  extracts minimal faces from the planar embedding (or
                 falls back to shapely.ops.polygonize).
classify_rooms(): assigns room types via three strategies (text, fixture, area).
"""

from __future__ import annotations

import logging
import math
from typing import Optional

import networkx as nx
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize

try:
    from backend.geometry.models import (
        AREA_HEURISTICS, DISPLAY_NAMES_EN_TO_HE, ROOM_LABELS_HE_TO_EN, Room,
    )
except ModuleNotFoundError:
    from geometry.models import (
        AREA_HEURISTICS, DISPLAY_NAMES_EN_TO_HE, ROOM_LABELS_HE_TO_EN, Room,
    )

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants (configurable per VG rule #2)
# ---------------------------------------------------------------------------

DEFAULT_MIN_ROOM_AREA = 1.0   # sqm — below this, discard as artifact
DEFAULT_SCALE_FACTOR = 1.0    # PDF points → metres (caller must supply)

# Confidence levels per classification strategy
CONFIDENCE_TEXT = 95
CONFIDENCE_FIXTURE = 80
CONFIDENCE_HEURISTIC = 60
CONFIDENCE_CROSS_BOOST = 10   # Boost when 2 strategies agree


# ---------------------------------------------------------------------------
# Room detection
# ---------------------------------------------------------------------------

def detect_rooms(
    G: nx.Graph,
    embedding: Optional[nx.PlanarEmbedding],
    scale_factor: float = DEFAULT_SCALE_FACTOR,
    min_room_area: float = DEFAULT_MIN_ROOM_AREA,
) -> tuple[list[Room], dict]:
    """
    Detect rooms as minimal bounded faces of the planar graph.

    Parameters
    ----------
    G : nx.Graph
        Wall graph (nodes = endpoints, edges = wall segments).
    embedding : nx.PlanarEmbedding or None
        If the graph is planar, the embedding for face traversal.
        If None, falls back to Shapely polygonize.
    scale_factor : float
        Converts PDF-point lengths to metres.
    min_room_area : float
        Minimum room area in sqm to keep (default 1.0).

    Returns
    -------
    rooms : list[Room]
        Detected room polygons with area, perimeter, centroid.
    report : dict
        Detection statistics.
    """
    if embedding is not None:
        polygons = _faces_from_embedding(G, embedding)
        method = "planar_embedding"
    else:
        polygons = _faces_from_polygonize(G)
        method = "polygonize"

    # Filter: valid, non-empty, above min area
    rooms: list[Room] = []
    discarded_small = 0
    discarded_invalid = 0
    discarded_outer = 0

    for poly, is_outer in polygons:
        if not poly.is_valid or poly.is_empty:
            discarded_invalid += 1
            continue

        if is_outer:
            discarded_outer += 1
            continue

        area_sqm = poly.area * (scale_factor ** 2)

        if area_sqm < min_room_area:
            discarded_small += 1
            continue

        perimeter_m = poly.length * scale_factor
        centroid_pt = poly.representative_point()

        rooms.append(Room(
            polygon=poly,
            area_sqm=area_sqm,
            perimeter_m=perimeter_m,
            centroid=(centroid_pt.x, centroid_pt.y),
        ))

    report = {
        "method": method,
        "faces_found": len(polygons),
        "rooms_kept": len(rooms),
        "discarded_small": discarded_small,
        "discarded_invalid": discarded_invalid,
        "discarded_outer_face": discarded_outer,
    }

    logger.info(
        "Room detection (%s): %d faces -> %d rooms "
        "(discarded: %d small, %d invalid, %d outer)",
        method, len(polygons), len(rooms),
        discarded_small, discarded_invalid,
        report["discarded_outer_face"],
    )

    return rooms, report


# ---------------------------------------------------------------------------
# Face extraction — planar embedding
# ---------------------------------------------------------------------------

def _faces_from_embedding(
    G: nx.Graph,
    embedding: nx.PlanarEmbedding,
) -> list[tuple[Polygon, bool]]:
    """
    Extract minimal face polygons from a NetworkX PlanarEmbedding.

    Traverses half-edges to enumerate all faces. Uses signed area
    (shoelace formula) to distinguish bounded (interior) faces from
    the unbounded (exterior) face.

    Returns list of (Polygon, is_outer) tuples.
    """
    visited_half_edges: set[tuple] = set()
    face_data: list[tuple[Polygon, float]] = []  # (polygon, signed_area)

    for u, v in embedding.edges():
        for start_node, next_node in [(u, v), (v, u)]:
            if (start_node, next_node) in visited_half_edges:
                continue

            # Traverse face starting from this half-edge
            face_nodes = []
            current, nxt = start_node, next_node

            while True:
                visited_half_edges.add((current, nxt))
                face_nodes.append(current)
                # Follow the face: next_face_half_edge returns (w, next_node)
                current, nxt = embedding.next_face_half_edge(current, nxt)

                if current == start_node and nxt == next_node:
                    break

                if len(face_nodes) > len(G.nodes()) + 1:
                    break

            if len(face_nodes) >= 3:
                coords = [(G.nodes[n]["x"], G.nodes[n]["y"]) for n in face_nodes]
                coords.append(coords[0])  # close the ring
                signed = _signed_area(coords)
                try:
                    poly = Polygon(coords)
                    if poly.is_valid and not poly.is_empty:
                        face_data.append((poly, signed))
                except Exception:
                    pass

    if not face_data:
        return []

    # Determine outer face by signed area:
    # Interior faces share one sign; the outer face has the opposite sign.
    # Count positive vs negative signed areas.
    pos_count = sum(1 for _, sa in face_data if sa > 0)
    neg_count = sum(1 for _, sa in face_data if sa < 0)

    # The minority sign is the outer face direction
    outer_sign_positive = pos_count < neg_count

    return [
        (poly, (sa > 0) == outer_sign_positive)
        for poly, sa in face_data
    ]


def _signed_area(coords: list[tuple[float, float]]) -> float:
    """Compute signed area using the shoelace formula."""
    n = len(coords) - 1  # Last point == first point
    area = 0.0
    for i in range(n):
        area += coords[i][0] * coords[i + 1][1]
        area -= coords[i + 1][0] * coords[i][1]
    return area / 2.0


# ---------------------------------------------------------------------------
# Face extraction — Shapely polygonize fallback
# ---------------------------------------------------------------------------

def _faces_from_polygonize(G: nx.Graph) -> list[tuple[Polygon, bool]]:
    """
    Fallback: use Shapely polygonize to find closed polygons from edges.

    Polygonize only returns bounded faces, so none are marked as outer.
    """
    lines = []
    for u, v in G.edges():
        lines.append(LineString([u, v]))

    return [(poly, False) for poly in polygonize(lines)]


# ---------------------------------------------------------------------------
# Room classification
# ---------------------------------------------------------------------------

def classify_rooms(
    rooms: list[Room],
    texts: list[dict],
    segments: list[dict],
    scale_factor: float = DEFAULT_SCALE_FACTOR,
) -> list[Room]:
    """
    Classify rooms using three strategies (text, fixture, area heuristics).

    Parameters
    ----------
    rooms : list[Room]
        Detected rooms with polygons.
    texts : list[dict]
        Text annotations with keys: content, x, y (or bbox).
    segments : list[dict]
        All segments (for fixture detection).
    scale_factor : float
        PDF points → metres.

    Returns
    -------
    rooms : list[Room]
        Same rooms with room_type, confidence, etc. filled in.
    """
    for room in rooms:
        candidates: list[tuple[str, float, str]] = []  # (type, confidence, strategy)

        # Strategy A: Text label matching
        text_match = _classify_by_text(room, texts)
        if text_match:
            candidates.append((*text_match, "text"))

        # Strategy B: Fixture analysis
        fixture_match = _classify_by_fixtures(room, segments, scale_factor)
        if fixture_match:
            candidates.append((*fixture_match, "fixture"))

        # Strategy C: Area/shape heuristics
        heuristic_match = _classify_by_area(room)
        if heuristic_match:
            candidates.append((*heuristic_match, "heuristic"))

        if not candidates:
            room.room_type = "unknown"
            room.room_type_he = DISPLAY_NAMES_EN_TO_HE.get("unknown", "חדר")
            room.confidence = 0.0
            room.classification_strategy = "none"
            room.needs_review = True
            continue

        # Sort by confidence descending
        candidates.sort(key=lambda x: x[1], reverse=True)
        best_type, best_conf, best_strategy = candidates[0]

        # Cross-validation boost: if top two strategies agree
        if len(candidates) >= 2 and candidates[0][0] == candidates[1][0]:
            best_conf = min(best_conf + CONFIDENCE_CROSS_BOOST, 100.0)

        room.room_type = best_type
        room.room_type_he = DISPLAY_NAMES_EN_TO_HE.get(best_type, "חדר")
        room.confidence = best_conf
        room.classification_strategy = best_strategy
        room.needs_review = best_conf < 70

        # Mamad is never modifiable
        if best_type == "mamad":
            room.is_modifiable = False

    # --- Post-classification sanity checks ---
    _fix_oversize_balconies(rooms)
    _enforce_single_mamad(rooms)

    return rooms


def _fix_oversize_balconies(rooms: list[Room]) -> None:
    """Reclassify balconies > 25 sqm as salon (living room)."""
    MAX_BALCONY_SQM = 25.0
    for room in rooms:
        if room.room_type == "balcony" and room.area_sqm > MAX_BALCONY_SQM:
            room.room_type = "salon"
            room.room_type_he = DISPLAY_NAMES_EN_TO_HE.get("salon", "סלון")
            room.confidence = max(room.confidence - 20, 40)
            room.needs_review = True
            logger.info(
                "Reclassified oversize balcony (%.1f sqm) as salon",
                room.area_sqm,
            )


def _enforce_single_mamad(rooms: list[Room]) -> None:
    """An Israeli apartment has exactly one mamad. Keep the best candidate."""
    mamads = [r for r in rooms if r.room_type == "mamad"]
    if len(mamads) <= 1:
        return

    # Keep the one with highest confidence, tiebreak by area closest to 12 sqm
    best = max(mamads, key=lambda r: (r.confidence, -abs(r.area_sqm - 12.0)))
    for r in mamads:
        if r is not best:
            r.room_type = "bedroom"
            r.room_type_he = DISPLAY_NAMES_EN_TO_HE.get("bedroom", "חדר שינה")
            r.confidence = max(r.confidence - 30, 30)
            r.needs_review = True
            r.is_modifiable = True
            logger.info(
                "Demoted duplicate mamad (%.1f sqm) to bedroom", r.area_sqm,
            )


# ---------------------------------------------------------------------------
# Strategy A: Text label matching
# ---------------------------------------------------------------------------

def _classify_by_text(
    room: Room,
    texts: list[dict],
) -> Optional[tuple[str, float]]:
    """
    Match Hebrew/English text labels inside the room polygon.

    Returns (room_type, confidence) or None.
    """
    for text in texts:
        # Get text position (support both flat x/y and bbox formats)
        tx = text.get("x")
        ty = text.get("y")
        if tx is None or ty is None:
            bbox = text.get("bbox")
            if bbox and len(bbox) == 4:
                tx = (bbox[0] + bbox[2]) / 2
                ty = (bbox[1] + bbox[3]) / 2
            else:
                continue

        point = Point(tx, ty)
        if not room.polygon.contains(point):
            continue

        content = text.get("content", "").strip()
        if not content:
            continue

        # Exact match
        if content in ROOM_LABELS_HE_TO_EN:
            return (ROOM_LABELS_HE_TO_EN[content], CONFIDENCE_TEXT)

        # Substring / fuzzy match: check if any known label is contained
        content_lower = content.lower()
        for label_he, room_type in ROOM_LABELS_HE_TO_EN.items():
            if label_he in content:
                return (room_type, CONFIDENCE_TEXT - 5)  # 90% for partial

        # English labels
        english_types = {
            "salon": "salon", "living": "salon",
            "bedroom": "bedroom", "bed": "bedroom",
            "kitchen": "kitchen",
            "bathroom": "bathroom", "bath": "bathroom", "wc": "bathroom",
            "mamad": "mamad",
            "balcony": "balcony",
            "storage": "storage",
            "hallway": "hallway", "corridor": "corridor",
            "entrance": "entrance",
        }
        for eng_label, room_type in english_types.items():
            if eng_label in content_lower:
                return (room_type, CONFIDENCE_TEXT - 5)

    return None


# ---------------------------------------------------------------------------
# Strategy B: Fixture analysis
# ---------------------------------------------------------------------------

def _classify_by_fixtures(
    room: Room,
    segments: list[dict],
    scale_factor: float,
) -> Optional[tuple[str, float]]:
    """
    Identify room type from fixture-like segments inside the room.

    Heuristic: count small segments inside the room polygon and match
    against fixture size signatures.
    """
    if not segments:
        return None

    # Find segments whose midpoint is inside the room
    interior_segs: list[dict] = []
    for seg in segments:
        mid_x = (seg["start"][0] + seg["end"][0]) / 2
        mid_y = (seg["start"][1] + seg["end"][1]) / 2
        if room.polygon.contains(Point(mid_x, mid_y)):
            interior_segs.append(seg)

    if not interior_segs:
        return None

    # Compute bounding box of interior segments to find fixture-sized clusters
    # Look for small rectangular groups that match fixture dimensions
    thin_segs = [s for s in interior_segs
                 if s.get("stroke_width", 0) < _median_width(segments) * 0.8]

    if not thin_segs:
        return None

    # Count thin interior segments as a fixture density proxy
    # Bathrooms and kitchens have more fixture symbols
    fixture_density = len(thin_segs)

    # Simple heuristic: rooms with many thin interior segments
    # are likely bathrooms or kitchens
    if fixture_density >= 8 and room.area_sqm < 12.0:
        return ("bathroom", CONFIDENCE_FIXTURE)
    elif fixture_density >= 12 and room.area_sqm >= 6.0:
        return ("kitchen", CONFIDENCE_FIXTURE)

    return None


def _median_width(segments: list[dict]) -> float:
    """Compute median stroke width of all segments."""
    widths = sorted(s.get("stroke_width", 0.0) for s in segments)
    if not widths:
        return 0.0
    mid = len(widths) // 2
    return widths[mid]


# ---------------------------------------------------------------------------
# Strategy C: Area and shape heuristics
# ---------------------------------------------------------------------------

def _classify_by_area(room: Room) -> Optional[tuple[str, float]]:
    """
    Classify room by area size and shape (aspect ratio).

    Returns (room_type, confidence) or None.
    """
    area = room.area_sqm

    # Shape analysis: aspect ratio from bounding box
    minx, miny, maxx, maxy = room.polygon.bounds
    width = maxx - minx
    height = maxy - miny
    if min(width, height) > 0:
        aspect_ratio = max(width, height) / min(width, height)
    else:
        aspect_ratio = 1.0

    # Long and narrow = hallway/corridor
    if aspect_ratio > 3.0 and area < 15.0:
        return ("hallway", CONFIDENCE_HEURISTIC)

    # Very small = storage or WC
    if area < 4.0:
        return ("storage", CONFIDENCE_HEURISTIC - 5)

    # Largest room heuristic is handled at apartment level,
    # but we can flag large rooms
    if area >= 18.0:
        return ("salon", CONFIDENCE_HEURISTIC + 5)

    # Medium rooms by area range
    # Try each room type; pick the one whose typical area is closest
    best_type = None
    best_dist = float("inf")

    for room_type, ranges in AREA_HEURISTICS.items():
        if room_type in ("salon", "hallway", "storage"):
            continue  # Already handled above
        if ranges["min"] <= area <= ranges["max"]:
            dist = abs(area - ranges["typical"])
            if dist < best_dist:
                best_dist = dist
                best_type = room_type

    if best_type:
        return (best_type, CONFIDENCE_HEURISTIC)

    return None
