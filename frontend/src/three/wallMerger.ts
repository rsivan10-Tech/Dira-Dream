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

/**
 * Min wall length (PDF points) to include in output.
 * At 1:50 scale, 20pt ≈ 35cm — filters bathroom fixtures, annotation
 * fragments, and other non-wall geometry that was classified as walls.
 */
const MIN_WALL_LENGTH = 20;

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

        // Determine wall type: structural types (exterior, mamad, structural)
        // take priority over partition. If ANY constituent segment has a
        // structural type, the merged wall inherits it — this prevents
        // exterior walls from being downgraded to partition when merged with
        // adjacent interior segments, which would break window matching.
        const typeCounts: Partial<Record<WallType, number>> = {};
        let bestWidth = 0;
        for (const idx of cur.wallIdxes) {
          const w = walls[idx];
          typeCounts[w.wall_type] = (typeCounts[w.wall_type] || 0) + 1;
          bestWidth = Math.max(bestWidth, w.width);
        }
        // Priority: mamad > exterior > structural > partition > unknown
        const TYPE_PRIORITY: WallType[] = ['mamad', 'exterior', 'structural', 'partition', 'unknown'];
        let wallType: WallType = 'partition';
        for (const t of TYPE_PRIORITY) {
          if ((typeCounts[t] ?? 0) > 0) {
            wallType = t;
            break;
          }
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

// ---------------------------------------------------------------------------
// Parallel wall merger — collapses double/triple-line walls into single walls
// ---------------------------------------------------------------------------

/** Max angle diff (radians) for parallel check (~5°). */
const PARALLEL_ANGLE_TOL = (5 * Math.PI) / 180;

/** Max perpendicular distance (PDF points) between parallel walls.
 *  35cm at 1:50 scale ≈ 20pt. We use a generous 25pt to cover mamad (35cm). */
const MAX_PERP_DIST_PT = 25;

/** Minimum overlap fraction of the shorter wall to consider a pair. */
const MIN_OVERLAP_FRAC = 0.3;

/**
 * Merge parallel overlapping walls into single walls.
 *
 * Israeli PDFs draw exterior walls as 2-3 parallel lines (inner face,
 * outer face, fill). After collinear merging, these produce separate
 * wall meshes at the same position. This step collapses them into one
 * wall per physical wall, with thickness = perpendicular distance.
 */
export function mergeParallelWalls(walls: MergedWall[]): MergedWall[] {
  if (walls.length <= 1) return walls;

  // Compute angle + direction for each wall
  const info = walls.map((w) => {
    const dx = w.end.x - w.start.x;
    const dy = w.end.y - w.start.y;
    const len = Math.sqrt(dx * dx + dy * dy);
    const ang = normAngle(Math.atan2(dy, dx));
    return { dx, dy, len, ang };
  });

  // Find parallel pairs
  interface ParallelPair {
    i: number;
    j: number;
    perpDist: number;
    overlap: number;
  }
  const pairs: ParallelPair[] = [];

  for (let i = 0; i < walls.length; i++) {
    const a = info[i];
    if (a.len < 0.01) continue;
    const dirX = a.dx / a.len;
    const dirY = a.dy / a.len;

    for (let j = i + 1; j < walls.length; j++) {
      const b = info[j];
      if (b.len < 0.01) continue;

      // Angle check
      const adiff = Math.abs(a.ang - b.ang);
      if (Math.min(adiff, Math.PI - adiff) > PARALLEL_ANGLE_TOL) continue;

      // Perpendicular distance: midpoint of wall j to line of wall i
      const bmx = (walls[j].start.x + walls[j].end.x) / 2;
      const bmy = (walls[j].start.y + walls[j].end.y) / 2;
      const cross = Math.abs(
        (bmx - walls[i].start.x) * dirY - (bmy - walls[i].start.y) * dirX,
      );
      const perpDist = cross; // already divided by unit-length dir
      if (perpDist > MAX_PERP_DIST_PT) continue;

      // Overlap check: project both onto shared direction axis
      const aT1 = walls[i].start.x * dirX + walls[i].start.y * dirY;
      const aT2 = walls[i].end.x * dirX + walls[i].end.y * dirY;
      const aMin = Math.min(aT1, aT2);
      const aMax = Math.max(aT1, aT2);
      const bT1 = walls[j].start.x * dirX + walls[j].start.y * dirY;
      const bT2 = walls[j].end.x * dirX + walls[j].end.y * dirY;
      const bMin = Math.min(bT1, bT2);
      const bMax = Math.max(bT1, bT2);

      const overlap = Math.max(0, Math.min(aMax, bMax) - Math.max(aMin, bMin));
      const shorter = Math.min(a.len, b.len);
      if (shorter < 0.01 || overlap / shorter < MIN_OVERLAP_FRAC) continue;

      pairs.push({ i, j, perpDist, overlap });
    }
  }

  // Sort pairs by perpendicular distance (closest first) for greedy merge
  pairs.sort((a, b) => a.perpDist - b.perpDist);

  const consumed = new Set<number>();
  const result: MergedWall[] = [];
  let nextId = 0;

  for (const pair of pairs) {
    if (consumed.has(pair.i) || consumed.has(pair.j)) continue;
    consumed.add(pair.i);
    consumed.add(pair.j);

    const wa = walls[pair.i];
    const wb = walls[pair.j];
    const ia = info[pair.i];

    // Merged position: midpoint between the two parallel lines
    const dirX = ia.dx / ia.len;
    const dirY = ia.dy / ia.len;

    // Project all 4 endpoints onto direction axis to find union extent
    const allPts = [wa.start, wa.end, wb.start, wb.end];
    let minT = Infinity, maxT = -Infinity;
    for (const pt of allPts) {
      const t = pt.x * dirX + pt.y * dirY;
      if (t < minT) minT = t;
      if (t > maxT) maxT = t;
    }

    // Midpoint perpendicular offset: average the midpoints of both walls
    const centerX = (wa.start.x + wa.end.x + wb.start.x + wb.end.x) / 4;
    const centerY = (wa.start.y + wa.end.y + wb.start.y + wb.end.y) / 4;

    // Perpendicular axis
    const perpX = -dirY;
    const perpY = dirX;
    const cPerp = centerX * perpX + centerY * perpY;

    // Reconstruct start/end at the merged centerline
    const startX = dirX * minT + perpX * cPerp;
    const startY = dirY * minT + perpY * cPerp;
    const endX = dirX * maxT + perpX * cPerp;
    const endY = dirY * maxT + perpY * cPerp;

    // Type priority
    const TYPE_PRIORITY: WallType[] = ['mamad', 'exterior', 'structural', 'partition', 'unknown'];
    let wallType: WallType = wa.wall_type;
    for (const t of TYPE_PRIORITY) {
      if (wa.wall_type === t || wb.wall_type === t) {
        wallType = t;
        break;
      }
    }

    result.push({
      id: `pmerged_${nextId++}`,
      start: { x: startX, y: startY },
      end: { x: endX, y: endY },
      wall_type: wallType,
      width: Math.max(wa.width, wb.width),
      is_structural: wallType !== 'partition',
      is_modifiable: wallType === 'partition',
      confidence: Math.max(wa.confidence, wb.confidence),
      rooms: [...new Set([...wa.rooms, ...wb.rooms])],
      originalIds: [...wa.originalIds, ...wb.originalIds],
    });
  }

  // Add unconsumed walls as-is
  for (let i = 0; i < walls.length; i++) {
    if (!consumed.has(i)) result.push(walls[i]);
  }

  console.log(
    `[3D] Parallel merger: ${walls.length} → ${result.length} walls (${pairs.length} pairs found, ${consumed.size / 2} merged)`,
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
