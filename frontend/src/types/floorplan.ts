/**
 * TypeScript interfaces for the floorplan rendering pipeline.
 * Matches the /api/detect-rooms response contract from api-contracts.md.
 */

// ---------------------------------------------------------------------------
// Primitives
// ---------------------------------------------------------------------------

export interface Point {
  x: number;
  y: number;
}

// ---------------------------------------------------------------------------
// Room
// ---------------------------------------------------------------------------

export type RoomType =
  | 'salon'
  | 'bedroom'
  | 'master_bedroom'
  | 'kitchen'
  | 'bathroom'
  | 'mamad'
  | 'balcony'
  | 'service_balcony'
  | 'storage'
  | 'hallway'
  | 'entrance'
  | 'corridor'
  | 'study'
  | 'laundry'
  | 'unknown';

export interface Room {
  id: string;
  type: RoomType;
  type_he: string;
  confidence: number;
  area_sqm: number;
  perimeter_m: number;
  polygon: number[][];          // [[x1,y1], [x2,y2], ...]
  centroid: Point;
  label_point: Point;           // representative_point for label placement
  classification_method: string; // 'text_label' | 'fixture' | 'area_heuristic' | 'user_override'
  needs_review: boolean;
  is_modifiable: boolean;
}

// ---------------------------------------------------------------------------
// Wall
// ---------------------------------------------------------------------------

export type WallType =
  | 'exterior'
  | 'mamad'
  | 'structural'
  | 'partition'
  | 'unknown';

export interface Wall {
  id: string;
  start: Point;
  end: Point;
  width: number;                 // stroke width in PDF points
  wall_type: WallType;
  is_structural: boolean;
  is_modifiable: boolean;
  confidence: number;
  rooms: string[];               // adjacent room IDs
}

// ---------------------------------------------------------------------------
// Opening (door / window)
// ---------------------------------------------------------------------------

export type OpeningType = 'door' | 'window' | 'sliding_door' | 'french_door';

export interface Opening {
  id: string;
  type: OpeningType;
  width_cm: number;
  position: Point;
  wall_id: string;
  rooms: string[];
  swing_direction?: string;      // 'left' | 'right' | 'inward' | 'outward'
  endpoints?: [Point, Point];
}

// ---------------------------------------------------------------------------
// Envelope & Validation
// ---------------------------------------------------------------------------

export interface Envelope {
  polygon: number[][];
  area_sqm: number;
  is_valid: boolean;
}

export interface Validation {
  has_mamad: boolean;
  has_kitchen: boolean;
  has_bathroom: boolean;
  has_salon: boolean;
  all_rooms_accessible: boolean;
  issues: string[];
}

// ---------------------------------------------------------------------------
// Full floorplan data (detect-rooms response)
// ---------------------------------------------------------------------------

export interface FloorplanData {
  rooms: Room[];
  walls: Wall[];
  openings: Opening[];
  envelope: Envelope | null;
  validation: Validation | null;
  confidence: number;
  page_size: { width: number; height: number };
  scale_factor: number;          // PDF points → metres
}

// ---------------------------------------------------------------------------
// UI state types
// ---------------------------------------------------------------------------

export type SelectionTarget =
  | { kind: 'room'; item: Room }
  | { kind: 'wall'; item: Wall }
  | null;

export interface LayerVisibility {
  walls: boolean;
  doorsWindows: boolean;
  furniture: boolean;
  dimensions: boolean;
  textAnnotations: boolean;
  structuralOverlay: boolean;
}

export interface MeasurementState {
  active: boolean;
  pointA: Point | null;
  pointB: Point | null;
}
