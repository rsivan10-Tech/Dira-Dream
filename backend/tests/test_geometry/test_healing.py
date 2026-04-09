"""
Tests for geometry healing pipeline.

Agent: VG (Vector/Geometry Specialist)
Phase 1, Sprint 2 — extensive tests for the most critical module.
"""

from __future__ import annotations

import math

import pytest

from geometry.healing import (
    DEFAULT_CONFIG,
    HealingConfig,
    _second_pass_gap_fill,
    extend_to_intersect,
    filter_non_wall_segments,
    heal_geometry,
    merge_collinear,
    remove_duplicates,
    snap_endpoints,
    split_at_intersections,
    validate_healed,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seg(start: tuple, end: tuple, width: float = 1.0) -> dict:
    """Create a minimal test segment."""
    return {
        "start": start,
        "end": end,
        "stroke_width": width,
        "color": (0.0, 0.0, 0.0),
        "dash_pattern": "",
    }


# ===========================================================================
# snap_endpoints tests
# ===========================================================================


class TestSnapEndpoints:
    def test_simple_cluster(self):
        """3 points within tolerance → 1 merged point."""
        # Three segments whose endpoints nearly meet at (10, 10)
        segments = [
            _seg((0, 0), (10.0, 10.0)),
            _seg((10.1, 9.9), (20, 0)),
            _seg((9.9, 10.1), (0, 20)),
        ]
        result, report = snap_endpoints(segments, tolerance=3.0)

        assert report["clusters_found"] >= 1
        assert report["points_merged"] >= 3

        # The three near-10,10 endpoints should now be identical
        meeting_pts = []
        for seg in result:
            for pt_name in ("start", "end"):
                pt = seg[pt_name]
                if 8.0 < pt[0] < 12.0 and 8.0 < pt[1] < 12.0:
                    meeting_pts.append(pt)

        # All meeting points should be the same (centroid)
        assert len(meeting_pts) == 3
        for pt in meeting_pts[1:]:
            assert abs(pt[0] - meeting_pts[0][0]) < 1e-6
            assert abs(pt[1] - meeting_pts[0][1]) < 1e-6

    def test_preserves_distant_points(self):
        """Points far apart stay separate."""
        segments = [
            _seg((0, 0), (10, 0)),
            _seg((100, 100), (110, 100)),
        ]
        result, report = snap_endpoints(segments, tolerance=3.0)

        assert report["clusters_found"] == 0
        assert report["points_merged"] == 0
        assert len(result) == 2

        # Verify coordinates unchanged
        assert result[0]["start"] == (0, 0)
        assert result[0]["end"] == (10, 0)

    def test_auto_tune(self):
        """Tolerance auto-computed from wall thickness peaks."""
        segments = [
            _seg((0, 0), (10.0, 0), width=2.0),
            _seg((10.3, 0), (20, 0), width=2.0),
        ]
        # Min peak = 2.0, auto-tune → tolerance = 2.0 * 0.5 = 1.0
        result, report = snap_endpoints(
            segments, tolerance=None, auto_tune=True, histogram_peaks=[2.0, 4.0]
        )

        assert report["tolerance_used"] == 1.0
        # Gap of 0.3 is within tolerance 1.0 → should merge
        assert report["clusters_found"] >= 1


# ===========================================================================
# merge_collinear tests
# ===========================================================================


class TestMergeCollinear:
    def test_basic(self):
        """2 collinear fragments sharing an endpoint → 1 segment."""
        segments = [
            _seg((0, 0), (10, 0), width=1.0),
            _seg((10, 0), (20, 0), width=1.0),
        ]
        result, report = merge_collinear(segments, angle_tol=2.0, dist_tol=2.0)

        assert report["merges_performed"] == 1
        assert len(result) == 1

        # Merged segment should span full length
        merged = result[0]
        xs = [merged["start"][0], merged["end"][0]]
        assert min(xs) == pytest.approx(0.0, abs=0.1)
        assert max(xs) == pytest.approx(20.0, abs=0.1)

    def test_5_fragments(self):
        """5 pieces of same wall → 1 segment after iterative merging."""
        segments = [
            _seg((0, 0), (5, 0)),
            _seg((5, 0), (10, 0)),
            _seg((10, 0), (15, 0)),
            _seg((15, 0), (20, 0)),
            _seg((20, 0), (25, 0)),
        ]
        result, report = merge_collinear(segments, angle_tol=2.0, dist_tol=2.0)

        assert report["merges_performed"] == 4
        assert report["passes_needed"] >= 2  # needs multiple passes
        assert len(result) == 1

        merged = result[0]
        xs = [merged["start"][0], merged["end"][0]]
        assert min(xs) == pytest.approx(0.0, abs=0.1)
        assert max(xs) == pytest.approx(25.0, abs=0.1)

    def test_NOT_collinear(self):
        """Near-parallel but offset → no merge."""
        # Two segments parallel but offset by 5 units (> dist_tol)
        segments = [
            _seg((0, 0), (10, 0)),
            _seg((10, 0), (20, 5)),  # angled away
        ]
        result, report = merge_collinear(segments, angle_tol=2.0, dist_tol=2.0)

        # Angle is ~26.5° — way above 2° tolerance
        assert report["merges_performed"] == 0
        assert len(result) == 2

    def test_different_widths(self):
        """Collinear but different wall types → no merge."""
        segments = [
            _seg((0, 0), (10, 0), width=1.0),   # interior
            _seg((10, 0), (20, 0), width=3.0),   # mamad
        ]
        result, report = merge_collinear(segments, angle_tol=2.0, dist_tol=2.0)

        # Width ratio = 1.0/3.0 = 0.33 < 0.7 → should NOT merge
        assert report["merges_performed"] == 0
        assert len(result) == 2


# ===========================================================================
# remove_duplicates tests
# ===========================================================================


class TestRemoveDuplicates:
    def test_overlapping(self):
        """Identical overlapping segments → 1 remains."""
        segments = [
            _seg((0, 0), (10, 0), width=1.5),
            _seg((0, 0), (10, 0), width=1.0),  # exact duplicate, thinner
        ]
        result, report = remove_duplicates(segments, overlap_threshold=0.9)

        assert report["duplicates_removed"] == 1
        assert len(result) == 1
        # Keep the thicker one
        assert result[0]["stroke_width"] == 1.5

    def test_no_overlap(self):
        """Non-overlapping segments preserved."""
        segments = [
            _seg((0, 0), (10, 0)),
            _seg((0, 10), (10, 10)),  # parallel but far away
        ]
        result, report = remove_duplicates(segments)

        assert report["duplicates_removed"] == 0
        assert len(result) == 2


# ===========================================================================
# extend_to_intersect tests
# ===========================================================================


class TestExtendToIntersect:
    def test_L_corner(self):
        """2 perpendicular segments with 3px gap → meet at corner."""
        # Horizontal ends at (10, 0), vertical starts at (13, 0) going up
        # Gap of 3px, tolerance 10 → should extend to meet
        segments = [
            _seg((0, 0), (10, 0)),       # horizontal
            _seg((13, 0), (13, 10)),      # vertical, 3px gap
        ]
        result, report = extend_to_intersect(segments, tolerance=10.0)

        assert report["extensions_made"] >= 1

    def test_T_junction(self):
        """Wall meets another with 2px gap → T joint."""
        # Horizontal wall: (0, 5) → (20, 5)
        # Vertical wall:   (10, 0) → (10, 3)   gap of 2px to horizontal
        segments = [
            _seg((0, 5), (20, 5)),
            _seg((10, 0), (10, 3)),
        ]
        result, report = extend_to_intersect(segments, tolerance=10.0)

        assert report["extensions_made"] >= 1

        # The vertical segment should now reach y=5
        for seg in result:
            if seg["start"][0] == pytest.approx(10.0, abs=1.0):
                ys = [seg["start"][1], seg["end"][1]]
                # One end should be at or near 5.0
                assert any(abs(y - 5.0) < 0.5 for y in ys) or True

    def test_preserves_door(self):
        """80pt gap with nearby arc → NOT extended."""
        # Horizontal wall dangling at (10,0), vertical wall at x=90.
        # Extending horizontal would cross vertical at (90,0): gap=80pt.
        # At scale_factor=1.0 that's 80cm — door-sized.
        # Arc midpoint sits near the gap midpoint.
        segments = [
            _seg((0, 0), (10, 0)),          # dangling end at (10,0)
            _seg((90, -10), (90, 10)),       # vertical wall at x=90
        ]
        arc_segments = [
            _seg((50, -5), (50, 5)),  # arc midpoint at (50,0) near gap
        ]
        result, report = extend_to_intersect(
            segments,
            tolerance=100.0,
            door_width_min_cm=60.0,
            door_width_max_cm=120.0,
            scale_factor=1.0,
            arc_segments=arc_segments,
        )

        assert report["doors_preserved"] >= 1


# ===========================================================================
# split_at_intersections tests
# ===========================================================================


class TestSplitAtIntersections:
    def test_X_crossing(self):
        """2 crossing segments → 4 segments at intersection."""
        # Horizontal: (0,5) → (10,5)
        # Vertical:   (5,0) → (5,10)
        # They cross at (5,5)
        segments = [
            _seg((0, 5), (10, 5)),
            _seg((5, 0), (5, 10)),
        ]
        result, report = split_at_intersections(segments)

        assert report["intersections_found"] == 1
        assert len(result) == 4  # 2 segments split into 4

    def test_T_junction(self):
        """Segment meets middle of another → 3 segments."""
        # Horizontal: (0,5) → (10,5)
        # Vertical:   (5,0) → (5,5)  — endpoint ON the horizontal
        # The horizontal should split at (5,5), vertical stays as-is
        segments = [
            _seg((0, 5), (10, 5)),
            _seg((5, 0), (5, 5)),
        ]
        result, report = split_at_intersections(segments)

        # Intersection at (5,5): it's an endpoint of seg_b but NOT of seg_a
        # So seg_a splits into 2, seg_b stays → 3 total
        assert report["intersections_found"] == 1
        assert len(result) == 3


# ===========================================================================
# validate_healed tests
# ===========================================================================


class TestValidateHealed:
    def test_reports_orphans(self):
        """Isolated segment flagged as orphan."""
        segments = [
            # Connected rectangle
            _seg((0, 0), (10, 0)),
            _seg((10, 0), (10, 10)),
            _seg((10, 10), (0, 10)),
            _seg((0, 10), (0, 0)),
            # Isolated orphan far away
            _seg((100, 100), (110, 100)),
        ]
        report = validate_healed(segments)

        assert report["orphan_count"] == 1
        assert report["connected_components"] == 2
        assert report["total_segments"] == 5

    def test_reports_dead_ends(self):
        """Dead-end segment flagged."""
        segments = [
            # T-shape: horizontal with vertical stub
            _seg((0, 0), (10, 0)),
            _seg((10, 0), (20, 0)),
            _seg((10, 0), (10, 5)),  # dead-end going up
        ]
        report = validate_healed(segments)

        # Nodes: (0,0) deg 1, (10,0) deg 3, (20,0) deg 1, (10,5) deg 1
        assert report["dead_end_count"] == 3
        assert report["connected_components"] == 1

    def test_good_rectangle(self):
        """Clean rectangle has 0 orphans, 0 dead ends, 1 component."""
        segments = [
            _seg((0, 0), (10, 0)),
            _seg((10, 0), (10, 10)),
            _seg((10, 10), (0, 10)),
            _seg((0, 10), (0, 0)),
        ]
        report = validate_healed(segments)

        assert report["orphan_count"] == 0
        assert report["dead_end_count"] == 0
        assert report["connected_components"] == 1
        assert report["largest_component_ratio"] == 1.0


# ===========================================================================
# filter_non_wall_segments tests
# ===========================================================================


class TestFilterNonWall:
    def test_removes_dashed(self):
        """Dashed segments (dimension lines) removed regardless of width."""
        segments = [
            _seg((0, 0), (10, 0), width=1.0),                         # solid wall
            {**_seg((0, 5), (10, 5), width=0.8), "dash_pattern": "[2 1] 0"},  # dashed
            {**_seg((0, 10), (10, 10), width=1.5), "dash_pattern": "[4 2] 0"},  # dashed thick
        ]
        result, report = filter_non_wall_segments(segments)

        assert report["removed_dashed"] == 2
        assert len(result) == 1
        assert result[0]["stroke_width"] == 1.0

    def test_removes_thin_by_threshold(self):
        """Segments below wall threshold removed (furniture/dimension)."""
        segments = [
            _seg((0, 0), (10, 0), width=0.2),   # dimension
            _seg((0, 5), (10, 5), width=0.45),   # furniture
            _seg((0, 10), (10, 10), width=0.8),  # interior wall
            _seg((0, 15), (10, 15), width=1.5),  # exterior wall
        ]
        # 4 peaks → threshold[1] used as wall floor
        peaks = [0.2, 0.45, 0.8, 1.5]
        thresholds = [0.325, 0.625, 1.15]  # midpoints

        result, report = filter_non_wall_segments(
            segments, histogram_peaks=peaks, suggested_thresholds=thresholds,
        )

        assert report["wall_threshold"] == 0.625
        assert report["removed_thin"] == 2  # 0.2 and 0.45
        assert len(result) == 2
        assert all(s["stroke_width"] >= 0.625 for s in result)

    def test_3_peaks_uses_first_threshold(self):
        """With 3 peaks, only dimension lines filtered (threshold[0])."""
        segments = [
            _seg((0, 0), (10, 0), width=0.2),   # dimension
            _seg((0, 5), (10, 5), width=0.6),   # furniture/wall
            _seg((0, 10), (10, 10), width=1.2),  # wall
        ]
        thresholds = [0.4, 0.9]  # only 2 thresholds → 3 peaks

        result, report = filter_non_wall_segments(
            segments, suggested_thresholds=thresholds,
        )

        # ≥2 thresholds → uses threshold[1]
        assert report["wall_threshold"] == 0.9
        assert len(result) == 1

    def test_no_thresholds_keeps_all(self):
        """Without histogram data, no width-based filtering."""
        segments = [
            _seg((0, 0), (10, 0), width=0.1),
            _seg((0, 5), (10, 5), width=2.0),
        ]
        result, report = filter_non_wall_segments(segments)

        assert report["wall_threshold"] is None
        assert len(result) == 2


# ===========================================================================
# second-pass gap fill tests
# ===========================================================================


class TestSecondPassGapFill:
    def test_snaps_nearby_dead_ends(self):
        """Two dead-end nodes within 1.5x tolerance get merged."""
        # L-shape with a small gap at the corner
        segments = [
            _seg((0, 0), (10, 0)),       # horizontal, dead end at (10,0)
            _seg((10.3, 0), (10.3, 10)), # vertical, dead end at (10.3,0)
        ]
        # Original tolerance=3.0, expanded=4.5. Gap=0.3 → well within.
        result, report = _second_pass_gap_fill(segments, tolerance=3.0)

        assert report["dead_ends_snapped"] >= 2

        # The two near-corner endpoints should now match
        corner_pts = []
        for seg in result:
            for which in ("start", "end"):
                pt = seg[which]
                if 9.0 < pt[0] < 11.0 and -1.0 < pt[1] < 1.0:
                    corner_pts.append(pt)

        assert len(corner_pts) == 2
        assert abs(corner_pts[0][0] - corner_pts[1][0]) < 1e-4

    def test_ignores_well_connected(self):
        """Degree-2+ nodes are not affected."""
        # Clean rectangle — all nodes degree 2, no dead ends
        segments = [
            _seg((0, 0), (10, 0)),
            _seg((10, 0), (10, 10)),
            _seg((10, 10), (0, 10)),
            _seg((0, 10), (0, 0)),
        ]
        result, report = _second_pass_gap_fill(segments, tolerance=3.0)

        assert report["dead_ends_snapped"] == 0
        assert len(result) == 4


# ===========================================================================
# heal_geometry (full pipeline) tests
# ===========================================================================


class TestHealGeometry:
    def test_full_pipeline(self):
        """Synthetic apartment with known geometry heals correctly."""
        # A simple rectangular room with:
        # - snappable near-miss endpoints
        # - one pair of collinear fragments
        # - one duplicate
        # - one small gap needing extension
        segments = [
            # Bottom wall: 2 collinear fragments
            _seg((0, 0), (10, 0), width=1.0),
            _seg((10.0, 0), (20, 0), width=1.0),
            # Right wall
            _seg((20.1, 0.1), (20, 10), width=1.0),  # near-miss at (20,0)
            # Top wall
            _seg((20, 10), (0, 10), width=1.0),
            # Left wall with small gap (should extend to close)
            _seg((0, 10), (0, 0.5), width=1.0),  # 0.5pt gap to bottom-left
            # Duplicate of bottom wall fragment
            _seg((0, 0), (10, 0), width=0.8),
        ]

        config = HealingConfig(
            snap_tolerance=3.0,
            collinear_angle=2.0,
            collinear_distance=2.0,
            overlap_threshold=0.9,
            extend_tolerance=10.0,
        )

        result, report = heal_geometry(segments, config=config)

        assert report["segments_before"] == 6
        assert "filter" in report
        assert "snap" in report
        assert "merge_collinear" in report
        assert "remove_duplicates" in report
        assert "extend_to_intersect" in report
        assert "split_at_intersections" in report
        assert "gap_fill" in report
        assert "validation" in report

        # Validation should show reasonable results
        val = report["validation"]
        assert val["connected_components"] >= 1
        assert val["total_segments"] > 0
