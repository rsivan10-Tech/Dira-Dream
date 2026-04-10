/**
 * SceneToolbar — overlay toolbar for the 3D scene.
 * Positioned absolute bottom-center, provides mode toggle (overview / walkthrough).
 */

import { Eye, Footprints } from 'lucide-react';

export type ViewMode = 'overview' | 'walkthrough';

interface SceneToolbarProps {
  viewMode: ViewMode;
  onToggle: () => void;
}

export default function SceneToolbar({ viewMode, onToggle }: SceneToolbarProps) {
  const isWalkthrough = viewMode === 'walkthrough';

  return (
    <div
      style={{
        position: 'absolute',
        bottom: 16,
        left: '50%',
        transform: 'translateX(-50%)',
        display: 'flex',
        gap: 8,
        zIndex: 10,
      }}
    >
      <button
        onClick={onToggle}
        title={isWalkthrough ? 'תצוגה עליונה' : 'סיור בדירה'}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '8px 16px',
          fontSize: '0.82rem',
          fontWeight: 600,
          background: isWalkthrough ? '#1a73e8' : '#333',
          color: '#fff',
          border: 'none',
          borderRadius: 8,
          cursor: 'pointer',
          boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
          transition: 'background 0.2s',
        }}
      >
        {isWalkthrough ? <Eye size={16} /> : <Footprints size={16} />}
        {isWalkthrough ? 'תצוגה עליונה' : 'סיור בדירה'}
      </button>
    </div>
  );
}
