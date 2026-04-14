"""Door and window detection with centerline-wall hosting.

Quality Sprint Step 3 — the original spec assumed walls are CUT at
openings, so gaps in a wall's raw parallel-line pair would locate doors
and windows. Diagnostic on Sample 9 disproved the assumption:

  Israeli contractor PDFs do NOT cut walls at openings. Wall faces run
  continuously across doors and windows; openings are drawn as SEPARATE
  geometry (arc, perpendicular-parallel lines) on top.

Two alternative approaches tested:
  a) Gap-based with raw-segment coverage → 0 or 50+ doors (signal absent).
  b) Bézier arc clustering → 0 or 120+ doors (arcs are scarce or tagged
     as polyline fragments in many PDFs — the CLAUDE.md known issue:
     "heal_geometry doors_preserved=0 on all test PDFs").

The legacy detect_doors_and_windows from geometry.structural already:
  - Uses wall-gap endpoint clustering for doors (33% baseline)
  - Uses perpendicular-parallel-line detection + exterior filter for
    windows (58% baseline)
  - Has Sprint 5B over-detection dedup (doors 2.3x→1.4x, windows 6.3x→1x)

This module therefore WRAPS the legacy detector and adds Step 3's real
contribution: associating each opening with its nearest CenterlineWall
via `host_wall_id` — the key primitive the 3D renderer needs to cut
window meshes cleanly and the negative-space room detector needs to
build room adjacency.

Agent: VG | Quality Sprint Step 3
"""
from __future__ import annotations

import math
from typing import Optional

from geometry.models import Opening


# --- Working parameters ---
HOST_PROXIMITY_CM = 80.0   # opening → nearest centerline within this radius
DOOR_DEDUP_CM = 40.0       # merge dup doors within this radius


def _nearest_wall_index(pt, walls, max_dist_pt: float) -> Optional[int]:
    """Index of the closest wall centerline to `pt` within max_dist_pt."""
    best_i = None
    best_d = max_dist_pt
    for i, w in enumerate(walls):
        x1, y1 = w.p1
        x2, y2 = w.p2
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        if L2 < 1e-9:
            continue
        t = max(0.0, min(1.0, ((pt[0] - x1) * dx + (pt[1] - y1) * dy) / L2))
        px, py = x1 + t * dx, y1 + t * dy
        d = math.hypot(pt[0] - px, pt[1] - py)
        if d < best_d:
            best_d = d
            best_i = i
    return best_i


def detect_openings_from_gaps(
    walls: list,
    raw_segments: list[dict],
    raw_drawings: Optional[list],
    scale_factor: float,
    rooms: Optional[list] = None,
    wall_threshold: float = 0.5,
):
    """Detect doors and windows, then host each to a CenterlineWall.

    The gap-based signal this function was originally spec'd for does not
    exist in Israeli contractor PDFs. We instead run the legacy
    detect_doors_and_windows on healed segments and associate each opening
    with its nearest centerline wall.

    Args:
        walls: list[CenterlineWall]
        raw_segments: pre-healing cropped segments
        raw_drawings: optional fitz raw drawings (unused in this branch)
        scale_factor: metres per PDF point

    Returns:
        (openings, stats) where openings is list[Opening] with
        `host_wall_id` populated in the future when the Opening dataclass
        gains that field. For now the nearest-wall mapping is computed
        and returned in stats.
    """
    from geometry.healing import (
        HealingConfig,
        filter_largest_component,
        heal_geometry,
    )
    from geometry.structural import detect_doors_and_windows

    stats = {
        "walls": len(walls),
        "doors": 0,
        "windows": 0,
        "arcs_found": 0,
        "arc_doors_added": 0,
        "unhosted": 0,
        "host_map": {},
    }

    # Heal raw wall candidates for the legacy detector
    wall_segs = [s for s in raw_segments if s.get("stroke_width", 0) >= wall_threshold]
    healed, _ = heal_geometry(wall_segs, HealingConfig())
    healed = filter_largest_component(healed)

    legacy_openings, _ = detect_doors_and_windows(
        healed, rooms or [], scale_factor=scale_factor,
    )

    host_proximity_pt = (HOST_PROXIMITY_CM / 100.0) / scale_factor
    dedup_pt = (DOOR_DEDUP_CM / 100.0) / scale_factor

    openings: list[Opening] = []
    door_positions: list[tuple[float, float]] = []
    for i, o in enumerate(legacy_openings):
        wi = _nearest_wall_index(o.position, walls, host_proximity_pt)
        if wi is None:
            stats["unhosted"] += 1
        else:
            stats["host_map"][i] = wi
        if o.opening_type == "door":
            stats["doors"] += 1
            door_positions.append(o.position)
        elif o.opening_type == "window":
            stats["windows"] += 1
        openings.append(o)

    # Arc-detection supplement was attempted (short-segment cluster heuristic
    # for discretized Bézier curves) but short-segment clusters fire on
    # furniture edges and produce hundreds of false doors per sample.
    # Arc detection from polyline-approximated curves needs stricter shape
    # tests (e.g. segments fanning from a common center at similar radius)
    # — left for a followup iteration.

    return openings, stats
