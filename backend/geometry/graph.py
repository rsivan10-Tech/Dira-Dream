"""
Topological planar graph construction from healed wall segments.

Agent: VG (Vector/Geometry Specialist)
Phase 1, Sprint 3 — Spec Step 4: build planar graph for room detection.

Takes healed segments (list[dict]) and produces a NetworkX Graph + PlanarEmbedding.
Each unique endpoint becomes a node; each segment becomes an edge.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

import networkx as nx
import numpy as np
from scipy.spatial import KDTree

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _point_key(pt: tuple[float, float], decimals: int = 2) -> tuple[float, float]:
    """Round a point to `decimals` places for use as a graph node key."""
    return (round(pt[0], decimals), round(pt[1], decimals))


def _seg_length(start: tuple[float, float], end: tuple[float, float]) -> float:
    """Euclidean distance between two points."""
    return math.hypot(end[0] - start[0], end[1] - start[1])


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_planar_graph(
    healed_segments: list[dict],
    decimals: int = 2,
) -> tuple[nx.Graph, Optional[nx.PlanarEmbedding], dict]:
    """
    Build a planar graph from healed wall segments.

    Parameters
    ----------
    healed_segments : list[dict]
        Segments with keys: start, end, stroke_width, color, dash_pattern.
    decimals : int
        Rounding precision for node coordinates (default 2).

    Returns
    -------
    G : nx.Graph
        Graph with node attrs {x, y, degree} and edge attrs
        {wall_type, thickness, length, color}.
    embedding : nx.PlanarEmbedding or None
        Planar embedding if graph is planar, else None.
    report : dict
        Statistics about the graph construction.
    """
    G = nx.Graph()

    skipped_zero = 0

    for seg in healed_segments:
        p1 = _point_key(seg["start"], decimals)
        p2 = _point_key(seg["end"], decimals)

        # Skip zero-length segments (degenerate after rounding)
        if p1 == p2:
            skipped_zero += 1
            continue

        # Add nodes with coordinate attrs
        if p1 not in G:
            G.add_node(p1, x=p1[0], y=p1[1])
        if p2 not in G:
            G.add_node(p2, x=p2[0], y=p2[1])

        # Edge attributes from segment metadata
        thickness = seg.get("stroke_width", 0.0)
        color = seg.get("color", (0, 0, 0))
        length = _seg_length(p1, p2)

        # If edge already exists, keep the thicker one
        if G.has_edge(p1, p2):
            existing = G[p1][p2].get("thickness", 0.0)
            if thickness <= existing:
                continue

        G.add_edge(
            p1, p2,
            wall_type="unknown",
            thickness=thickness,
            length=length,
            color=color,
        )

    # Compute degree attribute for each node
    for node in G.nodes():
        G.nodes[node]["degree"] = G.degree(node)

    # Planarity check
    is_planar, embedding = nx.check_planarity(G)

    if not is_planar:
        logger.warning(
            "Graph is NOT planar (%d nodes, %d edges). "
            "Room detection will fall back to polygonize.",
            G.number_of_nodes(), G.number_of_edges(),
        )
        embedding = None

    # Degree distribution
    degree_dist: dict[int, int] = {}
    for node in G.nodes():
        d = G.degree(node)
        degree_dist[d] = degree_dist.get(d, 0) + 1

    report = {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "is_planar": is_planar,
        "skipped_zero_length": skipped_zero,
        "connected_components": nx.number_connected_components(G),
        "degree_distribution": degree_dist,
        "dead_ends": degree_dist.get(1, 0),
    }

    logger.info(
        "Planar graph built: %d nodes, %d edges, planar=%s, "
        "components=%d, dead_ends=%d",
        report["nodes"], report["edges"], report["is_planar"],
        report["connected_components"], report["dead_ends"],
    )

    return G, embedding, report
