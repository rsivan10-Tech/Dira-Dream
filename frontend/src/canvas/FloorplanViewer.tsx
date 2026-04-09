import { useRef, useState, useCallback, useEffect, useMemo } from 'react';
import { Stage, Layer, Line, Arc, Circle, Text as KonvaText, Group } from 'react-konva';
import { useIntl } from 'react-intl';
import type Konva from 'konva';
import type {
  FloorplanData,
  Room,
  Wall,
  Opening,
  Point,
  SelectionTarget,
  LayerVisibility,
  MeasurementState,
  WallType,
  RoomType,
} from '@/types/floorplan';
import './FloorplanViewer.css';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const WALL_COLORS: Record<WallType, string> = {
  exterior: '#4A4A4A',
  structural: '#8B0000',
  partition: '#4682B4',
  mamad: '#FF8C00',
  unknown: '#999999',
};

const WALL_WIDTH_MULTIPLIER: Record<WallType, number> = {
  exterior: 2,
  structural: 1.5,
  partition: 1,
  mamad: 2.5,
  unknown: 1,
};

const ROOM_FILLS: Record<RoomType, string> = {
  salon: '#E8F5E9',
  bedroom: '#E3F2FD',
  master_bedroom: '#E3F2FD',
  kitchen: '#FFF3E0',
  bathroom: '#E0F7FA',
  mamad: '#FFEBEE',
  balcony: '#F1F8E9',
  service_balcony: '#F1F8E9',
  storage: '#EFEBE9',
  hallway: '#F5F5F5',
  entrance: '#FFF8E1',
  corridor: '#F5F5F5',
  study: '#EDE7F6',
  laundry: '#F3E5F5',
  unknown: '#F5F5F5',
};

const MIN_ZOOM = 0.2;
const MAX_ZOOM = 5;
const SNAP_DISTANCE = 10; // pixels for measurement snap

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function confidenceLevel(score: number): 'high' | 'medium' | 'low' {
  if (score >= 85) return 'high';
  if (score >= 50) return 'medium';
  return 'low';
}

function confidenceIcon(level: 'high' | 'medium' | 'low'): string {
  return { high: '\u2713', medium: '?', low: '!' }[level];
}

function labelFontSize(areaSqm: number): number {
  return Math.max(10, Math.min(18, 8 + areaSqm * 0.4));
}

function distanceBetween(a: Point, b: Point): number {
  return Math.hypot(b.x - a.x, b.y - a.y);
}

