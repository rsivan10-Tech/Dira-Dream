/**
 * Shared utility: convert /api/analyze response → FloorplanData.
 * Used by both App.tsx (for shared state) and FloorplanViewer.
 */
import type {
  FloorplanData,
  Room,
  Wall,
  Opening,
  WallType,
  RoomType,
  TextAnnotation,
} from '@/types/floorplan';

export interface AnalyzeResponse {
  rooms: Array<{
    id: string; type: string; type_he: string; confidence: number;
    area_sqm: number; perimeter_m: number; polygon: number[][];
    centroid: { x: number; y: number }; label_point: { x: number; y: number };
    classification_method: string; needs_review: boolean; is_modifiable: boolean;
  }>;
  walls: Array<{
    id: string; start: { x: number; y: number }; end: { x: number; y: number };
    width: number; wall_type: string; is_structural: boolean;
    is_modifiable: boolean; confidence: number; rooms: string[];
  }>;
  openings: Array<{
    id: string; type: string; width_cm: number;
    position: { x: number; y: number }; wall_id: string;
    rooms: string[]; swing_direction?: string;
    endpoints?: [{ x: number; y: number }, { x: number; y: number }];
  }>;
  texts: Array<{ content: string; x: number; y: number; font_size: number }>;
  confidence: number;
  page_size: { width: number; height: number };
  scale_factor: number;
  metadata?: {
    scale_notation: string | null; scale_value: number | null;
    total_area_sqm: number | null; balcony_area_sqm: number | null;
  };
  page_num: number;
  page_count: number;
  pipeline_stats?: Record<string, unknown>;
}

export function analyzeToFloorplan(raw: AnalyzeResponse): FloorplanData {
  const rooms: Room[] = raw.rooms.map((r) => ({
    id: r.id,
    type: r.type as RoomType,
    type_he: r.type_he,
    confidence: r.confidence,
    area_sqm: r.area_sqm,
    perimeter_m: r.perimeter_m,
    polygon: r.polygon,
    centroid: r.centroid,
    label_point: r.label_point,
    classification_method: r.classification_method,
    needs_review: r.needs_review,
    is_modifiable: r.is_modifiable,
  }));

  const walls: Wall[] = raw.walls.map((w) => ({
    id: w.id,
    start: w.start,
    end: w.end,
    width: w.width,
    wall_type: w.wall_type as WallType,
    is_structural: w.is_structural,
    is_modifiable: w.is_modifiable,
    confidence: w.confidence,
    rooms: w.rooms,
  }));

  const openings: Opening[] = raw.openings.map((o) => ({
    id: o.id,
    type: o.type as Opening['type'],
    width_cm: o.width_cm,
    position: o.position,
    wall_id: o.wall_id,
    rooms: o.rooms,
    swing_direction: o.swing_direction,
    endpoints: o.endpoints,
  }));

  const texts: TextAnnotation[] = (raw.texts ?? []).map((t) => ({
    content: t.content,
    x: t.x,
    y: t.y,
    font_size: t.font_size,
  }));

  return {
    rooms,
    walls,
    openings,
    envelope: null,
    validation: null,
    confidence: raw.confidence,
    page_size: raw.page_size,
    scale_factor: raw.scale_factor,
    texts,
    stated_area_sqm: raw.metadata?.total_area_sqm ?? null,
    stated_balcony_sqm: raw.metadata?.balcony_area_sqm ?? null,
  };
}
