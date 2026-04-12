/**
 * FloorplanScene — React Three Fiber component.
 * Converts Phase 1 2D plan data (walls, rooms) into a 3D scene.
 */

import { useMemo, useState, useRef, useCallback } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import type { FloorplanData, Wall as WallData, Room as RoomData, Opening as OpeningData } from '@/types/floorplan';
import {
  pdfToThree,
  CEILING_HEIGHT_M,
  WALL_THICKNESS_M,
  WALL_COLORS,
  FLOOR_COLORS,
  CEILING_COLOR,
  BASEBOARD_COLOR,
  BASEBOARD_HEIGHT_M,
} from './coordinateUtils';
import { matchOpeningsToWalls, type OpeningOnWall } from './openingUtils';
import { mergeCollinearWalls, mergeParallelWalls, mergedToWall, filterDoorZones } from './wallMerger';
import FirstPersonController, { computeStartPosition } from './FirstPersonController';
import CameraTransition from './CameraTransition';
import SceneToolbar, { type ViewMode } from './SceneToolbar';
import Minimap from './Minimap';
import MobileControls, { isMobileDevice } from './MobileControls';

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

  if (!geo) return null;

  const color = WALL_COLORS[wall.wall_type] ?? WALL_COLORS.unknown;
  const midX = (geo.s.x + geo.e.x) / 2;
  const midZ = (geo.s.z + geo.e.z) / 2;
  const rot: [number, number, number] = [0, -geo.angle, 0];

  // No openings — simple solid wall
  if (!openings || openings.length === 0) {
    return (
      <mesh
        position={[midX, CEILING_HEIGHT_M / 2, midZ]}
        rotation={rot}
        userData={{ wallType: wall.wall_type, id: wall.id }}
      >
        <boxGeometry args={[geo.length, CEILING_HEIGHT_M, geo.thickness]} />
        <meshStandardMaterial color={color} roughness={0.8} />
      </mesh>
    );
  }

  // ---- Wall splitting: build pieces around openings ----
  // Openings are sorted by offset. We split the wall into:
  //   solid pieces between openings + sill/lintel around each opening + glass pane
  // All positions are in LOCAL wall coords: X along wall, Y up, centered at wall midpoint.
  const halfLen = geo.length / 2;
  const pieces: JSX.Element[] = [];

  // Sort openings by offset (should already be sorted, but ensure)
  const sorted = [...openings].sort((a, b) => a.offset - b.offset);

  // Clamp openings to wall bounds
  const clamped = sorted.map((op) => {
    const halfW = op.width / 2;
    const left = Math.max(0, op.offset - halfW);
    const right = Math.min(geo.length, op.offset + halfW);
    return { ...op, left, right };
  });

  let cursor = 0; // current position along wall (from start)

  for (let i = 0; i < clamped.length; i++) {
    const op = clamped[i];
    const opLeft = op.left;
    const opRight = op.right;
    const opBottom = op.sillHeight;
    const opTop = op.sillHeight + op.height;

    // 1. Solid wall piece from cursor to opening left edge
    const solidLen = opLeft - cursor;
    if (solidLen > 0.01) {
      const solidCenterX = cursor + solidLen / 2 - halfLen;
      pieces.push(
        <mesh
          key={`${wall.id}-solid-${i}`}
          position={[solidCenterX, CEILING_HEIGHT_M / 2, 0]}
        >
          <boxGeometry args={[solidLen, CEILING_HEIGHT_M, geo.thickness]} />
          <meshStandardMaterial color={color} roughness={0.8} />
        </mesh>,
      );
    }

    // 2. Sill piece below opening (floor to sill height)
    if (opBottom > 0.01) {
      const sillCenterX = (opLeft + opRight) / 2 - halfLen;
      pieces.push(
        <mesh
          key={`${wall.id}-sill-${i}`}
          position={[sillCenterX, opBottom / 2, 0]}
        >
          <boxGeometry args={[opRight - opLeft, opBottom, geo.thickness]} />
          <meshStandardMaterial color={color} roughness={0.8} />
        </mesh>,
      );
    }

    // 3. Lintel piece above opening (opening top to ceiling)
    const lintelHeight = CEILING_HEIGHT_M - opTop;
    if (lintelHeight > 0.01) {
      const lintelCenterX = (opLeft + opRight) / 2 - halfLen;
      pieces.push(
        <mesh
          key={`${wall.id}-lintel-${i}`}
          position={[lintelCenterX, opTop + lintelHeight / 2, 0]}
        >
          <boxGeometry args={[opRight - opLeft, lintelHeight, geo.thickness]} />
          <meshStandardMaterial color={color} roughness={0.8} />
        </mesh>,
      );
    }

    // 4. Glass pane in the opening
    if (op.type === 'window' || op.type === 'french_door' || op.type === 'sliding_door') {
      const glassCenterX = (opLeft + opRight) / 2 - halfLen;
      pieces.push(
        <mesh
          key={`${wall.id}-glass-${i}`}
          position={[glassCenterX, opBottom + op.height / 2, 0]}
          material={glassMaterial}
        >
          <planeGeometry args={[opRight - opLeft, op.height]} />
        </mesh>,
      );
    }

    console.log(
      `[3D] Wall ${wall.id} split: ${op.type} ${op.id} at [${opLeft.toFixed(2)}-${opRight.toFixed(2)}]m, ` +
      `sill=${opBottom.toFixed(2)}m, top=${opTop.toFixed(2)}m, wallLen=${geo.length.toFixed(2)}m`,
    );

    cursor = opRight;
  }

  // 5. Final solid piece from last opening right edge to wall end
  const finalLen = geo.length - cursor;
  if (finalLen > 0.01) {
    const finalCenterX = cursor + finalLen / 2 - halfLen;
    pieces.push(
      <mesh
        key={`${wall.id}-solid-end`}
        position={[finalCenterX, CEILING_HEIGHT_M / 2, 0]}
      >
        <boxGeometry args={[finalLen, CEILING_HEIGHT_M, geo.thickness]} />
        <meshStandardMaterial color={color} roughness={0.8} />
      </mesh>,
    );
  }

  // Wrap all pieces in a group positioned + rotated like the original wall
  return (
    <group
      position={[midX, 0, midZ]}
      rotation={rot}
      userData={{ wallType: wall.wall_type, id: wall.id }}
    >
      {pieces}
    </group>
  );
}