function findNearestEndpoint(
  pos: Point,
  walls: Wall[],
  threshold: number,
): Point | null {
  let best: Point | null = null;
  let bestDist = threshold;
  for (const w of walls) {
    for (const pt of [w.start, w.end]) {
      const d = distanceBetween(pos, pt);
      if (d < bestDist) {
        bestDist = d;
        best = pt;
      }
    }
  }
  return best;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function WallSegment({
  wall,
  isHovered,
  isSelected,
  showStructural,
  onHover,
  onSelect,
  scale,
}: {
  wall: Wall;
  isHovered: boolean;
  isSelected: boolean;
  showStructural: boolean;
  onHover: (w: Wall | null) => void;
  onSelect: (w: Wall) => void;
  scale: number;
}) {
  const color = isHovered
    ? '#FFD600'
    : isSelected
      ? '#2196F3'
      : showStructural
        ? WALL_COLORS[wall.wall_type]
        : '#4A4A4A';

  const sw =
    Math.max(wall.width * WALL_WIDTH_MULTIPLIER[wall.wall_type], 1.5);

  const dash =
    wall.wall_type === 'unknown' && !isHovered && !isSelected
      ? [6, 3]
      : undefined;

  return (
    <Line
      points={[wall.start.x, wall.start.y, wall.end.x, wall.end.y]}
      stroke={color}
      strokeWidth={sw}
      dash={dash}
      hitStrokeWidth={Math.max(12 / scale, 6)}
      onClick={() => onSelect(wall)}
      onTap={() => onSelect(wall)}
      onMouseEnter={(e) => {
        onHover(wall);
        const c = e.target.getStage()?.container();
        if (c) c.style.cursor = 'pointer';
      }}
      onMouseLeave={(e) => {
        onHover(null);
        const c = e.target.getStage()?.container();
        if (c) c.style.cursor = 'default';
      }}
    />
  );
}

function RoomPolygon({
  room,
  isHovered,
  isSelected,
  onHover,
  onSelect,
}: {
  room: Room;
  isHovered: boolean;
  isSelected: boolean;
  onHover: (r: Room | null) => void;
  onSelect: (r: Room) => void;
}) {
  const points = room.polygon.flatMap(([x, y]) => [x, y]);
  const fill = ROOM_FILLS[room.type] ?? ROOM_FILLS.unknown;

  const opacity = isSelected ? 0.35 : isHovered ? 0.25 : 0.12;

  return (
    <Line
      points={points}
      closed
      fill={fill}
      opacity={opacity}
      stroke={isSelected ? '#2196F3' : isHovered ? '#2196F3' : fill}
      strokeWidth={isSelected ? 2 : 1}
      hitStrokeWidth={0}
      onClick={() => onSelect(room)}
      onTap={() => onSelect(room)}
      onMouseEnter={() => onHover(room)}
      onMouseLeave={() => onHover(null)}
    />
  );
}

function RoomLabel({
  room,
  intl,
}: {
  room: Room;
  intl: ReturnType<typeof useIntl>;
}) {
  const fontSize = labelFontSize(room.area_sqm);
  const nameKey = `rooms.${room.type}` as const;
  const name = intl.messages[nameKey]
    ? intl.formatMessage({ id: nameKey })
    : room.type_he;

  return (
    <Group listening={false}>
      <KonvaText
        x={room.label_point.x}
        y={room.label_point.y - fontSize * 0.6}
        text={name}
        fontSize={fontSize}
        fontFamily="Heebo, sans-serif"
        fill="#333"
        align="center"
        width={120}
        offsetX={60}
      />
      <KonvaText
        x={room.label_point.x}
        y={room.label_point.y + fontSize * 0.5}
        text={`${room.area_sqm.toFixed(1)} מ"ר`}
        fontSize={Math.max(fontSize - 2, 9)}
        fontFamily="Heebo, sans-serif"
        fill="#666"
        align="center"
        width={120}
        offsetX={60}
      />
    </Group>
  );
}

function DoorShape({
  opening,
  scale,
}: {
  opening: Opening;
  scale: number;
}) {
  // Quarter-circle arc from hinge point
  const radiusPt = opening.width_cm / 2;
  const radius = Math.max(radiusPt, 8);

  return (
    <Arc
      x={opening.position.x}
      y={opening.position.y}
      innerRadius={0}
      outerRadius={radius}
      angle={90}
      rotation={0}
      stroke="#333333"
      strokeWidth={Math.max(1, 1 / scale)}
      dash={[4, 2]}
      fill="transparent"
      listening={false}
    />
  );
}

function WindowShape({
  opening,
  scale,
}: {
  opening: Opening;
  scale: number;
}) {
  // Three parallel lines at opening position
  const halfW = opening.width_cm / 4;
  const sw = Math.max(0.8, 0.8 / scale);
  const gap = 3;

  return (
    <Group listening={false}>
      {[-gap, 0, gap].map((offset, i) => (
        <Line
          key={i}
          points={[
            opening.position.x - halfW,
            opening.position.y + offset,
            opening.position.x + halfW,
            opening.position.y + offset,
          ]}
          stroke="#4682B4"
          strokeWidth={sw}
        />
      ))}
    </Group>
  );
}

function MeasurementLine({
  a,
  b,
  scaleFactor,
}: {
  a: Point;
  b: Point;
  scaleFactor: number;
}) {
  const dist = distanceBetween(a, b);
  const meters = dist * scaleFactor;
  const midX = (a.x + b.x) / 2;
  const midY = (a.y + b.y) / 2;

  return (
    <Group listening={false}>
      <Line
        points={[a.x, a.y, b.x, b.y]}
        stroke="#E91E63"
        strokeWidth={2}
        dash={[6, 4]}
      />
      <Circle x={a.x} y={a.y} radius={4} fill="#E91E63" />
      <Circle x={b.x} y={b.y} radius={4} fill="#E91E63" />
      <KonvaText
        x={midX}
        y={midY - 16}
        text={`${meters.toFixed(2)} מ'`}
        fontSize={13}
        fontFamily="Heebo, sans-serif"
        fill="#E91E63"
        fontStyle="bold"
        align="center"
        width={80}
        offsetX={40}
      />
    </Group>
  );
}

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------

function Sidebar({
  data,
  selection,
  intl,
}: {
  data: FloorplanData;
  selection: SelectionTarget;
  intl: ReturnType<typeof useIntl>;
}) {
  const fmt = (id: string) => intl.formatMessage({ id });

  if (!selection) {
    // Overview stats
    const totalArea = data.rooms.reduce((sum, r) => sum + r.area_sqm, 0);
    return (
      <div className="fp-sidebar-section">
        <h3>{fmt('sidebar.overview')}</h3>
        <dl>
          <dt>{fmt('sidebar.totalArea')}</dt>
          <dd>{totalArea.toFixed(1)} {fmt('common.sqm')}</dd>
          <dt>{fmt('sidebar.roomCount')}</dt>
          <dd>{data.rooms.length}</dd>
          <dt>{fmt('sidebar.wallCount')}</dt>
          <dd>{data.walls.length}</dd>
          <dt>{fmt('sidebar.confidence')}</dt>
          <dd>
            <ConfidenceBadge score={data.confidence} />
          </dd>
        </dl>
        {data.rooms.length === 0 && (
          <p style={{ color: '#999', marginBlockStart: 12 }}>{fmt('viewer.noRooms')}</p>
        )}
      </div>
    );
  }

  if (selection.kind === 'room') {
    const room = selection.item;
    const nameKey = `rooms.${room.type}`;
    const name = intl.messages[nameKey]
      ? fmt(nameKey)
      : room.type_he;

    return (
      <div className="fp-sidebar-section">
        <h3>{fmt('sidebar.roomDetails')}</h3>
        <dl>
          <dt>{fmt('sidebar.roomType')}</dt>
          <dd>{name}</dd>
          <dt>{fmt('sidebar.roomArea')}</dt>
          <dd>{room.area_sqm.toFixed(1)} {fmt('common.sqm')}</dd>
          <dt>{fmt('sidebar.roomPerimeter')}</dt>
          <dd>{room.perimeter_m.toFixed(1)} {fmt('common.meters')}</dd>
          <dt>{fmt('sidebar.roomConfidence')}</dt>
          <dd><ConfidenceBadge score={room.confidence} /></dd>
          <dt>{fmt('sidebar.roomMethod')}</dt>
          <dd>{room.classification_method}</dd>
          <dt>{fmt('sidebar.roomModifiable')}</dt>
          <dd>{room.is_modifiable ? fmt('common.yes') : fmt('sidebar.notModifiable')}</dd>
        </dl>
        {room.needs_review && (
          <p style={{ color: '#f57f17', fontSize: '0.82rem', marginBlockStart: 8 }}>
            {fmt('sidebar.roomNeedsReview')}
          </p>
        )}
        {room.type === 'mamad' && (
          <div className="fp-mamad-warning">{fmt('sidebar.mamadWarning')}</div>
        )}
        <div className="fp-structural-disclaimer">{fmt('sidebar.structuralDisclaimer')}</div>
      </div>
    );
  }

  // Wall selected
  const wall = selection.item;
  const wallKey = `walls.${wall.wall_type}`;
  const wallName = intl.messages[wallKey]
    ? fmt(wallKey)
    : wall.wall_type;

  return (
    <div className="fp-sidebar-section">
      <h3>{fmt('sidebar.wallDetails')}</h3>
      <dl>
        <dt>{fmt('sidebar.wallType')}</dt>
        <dd>{wallName}</dd>
        <dt>{fmt('sidebar.wallThickness')}</dt>
        <dd>{wall.width.toFixed(1)} pt</dd>
        <dt>{fmt('sidebar.wallStructural')}</dt>
        <dd>{wall.is_structural ? fmt('common.yes') : fmt('common.no')}</dd>
        <dt>{fmt('sidebar.wallModifiable')}</dt>
        <dd>{wall.is_modifiable ? fmt('common.yes') : fmt('sidebar.notModifiable')}</dd>
        <dt>{fmt('sidebar.wallConfidence')}</dt>
        <dd><ConfidenceBadge score={wall.confidence} /></dd>
      </dl>
      {wall.wall_type === 'mamad' && (
        <div className="fp-mamad-warning">{fmt('sidebar.mamadWarning')}</div>
      )}
      <div className="fp-structural-disclaimer">{fmt('sidebar.structuralDisclaimer')}</div>
    </div>
  );
}

function ConfidenceBadge({ score }: { score: number }) {
  const level = confidenceLevel(score);
  const icon = confidenceIcon(level);
  return (
    <span
      className={`fp-confidence-badge fp-confidence-badge--${level}`}
      role="status"
    >
      {icon} {score}%
    </span>
  );
}

// ---------------------------------------------------------------------------
// Tooltip
// ---------------------------------------------------------------------------

function Tooltip({
  hoveredRoom,
  hoveredWall,
  mousePos,
  intl,
}: {
  hoveredRoom: Room | null;
  hoveredWall: Wall | null;
  mousePos: { x: number; y: number } | null;
  intl: ReturnType<typeof useIntl>;
}) {
  if ((!hoveredRoom && !hoveredWall) || !mousePos) return null;

  const fmt = (id: string) => intl.formatMessage({ id });

  const content = hoveredRoom ? (
    <dl>
      <dt>{fmt('tooltip.room')}:</dt>
      <dd>{hoveredRoom.type_he}</dd>
      <dt>{fmt('tooltip.area')}:</dt>
      <dd>{hoveredRoom.area_sqm.toFixed(1)} {fmt('common.sqm')}</dd>
      <dt>{fmt('tooltip.perimeter')}:</dt>
      <dd>{hoveredRoom.perimeter_m.toFixed(1)} {fmt('common.meters')}</dd>
    </dl>
  ) : hoveredWall ? (
    <dl>
      <dt>{fmt('tooltip.wallType')}:</dt>
      <dd>{intl.messages[`walls.${hoveredWall.wall_type}`]
        ? fmt(`walls.${hoveredWall.wall_type}`)
        : hoveredWall.wall_type}</dd>
      <dt>{fmt('tooltip.thickness')}:</dt>
      <dd>{hoveredWall.width.toFixed(1)} pt</dd>
      <dt>{fmt('tooltip.modifiable')}:</dt>
      <dd>{hoveredWall.is_modifiable ? fmt('tooltip.modifiable') : fmt('tooltip.notModifiable')}</dd>
    </dl>
  ) : null;

  return (
    <div
      className="fp-tooltip"
      style={{
        left: mousePos.x + 14,
        top: mousePos.y - 10,
      }}
    >
      {content}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Scale Bar
// ---------------------------------------------------------------------------

function ScaleBar({
  scale,
  scaleFactor,
}: {
  scale: number;
  scaleFactor: number;
}) {
  if (!scaleFactor || scaleFactor <= 0) return null;

  // Target ~100px on screen for the bar
  const targetPx = 100;
  const metersPerPx = scaleFactor / scale;
  const rawMeters = targetPx * metersPerPx;

  // Round to nice number
  const nice = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50];
  const niceVal = nice.find((n) => n >= rawMeters) ?? rawMeters;
  const barPx = niceVal / metersPerPx;

  return (
    <div className="fp-scale-bar">
      <div className="fp-scale-bar-line">
        <div className="fp-scale-bar-segment" style={{ width: barPx }} />
      </div>
      <span className="fp-scale-bar-label">{niceVal >= 1 ? `${niceVal} מ'` : `${niceVal * 100} ס"מ`}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Confidence Dashboard
// ---------------------------------------------------------------------------

function ConfidenceDashboard({
  data,
  intl,
}: {
  data: FloorplanData;
  intl: ReturnType<typeof useIntl>;
}) {
  const fmt = (id: string) => intl.formatMessage({ id });
  const level = confidenceLevel(data.confidence);

  const wallCounts = data.walls.reduce(
    (acc, w) => {
      acc[w.wall_type] = (acc[w.wall_type] || 0) + 1;
      return acc;
    },
    {} as Record<string, number>,
  );

  const doorCount = data.openings.filter((o) => o.type === 'door').length;
  const windowCount = data.openings.filter((o) => o.type === 'window').length;
  const reviewRooms = data.rooms.filter((r) => r.needs_review).length;
  const unknownWalls = wallCounts['unknown'] || 0;

  const actions: { text: string; severity: 'warning' | 'error' }[] = [];
  if (!data.scale_factor) actions.push({ text: fmt('viewer.scaleNeeded'), severity: 'error' });
  if (reviewRooms > 0) actions.push({ text: `${reviewRooms} ${fmt('sidebar.roomNeedsReview')}`, severity: 'warning' });
  if (unknownWalls > 0) actions.push({ text: `${unknownWalls} ${fmt('walls.unknown')}`, severity: 'warning' });

  return (
    <div className="fp-dashboard">
      <div className="fp-dashboard-header">
        <span className={`fp-dashboard-score fp-dashboard-score--${level}`}>
          {data.confidence}%
        </span>
        <span>{fmt('sidebar.confidence')}</span>
      </div>

      <div className="fp-dashboard-grid">
        <div className="fp-dashboard-card">
          <div className="fp-dashboard-card-label">{fmt('scale.label')}</div>
          <div className="fp-dashboard-card-value">
            {data.scale_factor ? `1:${Math.round(1 / (data.scale_factor * 100 / 2.835))}` : fmt('viewer.scaleNeeded')}
          </div>
        </div>
        <div className="fp-dashboard-card">
          <div className="fp-dashboard-card-label">{fmt('sidebar.roomCount')}</div>
          <div className="fp-dashboard-card-value">{data.rooms.length}</div>
        </div>
        <div className="fp-dashboard-card">
          <div className="fp-dashboard-card-label">{fmt('toolbar.walls')}</div>
          <div className="fp-dashboard-card-value">
            {wallCounts['exterior'] || 0} / {wallCounts['structural'] || 0} / {wallCounts['mamad'] || 0}
          </div>
        </div>
        <div className="fp-dashboard-card">
          <div className="fp-dashboard-card-label">{fmt('toolbar.doorsWindows')}</div>
          <div className="fp-dashboard-card-value">{doorCount} / {windowCount}</div>
        </div>
      </div>

      {actions.length > 0 && (
        <div className="fp-dashboard-actions">
          <h4>{fmt('sidebar.roomNeedsReview')}</h4>
          {actions.map((a, i) => (
            <div key={i} className="fp-dashboard-action-item">
              <span className={`fp-dashboard-action-dot fp-dashboard-action-dot--${a.severity}`} />
              {a.text}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Export utilities
// ---------------------------------------------------------------------------

function exportRoomScheduleCSV(data: FloorplanData): void {
  const header = 'room_name,room_type,area_sqm,perimeter_m,confidence,classification_method,is_modifiable';
  const rows = data.rooms.map((r) =>
    [
      r.type_he,
      r.type,
      r.area_sqm.toFixed(1),
      r.perimeter_m.toFixed(1),
      r.confidence,
      r.classification_method,
      r.is_modifiable,
    ].join(','),
  );
  const csv = [header, ...rows].join('\n');
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'room_schedule.csv';
  a.click();
  URL.revokeObjectURL(url);
}

function exportSVG(stageRef: React.RefObject<Konva.Stage | null>): void {
  const stage = stageRef.current;
  if (!stage) return;

  // Use Konva's toDataURL then convert to downloadable SVG-like PNG
  // True SVG export would need manual construction; for now export as high-res PNG
  const uri = stage.toDataURL({ pixelRatio: 2 });
  const a = document.createElement('a');
  a.href = uri;
  a.download = 'floorplan.png';
  a.click();
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function FloorplanViewer({
  data,
  loading = false,
}: {
  data: FloorplanData | null;
  loading?: boolean;
}) {
  const intl = useIntl();
  const stageRef = useRef<Konva.Stage>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Canvas size
  const [canvasSize, setCanvasSize] = useState({ width: 800, height: 600 });

  // Zoom / pan
  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });

  // Selection & hover
  const [selection, setSelection] = useState<SelectionTarget>(null);
  const [hoveredRoom, setHoveredRoom] = useState<Room | null>(null);
  const [hoveredWall, setHoveredWall] = useState<Wall | null>(null);
  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(null);
  const [cursorWorld, setCursorWorld] = useState<Point | null>(null);

  // Layers
  const [layers, setLayers] = useState<LayerVisibility>({
    walls: true,
    doorsWindows: true,
    furniture: false,
    dimensions: false,
    textAnnotations: false,
    structuralOverlay: true,
  });

  // Measurement tool
  const [measure, setMeasure] = useState<MeasurementState>({
    active: false,
    pointA: null,
    pointB: null,
  });

  const fmt = useCallback(
    (id: string) => intl.formatMessage({ id }),
    [intl],
  );

  // Resize observer
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new ResizeObserver((entries) => {
      const e = entries[0];
      if (e) setCanvasSize({ width: e.contentRect.width, height: e.contentRect.height });
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  // Fit-to-view when data loads
  useEffect(() => {
    if (!data) return;
    const pad = 40;
    const sx = canvasSize.width / (data.page_size.width + pad);
    const sy = canvasSize.height / (data.page_size.height + pad);
    const fitScale = Math.min(sx, sy, 2);
    setScale(fitScale);
    setPosition({ x: 20, y: 20 });
    setSelection(null);
    setMeasure({ active: false, pointA: null, pointB: null });
  }, [data, canvasSize]);

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

      const raw = e.evt.deltaY < 0 ? oldScale * scaleBy : oldScale / scaleBy;
      const clamped = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, raw));

      const mp = {
        x: (pointer.x - stage.x()) / oldScale,
        y: (pointer.y - stage.y()) / oldScale,
      };
      setScale(clamped);
      setPosition({
        x: pointer.x - mp.x * clamped,
        y: pointer.y - mp.y * clamped,
      });
    },
    [],
  );

  // Pointer move for tooltip + cursor coords
  const handlePointerMove = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      const stage = stageRef.current;
      if (!stage) return;
      const container = stage.container().getBoundingClientRect();
      setMousePos({
        x: e.evt.clientX - container.left,
        y: e.evt.clientY - container.top,
      });
      const pointer = stage.getPointerPosition();
      if (pointer && data) {
        const wx = (pointer.x - stage.x()) / stage.scaleX();
        const wy = (pointer.y - stage.y()) / stage.scaleY();
        setCursorWorld({ x: wx, y: wy });
      }
    },
    [data],
  );

  // Canvas click for measurement tool
  const handleStageClick = useCallback(
    (_e: Konva.KonvaEventObject<MouseEvent>) => {
      if (!measure.active || !data) return;
      const stage = stageRef.current;
      if (!stage) return;
      const pointer = stage.getPointerPosition();
      if (!pointer) return;

      const wx = (pointer.x - stage.x()) / stage.scaleX();
      const wy = (pointer.y - stage.y()) / stage.scaleY();
      let pt: Point = { x: wx, y: wy };

      // Snap to wall endpoint
      const snapped = findNearestEndpoint(pt, data.walls, SNAP_DISTANCE / scale);
      if (snapped) pt = snapped;

      if (!measure.pointA) {
        setMeasure({ ...measure, pointA: pt });
      } else {
        setMeasure({ ...measure, pointB: pt });
      }
    },
    [measure, data, scale],
  );

  // Room / wall select handlers
  const handleRoomSelect = useCallback((room: Room) => {
    if (measure.active) return;
    setSelection({ kind: 'room', item: room });
  }, [measure.active]);

  const handleWallSelect = useCallback((wall: Wall) => {
    if (measure.active) return;
    setSelection({ kind: 'wall', item: wall });
  }, [measure.active]);

  // Layer toggle
  const toggleLayer = useCallback((key: keyof LayerVisibility) => {
    setLayers((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  // Measurement toggle
  const toggleMeasure = useCallback(() => {
    setMeasure((prev) =>
      prev.active
        ? { active: false, pointA: null, pointB: null }
        : { active: true, pointA: null, pointB: null },
    );
  }, []);

  // Fit view
  const fitView = useCallback(() => {
    if (!data) return;
    const pad = 40;
    const sx = canvasSize.width / (data.page_size.width + pad);
    const sy = canvasSize.height / (data.page_size.height + pad);
    const fitScale = Math.min(sx, sy, 2);
    setScale(fitScale);
    setPosition({ x: 20, y: 20 });
  }, [data, canvasSize]);

  // Zoom buttons
  const zoomIn = useCallback(() => setScale((s) => Math.min(MAX_ZOOM, s * 1.3)), []);
  const zoomOut = useCallback(() => setScale((s) => Math.max(MIN_ZOOM, s / 1.3)), []);

  // Cursor coord display
  const cursorDisplay = useMemo(() => {
    if (!cursorWorld || !data?.scale_factor) return null;
    const mx = (cursorWorld.x * data.scale_factor).toFixed(2);
    const my = (cursorWorld.y * data.scale_factor).toFixed(2);
    return `${mx}, ${my} מ'`;
  }, [cursorWorld, data?.scale_factor]);

  // Measure hint text
  const measureHint = measure.active
    ? !measure.pointA
      ? fmt('measure.clickFirst')
      : !measure.pointB
        ? fmt('measure.clickSecond')
        : null
    : null;

  return (
    <div className="fp-viewer">
      {/* ---- Confidence dashboard ---- */}
      {data && <ConfidenceDashboard data={data} intl={intl} />}

      {/* ---- Toolbar ---- */}
      <div className="fp-toolbar" role="toolbar" aria-label={fmt('toolbar.layers')}>
        {/* Layer toggles */}
        <div className="fp-toolbar-group">
          <span className="fp-toolbar-label">{fmt('toolbar.layers')}</span>
          <label className="fp-layer-toggle">
            <input
              type="checkbox"
              checked={layers.walls}
              onChange={() => toggleLayer('walls')}
            />
            {fmt('toolbar.walls')}
          </label>
          <label className="fp-layer-toggle">
            <input
              type="checkbox"
              checked={layers.doorsWindows}
              onChange={() => toggleLayer('doorsWindows')}
            />
            {fmt('toolbar.doorsWindows')}
          </label>
          <label className="fp-layer-toggle">
            <input
              type="checkbox"
              checked={layers.textAnnotations}
              onChange={() => toggleLayer('textAnnotations')}
            />
            {fmt('toolbar.textAnnotations')}
          </label>
          <label className="fp-layer-toggle">
            <input
              type="checkbox"
              checked={layers.structuralOverlay}
              onChange={() => toggleLayer('structuralOverlay')}
            />
            {fmt('toolbar.structuralOverlay')}
          </label>
        </div>

        {/* Tools */}
        <div className="fp-toolbar-group">
          <button
            aria-pressed={measure.active}
            onClick={toggleMeasure}
            aria-label={fmt('toolbar.measure')}
          >
            {fmt('toolbar.measure')}
          </button>
          <button onClick={zoomIn} aria-label={fmt('toolbar.zoomIn')}>+</button>
          <button onClick={zoomOut} aria-label={fmt('toolbar.zoomOut')}>−</button>
          <button onClick={fitView} aria-label={fmt('toolbar.fitView')}>⊡</button>
        </div>

        {/* Export */}
        {data && (
          <div className="fp-toolbar-group">
            <button
              onClick={() => exportSVG(stageRef)}
              aria-label={fmt('toolbar.exportSvg')}
            >
              {fmt('toolbar.exportSvg')}
            </button>
            <button
              onClick={() => exportRoomScheduleCSV(data)}
              aria-label={fmt('toolbar.exportCsv')}
            >
              {fmt('toolbar.exportCsv')}
            </button>
          </div>
        )}
      </div>

      {/* ---- Main: canvas + sidebar ---- */}
      <div className="fp-main">
        <div className="fp-canvas-container" ref={containerRef}>
          {loading && (
            <div className="fp-loading" role="status" aria-live="polite">
              <div className="fp-spinner" />
              {fmt('viewer.processing')}
            </div>
          )}

          {!data && !loading && (
            <div className="fp-placeholder">{fmt('viewer.noData')}</div>
          )}

          {data && (
            <>
              <Stage
                ref={stageRef}
                width={canvasSize.width}
                height={canvasSize.height}
                scaleX={scale}
                scaleY={scale}
                x={position.x}
                y={position.y}
                draggable={!measure.active}
                onWheel={handleWheel}
                onDragEnd={(e) => setPosition({ x: e.target.x(), y: e.target.y() })}
                onMouseMove={handlePointerMove}
                onClick={handleStageClick}
              >
                {/* Room polygons layer */}
                <Layer>
                  {data.rooms.map((room) => (
                    <RoomPolygon
                      key={room.id}
                      room={room}
                      isHovered={hoveredRoom?.id === room.id}
                      isSelected={selection?.kind === 'room' && selection.item.id === room.id}
                      onHover={setHoveredRoom}
                      onSelect={handleRoomSelect}
                    />
                  ))}
                </Layer>

                {/* Walls layer */}
                {layers.walls && (
                  <Layer>
                    {data.walls.map((wall) => (
                      <WallSegment
                        key={wall.id}
                        wall={wall}
                        isHovered={hoveredWall?.id === wall.id}
                        isSelected={selection?.kind === 'wall' && selection.item.id === wall.id}
                        showStructural={layers.structuralOverlay}
                        onHover={setHoveredWall}
                        onSelect={handleWallSelect}
                        scale={scale}
                      />
                    ))}
                  </Layer>
                )}

                {/* Openings layer (doors & windows) */}
                {layers.doorsWindows && (
                  <Layer>
                    {data.openings.map((opening) =>
                      opening.type === 'door' ? (
                        <DoorShape key={opening.id} opening={opening} scale={scale} />
                      ) : (
                        <WindowShape key={opening.id} opening={opening} scale={scale} />
                      ),
                    )}
                  </Layer>
                )}

                {/* Room labels layer */}
                <Layer>
                  {data.rooms.map((room) => (
                    <RoomLabel key={room.id} room={room} intl={intl} />
                  ))}
                </Layer>

                {/* Measurement layer */}
                {measure.pointA && measure.pointB && data.scale_factor > 0 && (
                  <Layer>
                    <MeasurementLine
                      a={measure.pointA}
                      b={measure.pointB}
                      scaleFactor={data.scale_factor}
                    />
                  </Layer>
                )}

                {/* Measurement in-progress point */}
                {measure.active && measure.pointA && !measure.pointB && (
                  <Layer>
                    <Circle
                      x={measure.pointA.x}
                      y={measure.pointA.y}
                      radius={5 / scale}
                      fill="#E91E63"
                      listening={false}
                    />
                  </Layer>
                )}
              </Stage>

              {/* Tooltip (HTML overlay) */}
              <Tooltip
                hoveredRoom={hoveredRoom}
                hoveredWall={hoveredWall}
                mousePos={mousePos}
                intl={intl}
              />

              {/* Scale bar */}
              <ScaleBar scale={scale} scaleFactor={data.scale_factor} />

              {/* Cursor coordinates */}
              {cursorDisplay && (
                <div className="fp-cursor-coords">{cursorDisplay}</div>
              )}

              {/* Measurement hint */}
              {measureHint && (
                <div className="fp-measure-hint">{measureHint}</div>
              )}
            </>
          )}
        </div>

        {/* ---- Sidebar ---- */}
        <aside className="fp-sidebar" aria-label={fmt('sidebar.overview')}>
          {data ? (
            <Sidebar data={data} selection={selection} intl={intl} />
          ) : (
            <div className="fp-sidebar-empty">{fmt('sidebar.clickToSelect')}</div>
          )}
        </aside>
      </div>
    </div>
  );
}
