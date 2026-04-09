# API Contracts — FastAPI Endpoints

## Base URL
- Development: `http://localhost:8000`
- All endpoints prefixed with `/api`

## Health Check

```
GET /api/health
Response 200:
{
  "status": "ok",
  "version": "0.1.0",
  "database": "connected"
}
```

## PDF Extraction

```
POST /api/extract
Content-Type: multipart/form-data
Body: file=<PDF file>

Response 200:
{
  "segments": [
    {
      "x1": 72.5,
      "y1": 150.3,
      "x2": 350.8,
      "y2": 150.3,
      "width": 2.0,
      "color": [0, 0, 0],
      "dash_pattern": null,
      "classification": "WALL_EXTERIOR"
    }
  ],
  "texts": [
    {
      "content": "סלון",
      "x": 200.0,
      "y": 300.0,
      "font_size": 12.0
    }
  ],
  "page_size": { "width": 841.89, "height": 595.28 },
  "width_histogram": { "0.5": 45, "1.0": 120, "2.0": 89, "4.0": 23 },
  "crop_report": {
    "kartisiyyah_detected": true,
    "crop_rect": { "x": 0, "y": 0, "width": 700, "height": 595 },
    "segments_removed": 34
  },
  "stats": {
    "total_paths": 523,
    "total_segments": 847,
    "curved_paths_skipped": 12,
    "raster_elements": 0
  }
}

Error 400:
{
  "error": "RASTER_PDF",
  "message_he": "הקובץ אינו מכיל שרטוט וקטורי. יש להעלות קובץ PDF מבוסס וקטורים.",
  "message_en": "File contains no vector drawings. Please upload a vector-based PDF."
}

Error 400:
{
  "error": "INVALID_FILE",
  "message_he": "יש להעלות קובץ PDF בלבד.",
  "message_en": "Please upload a PDF file."
}
```

## Geometry Healing

```
POST /api/heal
Content-Type: application/json
Body:
{
  "segments": [...],  // From /api/extract
  "parameters": {
    "snap_tolerance": 3.0,       // Optional, default 3.0
    "collinear_angle": 2.0,      // Optional, default 2.0
    "extend_tolerance": 10.0,    // Optional, default 10.0
    "overlap_threshold": 0.9     // Optional, default 0.9
  }
}

Response 200:
{
  "healed_segments": [...],  // Same format as input segments
  "stats": {
    "segments_before": 847,
    "segments_after": 312,
    "snaps_performed": 156,
    "merges_performed": 234,
    "duplicates_removed": 89,
    "extensions_performed": 45,
    "splits_performed": 67,
    "orphan_segments": 12,
    "connected_components": 1,
    "door_openings_preserved": 8
  },
  "confidence": 87,
  "warnings": [
    { "type": "ORPHAN_SEGMENTS", "count": 12, "message_he": "נמצאו 12 קטעים לא מחוברים" }
  ]
}
```

## Room Detection

```
POST /api/detect-rooms
Content-Type: application/json
Body:
{
  "healed_segments": [...],  // From /api/heal
  "texts": [...],            // From /api/extract
  "scale_factor": 0.02       // PDF units to cm
}

Response 200:
{
  "rooms": [
    {
      "id": "room_1",
      "type": "salon",
      "type_he": "סלון",
      "confidence": 92,
      "area_sqm": 24.5,
      "polygon": [[x1,y1], [x2,y2], ...],  // Closed polygon vertices
      "centroid": { "x": 200, "y": 300 },
      "label_point": { "x": 205, "y": 295 },  // representative_point
      "classification_method": "text_label",
      "needs_review": false
    }
  ],
  "walls": [
    {
      "id": "wall_1",
      "start": { "x": 72.5, "y": 150.3 },
      "end": { "x": 350.8, "y": 150.3 },
      "width": 2.0,
      "wall_type": "WALL_EXTERIOR",
      "is_structural": true,
      "confidence": 95,
      "rooms": ["room_1", "room_3"]  // Adjacent room IDs
    }
  ],
  "openings": [
    {
      "id": "opening_1",
      "type": "door",
      "width_cm": 80,
      "position": { "x": 150, "y": 150 },
      "wall_id": "wall_5",
      "rooms": ["room_1", "room_4"]
    }
  ],
  "envelope": {
    "polygon": [[x1,y1], ...],
    "area_sqm": 95.2,
    "is_valid": true
  },
  "validation": {
    "has_mamad": true,
    "has_kitchen": true,
    "has_bathroom": true,
    "has_salon": true,
    "all_rooms_accessible": true,
    "issues": []
  },
  "confidence": 85
}
```

## Apartment (Full Data)

```
GET /api/apartment/{id}

Response 200:
{
  "id": "uuid",
  "created_at": "2026-04-09T10:30:00Z",
  "source_pdf": "filename.pdf",
  "rooms": [...],       // Same as detect-rooms
  "walls": [...],       // Same as detect-rooms
  "openings": [...],    // Same as detect-rooms
  "envelope": {...},
  "confidence": 85,
  "modifications": [],  // Future: user modifications
  "furniture": []       // Future: furniture placements
}
```

## Pydantic Schema Patterns

```python
from pydantic import BaseModel, Field
from typing import Optional

class Point(BaseModel):
    x: float
    y: float

class Segment(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    width: float = Field(gt=0)
    color: tuple[float, float, float] = (0, 0, 0)
    dash_pattern: Optional[str] = None
    classification: str = "UNKNOWN"

class Room(BaseModel):
    id: str
    type: str
    type_he: str
    confidence: int = Field(ge=0, le=100)
    area_sqm: float = Field(gt=0)
    polygon: list[list[float]]
    centroid: Point
    label_point: Point
    classification_method: str
    needs_review: bool = False

class HealingParameters(BaseModel):
    snap_tolerance: float = Field(default=3.0, gt=0)
    collinear_angle: float = Field(default=2.0, gt=0, lt=10)
    extend_tolerance: float = Field(default=10.0, gt=0)
    overlap_threshold: float = Field(default=0.9, gt=0, le=1.0)

class ErrorResponse(BaseModel):
    error: str
    message_he: str
    message_en: str
```

## Error Format

All errors return:
```json
{
  "error": "ERROR_CODE",
  "message_he": "הודעת שגיאה בעברית",
  "message_en": "Error message in English"
}
```

Error codes:
- `INVALID_FILE` — Not a PDF
- `RASTER_PDF` — No vector content
- `EMPTY_PDF` — No pages
- `EXTRACTION_FAILED` — PyMuPDF error
- `HEALING_FAILED` — Geometry healing error
- `NO_ROOMS_DETECTED` — Room detection found nothing
- `DATABASE_ERROR` — DB connection/query failure
- `INTERNAL_ERROR` — Unexpected server error
