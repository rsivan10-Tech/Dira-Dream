/**
 * Utilities for matching 2D openings (doors/windows) to 3D wall segments
 * and computing their positions along walls for ExtrudeGeometry holes.
 */

import type { Wall, Opening, OpeningType } from '@/types/floorplan';
import {
  pdfPointsToThree,
  DOOR_HEIGHT_M,
  WINDOW_HEIGHT_M,
  WINDOW_SILL_M,
  GLASS_DOOR_HEIGHT_M,
} from './coordinateUtils';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface OpeningOnWall {
  /** Distance along the wall from start to opening center (meters). */
  offset: number;
  /** Opening width (meters). */
  width: number;
  /** Opening height (meters). */
  height: number;
  /** Height from floor to bottom of opening (meters). */
  sillHeight: number;
  type: OpeningType;
  id: string;
}

/** Wall geometry in Three.js XZ space (precomputed for matching). */
interface Wall3D {
  id: string;
  sx: number;
  sz: number;
  ex: number;
  ez: number;
  length: number;
}

// ---------------------------------------------------------------------------
// Geometry helpers
// ---------------------------------------------------------------------------

/**
 * Project a point onto a line segment and return distance + parametric t.
 * All coordinates in the XZ plane (Three.js ground plane).
 */
function pointToSegmentProjection(
  px: number,
  pz: number,
  sx: number,
  sz: number,
  ex: number,
  ez: number,
): { distance: number; t: number } {
  const dx = ex - sx;
  const dz = ez - sz;
  const lenSq = dx * dx + dz * dz;

  if (lenSq < 1e-10) {
    // Degenerate segment
    const d = Math.sqrt((px - sx) ** 2 + (pz - sz) ** 2);
    return { distance: d, t: 0 };
  }

  // Parametric projection clamped to [0, 1]
  let t = ((px - sx) * dx + (pz - sz) * dz) / lenSq;
  t = Math.max(0, Math.min(1, t));

  const projX = sx + t * dx;
  const projZ = sz + t * dz;
  const distance = Math.sqrt((px - projX) ** 2 + (pz - projZ) ** 2);

  return { distance, t };
}

// ---------------------------------------------------------------------------
// Dimension lookup
// ---------------------------------------------------------------------------

function getOpeningHeight(type: OpeningType): number {
  switch (type) {
    case 'door':
      return DOOR_HEIGHT_M;
    case 'french_door':
    case 'sliding_door':
      return GLASS_DOOR_HEIGHT_M;
    case 'window':
      return WINDOW_HEIGHT_M;
  }
}

function getSillHeight(type: OpeningType): number {
  switch (type) {
    case 'door':
    case 'french_door':
    case 'sliding_door':
      return 0;
    case 'window':
      return WINDOW_SILL_M;
  }
}

// ---------------------------------------------------------------------------
// Main matching function
// ---------------------------------------------------------------------------

/** Maximum distance (meters) from opening to wall to be considered a match. */
const MATCH_THRESHOLD_M = 0.5;

/** Minimum margin (meters) between opening edge and wall edge. */
const EDGE_MARGIN_M = 0.02;

/**
 * Match each opening to its nearest wall and compute the position
 * along that wall where the opening should be cut.
 *
 * Returns a Map from wall ID to sorted array of openings on that wall.
 */
export function matchOpeningsToWalls(
  walls: Wall[],
  openings: Opening[],
  scaleFactor: number,
): Map<string, OpeningOnWall[]> {
  if (openings.length === 0) return new Map();

  // Pre-convert walls to 3D coordinates
  const walls3d: Wall3D[] = walls.map((w) => {
    const s = pdfPointsToThree(w.start.x, w.start.y, scaleFactor);
    const e = pdfPointsToThree(w.end.x, w.end.y, scaleFactor);
    const dx = e.x - s.x;
    const dz = e.z - s.z;
    return {
      id: w.id,
      sx: s.x,
      sz: s.z,
      ex: e.x,
      ez: e.z,
      length: Math.sqrt(dx * dx + dz * dz),
    };
  });

  const result = new Map<string, OpeningOnWall[]>();

  for (const opening of openings) {
    const pos = pdfPointsToThree(opening.position.x, opening.position.y, scaleFactor);

    let bestWall: Wall3D | null = null;
    let bestDist = Infinity;
    let bestT = 0;

    for (const w3d of walls3d) {
      if (w3d.length < 0.01) continue; // skip degenerate walls
      const { distance, t } = pointToSegmentProjection(
        pos.x, pos.z, w3d.sx, w3d.sz, w3d.ex, w3d.ez,
      );
      if (distance < bestDist) {
        bestDist = distance;
        bestWall = w3d;
        bestT = t;
      }
    }

    if (!bestWall || bestDist > MATCH_THRESHOLD_M) {
      console.warn(
        `[3D] Opening ${opening.id} (${opening.type}) not matched to any wall — ` +
        `nearest distance: ${bestDist.toFixed(3)}m`,
      );
      continue;
    }

    const widthM = opening.width_cm / 100;
    const offset = bestT * bestWall.length;

    // Clamp so opening doesn't exceed wall bounds
    const halfW = widthM / 2;
    const clampedOffset = Math.max(
      halfW + EDGE_MARGIN_M,
      Math.min(bestWall.length - halfW - EDGE_MARGIN_M, offset),
    );

    const entry: OpeningOnWall = {
      offset: clampedOffset,
      width: widthM,
      height: getOpeningHeight(opening.type),
      sillHeight: getSillHeight(opening.type),
      type: opening.type,
      id: opening.id,
    };

    const list = result.get(bestWall.id) ?? [];
    list.push(entry);
    result.set(bestWall.id, list);
  }

  // Sort each wall's openings by offset and filter overlaps
  for (const [wallId, list] of result) {
    list.sort((a, b) => a.offset - b.offset);

    // Remove overlapping openings (keep the first one)
    const filtered: OpeningOnWall[] = [list[0]];
    for (let i = 1; i < list.length; i++) {
      const prev = filtered[filtered.length - 1];
      const curr = list[i];
      const gap = (curr.offset - curr.width / 2) - (prev.offset + prev.width / 2);
      if (gap >= EDGE_MARGIN_M) {
        filtered.push(curr);
      } else {
        console.warn(
          `[3D] Skipping overlapping opening ${curr.id} on wall ${wallId}`,
        );
      }
    }
    result.set(wallId, filtered);
  }

  return result;
}
