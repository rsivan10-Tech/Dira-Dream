/**
 * Wall merger — combines short collinear wall segments into continuous walls.
 *
 * The healing pipeline splits walls at every intersection, producing hundreds
 * of tiny fragments (0.1–0.5m). These are too short to cut door/window holes
 * into. This module merges collinear, adjacent fragments back into long wall
 * runs (3–10m) suitable for ExtrudeGeometry with openings.
 *
 * Door gaps (65–100cm) are preserved because MERGE_GAP is much smaller.
 */

import type { Wall, WallType, Point } from '@/types/floorplan';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface MergedWall {
  id: string;
  start: Point;
  end: Point;
  wall_type: WallType;
  width: number;
  is_structural: boolean;
  is_modifiable: boolean;
  confidence: number;
  rooms: string[];
  originalIds: string[];
}

// ---------------------------------------------------------------------------
// Tuning constants
// ---------------------------------------------------------------------------

/** Max angle difference (radians) to consider two segments collinear. */
const ANGLE_TOL = (3 * Math.PI) / 180;

/** Max perpendicular distance (PDF points) for "same line". */
const PERP_TOL = 8;

/**
 * Max gap (PDF points) between segment endpoints to merge them.
 * ~9cm at 1:50 — merges healing artifacts but preserves door gaps (35+ pt).
 */
const MERGE_GAP = 5;

/** Min wall length (PDF points) to include in output. Filters dust. */
const MIN_WALL_LENGTH = 3;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Normalize angle to [0, π). */
function normAngle(a: number): number {
  let n = a % Math.PI;
  if (n < 0) n += Math.PI;
  return n;
}

