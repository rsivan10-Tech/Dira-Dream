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
// FloorplanScene
// ---------------------------------------------------------------------------

interface FloorplanSceneProps {
  data: FloorplanData;
}

export default function FloorplanScene({ data }: FloorplanSceneProps) {
  // Compute apartment centroid for camera target
  const center = useMemo(() => {
    if (!data.walls.length) return new THREE.Vector3(0, 0, 0);

    let sx = 0;
    let sz = 0;
    let n = 0;
    for (const w of data.walls) {
      const a = pdfToThree(toCm(w.start.x, data.scale_factor), toCm(w.start.y, data.scale_factor));
      const b = pdfToThree(toCm(w.end.x, data.scale_factor), toCm(w.end.y, data.scale_factor));
      sx += a.x + b.x;
      sz += a.z + b.z;
      n += 2;
    }
    return new THREE.Vector3(sx / n, 0, sz / n);
  }, [data]);

  return (
    <Canvas
      camera={{
        position: [center.x, 15, center.z + 10],
        fov: 60,
        near: 0.1,
        far: 200,
      }}
      dpr={[1, 2]}
      style={{ width: '100%', height: '100%', background: '#e8e8e8' }}
    >
      {/* Lighting */}
      <ambientLight intensity={0.4} color="#ffffff" />
      <directionalLight
        position={[center.x + 10, 20, center.z - 10]}
        intensity={0.6}
        color="#ffffff"
      />
      {/* Secondary fill from opposite side to reduce harsh shadows */}
      <directionalLight
        position={[center.x - 8, 12, center.z + 8]}
        intensity={0.25}
        color="#f0f0ff"
      />

      <WallGroup walls={data.walls} scaleFactor={data.scale_factor} />

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
        target={[center.x, CEILING_HEIGHT_M / 2, center.z]}
        enableDamping
        dampingFactor={0.05}
        minDistance={1}
        maxDistance={30}
      />
    </Canvas>
  );
}
