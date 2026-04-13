"""Negative-space room detection.

Quality Sprint — detect rooms as the empty spaces between centerline walls
(envelope minus wall mass), instead of planar-graph face enumeration which
fails when segments don't form closed rings.

Agent: VG | Quality Sprint Step 2
"""
from __future__ import annotations


def detect_rooms_negative_space(walls, texts, scale_factor: float, metadata: dict):
    """Extract room polygons by subtracting the wall mass from the apartment envelope.

    Not yet implemented — Quality Sprint Step 2.
    """
    raise NotImplementedError(
        "room_detection.detect_rooms_negative_space — arrives in Step 2"
    )
