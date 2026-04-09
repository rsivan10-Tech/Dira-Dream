# Konva.js Canvas Guide for Floorplan Rendering

## Architecture Overview

```
Stage (container div)
  └── Layer: background (grid, image)
  └── Layer: walls (wall segments, colored by type)
  └── Layer: rooms (filled polygons, labels)
  └── Layer: openings (doors, windows)
  └── Layer: furniture (draggable items)
  └── Layer: measurements (dimension lines, labels)
  └── Layer: ui (selection, hover highlights, tooltips)
```

**Key principle**: Separate layers for performance. Only redraw layers that change.

## Stage Setup

```tsx
import { Stage, Layer, Line, Rect, Text, Group } from 'react-konva';

const FloorplanViewer = ({ width, height, plan }) => {
  const stageRef = useRef<Konva.Stage>(null);
  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });

  return (
    <Stage
      ref={stageRef}
      width={width}
      height={height}
      scaleX={scale}
      scaleY={scale}
      x={position.x}
      y={position.y}
      draggable  // Pan support
      onWheel={handleWheel}  // Zoom support
    >
      <Layer name="walls">{/* Wall segments */}</Layer>
      <Layer name="rooms">{/* Room polygons */}</Layer>
      <Layer name="furniture">{/* Draggable furniture */}</Layer>
      <Layer name="ui">{/* Selection, hover */}</Layer>
    </Stage>
  );
};
```

## Coordinate System

- Canvas uses **screen coordinates**: (0,0) at top-left, Y increases downward
- This is LTR regardless of UI direction — canvas coordinates are mathematical
- PDF coordinates must be converted: `canvas_y = page_height - pdf_y`
- Scale factor converts PDF points → canvas pixels (based on plan scale + zoom)

```typescript
interface CoordinateTransform {
  scale: number;      // PDF points to canvas pixels
  offsetX: number;    // Pan offset
  offsetY: number;    // Pan offset
  flipY: boolean;     // PDF Y-axis flip
  pageHeight: number; // For Y-flip calculation
}

function pdfToCanvas(x: number, y: number, transform: CoordinateTransform): [number, number] {
  const canvasX = x * transform.scale + transform.offsetX;
  const canvasY = (transform.pageHeight - y) * transform.scale + transform.offsetY;
  return [canvasX, canvasY];
}
```

## Wall Rendering

```tsx
const WallSegment = ({ wall, transform, selected, onSelect }) => {
  const [x1, y1] = pdfToCanvas(wall.start.x, wall.start.y, transform);
  const [x2, y2] = pdfToCanvas(wall.end.x, wall.end.y, transform);

  const color = WALL_COLORS[wall.classification];
  const strokeWidth = wall.thickness * transform.scale;

  return (
    <Line
      points={[x1, y1, x2, y2]}
      stroke={color}
      strokeWidth={Math.max(strokeWidth, 2)} // Min 2px visibility
      hitStrokeWidth={10} // Easier to click
      onClick={() => onSelect(wall)}
      onMouseEnter={(e) => {
        e.target.getStage().container().style.cursor = 'pointer';
      }}
      onMouseLeave={(e) => {
        e.target.getStage().container().style.cursor = 'default';
      }}
    />
  );
};

const WALL_COLORS = {
  WALL_EXTERIOR: '#1a1a1a',    // Dark black
  WALL_INTERIOR: '#4a4a4a',    // Medium gray
  WALL_MAMAD: '#cc0000',       // Red (danger - never modify)
  WALL_STRUCTURAL: '#ff8800',  // Orange (caution)
  WALL_PARTITION: '#4a90d9',   // Blue (modifiable)
  WALL_UNKNOWN: '#999999',     // Gray
};
```

## Room Polygon Rendering

