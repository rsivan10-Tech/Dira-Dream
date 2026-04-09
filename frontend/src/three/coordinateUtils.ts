/**
 * Coordinate transformation utilities for 2D plan data -> Three.js 3D scene.
 *
 * Three.js convention: Y is UP, 1 unit = 1 meter.
 * 2D plan data arrives in PDF points; scale_factor converts to metres.
 * pdfToThree() expects centimetres and returns metres.
 */

import type { WallType, RoomType } from '@/types/floorplan';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Israeli standard ceiling height (meters) */
export const CEILING_HEIGHT_M = 2.60;

// ---------------------------------------------------------------------------
// Coordinate transform
// ---------------------------------------------------------------------------

/**
 * Convert 2D plan coordinates (centimetres) to Three.js world coordinates.
 *
 *   x_3d =  x_cm / 100   (cm -> m, same direction)
 *   z_3d = -y_cm / 100   (cm -> m, Y flipped to -Z)
 *   y_3d = height         (set separately)
 */
export function pdfToThree(x: number, y: number): { x: number; z: number } {
  return { x: x / 100, z: -y / 100 };
}

/**
 * Convert PDF-point coordinate to Three.js, applying the plan scale factor.
 * scaleFactor is "PDF points -> metres".
 */
export function pdfPointsToThree(
  pdfX: number,
  pdfY: number,
  scaleFactor: number,
): { x: number; z: number } {
  // PDF points -> cm -> Three.js metres
  const cmX = pdfX * scaleFactor * 100;
  const cmY = pdfY * scaleFactor * 100;
  return pdfToThree(cmX, cmY);
}

// ---------------------------------------------------------------------------
// Wall physical thickness (metres) by type — Israeli construction standards
// ---------------------------------------------------------------------------

export const WALL_THICKNESS_M: Record<WallType, number> = {
  exterior: 0.25, // 25 cm
  mamad: 0.35, // 35 cm reinforced concrete
  structural: 0.25, // 25 cm load-bearing
  partition: 0.10, // 10 cm
  unknown: 0.15, // 15 cm default
};

// ---------------------------------------------------------------------------
// Material colours — match 2D renderer palette
// ---------------------------------------------------------------------------

export const WALL_COLORS: Record<WallType, string> = {
  exterior: '#4A4A4A',
  mamad: '#FF8C00',
  structural: '#8B0000',
  partition: '#4682B4',
  unknown: '#888888',
};

export const FLOOR_COLORS: Record<RoomType, string> = {
  salon: '#F5E6D3', // warm beige
  bedroom: '#E8E0D8', // neutral warm
  kitchen: '#F0D9B5', // warm
  guest_toilet: '#D5E5F0', // cool
  bathroom: '#C8DDE8', // cool blue
  mamad: '#FFE0B2', // warm orange tint
  sun_balcony: '#E8F5E9', // light green
  service_balcony: '#ECEFF1', // gray
  storage: '#D7CCC8', // brown tint
  utility: '#CFD8DC', // blue-gray
  unknown: '#E0E0E0', // neutral gray
};
