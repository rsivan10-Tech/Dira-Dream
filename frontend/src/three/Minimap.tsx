/**
 * Minimap — 2D plan overlay in top-right corner of 3D view.
 *
 * Renders room polygons + walls on a plain HTML <canvas>.
 * Shows camera position (dot) and look direction (cone).
 * Click to teleport to that location.
 */

import { useRef, useEffect, useCallback, useMemo } from 'react';
import type { Room, Wall } from '@/types/floorplan';
import { pdfPointsToThree, FLOOR_COLORS, WALL_COLORS } from './coordinateUtils';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MINIMAP_SIZE = 200; // px
const PADDING = 12; // px inside canvas
const CAMERA_DOT_RADIUS = 4;
const CONE_LENGTH = 18;
const CONE_HALF_ANGLE = Math.PI / 6; // 30° half-FOV

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface BBox {
  minX: number;
  maxX: number;
  minZ: number;
  maxZ: number;
  scale: number; // world-to-canvas scale
  offsetX: number;
  offsetZ: number;
}

function computeBBox(walls: Wall[], scaleFactor: number): BBox {
  let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;

  for (const w of walls) {
    const a = pdfPointsToThree(w.start.x, w.start.y, scaleFactor);
    const b = pdfPointsToThree(w.end.x, w.end.y, scaleFactor);
    minX = Math.min(minX, a.x, b.x);
    maxX = Math.max(maxX, a.x, b.x);
    minZ = Math.min(minZ, a.z, b.z);
    maxZ = Math.max(maxZ, a.z, b.z);
  }

  const extentX = maxX - minX || 1;
  const extentZ = maxZ - minZ || 1;
  const drawSize = MINIMAP_SIZE - PADDING * 2;
  const scale = drawSize / Math.max(extentX, extentZ);

  return {
    minX, maxX, minZ, maxZ,
    scale,
    offsetX: PADDING + (drawSize - extentX * scale) / 2,
    offsetZ: PADDING + (drawSize - extentZ * scale) / 2,
  };
}

/** Convert Three.js world (x, z) to minimap canvas (px, py). */
export function worldToMinimap(
  worldX: number,
  worldZ: number,
  bbox: BBox,
): { px: number; py: number } {
  const px = (worldX - bbox.minX) * bbox.scale + bbox.offsetX;
  // Z → Y on canvas, but Z is negative in Three.js (camera looks -Z),
  // and we want "up" on minimap to correspond to -Z (forward)
  const py = (worldZ - bbox.minZ) * bbox.scale + bbox.offsetZ;
  return { px, py };
}

