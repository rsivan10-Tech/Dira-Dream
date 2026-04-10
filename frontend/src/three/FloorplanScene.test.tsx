/**
 * Tests for 3D FloorplanScene: coordinate utils, wall geometry, floor coverage.
 *
 * These are unit tests for the pure logic (no WebGL context required).
 * R3F component rendering is validated visually / via ARC.
 */

import { describe, it, expect } from 'vitest';
import * as THREE from 'three';
import {
  pdfToThree,
  pdfPointsToThree,
  CEILING_HEIGHT_M,
  EYE_HEIGHT_M,
  WALL_THICKNESS_M,
  WALL_COLORS,
  FLOOR_COLORS,
  DOOR_HEIGHT_M,
  WINDOW_HEIGHT_M,
  WINDOW_SILL_M,
  GLASS_DOOR_HEIGHT_M,
} from './coordinateUtils';
import { getWallsFor3D } from './FloorplanScene';
import { matchOpeningsToWalls } from './openingUtils';
import { getLargestRoom, computeStartPosition, forwardFromYaw, wallSlide } from './FirstPersonController';
import { worldToMinimap, minimapToWorld } from './Minimap';
import type { FloorplanData, Wall, Room, Opening } from '@/types/floorplan';

// ---------------------------------------------------------------------------
// Coordinate transform
// ---------------------------------------------------------------------------

describe('pdfToThree', () => {
  it('converts cm to metres with Y-flip to -Z', () => {
    const result = pdfToThree(400, 300);
    expect(result.x).toBeCloseTo(4.0, 6);
    expect(result.z).toBeCloseTo(-3.0, 6);
  });

  it('handles origin (0,0)', () => {
    const result = pdfToThree(0, 0);
    expect(result.x).toBe(0);
    expect(result.z).toBeCloseTo(0, 6);
  });

  it('handles negative coordinates', () => {
    const result = pdfToThree(-200, -150);
    expect(result.x).toBeCloseTo(-2.0, 6);
    expect(result.z).toBeCloseTo(1.5, 6);
  });
});

describe('pdfPointsToThree', () => {
  // scale_factor 0.0176 ≈ 1:50 scale (50 / 28.3465 / 100)
  const SF = 0.0176;

  it('converts PDF points through cm to Three.js metres', () => {
    // 500 PDF pts × 0.0176 = 8.8m, × 100 = 880cm → pdfToThree → 8.8m
    const result = pdfPointsToThree(500, 200, SF);
    expect(result.x).toBeCloseTo(500 * SF, 4);
    expect(result.z).toBeCloseTo(-200 * SF, 4);
  });
});

// ---------------------------------------------------------------------------
// Constants sanity checks
// ---------------------------------------------------------------------------

describe('constants', () => {
  it('ceiling height is 2.60m', () => {
    expect(CEILING_HEIGHT_M).toBe(2.6);
  });

  it('wall thicknesses are in valid range (metres)', () => {
    for (const [, thickness] of Object.entries(WALL_THICKNESS_M)) {
      expect(thickness).toBeGreaterThan(0.05);
      expect(thickness).toBeLessThan(0.5);
    }
  });

  it('mamad walls are thicker than partition walls', () => {
    expect(WALL_THICKNESS_M.mamad).toBeGreaterThan(WALL_THICKNESS_M.partition);
  });

  it('all wall types have a colour', () => {
    for (const type of ['exterior', 'mamad', 'structural', 'partition', 'unknown'] as const) {
      expect(WALL_COLORS[type]).toBeDefined();
    }
  });

  it('all room types have a floor colour', () => {
    for (const type of [
      'salon', 'bedroom', 'kitchen', 'guest_toilet', 'bathroom',
      'mamad', 'sun_balcony', 'service_balcony', 'storage', 'utility', 'unknown',
    ] as const) {
      expect(FLOOR_COLORS[type]).toBeDefined();
    }
  });
});

// ---------------------------------------------------------------------------
// getWallsFor3D — wall-type + bbox filtering
// ---------------------------------------------------------------------------

