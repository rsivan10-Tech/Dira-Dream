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
  WALL_THICKNESS_M,
  WALL_COLORS,
  FLOOR_COLORS,
} from './coordinateUtils';

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