/** Convert minimap canvas (px, py) back to Three.js world (x, z). */
export function minimapToWorld(
  px: number,
  py: number,
  bbox: BBox,
): { x: number; z: number } {
  const x = (px - bbox.offsetX) / bbox.scale + bbox.minX;
  const z = (py - bbox.offsetZ) / bbox.scale + bbox.minZ;
  return { x, z };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface MinimapProps {
  rooms: Room[];
  walls: Wall[];
  scaleFactor: number;
  cameraX: number;
  cameraZ: number;
  cameraYaw: number;
  onTeleport: (x: number, z: number) => void;
  visible: boolean;
}

export default function Minimap({
  rooms,
  walls,
  scaleFactor,
  cameraX,
  cameraZ,
  cameraYaw,
  onTeleport,
  visible,
}: MinimapProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const lastDraw = useRef({ x: 0, z: 0, yaw: 0 });

  const bbox = useMemo(() => computeBBox(walls, scaleFactor), [walls, scaleFactor]);

  // Draw minimap
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Clear
    ctx.clearRect(0, 0, MINIMAP_SIZE, MINIMAP_SIZE);

    // Background
    ctx.fillStyle = 'rgba(30, 30, 30, 0.85)';
    ctx.beginPath();
    ctx.roundRect(0, 0, MINIMAP_SIZE, MINIMAP_SIZE, 8);
    ctx.fill();

    // Room polygons
    for (const room of rooms) {
      if (room.polygon.length < 3) continue;
      const color = FLOOR_COLORS[room.type] ?? FLOOR_COLORS.unknown;

      ctx.fillStyle = color + 'AA'; // semi-transparent
      ctx.beginPath();
      const v0 = pdfPointsToThree(room.polygon[0][0], room.polygon[0][1], scaleFactor);
      const p0 = worldToMinimap(v0.x, v0.z, bbox);
      ctx.moveTo(p0.px, p0.py);
      for (let i = 1; i < room.polygon.length; i++) {
        const vi = pdfPointsToThree(room.polygon[i][0], room.polygon[i][1], scaleFactor);
        const pi = worldToMinimap(vi.x, vi.z, bbox);
        ctx.lineTo(pi.px, pi.py);
      }
      ctx.closePath();
      ctx.fill();
    }

    // Walls
    ctx.lineWidth = 1.5;
    for (const w of walls) {
      const a = pdfPointsToThree(w.start.x, w.start.y, scaleFactor);
      const b = pdfPointsToThree(w.end.x, w.end.y, scaleFactor);
      const pa = worldToMinimap(a.x, a.z, bbox);
      const pb = worldToMinimap(b.x, b.z, bbox);

      ctx.strokeStyle = WALL_COLORS[w.wall_type] ?? WALL_COLORS.unknown;
      ctx.beginPath();
      ctx.moveTo(pa.px, pa.py);
      ctx.lineTo(pb.px, pb.py);
      ctx.stroke();
    }

    // Camera position dot
    const cam = worldToMinimap(cameraX, cameraZ, bbox);
    ctx.fillStyle = '#ff4444';
    ctx.beginPath();
    ctx.arc(cam.px, cam.py, CAMERA_DOT_RADIUS, 0, Math.PI * 2);
    ctx.fill();

    // Camera direction cone
    // In Three.js: yaw=0 looks toward -Z. On the minimap canvas, -Z maps to
    // lower py values (up on screen). Canvas arc angles: 0 = right, PI/2 = down.
    // Forward (-Z) on canvas is "up" = -PI/2 in canvas angle space.
    // Adding yaw rotation: minimapAngle = -cameraYaw - PI/2.
    const minimapAngle = -cameraYaw - Math.PI / 2;
    ctx.fillStyle = 'rgba(255, 68, 68, 0.3)';
    ctx.beginPath();
    ctx.moveTo(cam.px, cam.py);
    ctx.arc(
      cam.px,
      cam.py,
      CONE_LENGTH,
      minimapAngle - CONE_HALF_ANGLE,
      minimapAngle + CONE_HALF_ANGLE,
    );
    ctx.closePath();
    ctx.fill();

    lastDraw.current = { x: cameraX, z: cameraZ, yaw: cameraYaw };
  }, [rooms, walls, scaleFactor, cameraX, cameraZ, cameraYaw, bbox]);

  // Redraw when camera moves enough
  useEffect(() => {
    if (!visible) return;
    const prev = lastDraw.current;
    const dx = cameraX - prev.x;
    const dz = cameraZ - prev.z;
    const dist = Math.sqrt(dx * dx + dz * dz);
    const dyaw = Math.abs(cameraYaw - prev.yaw);
    if (dist > 0.05 || dyaw > 0.02 || (prev.x === 0 && prev.z === 0)) {
      draw();
    }
  }, [visible, cameraX, cameraZ, cameraYaw, draw]);

  // Teleport on click — snap to nearest room centroid
  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const px = e.clientX - rect.left;
      const py = e.clientY - rect.top;
      const clickWorld = minimapToWorld(px, py, bbox);

      // Find nearest room centroid to the click position
      let bestRoom: Room | null = null;
      let bestDist = Infinity;
      for (const room of rooms) {
        const c = pdfPointsToThree(room.centroid.x, room.centroid.y, scaleFactor);
        const dx = c.x - clickWorld.x;
        const dz = c.z - clickWorld.z;
        const dist = dx * dx + dz * dz;
        if (dist < bestDist) {
          bestDist = dist;
          bestRoom = room;
        }
      }

      if (bestRoom) {
        const target = pdfPointsToThree(bestRoom.centroid.x, bestRoom.centroid.y, scaleFactor);
        onTeleport(target.x, target.z);
      } else {
        onTeleport(clickWorld.x, clickWorld.z);
      }
    },
    [bbox, onTeleport, rooms, scaleFactor],
  );

  if (!visible) return null;

  return (
    <div
      style={{
        position: 'absolute',
        top: 12,
        right: 12,
        zIndex: 10,
        pointerEvents: 'auto',
      }}
    >
      <canvas
        ref={canvasRef}
        width={MINIMAP_SIZE}
        height={MINIMAP_SIZE}
        onClick={handleClick}
        style={{
          borderRadius: 8,
          cursor: 'pointer',
          boxShadow: '0 2px 12px rgba(0,0,0,0.4)',
        }}
      />
    </div>
  );
}