// ---------------------------------------------------------------------------
// Glass material — shared by window panes in WallMesh and DirectDoorGroup
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

// ---------------------------------------------------------------------------
// Door material (shared by DirectDoorGroup)
// ---------------------------------------------------------------------------

const doorMaterial = new THREE.MeshStandardMaterial({
  color: '#8B6914',
  roughness: 0.6,
});

// ---------------------------------------------------------------------------
// WallGroup — all walls, toggleable as a layer
// ---------------------------------------------------------------------------

interface WallGroupProps {
  walls: WallData[];
  scaleFactor: number;
  wallOpenings: Map<string, OpeningOnWall[]>;
  groupRef?: React.RefObject<THREE.Group | null>;
}

function WallGroup({ walls, scaleFactor, wallOpenings, groupRef }: WallGroupProps) {
  return (
    <group name="walls" ref={groupRef as React.Ref<THREE.Group>}>
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
// DirectDoorGroup — renders door panels directly from API endpoint positions.
// Doors are gaps between wall segments.  The gap IS the opening; we just
// render a thin panel in the gap for visual context.
// ---------------------------------------------------------------------------

import {
  DOOR_HEIGHT_M,
  GLASS_DOOR_HEIGHT_M,
} from './coordinateUtils';

interface DirectDoorGroupProps {
  openings: OpeningData[];
  scaleFactor: number;
}

function DirectDoorGroup({ openings, scaleFactor }: DirectDoorGroupProps) {
  const doors = useMemo(() => {
    const result: Array<{
      id: string;
      position: [number, number, number];
      rotation: [number, number, number];
      width: number;
      height: number;
      isGlass: boolean;
    }> = [];

    for (const op of openings) {
      if (op.type === 'window') continue;
      if (!op.endpoints) continue;

      const [p1, p2] = op.endpoints;
      const s = pdfToThree(toCm(p1.x, scaleFactor), toCm(p1.y, scaleFactor));
      const e = pdfToThree(toCm(p2.x, scaleFactor), toCm(p2.y, scaleFactor));

      const dx = e.x - s.x;
      const dz = e.z - s.z;
      const width = Math.sqrt(dx * dx + dz * dz);
      const angle = Math.atan2(dz, dx);

      const isGlass =
        width > 1.4 ||
        op.type === 'french_door' ||
        op.type === 'sliding_door';
      const height = isGlass ? GLASS_DOOR_HEIGHT_M : DOOR_HEIGHT_M;

      result.push({
        id: op.id,
        position: [(s.x + e.x) / 2, height / 2, (s.z + e.z) / 2],
        rotation: [0, -angle, 0],
        width,
        height,
        isGlass,
      });
    }
    return result;
  }, [openings, scaleFactor]);

  return (
    <group name="doors">
      {doors.map((d) =>
        d.isGlass ? (
          <mesh
            key={`glass-door-${d.id}`}
            position={d.position}
            rotation={d.rotation}
            material={glassMaterial}
          >
            <planeGeometry args={[d.width, d.height]} />
          </mesh>
        ) : (
          <mesh
            key={`door-${d.id}`}
            position={d.position}
            rotation={d.rotation}
            material={doorMaterial}
          >
            <boxGeometry args={[d.width - 0.04, d.height - 0.02, 0.04]} />
          </mesh>
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
      <meshStandardMaterial color={CEILING_COLOR} roughness={0.9} side={THREE.BackSide} />
    </mesh>
  );
}

// ---------------------------------------------------------------------------
// BaseboardGroup — thin dark strip where walls meet floor
// ---------------------------------------------------------------------------

const baseboardMaterial = new THREE.MeshStandardMaterial({
  color: BASEBOARD_COLOR,
  roughness: 0.7,
});

function BaseboardGroup({
  walls,
  scaleFactor,
}: {
  walls: WallData[];
  scaleFactor: number;
}) {
  const baseboards = useMemo(() => {
    return walls
      .map((w) => {
        const s = pdfToThree(toCm(w.start.x, scaleFactor), toCm(w.start.y, scaleFactor));
        const e = pdfToThree(toCm(w.end.x, scaleFactor), toCm(w.end.y, scaleFactor));
        const dx = e.x - s.x;
        const dz = e.z - s.z;
        const length = Math.sqrt(dx * dx + dz * dz);
        if (length < 0.01) return null;
        const angle = Math.atan2(dz, dx);
        const thickness = (WALL_THICKNESS_M[w.wall_type] ?? WALL_THICKNESS_M.unknown) + 0.01;
        return { s, e, length, angle, thickness, id: w.id };
      })
      .filter(Boolean) as Array<{
      s: { x: number; z: number };
      e: { x: number; z: number };
      length: number;
      angle: number;
      thickness: number;
      id: string;
    }>;
  }, [walls, scaleFactor]);

  return (
    <group name="baseboards">
      {baseboards.map((b) => (
        <mesh
          key={`baseboard-${b.id}`}
          position={[
            (b.s.x + b.e.x) / 2,
            BASEBOARD_HEIGHT_M / 2,
            (b.s.z + b.e.z) / 2,
          ]}
          rotation={[0, -b.angle, 0]}
          material={baseboardMaterial}
        >
          <boxGeometry args={[b.length, BASEBOARD_HEIGHT_M, b.thickness]} />
        </mesh>
      ))}
    </group>
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
  const rawFiltered = getWallsFor3D(data);

  console.log(`[3D] computeLayout: ${data.walls.length} total walls, ${rawFiltered.length} after type filter, ${data.openings.length} openings`);

  // 1. Remove wall fragments inside door openings.  The door gap between
  //    segments IS the opening — we just need to clear fragments that block it.
  const afterDoorFilter = filterDoorZones(rawFiltered, data.openings);

  console.log(`[3D] After door zone filter: ${afterDoorFilter.length} walls (removed ${rawFiltered.length - afterDoorFilter.length})`);

  // 2. Merge collinear wall segments into continuous walls for 3D rendering.
  //    The healing pipeline splits walls at every intersection, producing
  //    hundreds of tiny fragments too short to cut window holes into.
  const collinearMerged = mergeCollinearWalls(afterDoorFilter);

  // 3. Merge parallel overlapping walls — Israeli PDFs draw exterior walls
  //    as 2-3 parallel lines (inner/outer face + fill). Without this,
  //    overlapping wall meshes block window/door openings.
  const parallelMerged = mergeParallelWalls(collinearMerged);
  let mergedWalls = parallelMerged.map(mergedToWall);

  console.log(`[3D] After merger: ${mergedWalls.length} merged walls`);

  // Remove outliers: walls whose midpoint is far from the apartment centroid.
  // Catches stairwell elements, legend fragments, and neighbor outlines that
  // survived the largest-component filter.
  if (mergedWalls.length > 4) {
    const midpoints = mergedWalls.map((w) => ({
      x: (w.start.x + w.end.x) / 2,
      y: (w.start.y + w.end.y) / 2,
    }));
    const cx = midpoints.reduce((s, p) => s + p.x, 0) / midpoints.length;
    const cy = midpoints.reduce((s, p) => s + p.y, 0) / midpoints.length;
    const dists = midpoints.map((p) =>
      Math.sqrt((p.x - cx) ** 2 + (p.y - cy) ** 2),
    );
    // Threshold: median distance × 2.0
    const sorted = [...dists].sort((a, b) => a - b);
    const median = sorted[Math.floor(sorted.length / 2)];
    const threshold = median * 2.0;
    const before = mergedWalls.length;
    mergedWalls = mergedWalls.filter((_, i) => dists[i] <= threshold);
    if (mergedWalls.length < before) {
      console.log(
        `[3D] Outlier filter: removed ${before - mergedWalls.length} distant walls (threshold=${threshold.toFixed(0)}pt)`,
      );
    }
  }

  const filteredWalls = mergedWalls;

  console.log(`[3D] Final wall count for rendering: ${filteredWalls.length}`);

  // Match openings to merged walls (now long enough for proper hole-cutting)
  const wallOpenings = matchOpeningsToWalls(
    filteredWalls,
    data.openings,
    data.scale_factor,
  );

  // Log all matched openings (windows + glass doors)
  let windowHoleCount = 0;
  let totalOpeningsMatched = 0;
  for (const [wallId, ops] of wallOpenings) {
    totalOpeningsMatched += ops.length;
    const windows = ops.filter((o) => o.type === 'window');
    if (windows.length > 0) {
      const wall = filteredWalls.find((w) => w.id === wallId);
      const wallLenM = wall
        ? Math.sqrt((wall.end.x - wall.start.x) ** 2 + (wall.end.y - wall.start.y) ** 2) * data.scale_factor
        : 0;
      for (const win of windows) {
        console.log(
          `[3D] WINDOW HOLE: ${win.id} on wall ${wallId} (${wall?.wall_type}, ${wallLenM.toFixed(2)}m): ` +
          `offset=${win.offset.toFixed(3)}m, size=${win.width.toFixed(2)}x${win.height.toFixed(2)}m, sill=${win.sillHeight.toFixed(2)}m`,
        );
      }
      windowHoleCount += windows.length;
    }
  }
  console.log(`[3D] Total openings matched: ${totalOpeningsMatched} (${windowHoleCount} windows, ${totalOpeningsMatched - windowHoleCount} others)`);

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

  // View mode state (lifted above Canvas so overlays can read it)
  const [viewMode, setViewMode] = useState<ViewMode>('overview');
  const [transitioning, setTransitioning] = useState(false);

  // Camera state for minimap
  const [cameraState, setCameraState] = useState({ x: 0, z: 0, yaw: 0 });

  // Wall group ref for collision detection
  const wallGroupRef = useRef<THREE.Group>(null);

  // Mobile input refs (shared between MobileControls and FirstPersonController)
  const moveInputRef = useRef({ x: 0, z: 0 });
  const lookInputRef = useRef({ yaw: 0, pitch: 0 });

  // Teleport ref — written by minimap click, consumed by FirstPersonController
  const teleportRef = useRef<{ x: number; z: number } | null>(null);

  const isMobile = useMemo(() => isMobileDevice(), []);

  // Start position for walkthrough (largest room centroid)
  const startPosition = useMemo(
    () => computeStartPosition(data.rooms, data.scale_factor),
    [data.rooms, data.scale_factor],
  );

  // Transition targets (state, not ref — used during render)
  const [transitionTarget, setTransitionTarget] = useState<{
    position: THREE.Vector3;
    quaternion: THREE.Quaternion;
    fov: number;
    nextMode: ViewMode;
  } | null>(null);

  const handleToggleMode = useCallback(() => {
    if (transitioning) return;

    const nextMode: ViewMode = viewMode === 'overview' ? 'walkthrough' : 'overview';

    if (nextMode === 'walkthrough') {
      // Transition to first-person position
      const q = new THREE.Quaternion();
      q.setFromEuler(new THREE.Euler(0, 0, 0, 'YXZ'));
      setTransitionTarget({
        position: startPosition.clone(),
        quaternion: q,
        fov: 70,
        nextMode,
      });
    } else {
      // Transition back to overview
      const lookAt = new THREE.Matrix4();
      lookAt.lookAt(layout.cameraPos, layout.center, new THREE.Vector3(0, 1, 0));
      const q = new THREE.Quaternion();
      q.setFromRotationMatrix(lookAt);
      setTransitionTarget({
        position: layout.cameraPos.clone(),
        quaternion: q,
        fov: 60,
        nextMode,
      });
    }

    setTransitioning(true);
  }, [viewMode, transitioning, startPosition, layout]);

  const handleTransitionComplete = useCallback(() => {
    const next = transitionTarget?.nextMode;
    if (next) setViewMode(next);
    setTransitioning(false);
    setTransitionTarget(null);
  }, [transitionTarget]);

  // Camera update callback from FirstPersonController
  const handleCameraUpdate = useCallback((pos: THREE.Vector3, yaw: number) => {
    setCameraState({ x: pos.x, z: pos.z, yaw });
  }, []);

  // Teleport from minimap
  const handleTeleport = useCallback(
    (x: number, z: number) => {
      teleportRef.current = { x, z };
    },
    [],
  );

  // FOV change from mobile pinch
  const handleFovChange = useCallback((_fov: number) => {
    // FOV is handled by FirstPersonController via camera ref
    // This is a simplified passthrough — in practice the camera.fov
    // is set by the controller
  }, []);

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
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
          groupRef={wallGroupRef}
        />

        {/* OpeningsGroup removed — glass panes now rendered inline by WallMesh */}

        <DirectDoorGroup
          openings={data.openings}
          scaleFactor={data.scale_factor}
        />

        <BaseboardGroup
          walls={layout.filteredWalls}
          scaleFactor={data.scale_factor}
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

        {/* Controls — only one active at a time */}
        {!transitioning && viewMode === 'overview' && (
          <OrbitControls
            target={layout.center.toArray()}
            enableDamping
            dampingFactor={0.05}
            minDistance={1}
            maxDistance={100}
          />
        )}

        {!transitioning && viewMode === 'walkthrough' && (
          <FirstPersonController
            enabled
            startPosition={startPosition}
            wallGroupRef={wallGroupRef}
            onPositionChange={handleCameraUpdate}
            moveInputRef={moveInputRef}
            lookInputRef={lookInputRef}
            teleportRef={teleportRef}
          />
        )}

        {transitioning && transitionTarget && (
          <CameraTransition
            targetPosition={transitionTarget.position}
            targetQuaternion={transitionTarget.quaternion}
            targetFov={transitionTarget.fov}
            duration={1.0}
            onComplete={handleTransitionComplete}
          />
        )}
      </Canvas>

      {/* HTML overlays — outside Canvas */}
      <SceneToolbar viewMode={viewMode} onToggle={handleToggleMode} />

      {viewMode === 'walkthrough' && !transitioning && (
        <>
          <Minimap
            rooms={data.rooms}
            walls={layout.filteredWalls}
            scaleFactor={data.scale_factor}
            cameraX={cameraState.x}
            cameraZ={cameraState.z}
            cameraYaw={cameraState.yaw}
            onTeleport={handleTeleport}
            visible
          />
          {isMobile && (
            <MobileControls
              moveInputRef={moveInputRef}
              lookInputRef={lookInputRef}
              onFovChange={handleFovChange}
              visible
            />
          )}
        </>
      )}

      {/* Pointer lock hint overlay */}
      {viewMode === 'walkthrough' && !transitioning && (
        <div
          style={{
            position: 'absolute',
            bottom: 60,
            left: '50%',
            transform: 'translateX(-50%)',
            color: 'rgba(255,255,255,0.5)',
            fontSize: '0.75rem',
            textAlign: 'center',
            zIndex: 5,
            pointerEvents: 'none',
          }}
        >
          WASD / חצים לתנועה | גרור עכבר להסתכלות | Shift = ריצה
        </div>
      )}
    </div>
  );
}
