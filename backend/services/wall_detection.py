"""Parallel-line wall detection with centerline extraction.

Quality Sprint — replaces stroke-width wall classification with
measurement-based classification from parallel line pairs. Real Israeli PDFs
draw each wall as two parallel strokes (inner + outer face); this module
collapses them into a single centerline carrying the measured thickness.

Agent: VG | Quality Sprint Step 1
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CenterlineWall:
    """A single wall represented by its centerline and measured thickness.

    Coordinates are in PDF points. Thickness is in real-world cm (already
    converted via scale_factor). Source segments are retained so the opening
    detector can inspect the original parallel pair for gaps.
    """

    id: str
    p1: tuple[float, float]
    p2: tuple[float, float]
    thickness_cm: float
    wall_type: str = "unknown"  # exterior | mamad | partition | unknown
    confidence: float = 0.0
    source_segment_ids: list[int] = field(default_factory=list)
    # (start_pos, end_pos) in PDF points along the centerline, for gap hosting
    gaps: list[tuple[float, float]] = field(default_factory=list)


def find_centerline_walls(segments, scale_factor: float, histogram: dict | None = None):
    """Collapse parallel line pairs into centerline walls.

    Not yet implemented — Quality Sprint Step 1.
    """
    raise NotImplementedError(
        "wall_detection.find_centerline_walls — arrives in Step 1"
    )
