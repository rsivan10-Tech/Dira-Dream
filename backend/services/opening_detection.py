"""Gap-based door and window detection.

Quality Sprint — scan each centerline wall for breaks in its source parallel
pair and classify each gap by the PDF primitives found inside (arc = door,
perpendicular parallel lines = window, wide gap with no arc = glass door).

Agent: VG | Quality Sprint Step 3
"""
from __future__ import annotations


def detect_openings_from_gaps(walls, raw_segments, raw_drawings, scale_factor: float):
    """Find door/window/glass_door openings by inspecting wall gaps.

    Not yet implemented — Quality Sprint Step 3.
    """
    raise NotImplementedError(
        "opening_detection.detect_openings_from_gaps — arrives in Step 3"
    )
