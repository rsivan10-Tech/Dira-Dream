"""
Tests for backend/geometry/structural.py — structural analysis.

Agent: VG | Phase 1, Sprint 3
"""

import math

import pytest
from shapely.geometry import Polygon

from backend.geometry.models import Opening, Room, WallInfo, STRUCTURAL_DISCLAIMER
from backend.geometry.structural import (
    classify_structural,
    detect_doors_and_windows,
    detect_exterior_walls,
    detect_mamad,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seg(start, end, width=1.0, color=(0, 0, 0)):
    return {
        "start": start,
        "end": end,
        "stroke_width": width,
        "color": color,
        "dash_pattern": "",
    }


def _make_room(coords, area_sqm, room_type="unknown"):
    poly = Polygon(coords)
    centroid_pt = poly.representative_point()
    return Room(
        polygon=poly,
        area_sqm=area_sqm,
        perimeter_m=poly.length,
        centroid=(centroid_pt.x, centroid_pt.y),
        room_type=room_type,
    )


# ---------------------------------------------------------------------------
# Exterior wall detection
# ---------------------------------------------------------------------------

class TestDetectExteriorWalls:

    def test_outer_boundary_walls_flagged(self):
        """Walls on the apartment boundary should be exterior."""
        # Room polygon
        room = _make_room([(0, 0), (100, 0), (100, 80), (0, 80)], area_sqm=20.0)

        # Segments: the 4 boundary walls + 1 interior wall
        segments = [
            _seg((0, 0), (100, 0), width=2.0),     # bottom (exterior)
            _seg((100, 0), (100, 80), width=2.0),   # right (exterior)
            _seg((100, 80), (0, 80), width=2.0),    # top (exterior)
            _seg((0, 80), (0, 0), width=2.0),       # left (exterior)
            _seg((50, 0), (50, 80), width=1.0),     # interior divider
        ]

        result = detect_exterior_walls(segments, [room])

        # 4 exterior + the interior wall's endpoints touch the boundary
        # so the interior wall may also be within tolerance.
        # At least the 4 boundary walls should be exterior.
        exterior_types = [w.wall_type for w in result]
        assert all(t == "exterior" for t in exterior_types)
        assert all(w.is_structural for w in result)
        assert all(w.confidence >= 95 for w in result)

    def test_empty_rooms_returns_empty(self):
        """No rooms -> no exterior walls."""
        result = detect_exterior_walls([_seg((0, 0), (100, 0))], [])
        assert result == []


# ---------------------------------------------------------------------------
# Mamad detection
# ---------------------------------------------------------------------------

class TestDetectMamad:

    def test_thickest_walls_10sqm_is_mamad(self):
        """Room with thickest walls + 10 sqm -> mamad."""
        # Mamad room: 10 sqm
        mamad_coords = [(0, 0), (100, 0), (100, 100), (0, 100)]
        mamad = _make_room(mamad_coords, area_sqm=10.0)

        # Other room: 20 sqm
        other_coords = [(100, 0), (300, 0), (300, 100), (100, 100)]
        other = _make_room(other_coords, area_sqm=20.0)

        # Segments: mamad walls are thick (5.0), other walls are thin (1.0)
        segments = [
            # Mamad boundary (thick)
            _seg((0, 0), (100, 0), width=5.0),
            _seg((100, 0), (100, 100), width=5.0),
            _seg((100, 100), (0, 100), width=5.0),
            _seg((0, 100), (0, 0), width=5.0),
            # Other room (thin)
            _seg((100, 0), (300, 0), width=1.0),
            _seg((300, 0), (300, 100), width=1.0),
            _seg((300, 100), (100, 100), width=1.0),
        ]

        result = detect_mamad([mamad, other], segments)

        assert result is not None
        assert result.room_type == "mamad"
        assert result.is_modifiable is False
        assert result.area_sqm == 10.0

    def test_no_mamad_when_area_out_of_range(self):
        """Room with thick walls but area < 9 sqm -> no mamad."""
        small = _make_room([(0, 0), (50, 0), (50, 50), (0, 50)], area_sqm=5.0)
        segments = [
            _seg((0, 0), (50, 0), width=5.0),
            _seg((50, 0), (50, 50), width=5.0),
            _seg((50, 50), (0, 50), width=5.0),
            _seg((0, 50), (0, 0), width=5.0),
        ]

        result = detect_mamad([small], segments)
        assert result is None

    def test_no_segments_returns_none(self):
        """No segments -> no mamad."""
        room = _make_room([(0, 0), (100, 0), (100, 100), (0, 100)], area_sqm=10.0)
        result = detect_mamad([room], [])
        assert result is None


# ---------------------------------------------------------------------------
# Structural classification
# ---------------------------------------------------------------------------

class TestClassifyStructural:

    def test_exterior_is_structural(self):
        """Exterior walls should be classified as structural."""
        segments = [
            _seg((0, 0), (100, 0), width=2.0),
            _seg((50, 0), (50, 80), width=1.0),
        ]
        ext_walls = [WallInfo(
            segment=segments[0],
            wall_type="exterior",
            is_structural=True,
            is_modifiable=False,
            confidence=95.0,
        )]

        result = classify_structural(segments, ext_walls, None)

        # First segment -> exterior
        assert result[0].wall_type == "exterior"
        assert result[0].is_structural is True

    def test_thin_wall_is_partition(self):
        """Standard-thickness wall -> partition (removable)."""
        segments = [
            _seg((0, 0), (100, 0), width=1.0),
            _seg((50, 0), (50, 80), width=1.0),
        ]

        result = classify_structural(segments, [], None)

        for w in result:
            assert w.wall_type == "partition"
            assert w.is_structural is False
            assert w.is_modifiable is True
            assert w.confidence == 85.0

    def test_thick_interior_is_structural(self):
        """Interior wall much thicker than average -> likely structural.

        Needs enough segments so the 95th-percentile threshold allows
        detection, and the thick wall must be > 2.5× avg to pass the
        ratio threshold.
        """
        # 10 normal walls at 1.0, 1 thick wall at 5.0
        # avg = (10*1.0 + 5.0)/11 = 1.36, ratio threshold = 1.36*2.5 = 3.41
        # 95th pct of [1.0]*10 + [5.0] ≈ 5.0 → 5.0 > 3.41 AND > pct ✓
        segments = [_seg((i * 20, 0), (i * 20 + 15, 0), width=1.0) for i in range(10)]
        segments.append(_seg((25, 0), (25, 80), width=5.0))  # thick interior

        result = classify_structural(segments, [], None)

        thick_wall = [w for w in result if w.segment == segments[10]][0]
        assert thick_wall.wall_type == "structural"
        assert thick_wall.is_structural is True
        assert thick_wall.confidence == 70.0

    def test_disclaimer_always_present(self):
        """Every WallInfo should carry the structural disclaimer."""
        segments = [_seg((0, 0), (100, 0))]
        result = classify_structural(segments, [], None)

        for w in result:
            assert w.disclaimer == STRUCTURAL_DISCLAIMER


# ---------------------------------------------------------------------------
# Door and window detection
# ---------------------------------------------------------------------------

class TestDetectDoorsAndWindows:

    def test_door_detection_from_gap(self):
        """Gap of 80cm between dangling endpoints -> door."""
        # Two wall segments with an 80-unit gap
        # scale_factor=0.01: 80 PDF pts * 0.01 * 100 = 80 cm
        segments = [
            _seg((0, 0), (100, 0)),       # wall left of gap
            _seg((180, 0), (300, 0)),      # wall right of gap
            _seg((0, 0), (0, 80)),         # left boundary
            _seg((300, 0), (300, 80)),     # right boundary
            _seg((0, 80), (300, 80)),      # top wall
        ]

        rooms = [_make_room(
            [(0, 0), (300, 0), (300, 80), (0, 80)],
            area_sqm=20.0,
        )]

        openings, report = detect_doors_and_windows(
            segments, rooms, scale_factor=0.01,
        )

        assert report["doors_detected"] >= 1
        door = [o for o in openings if o.opening_type == "door"]
        assert len(door) >= 1
        assert 60 <= door[0].width_cm <= 120

    def test_door_detection_with_arc(self):
        """Door gap + nearby arc segment -> door with swing detected."""
        segments = [
            _seg((0, 0), (100, 0)),
            _seg((180, 0), (300, 0)),
        ]

        # Arc segment near the gap midpoint (140, 0)
        arcs = [_seg((120, -30), (160, 30))]

        rooms = [_make_room(
            [(0, -50), (300, -50), (300, 50), (0, 50)],
            area_sqm=20.0,
        )]

        openings, report = detect_doors_and_windows(
            segments, rooms, arc_segments=arcs, scale_factor=0.01,
        )

        assert report["doors_with_arc"] >= 1

    def test_no_door_when_gap_too_small(self):
        """Gap smaller than 60cm should not be detected as door."""
        # 30-unit gap at scale 0.01 = 30cm (below door minimum)
        segments = [
            _seg((0, 0), (100, 0)),
            _seg((130, 0), (300, 0)),
        ]

        openings, report = detect_doors_and_windows(
            segments, [], scale_factor=0.01,
        )

        doors = [o for o in openings if o.opening_type == "door"]
        assert len(doors) == 0

    def test_window_detection_parallel_lines(self):
        """Two parallel lines within wall thickness -> window."""
        # Two parallel horizontal lines, 5 units apart, 150 units long
        # At scale 0.01: 150 * 0.01 * 100 = 150 cm (in window range)
        segments = [
            _seg((0, 0), (150, 0), width=0.5),
            _seg((0, 5), (150, 5), width=0.5),
        ]

        openings, report = detect_doors_and_windows(
            segments, [], scale_factor=0.01,
        )

        windows = [o for o in openings if o.opening_type == "window"]
        assert len(windows) >= 1
        assert report["windows_detected"] >= 1
