"""
Tests for backend/geometry/graph.py — planar graph construction.

Agent: VG | Phase 1, Sprint 3
"""

import math

import networkx as nx
import pytest

from backend.geometry.graph import build_planar_graph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seg(start, end, width=1.0, color=(0, 0, 0)):
    """Shorthand for creating a segment dict."""
    return {
        "start": start,
        "end": end,
        "stroke_width": width,
        "color": color,
        "dash_pattern": "",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildPlanarGraph:
    """Tests for build_planar_graph()."""

    def test_simple_rectangle_4_walls(self):
        """4 walls forming a rectangle = 4 nodes, 4 edges."""
        segments = [
            _seg((0, 0), (100, 0)),    # bottom
            _seg((100, 0), (100, 80)),  # right
            _seg((100, 80), (0, 80)),   # top
            _seg((0, 80), (0, 0)),      # left
        ]
        G, embedding, report = build_planar_graph(segments)

        assert report["nodes"] == 4
        assert report["edges"] == 4
        assert report["is_planar"] is True
        assert embedding is not None
        assert report["dead_ends"] == 0
        assert report["connected_components"] == 1

    def test_two_rooms_sharing_wall(self):
        """Two adjacent rooms sharing a wall = 6 nodes, 7 edges."""
        # Room 1: (0,0)-(50,0)-(50,80)-(0,80)
        # Room 2: (50,0)-(100,0)-(100,80)-(50,80)
        # Shared wall: (50,0)-(50,80)
        segments = [
            _seg((0, 0), (50, 0)),
            _seg((50, 0), (100, 0)),
            _seg((100, 0), (100, 80)),
            _seg((100, 80), (50, 80)),
            _seg((50, 80), (0, 80)),
            _seg((0, 80), (0, 0)),
            _seg((50, 0), (50, 80)),  # shared wall
        ]
        G, embedding, report = build_planar_graph(segments)

        assert report["nodes"] == 6
        assert report["edges"] == 7
        assert report["is_planar"] is True
        assert report["dead_ends"] == 0

    def test_node_attributes(self):
        """Nodes should have x, y, degree attributes."""
        segments = [_seg((10, 20), (30, 40))]
        G, _, _ = build_planar_graph(segments)

        node = (10.0, 20.0)
        assert G.nodes[node]["x"] == 10.0
        assert G.nodes[node]["y"] == 20.0
        assert G.nodes[node]["degree"] == 1

    def test_edge_attributes(self):
        """Edges should have wall_type, thickness, length, color."""
        segments = [_seg((0, 0), (30, 40), width=2.5, color=(1, 0, 0))]
        G, _, _ = build_planar_graph(segments)

        edge_data = G[(0.0, 0.0)][(30.0, 40.0)]
        assert edge_data["wall_type"] == "unknown"
        assert edge_data["thickness"] == 2.5
        assert edge_data["length"] == pytest.approx(50.0, abs=0.01)
        assert edge_data["color"] == (1, 0, 0)

    def test_duplicate_edge_keeps_thicker(self):
        """If two segments share endpoints, keep the thicker one."""
        segments = [
            _seg((0, 0), (100, 0), width=1.0),
            _seg((0, 0), (100, 0), width=3.0),
        ]
        G, _, report = build_planar_graph(segments)

        assert report["edges"] == 1
        assert G[(0.0, 0.0)][(100.0, 0.0)]["thickness"] == 3.0

    def test_zero_length_segments_skipped(self):
        """Segments that round to same start/end should be skipped."""
        segments = [
            _seg((10.001, 20.002), (10.004, 20.003)),  # rounds to same point
            _seg((0, 0), (100, 0)),  # valid
        ]
        G, _, report = build_planar_graph(segments)

        assert report["skipped_zero_length"] == 1
        assert report["edges"] == 1

    def test_disconnected_components(self):
        """Two separate rectangles = 2 connected components."""
        segments = [
            # Rectangle 1
            _seg((0, 0), (50, 0)),
            _seg((50, 0), (50, 50)),
            _seg((50, 50), (0, 50)),
            _seg((0, 50), (0, 0)),
            # Rectangle 2 (far away)
            _seg((200, 200), (250, 200)),
            _seg((250, 200), (250, 250)),
            _seg((250, 250), (200, 250)),
            _seg((200, 250), (200, 200)),
        ]
        G, _, report = build_planar_graph(segments)

        assert report["connected_components"] == 2

    def test_degree_distribution(self):
        """T-junction should produce node with degree 3."""
        # T-junction: horizontal wall with vertical wall meeting in middle
        segments = [
            _seg((0, 0), (100, 0)),    # horizontal
            _seg((50, 0), (50, 80)),   # vertical meeting at (50,0)
        ]
        G, _, report = build_planar_graph(segments)

        # (50,0) should have degree 3: left, right, up
        # But we only have 2 segments = 2 edges from (50,0) perspective
        # Actually the horizontal is one edge (0,0)-(100,0), so (50,0)
        # splits it into two edges only if split_at_intersections was run.
        # After healing, segments are already split, so we get 3 segments:
        # (0,0)-(50,0), (50,0)-(100,0), (50,0)-(50,80)
        # But here we pass unsplit segments, so (50,0) is an endpoint of
        # the vertical but NOT an endpoint of the horizontal.
        # The horizontal goes (0,0)-(100,0), skipping (50,0).
        # So we get: nodes (0,0), (100,0), (50,0), (50,80)
        # Edges: (0,0)-(100,0), (50,0)-(50,80)
        # This is correct — split_at_intersections handles this pre-graph.
        assert report["nodes"] == 4
        assert report["edges"] == 2

    def test_t_junction_pre_split(self):
        """Pre-split T-junction: 3 segments meeting at node = degree 3."""
        segments = [
            _seg((0, 0), (50, 0)),     # left half
            _seg((50, 0), (100, 0)),   # right half
            _seg((50, 0), (50, 80)),   # vertical
        ]
        G, _, report = build_planar_graph(segments)

        assert G.degree((50.0, 0.0)) == 3
        assert report["nodes"] == 4
        assert report["edges"] == 3

    def test_empty_input(self):
        """Empty segment list returns empty graph."""
        G, embedding, report = build_planar_graph([])

        assert report["nodes"] == 0
        assert report["edges"] == 0
        assert report["is_planar"] is True