function wallLength(w: { start: Point; end: Point }): number {
  const dx = w.end.x - w.start.x;
  const dy = w.end.y - w.start.y;
  return Math.sqrt(dx * dx + dy * dy);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

export function mergeCollinearWalls(walls: Wall[]): MergedWall[] {
  if (walls.length === 0) return [];

  // 1. Compute angle for each wall
  const angles = walls.map((w) => {
    const dx = w.end.x - w.start.x;
    const dy = w.end.y - w.start.y;
    return normAngle(Math.atan2(dy, dx));
  });

  // 2. Group walls by angle (within tolerance)
  const used = new Uint8Array(walls.length);
  const angleGroups: number[][] = [];

  for (let i = 0; i < walls.length; i++) {
    if (used[i]) continue;
    const group = [i];
    used[i] = 1;
    for (let j = i + 1; j < walls.length; j++) {
      if (used[j]) continue;
      const diff = Math.abs(angles[i] - angles[j]);
      if (Math.min(diff, Math.PI - diff) <= ANGLE_TOL) {
        group.push(j);
        used[j] = 1;
      }
    }
    angleGroups.push(group);
  }

  const result: MergedWall[] = [];
  let nextId = 0;

  for (const group of angleGroups) {
    // Reference direction from the longest segment in the group
    let refIdx = group[0];
    for (const idx of group) {
      if (wallLength(walls[idx]) > wallLength(walls[refIdx])) refIdx = idx;
    }
    const refAngle = angles[refIdx];
    const dirX = Math.cos(refAngle);
    const dirY = Math.sin(refAngle);
    const perpX = -dirY;
    const perpY = dirX;

    // Perpendicular position for each wall (midpoint projected onto perp axis)
    const perpPos = group.map((idx) => {
      const w = walls[idx];
      const mx = (w.start.x + w.end.x) / 2;
      const my = (w.start.y + w.end.y) / 2;
      return mx * perpX + my * perpY;
    });

    // 3. Sub-group by perpendicular position ("same line")
    const perpUsed = new Uint8Array(group.length);
    for (let a = 0; a < group.length; a++) {
      if (perpUsed[a]) continue;
      const lineIdxes: number[] = [a];
      perpUsed[a] = 1;
      for (let b = a + 1; b < group.length; b++) {
        if (perpUsed[b]) continue;
        if (Math.abs(perpPos[a] - perpPos[b]) <= PERP_TOL) {
          lineIdxes.push(b);
          perpUsed[b] = 1;
        }
      }

      // 4. Project each wall onto direction axis and sort
      const projected = lineIdxes.map((gi) => {
        const idx = group[gi];
        const w = walls[idx];
        const t1 = w.start.x * dirX + w.start.y * dirY;
        const t2 = w.end.x * dirX + w.end.y * dirY;
        return { idx, tMin: Math.min(t1, t2), tMax: Math.max(t1, t2) };
      });
      projected.sort((a, b) => a.tMin - b.tMin);

      // 5. Merge overlapping/adjacent segments
      let cur = {
        tMin: projected[0].tMin,
        tMax: projected[0].tMax,
        wallIdxes: [projected[0].idx],
      };

      const flush = () => {
        // Find the actual endpoints (extremes in the original wall data)
        let minT = Infinity;
        let maxT = -Infinity;
        let minPt: Point = walls[cur.wallIdxes[0]].start;
        let maxPt: Point = walls[cur.wallIdxes[0]].start;

        for (const idx of cur.wallIdxes) {
          const w = walls[idx];
          for (const pt of [w.start, w.end]) {
            const t = pt.x * dirX + pt.y * dirY;
            if (t < minT) { minT = t; minPt = pt; }
            if (t > maxT) { maxT = t; maxPt = pt; }
          }
        }

        // Skip very short merged walls (noise)
        const len = Math.sqrt(
          (maxPt.x - minPt.x) ** 2 + (maxPt.y - minPt.y) ** 2,
        );
        if (len < MIN_WALL_LENGTH) return;

        // Determine wall type by priority: mamad > exterior > structural > partition
        const typeCounts: Partial<Record<WallType, number>> = {};
        let bestWidth = 0;
        for (const idx of cur.wallIdxes) {
          const w = walls[idx];
          typeCounts[w.wall_type] = (typeCounts[w.wall_type] || 0) + 1;
          bestWidth = Math.max(bestWidth, w.width);
        }
        const priority: WallType[] = ['mamad', 'exterior', 'structural', 'partition'];
        let wallType: WallType = 'partition';
        for (const t of priority) {
          if ((typeCounts[t] || 0) > 0) { wallType = t; break; }
        }

        result.push({
          id: `merged_${nextId++}`,
          start: { x: minPt.x, y: minPt.y },
          end: { x: maxPt.x, y: maxPt.y },
          wall_type: wallType,
          width: bestWidth,
          is_structural: wallType !== 'partition',
          is_modifiable: wallType === 'partition',
          confidence: 1,
          rooms: [],
          originalIds: cur.wallIdxes.map((i) => walls[i].id),
        });
      };

      for (let k = 1; k < projected.length; k++) {
        const next = projected[k];
        if (next.tMin <= cur.tMax + MERGE_GAP) {
          cur.tMax = Math.max(cur.tMax, next.tMax);
          cur.wallIdxes.push(next.idx);
        } else {
          flush();
          cur = { tMin: next.tMin, tMax: next.tMax, wallIdxes: [next.idx] };
        }
      }
      flush();
    }
  }

  console.log(
    `[3D] Wall merger: ${walls.length} segments → ${result.length} merged walls`,
  );
  return result;
}

/** Convert a MergedWall to a Wall (for compatibility with existing components). */
export function mergedToWall(mw: MergedWall): Wall {
  return {
    id: mw.id,
    start: mw.start,
    end: mw.end,
    width: mw.width,
    wall_type: mw.wall_type,
    is_structural: mw.is_structural,
    is_modifiable: mw.is_modifiable,
    confidence: mw.confidence,
    rooms: mw.rooms,
  };
}

// ---------------------------------------------------------------------------
// Door zone filter — remove wall segments that occupy door openings
// ---------------------------------------------------------------------------

/** Angle tolerance (radians) for "parallel to door" check (~20°). */
const DOOR_PARALLEL_TOL = 0.35;

/** Perpendicular tolerance (PDF points) for "on the same wall line". */
const DOOR_PERP_TOL = 15;

/**
 * Remove wall segments whose midpoint falls inside a detected door opening.
 *
 * Doors are gaps between wall segments — the gap IS the opening.  But short
 * wall fragments near the gap can visually block the doorway.  This function
 * removes those fragments so the gap renders as an open passage.
 *
 * Only removes walls that are roughly parallel to the door direction
 * (perpendicular walls that happen to pass through the door area are kept).
 */
export function filterDoorZones(
  walls: Wall[],
  openings: Array<{
    type: string;
    endpoints?: [Point, Point];
    position: Point;
    width_cm: number;
  }>,
): Wall[] {
  // Build exclusion zones from door openings that have endpoints
  const zones: Array<{
    cx: number;
    cy: number;
    halfW: number; // half-width along door direction
    angle: number; // door direction
    dirX: number;
    dirY: number;
    perpX: number;
    perpY: number;
  }> = [];

  for (const op of openings) {
    if (op.type !== 'door' || !op.endpoints) continue;
    const [p1, p2] = op.endpoints;
    const dx = p2.x - p1.x;
    const dy = p2.y - p1.y;
    const len = Math.sqrt(dx * dx + dy * dy);
    if (len < 1) continue;
    const angle = Math.atan2(dy, dx);
    zones.push({
      cx: (p1.x + p2.x) / 2,
      cy: (p1.y + p2.y) / 2,
      halfW: len / 2 + 2, // small margin
      angle,
      dirX: dx / len,
      dirY: dy / len,
      perpX: -dy / len,
      perpY: dx / len,
    });
  }

  if (zones.length === 0) return walls;

  const before = walls.length;
  const filtered = walls.filter((w) => {
    const mx = (w.start.x + w.end.x) / 2;
    const my = (w.start.y + w.end.y) / 2;

    // Wall direction for parallelism check
    const wdx = w.end.x - w.start.x;
    const wdy = w.end.y - w.start.y;
    const wAngle = Math.atan2(wdy, wdx);

    for (const zone of zones) {
      // Check parallelism first (skip perpendicular walls)
      const angleDiff = Math.abs(wAngle - zone.angle) % Math.PI;
      const isParallel =
        angleDiff < DOOR_PARALLEL_TOL ||
        angleDiff > Math.PI - DOOR_PARALLEL_TOL;
      if (!isParallel) continue;

      // Project midpoint onto door-local coordinates
      const relX = mx - zone.cx;
      const relY = my - zone.cy;
      const alongDoor = relX * zone.dirX + relY * zone.dirY;
      const perpDoor = Math.abs(relX * zone.perpX + relY * zone.perpY);

      if (Math.abs(alongDoor) < zone.halfW && perpDoor < DOOR_PERP_TOL) {
        return false; // Wall is inside door zone — remove
      }
    }
    return true;
  });

  if (filtered.length < before) {
    console.log(
      `[3D] Door zone filter: removed ${before - filtered.length} wall segments from ${zones.length} door zones`,
    );
  }
  return filtered;
}
