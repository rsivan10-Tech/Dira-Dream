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

/** Eye height for first-person walkthrough (meters) */
export const EYE_HEIGHT_M = 1.65;

/** Opening heights (meters) — Israeli construction standards */
export const DOOR_HEIGHT_M = 2.10;
export const WINDOW_HEIGHT_M = 1.20;
export const WINDOW_SILL_M = 0.90;
export const GLASS_DOOR_HEIGHT_M = 2.20;

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
  exterior: '#5A5A5A',
  mamad: '#FF9F30',
  structural: '#9B2020',
  partition: '#7090A8',
  unknown: '#909090',
};

/** Ceiling color for 3D scene. */
export const CEILING_COLOR = '#F5F5F5';

/** Baseboard color — thin dark strip where wall meets floor. */
export const BASEBOARD_COLOR = '#3A3228';
export const BASEBOARD_HEIGHT_M = 0.08; // 8cm

export const FLOOR_COLORS: Record<RoomType, string> = {
  salon: '#D4B896', // light wood
  bedroom: '#DBBF9E', // warm wood
  kitchen: '#D9C4A0', // light maple
  guest_toilet: '#C8D8E4', // cool tile
  bathroom: '#B8CCD8', // cool blue tile
  mamad: '#E0C8A0', // warm tan
  sun_balcony: '#C8D8C4', // stone gray-green
  service_balcony: '#D0D0CC', // concrete gray
  storage: '#C8BCA8', // warm stone
  utility: '#C4C8CC', // utility gray
  unknown: '#D0C8BC', // neutral warm
};
