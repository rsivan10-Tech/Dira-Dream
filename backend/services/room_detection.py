"""Negative-space room detection.

Quality Sprint Step 2 — detect rooms as the empty spaces between centerline
walls (envelope minus wall mass), instead of planar-graph face enumeration
which fails when segments don't form closed rings.

Algorithm:
  1. Apartment envelope = concave hull of centerline endpoints, buffered
     slightly outward to be inclusive at the perimeter.
  2. Wall mass = union of each centerline buffered to its measured thickness,
     then buffered slightly to close micro-gaps from fragmentation.
  3. Room candidates = envelope.difference(wall_mass).
  4. Filter: drop tiny artifacts (<MIN_ROOM_SQM), drop the polygon hugging
     the envelope edge (= outside-of-walls noise).
  5. Classify: text label proximity > fixture proximity > mamad-by-thickness
     > area heuristic. Restricted to the 10 valid Israeli room types.
  6. Cap room count by apartment-size heuristic.

Agent: VG | Quality Sprint Step 2
"""
from __future__ import annotations

import math
from typing import Optional

from shapely import concave_hull
from shapely.geometry import LineString, MultiPoint, MultiPolygon, Point, Polygon
from shapely.ops import unary_union

from geometry.models import (
    DISPLAY_NAMES_EN_TO_HE,
    MIN_VALID_ROOM_AREA,
    ROOM_LABELS_HE_TO_EN,
    Room,
)


# --- Working parameters (configurable per VG rule #2) ---
ENVELOPE_CONCAVE_RATIO = 0.2
ENVELOPE_BUFFER_CM = 20.0          # outward buffer to include perimeter walls
WALL_MASS_BUFFER_CM = 3.0          # close micro-gaps from fragmentation
WALL_EXTENSION_CM = 30.0           # extend centerline endpoints up to this
                                   # to bridge gaps to nearest neighbor wall
WALL_CLOSING_CM = 60.0             # morphological closing radius — fills door
                                   # and fragmentation gaps, then erodes back
MIN_ROOM_SQM = 1.5                 # below this = artifact
MAX_ROOM_SQM = 60.0                # above this = likely outdoor space, flag
OUTSIDE_PERIMETER_RATIO = 0.30     # fraction of envelope boundary touched
                                   # ⇒ room polygon is the "outside" patch
LABEL_PROXIMITY_CM = 30.0          # distance to consider a label "near" a poly


# ---------------------------------------------------------------------------
# Envelope + wall mass
# ---------------------------------------------------------------------------

def compute_envelope(walls, scale_factor: float) -> Optional[Polygon]:
    """Compute the apartment envelope as a buffered concave hull.

    Args:
        walls: list of CenterlineWall
        scale_factor: metres per PDF point

    Returns:
        Polygon envelope, or None if too few walls.
    """
    if len(walls) < 3:
        return None

    points = []
    for w in walls:
        points.append(w.p1)
        points.append(w.p2)

    mp = MultiPoint(points)
    try:
        hull = concave_hull(mp, ratio=ENVELOPE_CONCAVE_RATIO)
    except Exception:
        hull = mp.convex_hull

    if hull.is_empty or hull.geom_type not in ("Polygon", "MultiPolygon"):
        hull = mp.convex_hull

    if hull.geom_type == "MultiPolygon":
        hull = max(hull.geoms, key=lambda g: g.area)

    buffer_pt = (ENVELOPE_BUFFER_CM / 100.0) / scale_factor
    return hull.buffer(buffer_pt)


