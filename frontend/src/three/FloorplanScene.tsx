/**
 * FloorplanScene — React Three Fiber component.
 * Converts Phase 1 2D plan data (walls, rooms) into a 3D scene.
 */

import { useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import type { FloorplanData, Wall as WallData, Room as RoomData } from '@/types/floorplan';
import {
  pdfToThree,
  CEILING_HEIGHT_M,
  WALL_THICKNESS_M,
  WALL_COLORS,
  FLOOR_COLORS,
} from './coordinateUtils';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Convert a PDF-point value to real-world centimetres. */
function toCm(pdfPt: number, scaleFactor: number): number {
  return pdfPt * scaleFactor * 100;
}

// ---------------------------------------------------------------------------
// Wall filter — only classified walls inside the apartment bbox
// ---------------------------------------------------------------------------

/** Wall types that should be extruded in 3D. */
const WALL_TYPES_FOR_3D = new Set(['exterior', 'mamad', 'structural', 'partition']);

/**
 * Return only wall segments suitable for 3D extrusion:
 *  1. wall_type must be a known wall type (not 'unknown')
 *  2. Segment midpoint must lie inside the apartment bbox (derived from
 *     room polygons when available, else from classified walls only)
 *  3. Page-boundary walls (both endpoints on outer AABB edge) are excluded
 */
export function getWallsFor3D(data: FloorplanData): WallData[] {
  // Step 1: keep only classified wall types
  const typed = data.walls.filter((w) => WALL_TYPES_FOR_3D.has(w.wall_type));
  if (typed.length === 0) return typed;

  // Step 2: compute apartment bbox — prefer room polygons (tighter), fall
  // back to the classified-wall endpoints
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;

  if (data.rooms.length > 0) {
    for (const r of data.rooms) {
      for (const [x, y] of r.polygon) {
        minX = Math.min(minX, x);
        maxX = Math.max(maxX, x);
        minY = Math.min(minY, y);
        maxY = Math.max(maxY, y);
      }
    }
  } else {
    for (const w of typed) {
      minX = Math.min(minX, w.start.x, w.end.x);
      maxX = Math.max(maxX, w.start.x, w.end.x);
      minY = Math.min(minY, w.start.y, w.end.y);
      maxY = Math.max(maxY, w.start.y, w.end.y);
    }
  }

  // Pad bbox by 10% so walls ON the apartment boundary aren't clipped
  const padX = (maxX - minX) * 0.10;
  const padY = (maxY - minY) * 0.10;
  minX -= padX; maxX += padX;
  minY -= padY; maxY += padY;

  // Step 3: keep walls whose midpoint is inside the padded apartment bbox
  return typed.filter((w) => {
    const mx = (w.start.x + w.end.x) / 2;
    const my = (w.start.y + w.end.y) / 2;
    return mx >= minX && mx <= maxX && my >= minY && my <= maxY;
  });
}

// ---------------------------------------------------------------------------
// WallMesh
// ---------------------------------------------------------------------------

interface WallMeshProps {
  wall: WallData;
  scaleFactor: number;
}

export function WallMesh({ wall, scaleFactor }: WallMeshProps) {
  const geo = useMemo(() => {
    const s = pdfToThree(toCm(wall.start.x, scaleFactor), toCm(wall.start.y, scaleFactor));
    const e = pdfToThree(toCm(wall.end.x, scaleFactor), toCm(wall.end.y, scaleFactor));

    const dx = e.x - s.x;
    const dz = e.z - s.z;
    const length = Math.sqrt(dx * dx + dz * dz);

    // Skip degenerate zero-length walls
    if (length < 0.001) return null;

    const angle = Math.atan2(dz, dx);
    const thickness = WALL_THICKNESS_M[wall.wall_type] ?? WALL_THICKNESS_M.unknown;

    return { s, e, length, angle, thickness };
  }, [wall, scaleFactor]);

  if (!geo) return null;

  return (
    <mesh
      position={[
        (geo.s.x + geo.e.x) / 2,
        CEILING_HEIGHT_M / 2,
        (geo.s.z + geo.e.z) / 2,
      ]}
      rotation={[0, -geo.angle, 0]}
      userData={{ wallType: wall.wall_type, id: wall.id }}
    >
      <boxGeometry args={[geo.length, CEILING_HEIGHT_M, geo.thickness]} />
      <meshStandardMaterial
        color={WALL_COLORS[wall.wall_type] ?? WALL_COLORS.unknown}
        roughness={0.8}
      />
    </mesh>
  );
}

// ---------------------------------------------------------------------------
// WallGroup — all walls, toggleable as a layer
// ---------------------------------------------------------------------------

function WallGroup({ walls, scaleFactor }: { walls: WallData[]; scaleFactor: number }) {
  return (
    <group name="walls">
      {walls.map((w) => (
        <WallMesh key={w.id} wall={w} scaleFactor={scaleFactor} />
      ))}
    </group>
  );
}

// ---------------------------------------------------------------------------
// FloorMesh — room polygon at y=0
// ---------------------------------------------------------------------------

interface RoomMeshProps {
  room: RoomData;
  scaleFactor: number;
}

export function FloorMesh({ room, scaleFactor }: RoomMeshProps) {
  const geometry = useMemo(() => {
    if (room.polygon.length < 3) return null;

    const verts = room.polygon.map(([x, y]) =>
      pdfToThree(toCm(x, scaleFactor), toCm(y, scaleFactor)),
    );

    const shape = new THREE.Shape();
    shape.moveTo(verts[0].x, verts[0].z);
    for (let i = 1; i < verts.length; i++) {
      shape.lineTo(verts[i].x, verts[i].z);
    }
    shape.closePath();

    const geom = new THREE.ShapeGeometry(shape);
    geom.rotateX(-Math.PI / 2); // lay flat on XZ plane
    return geom;
  }, [room, scaleFactor]);

  if (!geometry) return null;

  return (
    <mesh geometry={geometry} position={[0, 0, 0]} userData={{ roomId: room.id }}>
      <meshStandardMaterial
        color={FLOOR_COLORS[room.type] ?? FLOOR_COLORS.unknown}
        roughness={0.8}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
}

// ---------------------------------------------------------------------------
// CeilingMesh — same shape at y = CEILING_HEIGHT_M
// ---------------------------------------------------------------------------

export function CeilingMesh({ room, scaleFactor }: RoomMeshProps) {
  const geometry = useMemo(() => {
    if (room.polygon.length < 3) return null;

    const verts = room.polygon.map(([x, y]) =>
      pdfToThree(toCm(x, scaleFactor), toCm(y, scaleFactor)),
    );

    const shape = new THREE.Shape();
    shape.moveTo(verts[0].x, verts[0].z);
    for (let i = 1; i < verts.length; i++) {
      shape.lineTo(verts[i].x, verts[i].z);
    }
    shape.closePath();

    const geom = new THREE.ShapeGeometry(shape);
    geom.rotateX(-Math.PI / 2);
    return geom;
  }, [room, scaleFactor]);

  if (!geometry) return null;

  return (
    <mesh geometry={geometry} position={[0, CEILING_HEIGHT_M, 0]} userData={{ roomId: room.id }}>
      <meshStandardMaterial color="#ffffff" roughness={0.9} side={THREE.BackSide} />
    </mesh>
  );
}

// ---------------------------------------------------------------------------
// Bounding-box + camera helpers
// ---------------------------------------------------------------------------

interface SceneLayout {
  filteredWalls: WallData[];
  center: THREE.Vector3;
  cameraPos: THREE.Vector3;
}

/** Compute filtered walls, centroid, and auto-fit camera position. */
function computeLayout(data: FloorplanData): SceneLayout {
  const filteredWalls = getWallsFor3D(data);

  const walls = filteredWalls.length > 0 ? filteredWalls : data.walls;

  if (walls.length === 0) {
    return {
      filteredWalls,
      center: new THREE.Vector3(0, CEILING_HEIGHT_M / 2, 0),
      cameraPos: new THREE.Vector3(0, 15, 10),
    };
  }

  // Bounding box in Three.js space
  let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
  for (const w of walls) {
    const a = pdfToThree(toCm(w.start.x, data.scale_factor), toCm(w.start.y, data.scale_factor));
    const b = pdfToThree(toCm(w.end.x, data.scale_factor), toCm(w.end.y, data.scale_factor));
    minX = Math.min(minX, a.x, b.x);
    maxX = Math.max(maxX, a.x, b.x);
    minZ = Math.min(minZ, a.z, b.z);
    maxZ = Math.max(maxZ, a.z, b.z);
  }

  const cx = (minX + maxX) / 2;
  const cz = (minZ + maxZ) / 2;
  const center = new THREE.Vector3(cx, CEILING_HEIGHT_M / 2, cz);

  // Auto-fit: camera distance so bbox fills ~70% of vertical FOV
  const extentX = maxX - minX;
  const extentZ = maxZ - minZ;
  const maxExtent = Math.max(extentX, extentZ, 1);
  const fovRad = (60 * Math.PI) / 180; // 60 degree FOV
  const fitDistance = (maxExtent / 0.7) / (2 * Math.tan(fovRad / 2));

  // Position above and slightly behind, looking down at ~60° angle
  const height = fitDistance * 0.8;
  const pullback = fitDistance * 0.5;
  const cameraPos = new THREE.Vector3(cx, height, cz + pullback);

  return { filteredWalls, center, cameraPos };
}

// ---------------------------------------------------------------------------
// FloorplanScene
// ---------------------------------------------------------------------------

interface FloorplanSceneProps {
  data: FloorplanData;
}

export default function FloorplanScene({ data }: FloorplanSceneProps) {
  const layout = useMemo(() => computeLayout(data), [data]);

  return (
    <Canvas
      camera={{
        position: layout.cameraPos.toArray(),
        fov: 60,
        near: 0.1,
        far: 500,
      }}
      dpr={[1, 2]}
      style={{ width: '100%', height: '100%', background: '#e8e8e8' }}
    >
      {/* Lighting — positioned relative to apartment center */}
      <ambientLight intensity={0.4} color="#ffffff" />
      <directionalLight
        position={[layout.center.x + 10, 20, layout.center.z - 10]}
        intensity={0.6}
        color="#ffffff"
      />
      <directionalLight
        position={[layout.center.x - 8, 12, layout.center.z + 8]}
        intensity={0.25}
        color="#f0f0ff"
      />

      <WallGroup walls={layout.filteredWalls} scaleFactor={data.scale_factor} />

      <group name="floors">
        {data.rooms.map((r) => (
          <FloorMesh key={r.id} room={r} scaleFactor={data.scale_factor} />
        ))}
      </group>

      <group name="ceilings">
        {data.rooms.map((r) => (
          <CeilingMesh key={`ceil-${r.id}`} room={r} scaleFactor={data.scale_factor} />
        ))}
      </group>

      <OrbitControls
        target={layout.center.toArray()}
        enableDamping
        dampingFactor={0.05}
        minDistance={1}
        maxDistance={100}
      />
    </Canvas>
  );
}