```tsx
const RoomPolygon = ({ room, transform, onSelect }) => {
  // Convert polygon vertices to flat points array
  const points = room.polygon.coordinates.flatMap(([x, y]) => {
    const [cx, cy] = pdfToCanvas(x, y, transform);
    return [cx, cy];
  });

  const label = room.representative_point;
  const [labelX, labelY] = pdfToCanvas(label.x, label.y, transform);

  return (
    <Group>
      <Line
        points={points}
        closed
        fill={ROOM_FILLS[room.type]}
        opacity={0.2}
        stroke={ROOM_FILLS[room.type]}
        strokeWidth={1}
        onClick={() => onSelect(room)}
      />
      <Text
        x={labelX}
        y={labelY}
        text={room.name_he}
        fontSize={14}
        fontFamily="Heebo"
        fill="#333"
        align="center"
        offsetX={/* half text width */}
      />
      <Text
        x={labelX}
        y={labelY + 18}
        text={`${room.area_sqm.toFixed(1)} מ"ר`}
        fontSize={12}
        fontFamily="Heebo"
        fill="#666"
        align="center"
      />
    </Group>
  );
};

const ROOM_FILLS = {
  salon: '#E8F5E9',
  bedroom: '#E3F2FD',
  master_bedroom: '#E3F2FD',
  kitchen: '#FFF3E0',
  bathroom: '#E0F7FA',
  mamad: '#FFEBEE',
  balcony: '#F1F8E9',
  storage: '#EFEBE9',
  hallway: '#F5F5F5',
  entrance: '#FFF8E1',
};
```

## Pan & Zoom

```tsx
const handleWheel = (e: Konva.KonvaEventObject<WheelEvent>) => {
  e.evt.preventDefault();
  const stage = stageRef.current;
  if (!stage) return;

  const scaleBy = 1.1;
  const oldScale = stage.scaleX();
  const pointer = stage.getPointerPosition();

  const newScale = e.evt.deltaY < 0
    ? oldScale * scaleBy
    : oldScale / scaleBy;

  // Clamp scale
  const clampedScale = Math.max(0.1, Math.min(10, newScale));

  // Zoom toward pointer position
  const mousePointTo = {
    x: (pointer.x - stage.x()) / oldScale,
    y: (pointer.y - stage.y()) / oldScale,
  };

  setScale(clampedScale);
  setPosition({
    x: pointer.x - mousePointTo.x * clampedScale,
    y: pointer.y - mousePointTo.y * clampedScale,
  });
};
```

## Performance with Many Elements

For floorplans with thousands of wall segments:

1. **Layer caching**: `layer.cache()` for static layers (walls after loading)
2. **Viewport culling**: Only render elements visible in current viewport
3. **Level of detail**: Hide small elements at low zoom levels
4. **Batch drawing**: Use `layer.batchDraw()` instead of `layer.draw()`
5. **Hit detection optimization**: Set `hitStrokeWidth` larger than visual stroke for easier clicking without rendering overhead

```tsx
// Viewport culling
const isVisible = (element, viewport) => {
  return !(element.maxX < viewport.x ||
           element.minX > viewport.x + viewport.width ||
           element.maxY < viewport.y ||
           element.minY > viewport.y + viewport.height);
};
```

## Selection & Interaction

```tsx
const [selectedWall, setSelectedWall] = useState(null);
const [hoveredRoom, setHoveredRoom] = useState(null);

// Selection highlight
{selectedWall && (
  <Line
    points={selectedWallPoints}
    stroke="#2196F3"
    strokeWidth={4}
    dash={[8, 4]}
    listening={false}  // Don't intercept events
  />
)}

// Hover highlight
{hoveredRoom && (
  <Line
    points={hoveredRoomPoints}
    closed
    fill="#2196F3"
    opacity={0.1}
    listening={false}
  />
)}
```

## Debug Viewer (Sprint 1)

Essential debugging overlay for development:

```tsx
const DebugLayer = ({ segments, showLabels, showEndpoints }) => (
  <Layer>
    {segments.map((seg, i) => (
      <Group key={i}>
        <Line
          points={[seg.x1, seg.y1, seg.x2, seg.y2]}
          stroke={getDebugColor(seg)}
          strokeWidth={2}
        />
        {showEndpoints && (
          <>
            <Circle x={seg.x1} y={seg.y1} radius={3} fill="red" />
            <Circle x={seg.x2} y={seg.y2} radius={3} fill="blue" />
          </>
        )}
        {showLabels && (
          <Text
            x={(seg.x1 + seg.x2) / 2}
            y={(seg.y1 + seg.y2) / 2}
            text={`w:${seg.width.toFixed(1)} #${i}`}
            fontSize={9}
          />
        )}
      </Group>
    ))}
  </Layer>
);
```
