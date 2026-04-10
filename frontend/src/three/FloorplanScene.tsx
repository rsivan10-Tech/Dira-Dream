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

/**
 * Tiny inset (1mm) applied to hole edges that coincide with the outer shape
 * boundary. Without this, earcut triangulation produces degenerate triangles
 * when hole vertices sit exactly on the outer contour (e.g. door sill at y=0).
 */
const HOLE_INSET = 0.001;
import { matchOpeningsToWalls, type OpeningOnWall } from './openingUtils';

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
 * Return only wall segments suitable for 3D extrusion.
 *
 * The backend already filters to the largest connected component (the
 * apartment), so we only need to exclude 'unknown' wall types here
 * (doors, dimension lines, unclassified segments).
 */
export function getWallsFor3D(data: FloorplanData): WallData[] {
  return data.walls.filter((w) => WALL_TYPES_FOR_3D.has(w.wall_type));
}

// ---------------------------------------------------------------------------
// WallMesh
// ---------------------------------------------------------------------------

interface WallMeshProps {
  wall: WallData;
  scaleFactor: number;
  openings?: OpeningOnWall[];
}

export function WallMesh({ wall, scaleFactor, openings }: WallMeshProps) {
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

  const geometry = useMemo(() => {
    if (!geo) return null;

    // No openings — simple box (more efficient)
    if (!openings || openings.length === 0) {
      return new THREE.BoxGeometry(geo.length, CEILING_HEIGHT_M, geo.thickness);
    }

    // Build wall face with holes for openings
    const halfLen = geo.length / 2;
    const shape = new THREE.Shape();
    shape.moveTo(-halfLen, 0);
    shape.lineTo(halfLen, 0);
    shape.lineTo(halfLen, CEILING_HEIGHT_M);
    shape.lineTo(-halfLen, CEILING_HEIGHT_M);
    shape.closePath();

    for (const op of openings) {
      // Convert offset (from wall start) to centered coords
      const cx = op.offset - halfLen;
      let left = cx - op.width / 2;
      let right = cx + op.width / 2;
      let bottom = op.sillHeight;
      let top = op.sillHeight + op.height;

      // Inset hole edges that coincide with the outer shape boundary.
      // Earcut triangulation fails silently when hole vertices sit exactly
      // on the outer contour (produces zero-area triangles → no visible hole).
      if (bottom <= 0) bottom = HOLE_INSET;
      if (top >= CEILING_HEIGHT_M) top = CEILING_HEIGHT_M - HOLE_INSET;
      if (left <= -halfLen) left = -halfLen + HOLE_INSET;
      if (right >= halfLen) right = halfLen - HOLE_INSET;

      const hole = new THREE.Path();
      hole.moveTo(left, bottom);
      hole.lineTo(right, bottom);
      hole.lineTo(right, top);
      hole.lineTo(left, top);
      hole.closePath();
      shape.holes.push(hole);
    }

    const extruded = new THREE.ExtrudeGeometry(shape, {
      depth: geo.thickness,
      bevelEnabled: false,
    });
    // Center on thickness axis so wall midline aligns with position
    extruded.translate(0, 0, -geo.thickness / 2);
    return extruded;
  }, [geo, openings]);

  if (!geo || !geometry) return null;

  // BoxGeometry is centered at origin → position at midpoint, half-height up.
  // ExtrudeGeometry starts at Y=0 → position at midpoint, Y=0.
  const hasOpenings = openings && openings.length > 0;
  const posY = hasOpenings ? 0 : CEILING_HEIGHT_M / 2;

  return (
    <mesh
      geometry={geometry}
      position={[
        (geo.s.x + geo.e.x) / 2,
        posY,
        (geo.s.z + geo.e.z) / 2,
      ]}
      rotation={[0, -geo.angle, 0]}
      userData={{ wallType: wall.wall_type, id: wall.id }}
    >
      <meshStandardMaterial
        color={WALL_COLORS[wall.wall_type] ?? WALL_COLORS.unknown}
        roughness={0.8}
      />
    </mesh>
  );
}

// ---------------------------------------------------------------------------
// GlassPane — translucent panel for window openings
// ---------------------------------------------------------------------------

const glassMaterial = new THREE.MeshPhysicalMaterial({
  color: '#E8F4FD',
  metalness: 0,
  roughness: 0.1,
  transmission: 0.9,
  thickness: 0.01,
  ior: 1.5,
  transparent: true,
  opacity: 0.3,
  side: THREE.DoubleSide,
});

interface GlassPaneProps {
  opening: OpeningOnWall;
  wallStart: { x: number; z: number };
  wallEnd: { x: number; z: number };
  wallLength: number;
  wallAngle: number;
}