def _extend_centerlines(walls, scale_factor: float):
    """Extend each centerline endpoint toward its nearest neighbor wall.

    Closes the fragmentation gaps that prevent rooms from being detected.
    Each endpoint may be extended by up to WALL_EXTENSION_CM along its own
    direction. Endpoints that already touch a neighbor (within 1cm) are left
    alone.
    """
    from scipy.spatial import KDTree

    if len(walls) < 2:
        return walls

    extend_pt = (WALL_EXTENSION_CM / 100.0) / scale_factor
    touch_pt = (1.0 / 100.0) / scale_factor

    # Collect endpoints + which wall/end they belong to
    pts = []
    refs = []  # (wall_idx, 'p1'|'p2', dir_x, dir_y) — dir points OUT of the wall
    for i, w in enumerate(walls):
        L = math.hypot(w.p2[0] - w.p1[0], w.p2[1] - w.p1[1])
        if L < 1e-9:
            continue
        dx, dy = (w.p2[0] - w.p1[0]) / L, (w.p2[1] - w.p1[1]) / L
        pts.append(w.p1)
        refs.append((i, "p1", -dx, -dy))
        pts.append(w.p2)
        refs.append((i, "p2", dx, dy))

    if len(pts) < 2:
        return walls

    tree = KDTree(pts)

    new_p1 = {i: list(w.p1) for i, w in enumerate(walls)}
    new_p2 = {i: list(w.p2) for i, w in enumerate(walls)}

    for k, (px, py) in enumerate(pts):
        wall_idx, side, dx, dy = refs[k]
        # Find nearest neighbor endpoint in [touch_pt, extend_pt]
        dists, idxs = tree.query([px, py], k=min(8, len(pts)))
        if not hasattr(dists, "__iter__"):
            dists, idxs = [dists], [idxs]
        for d, ni in zip(dists, idxs):
            if ni == k or d <= touch_pt:
                continue
            if d > extend_pt:
                break
            other_idx, _, _, _ = refs[ni]
            if other_idx == wall_idx:
                continue
            # Check the neighbor is roughly in the extension direction
            ox, oy = pts[ni]
            vx, vy = ox - px, oy - py
            vlen = math.hypot(vx, vy)
            if vlen < 1e-9:
                continue
            cos = (vx * dx + vy * dy) / vlen
            if cos < 0.5:  # not in front of us (within ~60°)
                continue
            # Extend to the neighbor point
            target = (ox, oy)
            if side == "p1":
                new_p1[wall_idx] = list(target)
            else:
                new_p2[wall_idx] = list(target)
            break

    extended = []
    for i, w in enumerate(walls):
        from dataclasses import replace
        extended.append(replace(
            w,
            p1=tuple(new_p1[i]),
            p2=tuple(new_p2[i]),
        ))
    return extended


def build_wall_mass(walls, scale_factor: float):
    """Union all centerlines as thick rectangles, buffered to close gaps."""
    if not walls:
        return None

    walls = _extend_centerlines(walls, scale_factor)

    rects = []
    for w in walls:
        thick_pt = (w.thickness_cm / 100.0) / scale_factor
        line = LineString([w.p1, w.p2])
        if line.length < 1e-6:
            continue
        rects.append(line.buffer(thick_pt / 2, cap_style=2))  # flat caps

    if not rects:
        return None

    merged = unary_union(rects)
    # Morphological closing: dilate by R then erode by R closes gaps up to
    # 2R wide (doors, fragmentation) without permanently fattening walls.
    closing_pt = (WALL_CLOSING_CM / 100.0) / scale_factor
    closed = merged.buffer(closing_pt, join_style=2).buffer(
        -closing_pt, join_style=2,
    )
    return closed


# ---------------------------------------------------------------------------
# Room polygon extraction
# ---------------------------------------------------------------------------

def _polygons_from(geom) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    if geom.geom_type == "MultiPolygon":
        return list(geom.geoms)
    if geom.geom_type == "GeometryCollection":
        return [g for g in geom.geoms if g.geom_type == "Polygon"]
    return []


def _is_outside_patch(poly: Polygon, envelope: Polygon, tol: float) -> bool:
    """True if poly hugs the envelope boundary (= outside-of-walls space)."""
    boundary = envelope.boundary
    intersection = poly.boundary.intersection(boundary.buffer(tol))
    if intersection.is_empty:
        return False
    touched = intersection.length
    return (touched / poly.boundary.length) > OUTSIDE_PERIMETER_RATIO


