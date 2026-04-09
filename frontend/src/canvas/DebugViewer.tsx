import { useRef, useState, useCallback, useEffect } from 'react';
import { Stage, Layer, Line, Circle, Text as KonvaText, Rect } from 'react-konva';
import { useIntl } from 'react-intl';
import type Konva from 'konva';
import './DebugViewer.css';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Segment {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  width: number;
  color: number[];
  dash_pattern: string | null;
}

interface TextAnnotation {
  content: string;
  x: number;
  y: number;
  font_size: number;
}

interface PageSize {
  width: number;
  height: number;
}

interface CropReport {
  original_segments: number;
  kept_segments: number;
  crop_bbox: number[] | null;
}

interface StrokeHistogram {
  widths: number[];
  peaks: number[];
  suggested_thresholds: number[];
}

interface ExtractResponse {
  segments: Segment[];
  texts: TextAnnotation[];
  page_size: PageSize;
  histogram: StrokeHistogram;
  crop_report: CropReport;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function segmentLength(seg: Segment): number {
  return Math.hypot(seg.x2 - seg.x1, seg.y2 - seg.y1);
}

function getSegmentColor(
  width: number,
  thresholds: number[],
): string {
  if (thresholds.length === 0) return '#4a90d9';
  if (thresholds.length === 1) {
    return width <= thresholds[0] ? '#4a90d9' : '#cc0000';
  }
  if (width <= thresholds[0]) return '#4a90d9'; // thin = blue
  if (width <= thresholds[thresholds.length - 1]) return '#2e7d32'; // medium = green
  return '#cc0000'; // thick = red
}

// ---------------------------------------------------------------------------
// Histogram sub-component (plain <canvas>)
// ---------------------------------------------------------------------------

function StrokeHistogramChart({
  histogram,
  widthRange,
}: {
  histogram: StrokeHistogram;
  widthRange: [number, number];
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const intl = useIntl();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || histogram.widths.length === 0) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const W = rect.width;
    const H = rect.height;
    const padding = { top: 20, right: 20, bottom: 30, left: 40 };
    const chartW = W - padding.left - padding.right;
    const chartH = H - padding.top - padding.bottom;

    ctx.clearRect(0, 0, W, H);

    // Build buckets from widths
    const widths = histogram.widths;
    const bucketCount = Math.min(widths.length, 30);
    const minW = widths[0];
    const maxW = widths[widths.length - 1];
    const range = maxW - minW || 1;
    const bucketSize = range / bucketCount;

    const buckets = new Array(bucketCount).fill(0);
    for (const w of widths) {
      const idx = Math.min(Math.floor((w - minW) / bucketSize), bucketCount - 1);
      buckets[idx]++;
    }

    const maxCount = Math.max(...buckets, 1);
    const barW = chartW / bucketCount;

    // Draw bars
    for (let i = 0; i < bucketCount; i++) {
      const bucketMid = minW + (i + 0.5) * bucketSize;
      const inRange = bucketMid >= widthRange[0] && bucketMid <= widthRange[1];

      const barH = (buckets[i] / maxCount) * chartH;
      const x = padding.left + i * barW;
      const y = padding.top + chartH - barH;

      ctx.fillStyle = inRange ? '#4a90d9' : '#ccc';
      ctx.fillRect(x + 1, y, barW - 2, barH);
    }

    // Draw peak markers
    ctx.fillStyle = '#cc0000';
    for (const peak of histogram.peaks) {
      const px = padding.left + ((peak - minW) / range) * chartW;
      ctx.beginPath();
      ctx.moveTo(px, padding.top);
      ctx.lineTo(px - 4, padding.top - 8);
      ctx.lineTo(px + 4, padding.top - 8);
      ctx.fill();
    }

    // X-axis labels
    ctx.fillStyle = '#666';
    ctx.font = '10px Heebo, sans-serif';
    ctx.textAlign = 'center';
    const labelCount = Math.min(6, bucketCount);
    for (let i = 0; i <= labelCount; i++) {
      const val = minW + (range * i) / labelCount;
      const x = padding.left + (chartW * i) / labelCount;
      ctx.fillText(val.toFixed(1), x, H - 5);
    }

    // Y-axis label
    ctx.save();
    ctx.translate(12, padding.top + chartH / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = 'center';
    ctx.fillText(intl.formatMessage({ id: 'debug.segments' }), 0, 0);
    ctx.restore();
  }, [histogram, widthRange, intl]);

