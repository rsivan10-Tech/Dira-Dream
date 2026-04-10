/**
 * CameraTransition — animates camera between overview and walkthrough positions.
 *
 * Lerps position + slerps quaternion over a configurable duration.
 * Both OrbitControls and FirstPersonController should be unmounted while this
 * component is active.
 */

import { useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';

interface CameraTransitionProps {
  /** Target position to animate toward. */
  targetPosition: THREE.Vector3;
  /** Target quaternion to animate toward. */
  targetQuaternion: THREE.Quaternion;
  /** Target FOV to animate toward. */
  targetFov: number;
  /** Duration in seconds (default 1.0). */
  duration?: number;
  /** Called when animation completes. */
  onComplete: () => void;
}

export default function CameraTransition({
  targetPosition,
  targetQuaternion,
  targetFov,
  duration = 1.0,
  onComplete,
}: CameraTransitionProps) {
  const { camera } = useThree();
  const elapsed = useRef(0);
  const startPos = useRef<THREE.Vector3 | null>(null);
  const startQuat = useRef<THREE.Quaternion | null>(null);
  const startFov = useRef<number | null>(null);
  const completed = useRef(false);

  useFrame((_, delta) => {
    if (completed.current) return;

    // Capture start state on first frame
    if (!startPos.current) {
      startPos.current = camera.position.clone();
      startQuat.current = camera.quaternion.clone();
      startFov.current = (camera as THREE.PerspectiveCamera).fov;
    }

    elapsed.current += delta;
    // Ease-in-out (smoothstep)
    const raw = Math.min(elapsed.current / duration, 1);
    const t = raw * raw * (3 - 2 * raw);

    // Interpolate position
    camera.position.lerpVectors(startPos.current, targetPosition, t);

    // Interpolate rotation
    camera.quaternion.slerpQuaternions(startQuat.current!, targetQuaternion, t);

    // Interpolate FOV
    const perspCam = camera as THREE.PerspectiveCamera;
    // eslint-disable-next-line react-hooks/immutability -- R3F camera is intentionally mutable
    perspCam.fov = startFov.current! + (targetFov - startFov.current!) * t;
    perspCam.updateProjectionMatrix();

    if (raw >= 1) {
      completed.current = true;
      onComplete();
    }
  });

  return null;
}