def extract_room_polygons(envelope: Polygon, wall_mass, scale_factor: float) -> list[Polygon]:
    if envelope is None or wall_mass is None:
        return []

    diff = envelope.difference(wall_mass)
    candidates = _polygons_from(diff)

    min_area_pt2 = (MIN_ROOM_SQM / (scale_factor ** 2))
    max_area_pt2 = (MAX_ROOM_SQM / (scale_factor ** 2))

    rooms = []
    for poly in candidates:
        if not poly.is_valid:
            poly = poly.buffer(0)
            if poly.is_empty:
                continue
        if poly.geom_type == "MultiPolygon":
            poly = max(poly.geoms, key=lambda g: g.area)
        if poly.area < min_area_pt2:
            continue
        # Drop the outside frame — it's a ring polygon, identifiable by
        # having interior holes (the apartment cut out of it).
        if len(poly.interiors) > 0:
            continue
        # Drop polygons larger than MAX_ROOM_SQM (likely the un-subdivided
        # apartment when closing failed to seal walls)
        if poly.area > max_area_pt2:
            continue
        rooms.append(poly)

    # Sort by area descending so the largest room (likely salon) is first
    rooms.sort(key=lambda p: -p.area)
    return rooms


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

# Fixture label → likely room type
_FIXTURE_TO_ROOM = {
    'אסלה': 'guest_toilet',
    'שירותים': 'guest_toilet',
    'אמבט': 'bathroom',
    'אמבטיה': 'bathroom',
    'מקלחון': 'bathroom',
    'מקלחת': 'bathroom',
    'כיריים': 'kitchen',
    'תנור': 'kitchen',
    'מטבח': 'kitchen',
    'מדיח': 'kitchen',
    'מכונת כביסה': 'utility',
    'מייבש': 'utility',
    'חדר כביסה': 'utility',
}


# Substring patterns for Hebrew room labels — handle RTL extraction quirks
# where PyMuPDF reverses character order (e.g. ממ"ד → ד" ממ) and where
# labels are split by spaces (ד ח " ממ).
_LABEL_PATTERNS = [
    # (canonical_type, substrings to check after normalization)
    ("mamad",       ["ממ\"ד", "ממד", "דממ", "\"דממ"]),
    ("salon",       ["סלון", "דיור", "נולס"]),
    ("kitchen",     ["מטבח", "חבטמ"]),
    ("bedroom",     ["שינה", "הניש"]),
    ("guest_toilet", ["שירותים", "םיתוריש", "אסלה"]),
    ("bathroom",    ["אמבטיה", "אמבט", "טבמא", "מקלחת", "תחלקמ", "רחצה", "הצחר"]),
    ("sun_balcony", ["מרפסת שמש", "שמש תספרמ", "מרפסת", "תספרמ"]),
    ("service_balcony", ["מרפסת שירות", "תוריש תספרמ"]),
    ("storage",     ["מחסן", "ןסחמ"]),
    ("utility",     ["חדר שירות", "תוריש"]),
]


def _normalize_text(text: str) -> str:
    """Strip whitespace + zero-width chars + Unicode quote variants."""
    return (text or "").replace(" ", "").replace("\u201d", "\"").replace("\u05f4", "\"").strip()


def _text_label_to_type(text: str) -> Optional[str]:
    """Match Hebrew text (possibly RTL-reversed) against the vocabulary."""
    norm = _normalize_text(text)
    if not norm:
        return None
    rev = norm[::-1]

    # Direct dictionary lookup first
    for candidate in (text.strip(), norm, rev):
        if candidate in ROOM_LABELS_HE_TO_EN:
            return ROOM_LABELS_HE_TO_EN[candidate]

    # Distinctive substrings — mamad is "ממ" plus a quote/ד nearby. Most
    # short Hebrew strings containing "ממ" are mamad in floorplan context;
    # the Hebrew word for "mother" (אמא) doesn't appear on plans.
    if ("ממ" in norm or "ממ" in rev) and len(norm) <= 6:
        return "mamad"

    # Pattern substring match (mamad first — most distinctive)
    for room_type, patterns in _LABEL_PATTERNS:
        for p in patterns:
            p_norm = _normalize_text(p)
            if p_norm and (p_norm in norm or p_norm in rev):
                return room_type
    return None