  return (
    <canvas
      ref={canvasRef}
      className="debug-histogram-canvas"
      aria-label={intl.formatMessage({ id: 'debug.histogram' })}
    />
  );
}

// ---------------------------------------------------------------------------
// Properties panel sub-component
// ---------------------------------------------------------------------------

function PropertiesPanel({
  segment,
}: {
  segment: Segment | null;
}) {
  const intl = useIntl();

  if (!segment) {
    return (
      <div className="debug-properties-empty">
        {intl.formatMessage({ id: 'debug.clickSegment' })}
      </div>
    );
  }

  const length = segmentLength(segment);
  const colorHex = `rgb(${segment.color.map((c) => Math.round(c * 255)).join(',')})`;

  return (
    <div className="debug-properties-content">
      <h3>{intl.formatMessage({ id: 'debug.properties' })}</h3>
      <dl>
        <dt>{intl.formatMessage({ id: 'debug.start' })}</dt>
        <dd>({segment.x1.toFixed(1)}, {segment.y1.toFixed(1)})</dd>

        <dt>{intl.formatMessage({ id: 'debug.end' })}</dt>
        <dd>({segment.x2.toFixed(1)}, {segment.y2.toFixed(1)})</dd>

        <dt>{intl.formatMessage({ id: 'debug.width' })}</dt>
        <dd>{segment.width.toFixed(2)} pt</dd>

        <dt>{intl.formatMessage({ id: 'debug.length' })}</dt>
        <dd>{length.toFixed(1)} pt</dd>

        <dt>{intl.formatMessage({ id: 'debug.color' })}</dt>
        <dd>
          <span
            className="debug-color-swatch"
            style={{ background: colorHex }}
          />
          {colorHex}
        </dd>
      </dl>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main DebugViewer
// ---------------------------------------------------------------------------

export default function DebugViewer() {
  const intl = useIntl();
  const stageRef = useRef<Konva.Stage>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Data state
  const [data, setData] = useState<ExtractResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // UI state
  const [selectedSegment, setSelectedSegment] = useState<Segment | null>(null);
  const [showTexts, setShowTexts] = useState(true);
  const [showCropOverlay, setShowCropOverlay] = useState(false);
  const [widthRange, setWidthRange] = useState<[number, number]>([0, 10]);

  // Canvas dimensions
  const [canvasSize, setCanvasSize] = useState({ width: 800, height: 600 });

  // Zoom/pan
  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });

  // Resize observer
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        setCanvasSize({
          width: entry.contentRect.width,
          height: entry.contentRect.height,
        });
      }
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  // Fit-to-view when data loads
  useEffect(() => {
    if (!data) return;
    const padded = 40;
    const scaleX = canvasSize.width / (data.page_size.width + padded);
    const scaleY = canvasSize.height / (data.page_size.height + padded);
    const fitScale = Math.min(scaleX, scaleY, 2);
    setScale(fitScale);
    setPosition({ x: 20, y: 20 });

    // Set width range from data
    if (data.segments.length > 0) {
      const widths = data.segments.map((s) => s.width);
      setWidthRange([Math.min(...widths), Math.max(...widths)]);
    }
  }, [data, canvasSize]);

  // Upload handler
  const handleUpload = useCallback(async () => {
    const input = fileInputRef.current;
    if (!input?.files?.[0]) return;

    const file = input.files[0];
    setLoading(true);
    setError(null);
    setSelectedSegment(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('http://localhost:8000/api/extract', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail?.message_he || err.detail?.message_en || 'Upload failed');
      }

      const result: ExtractResponse = await response.json();
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'שגיאה');
    } finally {
      setLoading(false);
    }
  }, []);

  // Zoom handler
  const handleWheel = useCallback(
    (e: Konva.KonvaEventObject<WheelEvent>) => {
      e.evt.preventDefault();
      const stage = stageRef.current;
      if (!stage) return;

      const scaleBy = 1.1;
      const oldScale = stage.scaleX();
      const pointer = stage.getPointerPosition();
      if (!pointer) return;

      const newScale =
        e.evt.deltaY < 0 ? oldScale * scaleBy : oldScale / scaleBy;
      const clampedScale = Math.max(0.1, Math.min(10, newScale));

      const mousePointTo = {
        x: (pointer.x - stage.x()) / oldScale,
        y: (pointer.y - stage.y()) / oldScale,
      };

      setScale(clampedScale);
      setPosition({
        x: pointer.x - mousePointTo.x * clampedScale,
        y: pointer.y - mousePointTo.y * clampedScale,
      });
    },
    [],
  );

  // Filter segments by width range
  const visibleSegments = data
    ? data.segments.filter(
        (s) => s.width >= widthRange[0] && s.width <= widthRange[1],
      )
    : [];

  const thresholds = data?.histogram.suggested_thresholds ?? [];

  // Width bounds for sliders
  const allWidths = data?.segments.map((s) => s.width) ?? [];
  const minWidth = allWidths.length > 0 ? Math.min(...allWidths) : 0;
  const maxWidth = allWidths.length > 0 ? Math.max(...allWidths) : 10;

  return (
    <div className="debug-viewer">
      {/* ---- Toolbar ---- */}
      <div className="debug-toolbar">
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          onChange={handleUpload}
          hidden
          aria-label={intl.formatMessage({ id: 'debug.uploadPdf' })}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          aria-label={intl.formatMessage({ id: 'debug.uploadPdf' })}
        >
          {intl.formatMessage({ id: 'debug.uploadPdf' })}
        </button>

        {data && (
          <>
            <span className="debug-stat">
              {intl.formatMessage({ id: 'debug.segments' })}: {visibleSegments.length}/{data.segments.length}
            </span>
            <span className="debug-stat">
              {intl.formatMessage({ id: 'debug.texts' })}: {data.texts.length}
            </span>

            <label className="debug-toggle">
              <input
                type="checkbox"
                checked={showTexts}
                onChange={(e) => setShowTexts(e.target.checked)}
              />
              {intl.formatMessage({ id: 'debug.showTexts' })}
            </label>

            <label className="debug-toggle">
              <input
                type="checkbox"
                checked={showCropOverlay}
                onChange={(e) => setShowCropOverlay(e.target.checked)}
              />
              {intl.formatMessage({ id: 'debug.showCrop' })}
            </label>

            <div className="debug-width-filter">
              <span>{intl.formatMessage({ id: 'debug.widthFilter' })}:</span>
              <label>
                {intl.formatMessage({ id: 'debug.min' })}
                <input
                  type="range"
                  min={minWidth}
                  max={maxWidth}
                  step={0.01}
                  value={widthRange[0]}
                  onChange={(e) =>
                    setWidthRange([
                      Math.min(parseFloat(e.target.value), widthRange[1]),
                      widthRange[1],
                    ])
                  }
                />
                <span className="debug-range-value">{widthRange[0].toFixed(2)}</span>
              </label>
              <label>
                {intl.formatMessage({ id: 'debug.max' })}
                <input
                  type="range"
                  min={minWidth}
                  max={maxWidth}
                  step={0.01}
                  value={widthRange[1]}
                  onChange={(e) =>
                    setWidthRange([
                      widthRange[0],
                      Math.max(parseFloat(e.target.value), widthRange[0]),
                    ])
                  }
                />
                <span className="debug-range-value">{widthRange[1].toFixed(2)}</span>
              </label>
            </div>
          </>
        )}
      </div>

      {/* ---- Main area: canvas + properties ---- */}
      <div className="debug-main">
        <div className="debug-canvas-container" ref={containerRef}>
          {loading && (
            <div className="debug-loading" role="status" aria-live="polite">
              <div className="debug-spinner" />
              {intl.formatMessage({ id: 'debug.processing' })}
            </div>
          )}

          {error && (
            <div className="debug-error" role="alert">
              {error}
            </div>
          )}

          {!data && !loading && !error && (
            <div className="debug-placeholder">
              {intl.formatMessage({ id: 'debug.uploadPdf' })}
            </div>
          )}

          {data && (
            <Stage
              ref={stageRef}
              width={canvasSize.width}
              height={canvasSize.height}
              scaleX={scale}
              scaleY={scale}
              x={position.x}
              y={position.y}
              draggable
              onWheel={handleWheel}
              onDragEnd={(e) => {
                setPosition({ x: e.target.x(), y: e.target.y() });
              }}
            >
              {/* Crop overlay layer */}
              {showCropOverlay && data.crop_report.crop_bbox && (
                <Layer>
                  {/* Full page dim */}
                  <Rect
                    x={0}
                    y={0}
                    width={data.page_size.width}
                    height={data.page_size.height}
                    fill="rgba(0,0,0,0.3)"
                    listening={false}
                  />
                  {/* Clear the crop area */}
                  <Rect
                    x={data.crop_report.crop_bbox[0]}
                    y={data.crop_report.crop_bbox[1]}
                    width={data.crop_report.crop_bbox[2] - data.crop_report.crop_bbox[0]}
                    height={data.crop_report.crop_bbox[3] - data.crop_report.crop_bbox[1]}
                    fill="white"
                    listening={false}
                  />
                </Layer>
              )}

              {/* Segments layer */}
              <Layer>
                {visibleSegments.map((seg, i) => (
                  <Line
                    key={i}
                    points={[seg.x1, seg.y1, seg.x2, seg.y2]}
                    stroke={getSegmentColor(seg.width, thresholds)}
                    strokeWidth={Math.max(seg.width, 0.5)}
                    hitStrokeWidth={Math.max(8 / scale, 4)}
                    onClick={() => setSelectedSegment(seg)}
                    onTap={() => setSelectedSegment(seg)}
                    onMouseEnter={(e) => {
                      const container = e.target.getStage()?.container();
                      if (container) container.style.cursor = 'pointer';
                    }}
                    onMouseLeave={(e) => {
                      const container = e.target.getStage()?.container();
                      if (container) container.style.cursor = 'default';
                    }}
                  />
                ))}
              </Layer>

              {/* Selection highlight layer */}
              {selectedSegment && (
                <Layer>
                  <Line
                    points={[
                      selectedSegment.x1,
                      selectedSegment.y1,
                      selectedSegment.x2,
                      selectedSegment.y2,
                    ]}
                    stroke="#2196F3"
                    strokeWidth={Math.max(selectedSegment.width + 2, 3)}
                    dash={[6, 3]}
                    listening={false}
                  />
                  <Circle
                    x={selectedSegment.x1}
                    y={selectedSegment.y1}
                    radius={4 / scale}
                    fill="#ff5722"
                    listening={false}
                  />
                  <Circle
                    x={selectedSegment.x2}
                    y={selectedSegment.y2}
                    radius={4 / scale}
                    fill="#4caf50"
                    listening={false}
                  />
                </Layer>
              )}

              {/* Text annotations layer */}
              {showTexts && (
                <Layer>
                  {data.texts.map((t, i) => (
                    <KonvaText
                      key={i}
                      x={t.x}
                      y={t.y}
                      text={t.content}
                      fontSize={Math.max(t.font_size, 8)}
                      fontFamily="Heebo, sans-serif"
                      fill="#333"
                      opacity={0.8}
                      listening={false}
                    />
                  ))}
                </Layer>
              )}
            </Stage>
          )}
        </div>

        {/* ---- Properties panel (LEFT side in RTL) ---- */}
        <aside className="debug-panel" aria-label={intl.formatMessage({ id: 'debug.properties' })}>
          <PropertiesPanel segment={selectedSegment} />
        </aside>
      </div>

      {/* ---- Histogram at bottom ---- */}
      {data && (
        <div className="debug-histogram">
          <h3>{intl.formatMessage({ id: 'debug.histogram' })}</h3>
          <StrokeHistogramChart histogram={data.histogram} widthRange={widthRange} />
        </div>
      )}
    </div>
  );
}
