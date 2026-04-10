/**
 * MobileControls — touch controls overlay for mobile/tablet walkthrough.
 *
 * Left side: virtual joystick for movement.
 * Right side: touch drag for look direction.
 * Two-finger pinch: FOV zoom.
 *
 * Writes to shared refs (moveInputRef, lookInputRef) that
 * FirstPersonController reads each frame.
 */

import { useRef, useEffect, useCallback } from 'react';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const JOYSTICK_SIZE = 120; // px outer ring
const KNOB_SIZE = 44; // px inner knob
const LOOK_SENSITIVITY = 0.003; // rad/px
const MIN_FOV = 50;
const MAX_FOV = 90;

// ---------------------------------------------------------------------------
// Mobile detection
// ---------------------------------------------------------------------------

export function isMobileDevice(): boolean {
  return 'ontouchstart' in window || window.matchMedia('(pointer: coarse)').matches;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface MobileControlsProps {
  moveInputRef: React.RefObject<{ x: number; z: number }>;
  lookInputRef: React.RefObject<{ yaw: number; pitch: number }>;
  onFovChange: (fov: number) => void;
  visible: boolean;
}

export default function MobileControls({
  moveInputRef,
  lookInputRef,
  onFovChange,
  visible,
}: MobileControlsProps) {
  const joystickRef = useRef<HTMLDivElement>(null);
  const knobRef = useRef<HTMLDivElement>(null);
  const joystickTouchId = useRef<number | null>(null);
  const lookTouchId = useRef<number | null>(null);
  const lastLookPos = useRef<{ x: number; y: number } | null>(null);

  // Pinch state
  const pinchStartDist = useRef<number | null>(null);
  const baseFov = useRef(70);

  // -----------------------------------------------------------------------
  // Virtual joystick (left side)
  // -----------------------------------------------------------------------

  const handleJoystickStart = useCallback(
    (e: React.TouchEvent) => {
      if (joystickTouchId.current !== null) return;
      const touch = e.changedTouches[0];
      joystickTouchId.current = touch.identifier;
      e.preventDefault();
    },
    [],
  );

  const handleJoystickMove = useCallback(
    (e: React.TouchEvent) => {
      if (joystickTouchId.current === null) return;
      const touch = Array.from(e.changedTouches).find(
        (t) => t.identifier === joystickTouchId.current,
      );
      if (!touch || !joystickRef.current || !knobRef.current) return;

      const rect = joystickRef.current.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;

      let dx = touch.clientX - centerX;
      let dy = touch.clientY - centerY;

      // Clamp to circle
      const maxRadius = JOYSTICK_SIZE / 2 - KNOB_SIZE / 2;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist > maxRadius) {
        dx = (dx / dist) * maxRadius;
        dy = (dy / dist) * maxRadius;
      }

      // Move knob visual
      knobRef.current.style.transform = `translate(${dx}px, ${dy}px)`;

      // Normalize to [-1, 1]
      if (moveInputRef.current) {
        moveInputRef.current.x = dx / maxRadius;
        moveInputRef.current.z = dy / maxRadius;
      }

      e.preventDefault();
    },
    [moveInputRef],
  );

  const handleJoystickEnd = useCallback(
    (e: React.TouchEvent) => {
      const released = Array.from(e.changedTouches).find(
        (t) => t.identifier === joystickTouchId.current,
      );
      if (!released) return;

      joystickTouchId.current = null;
      if (knobRef.current) {
        knobRef.current.style.transform = 'translate(0px, 0px)';
      }
      if (moveInputRef.current) {
        moveInputRef.current.x = 0;
        moveInputRef.current.z = 0;
      }
    },
    [moveInputRef],
  );

  // -----------------------------------------------------------------------
  // Look drag (right side) + pinch zoom
  // -----------------------------------------------------------------------

  useEffect(() => {
    if (!visible) return;

    const handleTouchStart = (e: TouchEvent) => {
      // Pinch detection: two touches
      if (e.touches.length === 2) {
        const t1 = e.touches[0];
        const t2 = e.touches[1];
        pinchStartDist.current = Math.sqrt(
          (t2.clientX - t1.clientX) ** 2 + (t2.clientY - t1.clientY) ** 2,
        );
        return;
      }

      // Single touch on right half → look
      const touch = e.changedTouches[0];
      if (touch.clientX > window.innerWidth / 2 && lookTouchId.current === null) {
        lookTouchId.current = touch.identifier;
        lastLookPos.current = { x: touch.clientX, y: touch.clientY };
      }
    };

    const handleTouchMove = (e: TouchEvent) => {
      // Pinch zoom
      if (e.touches.length === 2 && pinchStartDist.current !== null) {
        const t1 = e.touches[0];
        const t2 = e.touches[1];
        const curDist = Math.sqrt(
          (t2.clientX - t1.clientX) ** 2 + (t2.clientY - t1.clientY) ** 2,
        );
        const ratio = pinchStartDist.current / curDist;
        const newFov = Math.max(MIN_FOV, Math.min(MAX_FOV, baseFov.current * ratio));
        onFovChange(newFov);
        return;
      }

      // Look drag
      if (lookTouchId.current === null || !lastLookPos.current) return;
      const touch = Array.from(e.changedTouches).find(
        (t) => t.identifier === lookTouchId.current,
      );
      if (!touch) return;

      const dx = touch.clientX - lastLookPos.current.x;
      const dy = touch.clientY - lastLookPos.current.y;

      if (lookInputRef.current) {
        lookInputRef.current.yaw -= dx * LOOK_SENSITIVITY;
        lookInputRef.current.pitch -= dy * LOOK_SENSITIVITY;
      }

      lastLookPos.current = { x: touch.clientX, y: touch.clientY };
    };

    const handleTouchEnd = (e: TouchEvent) => {
      // End pinch
      if (e.touches.length < 2) {
        pinchStartDist.current = null;
      }

      // End look
      const released = Array.from(e.changedTouches).find(
        (t) => t.identifier === lookTouchId.current,
      );
      if (released) {
        lookTouchId.current = null;
        lastLookPos.current = null;
      }
    };

    // Listen on document to capture touches outside the joystick
    document.addEventListener('touchstart', handleTouchStart, { passive: false });
    document.addEventListener('touchmove', handleTouchMove, { passive: false });
    document.addEventListener('touchend', handleTouchEnd);

    return () => {
      document.removeEventListener('touchstart', handleTouchStart);
      document.removeEventListener('touchmove', handleTouchMove);
      document.removeEventListener('touchend', handleTouchEnd);
    };
  }, [visible, lookInputRef, onFovChange]);

  if (!visible) return null;

  return (
    <>
      {/* Virtual joystick — bottom-left */}
      <div
        ref={joystickRef}
        onTouchStart={handleJoystickStart}
        onTouchMove={handleJoystickMove}
        onTouchEnd={handleJoystickEnd}
        style={{
          position: 'absolute',
          bottom: 40,
          left: 40,
          width: JOYSTICK_SIZE,
          height: JOYSTICK_SIZE,
          borderRadius: '50%',
          border: '2px solid rgba(255,255,255,0.4)',
          background: 'rgba(255,255,255,0.1)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 10,
          touchAction: 'none',
        }}
      >
        {/* Knob */}
        <div
          ref={knobRef}
          style={{
            width: KNOB_SIZE,
            height: KNOB_SIZE,
            borderRadius: '50%',
            background: 'rgba(255,255,255,0.5)',
            transition: 'none',
            pointerEvents: 'none',
          }}
        />
      </div>

      {/* Right-side hint */}
      <div
        style={{
          position: 'absolute',
          bottom: 40,
          right: 40,
          color: 'rgba(255,255,255,0.4)',
          fontSize: '0.75rem',
          textAlign: 'center',
          zIndex: 10,
          pointerEvents: 'none',
        }}
      >
        גרור להסתכלות
      </div>
    </>
  );
}