def _text_centroid(t: dict) -> Optional[tuple[float, float]]:
    bbox = t.get("bbox")
    if not bbox or len(bbox) < 4:
        return None
    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)


def _allocate_labels_to_polygons(
    polygons: list[Polygon],
    texts: list,
    proximity_pt: float,
) -> dict:
    """Assign each label to one polygon (containing > nearest-within-range).

    Returns dict[poly_index → (room_type, confidence)]. Each polygon gets
    AT MOST ONE label allocation; we prefer labels strictly inside the
    polygon, falling back to the nearest polygon within proximity_pt.

    Mamad labels get priority: even if a polygon already has a different
    label, mamad overrides because the regulation guarantees there's
    exactly one mamad and it's structurally distinctive.
    """
    allocations: dict[int, tuple[str, float]] = {}
    used_text_ids: set[int] = set()

    # Pass 1 — strict containment
    for ti, t in enumerate(texts):
        ctr = _text_centroid(t)
        if ctr is None:
            continue
        label = _text_label_to_type(t.get("content", ""))
        if not label:
            continue
        pt = Point(ctr)
        for pi, poly in enumerate(polygons):
            if not poly.contains(pt):
                continue
            existing = allocations.get(pi)
            # Mamad always wins; otherwise first-come
            if existing is None or label == "mamad":
                allocations[pi] = (label, 0.95)
                used_text_ids.add(ti)
                break

    # Pass 2 — nearest polygon within proximity for any text not used yet
    for ti, t in enumerate(texts):
        if ti in used_text_ids:
            continue
        ctr = _text_centroid(t)
        if ctr is None:
            continue
        label = _text_label_to_type(t.get("content", ""))
        if not label:
            continue
        pt = Point(ctr)
        # Find closest polygon
        best: Optional[tuple[int, float]] = None
        for pi, poly in enumerate(polygons):
            d = poly.distance(pt)
            if d > proximity_pt:
                continue
            if best is None or d < best[1]:
                best = (pi, d)
        if best is None:
            continue
        pi, _ = best
        existing = allocations.get(pi)
        if existing is None or label == "mamad":
            allocations[pi] = (label, 0.75)

    return allocations


def _adjacent_max_thickness(poly: Polygon, walls: list, buffer_pt: float) -> float:
    poly_buf = poly.buffer(buffer_pt)
    adjacent_thick = []
    for w in walls:
        line = LineString([w.p1, w.p2])
        if line.intersects(poly_buf):
            adjacent_thick.append(w.thickness_cm)
    return max(adjacent_thick) if adjacent_thick else 0.0