function GlassPane({ opening, wallStart, wallEnd, wallLength, wallAngle }: GlassPaneProps) {
  const position = useMemo(() => {
    // Interpolate position along wall at opening.offset
    const t = opening.offset / wallLength;
    const x = wallStart.x + t * (wallEnd.x - wallStart.x);
    const z = wallStart.z + t * (wallEnd.z - wallStart.z);
    const y = opening.sillHeight + opening.height / 2;
    return [x, y, z] as [number, number, number];
  }, [opening, wallStart, wallEnd, wallLength]);

  return (
    <mesh
      position={position}
      rotation={[0, -wallAngle, 0]}
      material={glassMaterial}
    >
      <planeGeometry args={[opening.width, opening.height]} />
    </mesh>
  );
}

// ---------------------------------------------------------------------------
// DoorPanel — thin recessed panel for door openings
// ---------------------------------------------------------------------------

const doorMaterial = new THREE.MeshStandardMaterial({
  color: '#8B6914',
  roughness: 0.6,
});

function DoorPanel({ opening, wallStart, wallEnd, wallLength, wallAngle }: GlassPaneProps) {
  const position = useMemo(() => {
    const t = opening.offset / wallLength;
    const x = wallStart.x + t * (wallEnd.x - wallStart.x);
    const z = wallStart.z + t * (wallEnd.z - wallStart.z);
    const y = opening.height / 2; // doors start at floor
    return [x, y, z] as [number, number, number];
  }, [opening, wallStart, wallEnd, wallLength]);

  return (
    <mesh
      position={position}
      rotation={[0, -wallAngle, 0]}
      material={doorMaterial}
    >
      <boxGeometry args={[opening.width - 0.04, opening.height - 0.02, 0.03]} />
    </mesh>
  );
}

// ---------------------------------------------------------------------------
// WallGroup — all walls, toggleable as a layer
// ---------------------------------------------------------------------------

interface WallGroupProps {
  walls: WallData[];
  scaleFactor: number;
  wallOpenings: Map<string, OpeningOnWall[]>;
}

function WallGroup({ walls, scaleFactor, wallOpenings }: WallGroupProps) {
  return (
    <group name="walls">
      {walls.map((w) => {
        const openings = wallOpenings.get(w.id);
        return (
          <WallMesh
            key={w.id}
            wall={w}
            scaleFactor={scaleFactor}
            openings={openings}
          />
        );
      })}
    </group>
  );
}

// ---------------------------------------------------------------------------
// OpeningsGroup — glass panes for windows, door panels for doors
// ---------------------------------------------------------------------------

function OpeningsGroup({
  walls,
  scaleFactor,
  wallOpenings,
}: WallGroupProps) {
  const items = useMemo(() => {
    const result: Array<{
      opening: OpeningOnWall;
      wallStart: { x: number; z: number };
      wallEnd: { x: number; z: number };
      wallLength: number;
      wallAngle: number;
    }> = [];

    for (const wall of walls) {
      const openings = wallOpenings.get(wall.id);
      if (!openings || openings.length === 0) continue;

      const s = pdfToThree(toCm(wall.start.x, scaleFactor), toCm(wall.start.y, scaleFactor));
      const e = pdfToThree(toCm(wall.end.x, scaleFactor), toCm(wall.end.y, scaleFactor));
      const dx = e.x - s.x;
      const dz = e.z - s.z;
      const length = Math.sqrt(dx * dx + dz * dz);
      const angle = Math.atan2(dz, dx);

      for (const op of openings) {
        result.push({
          opening: op,
          wallStart: s,
          wallEnd: e,
          wallLength: length,
          wallAngle: angle,
        });
      }
    }
    return result;
  }, [walls, scaleFactor, wallOpenings]);

  return (
    <group name="openings">
      {items.map((item) =>
        item.opening.type === 'window' ? (
          <GlassPane key={`glass-${item.opening.id}`} {...item} />
        ) : item.opening.type === 'door' ? (
          <DoorPanel key={`door-${item.opening.id}`} {...item} />
        ) : (
          // french_door / sliding_door → glass pane (full height, no door panel)
          <GlassPane key={`glass-${item.opening.id}`} {...item} />
        ),
      )}
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
  wallOpenings: Map<string, OpeningOnWall[]>;
  center: THREE.Vector3;
  cameraPos: THREE.Vector3;
}

/** Compute filtered walls, opening matching, centroid, and auto-fit camera position. */
function computeLayout(data: FloorplanData): SceneLayout {
  const filteredWalls = getWallsFor3D(data);

  // Match openings to walls
  const wallOpenings = matchOpeningsToWalls(
    filteredWalls,
    data.openings,
    data.scale_factor,
  );

  const walls = filteredWalls.length > 0 ? filteredWalls : data.walls;

  if (walls.length === 0) {
    return {
      filteredWalls,
      wallOpenings,
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

  return { filteredWalls, wallOpenings, center, cameraPos };
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

      <WallGroup
        walls={layout.filteredWalls}
        scaleFactor={data.scale_factor}
        wallOpenings={layout.wallOpenings}
      />

      <OpeningsGroup
        walls={layout.filteredWalls}
        scaleFactor={data.scale_factor}
        wallOpenings={layout.wallOpenings}
      />

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
