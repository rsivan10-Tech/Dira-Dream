import { useState } from 'react';
import { IntlProvider } from 'react-intl';
import messages_he from './i18n/he.json';
import DebugViewer from './canvas/DebugViewer';
import FloorplanViewer from './canvas/FloorplanViewer';

type AppMode = 'debug' | 'viewer';

function App() {
  const [mode, setMode] = useState<AppMode>('viewer');

  return (
    <IntlProvider locale="he" messages={messages_he}>
      {/* Mode switcher (dev only — top bar) */}
      <div style={{
        display: 'flex',
        gap: 8,
        padding: '4px 12px',
        background: '#1a1a1a',
        alignItems: 'center',
      }}>
        <span style={{ color: '#fff', fontSize: '0.85rem', fontWeight: 700 }}>
          DiraDream
        </span>
        <button
          onClick={() => setMode('debug')}
          style={{
            padding: '3px 10px',
            fontSize: '0.78rem',
            background: mode === 'debug' ? '#2196f3' : '#333',
            color: '#fff',
            border: 'none',
            borderRadius: 4,
            cursor: 'pointer',
            minHeight: 28,
          }}
        >
          {messages_he['app.modeDebug']}
        </button>
        <button
          onClick={() => setMode('viewer')}
          style={{
            padding: '3px 10px',
            fontSize: '0.78rem',
            background: mode === 'viewer' ? '#2196f3' : '#333',
            color: '#fff',
            border: 'none',
            borderRadius: 4,
            cursor: 'pointer',
            minHeight: 28,
          }}
        >
          {messages_he['app.modeViewer']}
        </button>
      </div>

      {mode === 'debug' ? (
        <DebugViewer />
      ) : (
        <FloorplanViewer />
      )}
    </IntlProvider>
  );
}

export default App;
