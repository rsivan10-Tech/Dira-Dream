import { useState, useCallback, useRef } from 'react';
import { IntlProvider } from 'react-intl';
import messages_he from './i18n/he.json';
import DebugViewer from './canvas/DebugViewer';
import FloorplanViewer from './canvas/FloorplanViewer';
import FloorplanScene from './three/FloorplanScene';
import type { FloorplanData } from '@/types/floorplan';

type AppMode = 'debug' | 'viewer' | '3d';

function App() {
  const [mode, setMode] = useState<AppMode>('viewer');

  // Shared state: PDF file + analyzed data persists across view switches
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [floorplanData, setFloorplanData] = useState<FloorplanData | null>(null);
  const [pageCount, setPageCount] = useState(1);
  const [currentPage, setCurrentPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Shared fetch: calls /api/analyze and stores result
  const fetchPage = useCallback(async (file: File, pageNum: number) => {
    setLoading(true);
    setError(null);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('page_num', String(pageNum));

    try {
      const resp = await fetch('http://localhost:8000/api/analyze', {
        method: 'POST',
        body: formData,
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail?.message_he || err.detail?.message_en || 'שגיאה');
      }
      const raw = await resp.json();

      // Import the converter dynamically to avoid circular deps
      const { analyzeToFloorplan } = await import('./canvas/floorplanUtils');
      setFloorplanData(analyzeToFloorplan(raw));
      setPageCount(raw.page_count);
      setCurrentPage(raw.page_num);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'שגיאה');
    } finally {
      setLoading(false);
    }
  }, []);

  const handleUpload = useCallback(async () => {
    const input = fileInputRef.current;
    if (!input?.files?.[0]) return;
    const file = input.files[0];
    setPdfFile(file);
    setCurrentPage(0);
    setFloorplanData(null);
    await fetchPage(file, 0);
  }, [fetchPage]);

  const handlePageChange = useCallback(
    (pageNum: number) => {
      if (!pdfFile || pageNum === currentPage) return;
      fetchPage(pdfFile, pageNum);
    },
    [pdfFile, currentPage, fetchPage],
  );

  return (
    <IntlProvider locale="he" messages={messages_he}>
      {/* Top bar: mode switch + shared upload */}
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
        <button
          onClick={() => setMode('3d')}
          style={{
            padding: '3px 10px',
            fontSize: '0.78rem',
            background: mode === '3d' ? '#2196f3' : '#333',
            color: '#fff',
            border: 'none',
            borderRadius: 4,
            cursor: 'pointer',
            minHeight: 28,
          }}
        >
          {messages_he['app.mode3D']}
        </button>

        {/* Shared upload button — always visible in top bar */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          onChange={handleUpload}
          hidden
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          style={{
            padding: '3px 10px',
            fontSize: '0.78rem',
            background: '#4CAF50',
            color: '#fff',
            border: 'none',
            borderRadius: 4,
            cursor: 'pointer',
            minHeight: 28,
            marginInlineStart: 'auto',
          }}
        >
          {messages_he['debug.uploadPdf']}
        </button>

        {/* Page selector */}
        {pageCount > 1 && (
          <select
            value={currentPage}
            onChange={(e) => handlePageChange(Number(e.target.value))}
            style={{
              padding: '3px 8px',
              fontSize: '0.78rem',
              borderRadius: 4,
              border: '1px solid #555',
              background: '#333',
              color: '#fff',
              minHeight: 28,
            }}
          >
            {Array.from({ length: pageCount }, (_, i) => (
              <option key={i} value={i}>{`${i + 1} / ${pageCount}`}</option>
            ))}
          </select>
        )}

        {pdfFile && (
          <span style={{ color: '#aaa', fontSize: '0.72rem', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {pdfFile.name}
          </span>
        )}
      </div>

      {mode === 'debug' ? (
        <DebugViewer />
      ) : mode === '3d' ? (
        floorplanData ? (
          <FloorplanScene data={floorplanData} />
        ) : (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            height: 'calc(100vh - 36px)',
            color: '#888',
            fontSize: '0.9rem',
          }}>
            {loading ? messages_he['common.loading'] : messages_he['viewer.noData']}
          </div>
        )
      ) : (
        <FloorplanViewer
          data={floorplanData}
          loading={loading}
          error={error}
          pageCount={pageCount}
          currentPage={currentPage}
          onPageChange={handlePageChange}
          onUpload={() => fileInputRef.current?.click()}
        />
      )}
    </IntlProvider>
  );
}

export default App;
