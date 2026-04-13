"""Unit tests for services.wall_detection.find_centerline_walls.

Covers: parallel pair → centerline, perpendicular non-pair, too-far/too-close
distance rejection, insufficient overlap, relative thickness classification,
dashed line filter, single-line fallback.

Agent: VG | Quality Sprint Step 1
"""
from __future__ import annotations

import math

from services.wall_detection import (
    MAX_WALL_THICKNESS_CM,
    MIN_WALL_THICKNESS_CM,
    find_centerline_walls,
)

# Scale 1:50 → 1 PDF point ≈ 1.764 cm
SCALE = 0.0254 / 72 * 50


def _seg(x1, y1, x2, y2, w=1.0, dash=None):
    return {
        "start": (x1, y1),
        "end": (x2, y2),
        "stroke_width": w,
        "color": (0, 0, 0),
        "dash_pattern": dash,
    }


def _pt(cm: float) -> float:
    """Convert cm to PDF points at scale 1:50."""
    return (cm / 100.0) / SCALE


class TestParallelPairing:
    def test_horizontal_parallel_pair_produces_one_centerline(self):
        d = _pt(10.0)  # 10cm thick wall
        segs = [_seg(0, 0, 100, 0), _seg(0, d, 100, d)]
        walls, stats = find_centerline_walls(segs, SCALE)
        assert stats["centerlines"] == 1
        w = walls[0]
        assert abs(w.thickness_cm - 10.0) < 0.5
        # Centerline should sit at y ≈ d/2
        mid_y = (w.p1[1] + w.p2[1]) / 2
        assert abs(mid_y - d / 2) < 0.1

    def test_vertical_parallel_pair(self):
        d = _pt(10.0)
        segs = [_seg(0, 0, 0, 100), _seg(d, 0, d, 100)]
        walls, stats = find_centerline_walls(segs, SCALE)
        assert stats["centerlines"] == 1
        assert abs(walls[0].thickness_cm - 10.0) < 0.5

    def test_perpendicular_lines_no_pair(self):
        segs = [_seg(0, 0, 100, 0), _seg(50, -50, 50, 50)]
        walls, stats = find_centerline_walls(segs, SCALE)
        assert stats["pairs_found"] == 0
        assert stats["centerlines"] == 0

    def test_pair_too_far_apart(self):
        # 50cm apart > MAX_WALL_THICKNESS_CM (40)
        far = _pt(50.0)
        segs = [_seg(0, 0, 100, 0), _seg(0, far, 100, far)]
        walls, stats = find_centerline_walls(segs, SCALE)
        assert stats["pairs_found"] == 0

    def test_pair_too_close(self):
        # 4cm < MIN_WALL_THICKNESS_CM (6)
        near = _pt(4.0)
        segs = [_seg(0, 0, 100, 0), _seg(0, near, 100, near)]
        walls, stats = find_centerline_walls(segs, SCALE)
        assert stats["pairs_found"] == 0

    def test_insufficient_overlap_rejected(self):
        # Two parallel segs with only ~20% overlap (40 / 200)
        d = _pt(10.0)
        segs = [_seg(0, 0, 200, 0), _seg(160, d, 360, d)]
        walls, stats = find_centerline_walls(segs, SCALE)
        assert stats["pairs_found"] == 0

    def test_full_overlap_with_offset_lengths(self):
        # Long seg + short seg fully contained within projection → high overlap
        d = _pt(10.0)
        segs = [_seg(0, 0, 200, 0), _seg(50, d, 150, d)]
        walls, stats = find_centerline_walls(segs, SCALE)
        assert stats["centerlines"] == 1


class TestThicknessClassification:
    def test_three_clusters_ranked_correctly(self):
        # 8cm partition / 14cm exterior / 22cm mamad — well separated
        thin = _pt(8.0)
        med = _pt(14.0)
        thick = _pt(22.0)
        segs = [
            _seg(0, 0, 100, 0),     _seg(0, thin, 100, thin),
            _seg(0, 200, 100, 200), _seg(0, 200 + med, 100, 200 + med),
            _seg(0, 400, 100, 400), _seg(0, 400 + thick, 100, 400 + thick),
        ]
        walls, stats = find_centerline_walls(segs, SCALE)
        assert stats["centerlines"] == 3
        by_th = sorted(walls, key=lambda w: w.thickness_cm)
        assert by_th[0].wall_type == "partition"
        assert by_th[2].wall_type == "mamad"
        # Mamad must be the thickest (authoritative ordering rule)
        assert by_th[2].thickness_cm > by_th[1].thickness_cm > by_th[0].thickness_cm

    def test_single_thickness_population_falls_back_to_spec_bands(self):
        # Single 14cm wall — no population variance, falls back to spec
        d = _pt(14.0)
        segs = [_seg(0, 0, 100, 0), _seg(0, d, 100, d)]
        walls, _ = find_centerline_walls(segs, SCALE)
        assert walls[0].wall_type == "exterior"


class TestFilters:
    def test_dashed_lines_dropped_pre_pairing(self):
        d = _pt(10.0)
        segs = [
            _seg(0, 0, 100, 0, dash="[3 3] 0"),
            _seg(0, d, 100, d, dash="[3 3] 0"),
        ]
        _, stats = find_centerline_walls(segs, SCALE)
        assert stats["wall_candidates"] == 0
        assert stats["centerlines"] == 0

    def test_short_segments_dropped(self):
        d = _pt(10.0)
        # Both segments only 3pt long — below MIN_SEGMENT_LENGTH_PT=5
        segs = [_seg(0, 0, 3, 0), _seg(0, d, 3, d)]
        _, stats = find_centerline_walls(segs, SCALE)
        assert stats["wall_candidates"] == 0

    def test_unpaired_thick_segment_kept_when_fallback_enabled(self):
        # Single-line fallback is OFF by default — furniture pollutes it.
        # Test by toggling the module flag.
        from services import wall_detection as wd
        seg = _seg(0, 0, 100, 0, w=2.5)
        original = wd.ENABLE_SINGLE_LINE_FALLBACK
        wd.ENABLE_SINGLE_LINE_FALLBACK = True
        try:
            walls, stats = find_centerline_walls(
                [seg], SCALE, histogram={"suggested_thresholds": [0.5]},
            )
            assert stats["single_line_walls"] == 1
            assert walls[0].source_segment_ids == [0]
        finally:
            wd.ENABLE_SINGLE_LINE_FALLBACK = original

    def test_single_line_fallback_disabled_by_default(self):
        seg = _seg(0, 0, 100, 0, w=2.5)
        walls, stats = find_centerline_walls(
            [seg], SCALE, histogram={"suggested_thresholds": [0.5]},
        )
        assert stats["single_line_walls"] == 0
