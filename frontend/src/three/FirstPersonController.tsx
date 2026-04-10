/**
 * FirstPersonController — first-person camera for 3D walkthrough.
 *
 * Handles: pointer lock, mouse look (yaw/pitch), WASD movement,
 * wall collision with slide, and mobile input via shared refs.
 *
 * Renders null — manages the R3F camera via useThree + useFrame.
 */

import { useEffect, useRef, useCallback } from 'react';
import { useThree, useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { EYE_HEIGHT_M } from './coordinateUtils';
import type { Room } from '@/types/floorplan';
import { pdfPointsToThree } from './coordinateUtils';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MOVE_SPEED = 2.0; // m/s
const SPRINT_MULTIPLIER = 2.0;
const MOUSE_SENSITIVITY = 0.002; // rad/px
const PITCH_LIMIT = (80 * Math.PI) / 180; // ±80°
const COLLISION_DISTANCE = 0.3; // m — raycast lookahead
const LERP_FACTOR = 0.15; // position smoothing per frame
const FPS_FOV = 70;
const OVERVIEW_FOV = 60;

// 8 ray directions for collision (cardinal + diagonal)
const RAY_DIRECTIONS = [
  new THREE.Vector3(1, 0, 0),
  new THREE.Vector3(-1, 0, 0),
  new THREE.Vector3(0, 0, 1),
  new THREE.Vector3(0, 0, -1),
  new THREE.Vector3(0.7071, 0, 0.7071),
  new THREE.Vector3(-0.7071, 0, 0.7071),
  new THREE.Vector3(0.7071, 0, -0.7071),
  new THREE.Vector3(-0.7071, 0, -0.7071),
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Find the best room to start in: prefer salon, then largest by area. */
export function getLargestRoom(rooms: Room[]): Room | undefined {
  if (rooms.length === 0) return undefined;
  const salon = rooms.find((r) => r.type === 'salon');
  if (salon) return salon;
  return rooms.reduce((best, r) => (r.area_sqm > best.area_sqm ? r : best), rooms[0]);
}

/** Compute start position from the best room's centroid. */
export function computeStartPosition(
  rooms: Room[],
  scaleFactor: number,
): THREE.Vector3 {
  const room = getLargestRoom(rooms);
  if (!room) return new THREE.Vector3(0, EYE_HEIGHT_M, 0);
  const pos = pdfPointsToThree(room.centroid.x, room.centroid.y, scaleFactor);
  return new THREE.Vector3(pos.x, EYE_HEIGHT_M, pos.z);
}

/** Compute forward direction from yaw (projected to XZ plane). */
export function forwardFromYaw(yaw: number): THREE.Vector3 {
  return new THREE.Vector3(-Math.sin(yaw), 0, -Math.cos(yaw));
}

/** Compute right direction from yaw. */
function rightFromYaw(yaw: number): THREE.Vector3 {
  return new THREE.Vector3(-Math.cos(yaw), 0, Math.sin(yaw));
}

/**
 * Project a movement vector onto a wall surface (wall slide).
 * Removes the component of movement that goes into the wall.
 */
export function wallSlide(
  movement: THREE.Vector3,
  wallNormal: THREE.Vector3,
): THREE.Vector3 {
  const dot = movement.dot(wallNormal);
  if (dot >= 0) return movement.clone(); // moving away from wall
  return movement.clone().sub(wallNormal.clone().multiplyScalar(dot));
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface FirstPersonControllerProps {
  enabled: boolean;
  startPosition: THREE.Vector3;
  wallGroupRef: React.RefObject<THREE.Group | null>;
  onPositionChange?: (pos: THREE.Vector3, yaw: number) => void;
  moveInputRef?: React.RefObject<{ x: number; z: number }>;
  lookInputRef?: React.RefObject<{ yaw: number; pitch: number }>;
  /** Write { x, z } to this ref to teleport the camera. Consumed once per frame. */
  teleportRef?: React.MutableRefObject<{ x: number; z: number } | null>;
}

export default function FirstPersonController({
  enabled,
  startPosition,
  wallGroupRef,
  onPositionChange,
  moveInputRef,
  lookInputRef,
  teleportRef,
}: FirstPersonControllerProps) {
  const { camera, gl } = useThree();

  const yaw = useRef(0);
  const pitch = useRef(0);
  const keys = useRef(new Set<string>());
  const isLocked = useRef(false);
  const isDragging = useRef(false);
  const lastDrag = useRef<{ x: number; y: number } | null>(null);
  const targetPos = useRef(new THREE.Vector3());
  const raycaster = useRef(new THREE.Raycaster());
  const prevFov = useRef(OVERVIEW_FOV);
  const initialized = useRef(false);

  // Reusable vectors (avoid GC)
  const _movement = useRef(new THREE.Vector3());
  const _rayOrigin = useRef(new THREE.Vector3());

  // -----------------------------------------------------------------------
  // Init / cleanup
  // -----------------------------------------------------------------------

  useEffect(() => {
    if (!enabled) return;

    // Save previous FOV and set FPS FOV
    const perspCam = camera as THREE.PerspectiveCamera;
    prevFov.current = perspCam.fov;
    // eslint-disable-next-line react-hooks/immutability -- R3F camera is intentionally mutable
    perspCam.fov = FPS_FOV;
    perspCam.updateProjectionMatrix();

    // Set start position
    camera.position.copy(startPosition);
    targetPos.current.copy(startPosition);
    yaw.current = 0;
    pitch.current = 0;
    initialized.current = true;

    return () => {
      // Restore FOV
      perspCam.fov = prevFov.current;
      perspCam.updateProjectionMatrix();

      // Exit pointer lock if active
      if (document.pointerLockElement === gl.domElement) {
        document.exitPointerLock();
      }
      initialized.current = false;
    };
  }, [enabled, camera, gl, startPosition]);

  // -----------------------------------------------------------------------
  // Pointer lock + click-drag look (alternative)
  // -----------------------------------------------------------------------

  const requestLock = useCallback(() => {
    if (enabled && gl.domElement) {
      gl.domElement.requestPointerLock();
    }
  }, [enabled, gl]);

  useEffect(() => {
    if (!enabled) return;

    const canvas = gl.domElement;

    const onLockChange = () => {
      isLocked.current = document.pointerLockElement === canvas;
    };

    const onMouseMove = (e: MouseEvent) => {
      if (isLocked.current) {
        // Pointer lock mode: use movementX/Y
        yaw.current -= e.movementX * MOUSE_SENSITIVITY;
        pitch.current -= e.movementY * MOUSE_SENSITIVITY;
        pitch.current = Math.max(-PITCH_LIMIT, Math.min(PITCH_LIMIT, pitch.current));
      } else if (isDragging.current && lastDrag.current) {
        // Click-drag mode: compute delta from last position
        const dx = e.clientX - lastDrag.current.x;
        const dy = e.clientY - lastDrag.current.y;
        yaw.current -= dx * MOUSE_SENSITIVITY;
        pitch.current -= dy * MOUSE_SENSITIVITY;
        pitch.current = Math.max(-PITCH_LIMIT, Math.min(PITCH_LIMIT, pitch.current));
        lastDrag.current = { x: e.clientX, y: e.clientY };
      }
    };

    const onMouseDown = (e: MouseEvent) => {
      if (e.button === 0 && !isLocked.current) {
        isDragging.current = true;
        lastDrag.current = { x: e.clientX, y: e.clientY };
        canvas.style.cursor = 'grabbing';
      }
    };

    const onMouseUp = () => {
      isDragging.current = false;
      lastDrag.current = null;
      if (!isLocked.current) {
        canvas.style.cursor = 'grab';
      }
    };

    const onDblClick = () => {
      // Double-click to enter pointer lock (optional)
      requestLock();
    };

    // Set initial cursor
    // eslint-disable-next-line react-hooks/immutability -- DOM style, not React state
    canvas.style.cursor = 'grab';

    canvas.addEventListener('mousedown', onMouseDown);
    canvas.addEventListener('dblclick', onDblClick);
    document.addEventListener('mouseup', onMouseUp);
    document.addEventListener('pointerlockchange', onLockChange);
    document.addEventListener('mousemove', onMouseMove);

    return () => {
      canvas.removeEventListener('mousedown', onMouseDown);
      canvas.removeEventListener('dblclick', onDblClick);
      document.removeEventListener('mouseup', onMouseUp);
      document.removeEventListener('pointerlockchange', onLockChange);
      document.removeEventListener('mousemove', onMouseMove);
      canvas.style.cursor = '';
    };
  }, [enabled, gl, requestLock]);

  // -----------------------------------------------------------------------
  // Keyboard
  // -----------------------------------------------------------------------

  useEffect(() => {
    if (!enabled) return;

    const onKeyDown = (e: KeyboardEvent) => {
      keys.current.add(e.code);
    };
    const onKeyUp = (e: KeyboardEvent) => {
      keys.current.delete(e.code);
    };

    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);

    const keysRef = keys.current;
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
      keysRef.clear();
    };
  }, [enabled]);

  // -----------------------------------------------------------------------
  // Collision check
  // -----------------------------------------------------------------------

  const checkCollision = useCallback(
    (origin: THREE.Vector3, direction: THREE.Vector3): THREE.Intersection | null => {
      if (!wallGroupRef.current) return null;

      const rc = raycaster.current;
      rc.set(origin, direction.clone().normalize());
      rc.near = 0;
      rc.far = COLLISION_DISTANCE;

      const hits = rc.intersectObjects(wallGroupRef.current.children, true);
      return hits.length > 0 ? hits[0] : null;
    },
    [wallGroupRef],
  );

  // -----------------------------------------------------------------------
  // Frame loop
  // -----------------------------------------------------------------------

  useFrame((_, delta) => {
    if (!enabled || !initialized.current) return;

    // Clamp delta to avoid huge jumps after tab switch
    const dt = Math.min(delta, 0.1);

    // --- Look (mobile input or mouse) ---
    if (lookInputRef?.current) {
      const look = lookInputRef.current;
      yaw.current += look.yaw;
      pitch.current += look.pitch;
      pitch.current = Math.max(-PITCH_LIMIT, Math.min(PITCH_LIMIT, pitch.current));
      look.yaw = 0;
      look.pitch = 0;
    }

    // Apply rotation
    const euler = new THREE.Euler(pitch.current, yaw.current, 0, 'YXZ');
    camera.quaternion.setFromEuler(euler);

    // --- Movement ---
    const fwd = forwardFromYaw(yaw.current);
    const right = rightFromYaw(yaw.current);
    const move = _movement.current.set(0, 0, 0);

    // Desktop keyboard input
    const k = keys.current;
    if (k.has('KeyW') || k.has('ArrowUp')) move.add(fwd);
    if (k.has('KeyS') || k.has('ArrowDown')) move.sub(fwd);
    if (k.has('KeyA') || k.has('ArrowLeft')) move.add(right);
    if (k.has('KeyD') || k.has('ArrowRight')) move.sub(right);

    // Mobile joystick input (additive)
    if (moveInputRef?.current) {
      const mi = moveInputRef.current;
      if (mi.x !== 0 || mi.z !== 0) {
        move.add(right.clone().multiplyScalar(-mi.x));
        move.add(fwd.clone().multiplyScalar(-mi.z));
      }
    }

    // Normalize diagonal movement
    if (move.lengthSq() > 0) {
      move.normalize();

      const speed = k.has('ShiftLeft') || k.has('ShiftRight')
        ? MOVE_SPEED * SPRINT_MULTIPLIER
        : MOVE_SPEED;
      move.multiplyScalar(speed * dt);

      // --- Collision detection + wall slide ---
      const origin = _rayOrigin.current.copy(camera.position);
      const moveDir = move.clone().normalize();

      const hit = checkCollision(origin, moveDir);
      if (hit && hit.face) {
        // Transform face normal to world space
        const normal = hit.face.normal.clone();
        normal.transformDirection(hit.object.matrixWorld);
        normal.y = 0;
        normal.normalize();

        // Wall slide: remove component into wall
        const slid = wallSlide(move, normal);
        targetPos.current.add(slid);
      } else {
        targetPos.current.add(move);
      }

      // Secondary collision check after slide (prevent corner clipping)
      for (const dir of RAY_DIRECTIONS) {
        const secondHit = checkCollision(targetPos.current, dir);
        if (secondHit && secondHit.distance < COLLISION_DISTANCE * 0.5) {
          // Push back out of wall
          const pushDir = dir.clone().negate();
          const pushDist = COLLISION_DISTANCE * 0.5 - secondHit.distance;
          targetPos.current.add(pushDir.multiplyScalar(pushDist));
        }
      }
    }

    // Teleport request (from minimap click)
    if (teleportRef?.current) {
      const tp = teleportRef.current;
      targetPos.current.set(tp.x, EYE_HEIGHT_M, tp.z);
      camera.position.set(tp.x, EYE_HEIGHT_M, tp.z);
      teleportRef.current = null;
    }

    // Lock Y to eye height
    targetPos.current.y = EYE_HEIGHT_M;

    // Smooth position
    camera.position.lerp(targetPos.current, LERP_FACTOR);
    // eslint-disable-next-line react-hooks/immutability -- R3F camera position is intentionally mutable
    camera.position.y = EYE_HEIGHT_M;

    // Notify parent (for minimap)
    onPositionChange?.(camera.position, yaw.current);
  });

  return null;
}