def _classify_one(
    poly: Polygon,
    area_sqm: float,
    texts: list,
    walls: list,
    scale_factor: float,
    is_largest_interior: bool,
    has_mamad_text: bool,
    pre_allocated_label: Optional[tuple[str, float]],
) -> tuple[str, str, float]:
    """Return (room_type, strategy, confidence).

    `pre_allocated_label` is the (label, confidence) assigned to this
    polygon by the label-allocation pass, or None.
    `has_mamad_text` is True if a ממ"ד label was found anywhere — when
    true, mamad-by-thickness is suppressed.
    """
    # Strategy A — pre-allocated text label
    if pre_allocated_label is not None:
        return pre_allocated_label[0], "text", pre_allocated_label[1]

    # Strategy B — fixture proximity (text fixtures inside polygon)
    for t in texts:
        content = (t.get("content") or "").strip()
        if content not in _FIXTURE_TO_ROOM:
            continue
        ctr = _text_centroid(t)
        if ctr and poly.contains(Point(ctr)):
            return _FIXTURE_TO_ROOM[content], "fixture", 0.75

    # Strategy C — salon: ALWAYS the largest interior room ≥ 18 sqm
    if is_largest_interior and area_sqm >= 18.0:
        return "salon", "heuristic_largest", 0.65

    # Strategy D — mamad by thickness (suppressed if a text mamad exists)
    if not has_mamad_text and len(walls) >= 5 and 8.0 <= area_sqm <= 14.0:
        max_thick = _adjacent_max_thickness(
            poly, walls, (10.0 / 100.0) / scale_factor,
        )
        all_thick = sorted(w.thickness_cm for w in walls)
        p95 = all_thick[int(len(all_thick) * 0.95)]
        median = all_thick[len(all_thick) // 2]
        if max_thick >= p95 and max_thick >= median + 4.0:
            return "mamad", "wall_thickness", 0.70

    # Strategy E — area-only heuristics
    if 8.0 <= area_sqm <= 18.0:
        return "bedroom", "heuristic_area", 0.45
    if 4.0 <= area_sqm <= 8.0:
        return "bathroom", "heuristic_area", 0.40
    if 1.5 <= area_sqm <= 4.0:
        return "guest_toilet", "heuristic_area", 0.35
    if 6.0 <= area_sqm <= 16.0:
        return "kitchen", "heuristic_area", 0.35
    if area_sqm > 18.0:
        return "salon", "heuristic_area", 0.40

    return "unknown", "none", 0.0


def _find_largest_interior_index(polygons: list[Polygon], texts: list) -> int:
    """Return index of the largest polygon NOT labelled as a balcony.

    Polygons are sorted by area desc on entry. Walks from the top until it
    finds one whose own label (if any) isn't a balcony.
    """
    for i, poly in enumerate(polygons):
        for t in texts:
            ctr = _text_centroid(t)
            if ctr is None:
                continue
            if not poly.contains(Point(ctr)):
                continue
            label = _text_label_to_type(t.get("content", ""))
            if label in ("sun_balcony", "service_balcony"):
                break
        else:
            return i
        continue
    return 0


def classify_rooms_negative_space(
    polygons: list[Polygon],
    texts: list,
    walls: list,
    scale_factor: float,
) -> list[Room]:
    """Wrap polygons in Room dataclasses with classification.

    Two-pass: first scans for mamad-text and largest-interior, then
    classifies each polygon with that context. Post-classification dedup
    ensures at most one mamad (Israeli regulation: exactly 1 per apartment)
    and at most one salon.
    """
    if not polygons:
        return []

    proximity_pt = (LABEL_PROXIMITY_CM / 100.0) / scale_factor
    allocations = _allocate_labels_to_polygons(polygons, texts, proximity_pt)
    has_mamad_text = any(l[0] == "mamad" for l in allocations.values())
    largest_interior = _find_largest_interior_index(polygons, texts)

    rooms = []
    for i, poly in enumerate(polygons):
        area_sqm = poly.area * (scale_factor ** 2)
        perimeter_m = poly.length * scale_factor
        centroid = poly.centroid
        is_largest_interior = (i == largest_interior)

        room_type, strategy, conf = _classify_one(
            poly, area_sqm, texts, walls, scale_factor,
            is_largest_interior, has_mamad_text,
            allocations.get(i),
        )
        room_type_he = DISPLAY_NAMES_EN_TO_HE.get(room_type, "חדר")

        rooms.append(Room(
            polygon=poly,
            area_sqm=area_sqm,
            perimeter_m=perimeter_m,
            centroid=(centroid.x, centroid.y),
            room_type=room_type,
            room_type_he=room_type_he,
            confidence=conf * 100,
            needs_review=conf < 0.7,
            classification_strategy=strategy,
            is_modifiable=(room_type != "mamad"),
        ))

    # Dedup mamad: keep only the highest-confidence one
    mamads = [r for r in rooms if r.room_type == "mamad"]
    if len(mamads) > 1:
        keeper = max(mamads, key=lambda r: r.confidence)
        for r in mamads:
            if r is keeper:
                continue
            if 8.0 <= r.area_sqm <= 18.0:
                r.room_type = "bedroom"
                r.room_type_he = DISPLAY_NAMES_EN_TO_HE["bedroom"]
                r.classification_strategy = "demoted_from_mamad"
            else:
                r.room_type = "unknown"
                r.room_type_he = DISPLAY_NAMES_EN_TO_HE["unknown"]
            r.is_modifiable = True

    # Dedup salon: keep only the largest one classified as salon
    salons = [r for r in rooms if r.room_type == "salon"]
    if len(salons) > 1:
        keeper = max(salons, key=lambda r: r.area_sqm)
        for r in salons:
            if r is keeper:
                continue
            if 8.0 <= r.area_sqm <= 18.0:
                r.room_type = "bedroom"
                r.room_type_he = DISPLAY_NAMES_EN_TO_HE["bedroom"]
                r.classification_strategy = "demoted_from_salon"

    return rooms


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_rooms_negative_space(
    walls: list,
    texts: list,
    scale_factor: float,
    metadata: Optional[dict] = None,
):
    """Detect rooms by subtracting wall mass from the apartment envelope.

    Returns:
        (rooms, stats) where rooms is list[Room] and stats is a dict.
    """
    stats = {
        "walls": len(walls),
        "envelope_sqm": 0.0,
        "wall_mass_sqm": 0.0,
        "raw_candidates": 0,
        "rooms_after_filter": 0,
    }

    envelope = compute_envelope(walls, scale_factor)
    if envelope is None or envelope.is_empty:
        return [], stats
    stats["envelope_sqm"] = envelope.area * (scale_factor ** 2)

    wall_mass = build_wall_mass(walls, scale_factor)
    if wall_mass is None or wall_mass.is_empty:
        return [], stats
    stats["wall_mass_sqm"] = wall_mass.area * (scale_factor ** 2)

    raw = envelope.difference(wall_mass)
    stats["raw_candidates"] = len(_polygons_from(raw))

    polygons = extract_room_polygons(envelope, wall_mass, scale_factor)
    stats["rooms_after_filter"] = len(polygons)

    rooms = classify_rooms_negative_space(polygons, texts, walls, scale_factor)
    return rooms, stats


# ---------------------------------------------------------------------------
# Diagnostic CLI
# ---------------------------------------------------------------------------

def _diagnostic_run():
    from collections import Counter
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
    from services.wall_detection import find_centerline_walls

    print("\n=== Room detection diagnostic (Step 2) ===\n")
    for name, pdf_name, page in samples:
        pdf = PROJECT_ROOT / "docs" / "test-pdfs" / pdf_name
        if not pdf.exists():
            continue
        raw = extract_vectors(str(pdf), page_num=page)
        meta = extract_metadata(raw["texts"])
        cropped = crop_legend(raw)
        hist = compute_stroke_histogram(cropped["segments"])
        scale_value = meta.get("scale_value") or 50
        scale_factor = (0.0254 / 72) * scale_value
        walls, _ = find_centerline_walls(cropped["segments"], scale_factor, hist)

        envelope = compute_envelope(walls, scale_factor)
        wall_mass = build_wall_mass(walls, scale_factor)
        raw_polys = _polygons_from(envelope.difference(wall_mass))
        # area distribution of raw polygons
        areas_sqm = sorted([p.area * scale_factor**2 for p in raw_polys], reverse=True)
        areas_str = ", ".join(f"{a:.1f}" for a in areas_sqm[:15])

        rooms, stats = detect_rooms_negative_space(walls, cropped["texts"], scale_factor, meta)
        types = Counter(r.room_type for r in rooms)
        print(f"{name}: walls={stats['walls']} env={stats['envelope_sqm']:.1f}sqm "
              f"mass={stats['wall_mass_sqm']:.1f}sqm raw={len(raw_polys)} "
              f"final={len(rooms)}")
        print(f"  raw areas (sqm): [{areas_str}]")
        print(f"  classified: {dict(types)}")


if __name__ == "__main__":
    _diagnostic_run()