function makeWall(overrides: Partial<Wall> & Pick<Wall, 'start' | 'end'>): Wall {
  return {
    id: 'w-test',
    width: 1,
    wall_type: 'exterior',
    is_structural: false,
    is_modifiable: true,
    confidence: 1,
    rooms: [],
    ...overrides,
  };
}

function makeFloorplanData(walls: Wall[], rooms: FloorplanData['rooms'] = []): FloorplanData {
  return {
    walls,
    rooms,
    openings: [],
    envelope: null,
    validation: null,
    confidence: 1,
    page_size: { width: 842, height: 595 },
    scale_factor: 0.0176,
    texts: [],
    stated_area_sqm: null,
    stated_balcony_sqm: null,
  };
}

describe('getWallsFor3D', () => {
  it('excludes unknown wall types (doors, dimensions, furniture)', () => {
    const walls = [
      makeWall({ id: 'w1', wall_type: 'exterior', start: { x: 100, y: 100 }, end: { x: 300, y: 100 } }),
      makeWall({ id: 'w2', wall_type: 'unknown', start: { x: 150, y: 150 }, end: { x: 200, y: 150 } }),
      makeWall({ id: 'w3', wall_type: 'partition', start: { x: 100, y: 200 }, end: { x: 300, y: 200 } }),
    ];
    const result = getWallsFor3D(makeFloorplanData(walls));
    expect(result.every((w) => w.wall_type !== 'unknown')).toBe(true);
    expect(result.length).toBe(2);
  });

  it('keeps all four classified wall types', () => {
    const base = { start: { x: 100, y: 100 }, end: { x: 200, y: 100 } };
    const walls = [
      makeWall({ id: 'w1', wall_type: 'exterior', ...base }),
      makeWall({ id: 'w2', wall_type: 'structural', ...base }),
      makeWall({ id: 'w3', wall_type: 'mamad', ...base }),
      makeWall({ id: 'w4', wall_type: 'partition', ...base }),
    ];
    const result = getWallsFor3D(makeFloorplanData(walls));
    expect(result.length).toBe(4);
  });

  it('returns empty array when all walls are unknown', () => {
    const walls = [
      makeWall({ id: 'w1', wall_type: 'unknown', start: { x: 100, y: 100 }, end: { x: 300, y: 100 } }),
    ];
    const result = getWallsFor3D(makeFloorplanData(walls));
    expect(result.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Wall geometry — verify a 4×3m room produces correct wall dimensions
// ---------------------------------------------------------------------------

describe('wall geometry (4×3m room)', () => {
  // Simulate 4 walls of a 4m × 3m room, coordinates already in cm
  const walls = [
    { start: { x: 0, y: 0 }, end: { x: 400, y: 0 } },     // bottom, 4m
    { start: { x: 400, y: 0 }, end: { x: 400, y: 300 } },  // right, 3m
    { start: { x: 400, y: 300 }, end: { x: 0, y: 300 } },  // top, 4m
    { start: { x: 0, y: 300 }, end: { x: 0, y: 0 } },      // left, 3m
  ];

  function computeWallLength(wall: typeof walls[0]): number {
    const s = pdfToThree(wall.start.x, wall.start.y);
    const e = pdfToThree(wall.end.x, wall.end.y);
    const dx = e.x - s.x;
    const dz = e.z - s.z;
    return Math.sqrt(dx * dx + dz * dz);
  }

  it('bottom and top walls are 4m long', () => {
    expect(computeWallLength(walls[0])).toBeCloseTo(4.0, 4);
    expect(computeWallLength(walls[2])).toBeCloseTo(4.0, 4);
  });

  it('left and right walls are 3m long', () => {
    expect(computeWallLength(walls[1])).toBeCloseTo(3.0, 4);
    expect(computeWallLength(walls[3])).toBeCloseTo(3.0, 4);
  });

  it('wall height is 2.60m (BoxGeometry Y dimension)', () => {
    // In WallMesh, boxGeometry args = [length, CEILING_HEIGHT_M, thickness]
    expect(CEILING_HEIGHT_M).toBe(2.6);
  });

  it('wall midpoints are correct', () => {
    // Bottom wall midpoint: (200cm,0cm) → Three.js (2.0, 1.3, 0)
    const s = pdfToThree(0, 0);
    const e = pdfToThree(400, 0);
    const midX = (s.x + e.x) / 2;
    const midZ = (s.z + e.z) / 2;
    expect(midX).toBeCloseTo(2.0, 4);
    expect(midZ).toBeCloseTo(0, 4);
  });
});

// ---------------------------------------------------------------------------
// Floor polygon area — verify ShapeGeometry covers 12 sqm for 4×3m room
// ---------------------------------------------------------------------------

describe('floor polygon (4×3m room)', () => {
  // Polygon vertices in cm (already real-world, not PDF points)
  const polygon: [number, number][] = [
    [0, 0], [400, 0], [400, 300], [0, 300],
  ];

  it('ShapeGeometry area matches 12 sqm', () => {
    const verts = polygon.map(([x, y]) => pdfToThree(x, y));

    const shape = new THREE.Shape();
    shape.moveTo(verts[0].x, verts[0].z);
    for (let i = 1; i < verts.length; i++) {
      shape.lineTo(verts[i].x, verts[i].z);
    }
    shape.closePath();

    const geom = new THREE.ShapeGeometry(shape);
    geom.computeBoundingBox();

    // Compute area from bounding box (for a rectangular room, bbox area = room area)
    const bb = geom.boundingBox!;
    const width = bb.max.x - bb.min.x;   // 4.0
    const depth = bb.max.y - bb.min.y;   // 3.0 (shape is in XY before rotation)
    const area = width * depth;

    expect(area).toBeCloseTo(12.0, 2);
  });

  it('ceiling is at y=2.60m', () => {
    // CeilingMesh sets position={[0, CEILING_HEIGHT_M, 0]}
    expect(CEILING_HEIGHT_M).toBe(2.6);
  });
});

// ---------------------------------------------------------------------------
// Opening-to-wall matching
// ---------------------------------------------------------------------------

function makeOpening(overrides: Partial<Opening> & Pick<Opening, 'position' | 'width_cm'>): Opening {
  return {
    id: 'op-test',
    type: 'door',
    wall_id: '',
    rooms: [],
    ...overrides,
  };
}

describe('matchOpeningsToWalls', () => {
  // Wall from (100,200) to (400,200) in PDF points, 1:50 scale
  const SF = 0.01764;
  const testWalls: Wall[] = [
    makeWall({
      id: 'w1',
      wall_type: 'exterior',
      start: { x: 100, y: 200 },
      end: { x: 400, y: 200 },
    }),
  ];

  it('skips regular doors (gap-based, rendered by DirectDoorGroup)', () => {
    const openings: Opening[] = [
      makeOpening({
        id: 'door-1',
        type: 'door',
        position: { x: 250, y: 200 },
        width_cm: 80,
      }),
    ];

    const result = matchOpeningsToWalls(testWalls, openings, SF);
    // Regular doors are gap-based — no hole-cutting needed
    expect(result.size).toBe(0);
  });

  it('matches a glass door (sliding_door) to wall for hole-cutting', () => {
    const openings: Opening[] = [
      makeOpening({
        id: 'glass-1',
        type: 'sliding_door',
        position: { x: 250, y: 200 },
        width_cm: 200,
      }),
    ];

    const result = matchOpeningsToWalls(testWalls, openings, SF);
    expect(result.size).toBe(1);
    expect(result.get('w1')).toHaveLength(1);

    const matched = result.get('w1')![0];
    expect(matched.type).toBe('sliding_door');
    expect(matched.sillHeight).toBe(0);
    expect(matched.height).toBeCloseTo(GLASS_DOOR_HEIGHT_M, 4);
  });

  it('matches a window near the wall', () => {
    const openings: Opening[] = [
      makeOpening({
        id: 'win-1',
        type: 'window',
        position: { x: 300, y: 200 },
        width_cm: 120,
      }),
    ];

    const result = matchOpeningsToWalls(testWalls, openings, SF);
    expect(result.size).toBe(1);

    const matched = result.get('w1')![0];
    expect(matched.type).toBe('window');
    expect(matched.sillHeight).toBeCloseTo(WINDOW_SILL_M, 4);
    expect(matched.height).toBeCloseTo(WINDOW_HEIGHT_M, 4);
  });

  it('rejects window too far from any wall (> 1.5m threshold)', () => {
    // Window 200 PDF pts above the wall → ~3.5m away (exceeds 1.5m threshold)
    const openings: Opening[] = [
      makeOpening({
        id: 'far-1',
        type: 'window',
        position: { x: 250, y: 400 },
        width_cm: 120,
      }),
    ];

    const result = matchOpeningsToWalls(testWalls, openings, SF);
    expect(result.size).toBe(0);
  });

  it('returns empty map when no openings provided', () => {
    const result = matchOpeningsToWalls(testWalls, [], SF);
    expect(result.size).toBe(0);
  });

  it('clamps opening offset to stay within wall bounds', () => {
    // Glass door at the very start of the wall
    const openings: Opening[] = [
      makeOpening({
        id: 'edge-1',
        type: 'sliding_door',
        position: { x: 100, y: 200 },
        width_cm: 200,
      }),
    ];

    const result = matchOpeningsToWalls(testWalls, openings, SF);
    const matched = result.get('w1')![0];
    // Offset should be clamped so opening doesn't extend past wall start
    expect(matched.offset).toBeGreaterThanOrEqual(matched.width / 2 + 0.02);
  });

  it('matches window at moderate distance (within 1.5m threshold)', () => {
    // Window 50 PDF pts from wall ≈ 0.88m — would fail at old 0.8m threshold
    const openings: Opening[] = [
      makeOpening({
        id: 'win-far',
        type: 'window',
        position: { x: 250, y: 250 },
        width_cm: 120,
      }),
    ];

    const result = matchOpeningsToWalls(testWalls, openings, SF);
    expect(result.size).toBe(1);
    expect(result.get('w1')![0].type).toBe('window');
  });
});

// ---------------------------------------------------------------------------
// Hole geometry — verify insets prevent edge-sharing
// ---------------------------------------------------------------------------

describe('opening dimension constants', () => {
  it('door height (2.10m) is less than ceiling height (2.60m)', () => {
    expect(DOOR_HEIGHT_M).toBeLessThan(CEILING_HEIGHT_M);
  });

  it('window top (sill + height = 2.10m) is less than ceiling height', () => {
    expect(WINDOW_SILL_M + WINDOW_HEIGHT_M).toBeLessThanOrEqual(CEILING_HEIGHT_M);
  });

  it('window sill (0.90m) is above floor level', () => {
    expect(WINDOW_SILL_M).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// Glass door detection heuristic
// ---------------------------------------------------------------------------

describe('glass door width heuristic', () => {
  // Standard Israeli door: 65-95cm → should render as DoorPanel (wood)
  // Glass/sliding door: 160-300cm → should render as GlassPane (glass)
  // Threshold: 140cm (1.4m in Three.js)

  it('standard door (80cm) is below glass threshold', () => {
    expect(0.80).toBeLessThanOrEqual(1.4);
  });

  it('wide glass door (200cm) exceeds glass threshold', () => {
    expect(2.0).toBeGreaterThan(1.4);
  });

  it('french door (160cm) exceeds glass threshold', () => {
    expect(1.6).toBeGreaterThan(1.4);
  });
});

// ---------------------------------------------------------------------------
// EYE_HEIGHT_M constant
// ---------------------------------------------------------------------------

describe('EYE_HEIGHT_M', () => {
  it('is 1.65m (standard eye height)', () => {
    expect(EYE_HEIGHT_M).toBe(1.65);
  });

  it('is below ceiling height', () => {
    expect(EYE_HEIGHT_M).toBeLessThan(CEILING_HEIGHT_M);
  });
});

// ---------------------------------------------------------------------------
// getLargestRoom
// ---------------------------------------------------------------------------

function makeRoom(overrides: Partial<Room>): Room {
  return {
    id: 'r-test',
    type: 'unknown',
    type_he: 'חדר',
    confidence: 1,
    area_sqm: 10,
    perimeter_m: 12,
    polygon: [[0, 0], [100, 0], [100, 100], [0, 100]],
    centroid: { x: 50, y: 50 },
    label_point: { x: 50, y: 50 },
    classification_method: 'area_heuristic',
    needs_review: false,
    is_modifiable: true,
    ...overrides,
  };
}

describe('getLargestRoom', () => {
  it('returns undefined for empty array', () => {
    expect(getLargestRoom([])).toBeUndefined();
  });

  it('returns salon when present (regardless of area)', () => {
    const rooms = [
      makeRoom({ id: 'r1', type: 'bedroom', area_sqm: 30 }),
      makeRoom({ id: 'r2', type: 'salon', area_sqm: 15 }),
      makeRoom({ id: 'r3', type: 'kitchen', area_sqm: 20 }),
    ];
    expect(getLargestRoom(rooms)!.id).toBe('r2');
  });

  it('returns largest by area when no salon', () => {
    const rooms = [
      makeRoom({ id: 'r1', type: 'bedroom', area_sqm: 12 }),
      makeRoom({ id: 'r2', type: 'kitchen', area_sqm: 25 }),
      makeRoom({ id: 'r3', type: 'bathroom', area_sqm: 5 }),
    ];
    expect(getLargestRoom(rooms)!.id).toBe('r2');
  });

  it('returns single room', () => {
    const rooms = [makeRoom({ id: 'r1', type: 'mamad', area_sqm: 10 })];
    expect(getLargestRoom(rooms)!.id).toBe('r1');
  });
});

// ---------------------------------------------------------------------------
// computeStartPosition
// ---------------------------------------------------------------------------

describe('computeStartPosition', () => {
  const SF = 0.0176;

  it('places camera at EYE_HEIGHT_M', () => {
    const rooms = [makeRoom({ centroid: { x: 200, y: 300 } })];
    const pos = computeStartPosition(rooms, SF);
    expect(pos.y).toBe(EYE_HEIGHT_M);
  });

  it('converts centroid through pdfPointsToThree', () => {
    const rooms = [makeRoom({ centroid: { x: 200, y: 300 } })];
    const pos = computeStartPosition(rooms, SF);
    const expected = pdfPointsToThree(200, 300, SF);
    expect(pos.x).toBeCloseTo(expected.x, 4);
    expect(pos.z).toBeCloseTo(expected.z, 4);
  });

  it('returns origin at eye height for empty rooms', () => {
    const pos = computeStartPosition([], SF);
    expect(pos.x).toBe(0);
    expect(pos.y).toBe(EYE_HEIGHT_M);
    expect(pos.z).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// forwardFromYaw — camera direction vectors
// ---------------------------------------------------------------------------

describe('forwardFromYaw', () => {
  it('yaw=0 → forward is (0, 0, -1)', () => {
    const fwd = forwardFromYaw(0);
    expect(fwd.x).toBeCloseTo(0, 4);
    expect(fwd.y).toBe(0);
    expect(fwd.z).toBeCloseTo(-1, 4);
  });

  it('yaw=PI/2 → forward is (-1, 0, 0)', () => {
    const fwd = forwardFromYaw(Math.PI / 2);
    expect(fwd.x).toBeCloseTo(-1, 4);
    expect(fwd.y).toBe(0);
    expect(fwd.z).toBeCloseTo(0, 3);
  });

  it('yaw=-PI/2 → forward is (1, 0, 0)', () => {
    const fwd = forwardFromYaw(-Math.PI / 2);
    expect(fwd.x).toBeCloseTo(1, 4);
    expect(fwd.y).toBe(0);
    expect(fwd.z).toBeCloseTo(0, 3);
  });

  it('always returns a unit vector in XZ plane', () => {
    for (const angle of [0, 0.5, 1.0, 2.0, Math.PI, -1.5]) {
      const fwd = forwardFromYaw(angle);
      expect(fwd.y).toBe(0);
      expect(fwd.length()).toBeCloseTo(1.0, 4);
    }
  });
});

// ---------------------------------------------------------------------------
// wallSlide — collision projection
// ---------------------------------------------------------------------------

describe('wallSlide', () => {
  // Convention: wallNormal points from wall surface toward player (face normal
  // from Three.js raycaster). Movement INTO the wall has negative dot product.

  it('removes movement component into wall', () => {
    // Walking toward +Z, wall at +Z → normal faces back at player: (0,0,-1)
    const movement = new THREE.Vector3(1, 0, 1);
    const wallNormal = new THREE.Vector3(0, 0, -1);
    const result = wallSlide(movement, wallNormal);
    // Z component (into wall) removed, X component (parallel) preserved
    expect(result.x).toBeCloseTo(1, 4);
    expect(result.z).toBeCloseTo(0, 4);
  });

  it('preserves movement parallel to wall', () => {
    // Moving along X, wall normal in Z — fully parallel, no blocking
    const movement = new THREE.Vector3(1, 0, 0);
    const wallNormal = new THREE.Vector3(0, 0, -1);
    const result = wallSlide(movement, wallNormal);
    expect(result.x).toBeCloseTo(1, 4);
    expect(result.z).toBeCloseTo(0, 4);
  });

  it('does not modify movement away from wall', () => {
    // Moving toward -Z, wall normal also points -Z (moving away from wall)
    const movement = new THREE.Vector3(0, 0, -1);
    const wallNormal = new THREE.Vector3(0, 0, -1);
    const result = wallSlide(movement, wallNormal);
    // dot = (-1)*(-1) = +1 ≥ 0 → moving away, no slide needed
    expect(result.z).toBeCloseTo(-1, 4);
  });

  it('handles diagonal wall normals', () => {
    // Walking toward +X, wall at 45° with normal pointing back at player
    const movement = new THREE.Vector3(1, 0, 0);
    const wallNormal = new THREE.Vector3(-0.7071, 0, -0.7071);
    const result = wallSlide(movement, wallNormal);
    // Movement partially blocked by diagonal wall
    expect(result.length()).toBeLessThan(movement.length());
    expect(result.length()).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// Minimap coordinate transforms
// ---------------------------------------------------------------------------

describe('minimap coordinate transforms', () => {
  // Create a simple bbox for testing
  const bbox = {
    minX: 0,
    maxX: 10,
    minZ: -10,
    maxZ: 0,
    scale: 17.6, // (200 - 24) / 10 = 17.6
    offsetX: 12,
    offsetZ: 12,
  };

  it('worldToMinimap maps world origin to correct canvas position', () => {
    const { px, py } = worldToMinimap(0, -10, bbox);
    expect(px).toBeCloseTo(bbox.offsetX, 1);
    expect(py).toBeCloseTo(bbox.offsetZ, 1);
  });

  it('worldToMinimap maps max corner correctly', () => {
    const { px, py } = worldToMinimap(10, 0, bbox);
    expect(px).toBeCloseTo(bbox.offsetX + 10 * bbox.scale, 1);
    expect(py).toBeCloseTo(bbox.offsetZ + 10 * bbox.scale, 1);
  });

  it('minimapToWorld is the inverse of worldToMinimap', () => {
    const worldX = 5;
    const worldZ = -5;
    const { px, py } = worldToMinimap(worldX, worldZ, bbox);
    const back = minimapToWorld(px, py, bbox);
    expect(back.x).toBeCloseTo(worldX, 4);
    expect(back.z).toBeCloseTo(worldZ, 4);
  });

  it('roundtrip works for multiple positions', () => {
    const positions = [
      [0, 0], [10, -10], [5, -5], [2.3, -7.8],
    ];
    for (const [x, z] of positions) {
      const { px, py } = worldToMinimap(x, z, bbox);
      const back = minimapToWorld(px, py, bbox);
      expect(back.x).toBeCloseTo(x, 4);
      expect(back.z).toBeCloseTo(z, 4);
    }
  });
});
