"""Unit tests for services.opening_detection.

Covers: host-wall association, dedup, empty wall list handling.

Agent: VG | Quality Sprint Step 3
"""
from __future__ import annotations

from services.opening_detection import _nearest_wall_index, detect_openings_from_gaps
from services.wall_detection import CenterlineWall

SCALE = 0.0254 / 72 * 50


def _w(x1, y1, x2, y2):
    return CenterlineWall(
        id=f"w_{x1}_{y1}",
        p1=(x1, y1), p2=(x2, y2),
        thickness_cm=10.0,
        wall_type="partition",
        confidence=80.0,
    )


class TestHostMapping:
    def test_point_on_wall_returns_wall_index(self):
        walls = [_w(0, 0, 100, 0), _w(0, 50, 100, 50)]
        idx = _nearest_wall_index((50, 0.5), walls, max_dist_pt=10.0)
        assert idx == 0

    def test_point_near_second_wall(self):
        walls = [_w(0, 0, 100, 0), _w(0, 50, 100, 50)]
        idx = _nearest_wall_index((50, 49), walls, max_dist_pt=10.0)
        assert idx == 1

    def test_point_beyond_proximity_returns_none(self):
        walls = [_w(0, 0, 100, 0)]
        assert _nearest_wall_index((50, 500), walls, max_dist_pt=10.0) is None

    def test_empty_wall_list(self):
        assert _nearest_wall_index((0, 0), [], max_dist_pt=10.0) is None


class TestDetectOpenings:
    def test_empty_inputs_return_empty_list(self):
        openings, stats = detect_openings_from_gaps(
            walls=[], raw_segments=[], raw_drawings=None, scale_factor=SCALE,
        )
        assert openings == []
        assert stats["doors"] == 0
        assert stats["windows"] == 0
