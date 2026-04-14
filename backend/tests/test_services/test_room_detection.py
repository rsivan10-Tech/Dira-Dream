"""Unit tests for services.room_detection.

Synthetic test apartments built from CenterlineWall objects so we can verify
the negative-space algorithm in isolation from PDF extraction.

Agent: VG | Quality Sprint Step 2
"""
from __future__ import annotations

from services.room_detection import (
    build_wall_mass,
    compute_envelope,
    detect_rooms_negative_space,
    extract_room_polygons,
)
from services.wall_detection import CenterlineWall

# Scale 1:50 → 1 cm = ~0.567 PDF pt
SCALE = 0.0254 / 72 * 50
M = 1.0 / SCALE  # PDF points per metre


def _wall(x1, y1, x2, y2, thickness_cm=10.0, wall_type="partition"):
    return CenterlineWall(
        id=f"w_{x1}_{y1}",
        p1=(x1, y1), p2=(x2, y2),
        thickness_cm=thickness_cm,
        wall_type=wall_type,
        confidence=80.0,
    )


def _square_apartment(side_m: float, thickness_cm: float = 20.0):
    """4 exterior walls forming a closed square of side_m metres."""
    s = side_m * M
    return [
        _wall(0, 0, s, 0, thickness_cm, "exterior"),
        _wall(s, 0, s, s, thickness_cm, "exterior"),
        _wall(s, s, 0, s, thickness_cm, "exterior"),
        _wall(0, s, 0, 0, thickness_cm, "exterior"),
    ]


class TestEnvelope:
    def test_envelope_produced_from_square_apartment(self):
        walls = _square_apartment(side_m=10.0)
        env = compute_envelope(walls, SCALE)
        assert env is not None
        # 10x10m apartment = 100 sqm + envelope buffer ~20cm extra
        area_sqm = env.area * SCALE ** 2
        assert 100.0 < area_sqm < 130.0

    def test_too_few_walls_returns_none(self):
        walls = [_wall(0, 0, 1, 0)]
        assert compute_envelope(walls, SCALE) is None


class TestNegativeSpace:
    def test_single_room_apartment_detects_one_room(self):
        walls = _square_apartment(side_m=5.0)
        rooms, stats = detect_rooms_negative_space(walls, [], SCALE, {})
        assert stats["rooms_after_filter"] == 1
        assert 15.0 < rooms[0].area_sqm < 25.0  # ~5x5m minus walls

    def test_two_rooms_split_by_interior_wall(self):
        # 6x4m apartment + interior wall at x=3
        walls = _square_apartment(side_m=4.0, thickness_cm=20.0)
        # Stretch to 6m wide
        walls[0] = _wall(0, 0, 6 * M, 0, 20.0, "exterior")
        walls[2] = _wall(6 * M, 4 * M, 0, 4 * M, 20.0, "exterior")
        walls[1] = _wall(6 * M, 0, 6 * M, 4 * M, 20.0, "exterior")
        # Interior partition splitting at x=3m
        walls.append(_wall(3 * M, 0, 3 * M, 4 * M, 10.0, "partition"))

        rooms, stats = detect_rooms_negative_space(walls, [], SCALE, {})
        assert stats["rooms_after_filter"] == 2
        # Both rooms ~3x4m = 12 sqm minus walls
        for r in rooms:
            assert 5.0 < r.area_sqm < 12.0

    def test_classification_via_text_label(self):
        walls = _square_apartment(side_m=5.0)
        # Place a "סלון" label inside the room
        s = 5 * M
        texts = [{
            "content": "סלון",
            "bbox": [s / 2 - 5, s / 2 - 5, s / 2 + 5, s / 2 + 5],
            "font_size": 12.0,
        }]
        rooms, _ = detect_rooms_negative_space(walls, texts, SCALE, {})
        assert len(rooms) == 1
        assert rooms[0].room_type == "salon"
        assert rooms[0].classification_strategy == "text"

    def test_outside_frame_filtered_out(self):
        walls = _square_apartment(side_m=5.0)
        rooms, _ = detect_rooms_negative_space(walls, [], SCALE, {})
        # Should be exactly 1 room — the outside frame (between envelope
        # buffer and exterior walls) must be dropped.
        assert len(rooms) == 1
