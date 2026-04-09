import os
import tempfile
from typing import Optional

import fitz
from fastapi import APIRouter, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from geometry.extraction import (
    compute_stroke_histogram,
    crop_legend,
    extract_metadata,
    extract_vectors,
)
from geometry.graph import build_planar_graph
from geometry.healing import HealingConfig, filter_largest_component, heal_geometry
from geometry.rooms import classify_rooms, detect_rooms
from geometry.structural import (
    classify_structural,
    detect_doors_and_windows,
    detect_exterior_walls,
    detect_mamad,
)

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str


class ErrorResponse(BaseModel):
    error: str
    message_he: str
    message_en: str


class SegmentResponse(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    width: float
    color: list[float]
    dash_pattern: Optional[str] = None


class TextResponse(BaseModel):
    content: str
    x: float
    y: float
    font_size: float


class PageSizeResponse(BaseModel):
    width: float
    height: float


class CropReportResponse(BaseModel):
    original_segments: int
    kept_segments: int
    crop_bbox: Optional[list[float]] = None


class StrokeHistogramResponse(BaseModel):
    widths: list[float] = Field(default_factory=list)
    peaks: list[float] = Field(default_factory=list)
    suggested_thresholds: list[float] = Field(default_factory=list)


class AreaValueResponse(BaseModel):
    value: float
    context: str
    bbox: list[float]


class FixtureLabelResponse(BaseModel):
    label: str
    bbox: list[float]
    font_size: float


class MetadataResponse(BaseModel):
    scale_notation: Optional[str] = None
    scale_value: Optional[int] = None
    total_area_sqm: Optional[float] = None
    balcony_area_sqm: Optional[float] = None
    area_values: list[AreaValueResponse] = Field(default_factory=list)
    fixture_labels: list[FixtureLabelResponse] = Field(default_factory=list)


class ExtractResponse(BaseModel):
    segments: list[SegmentResponse]
    texts: list[TextResponse]
    page_size: PageSizeResponse
    histogram: StrokeHistogramResponse
    crop_report: CropReportResponse
    metadata: MetadataResponse
    page_num: int = 0
    page_count: int = 1


class PointResponse(BaseModel):
    x: float
    y: float


class RoomResponse(BaseModel):
    id: str
    type: str
    type_he: str
    confidence: float
    area_sqm: float
    perimeter_m: float
    polygon: list[list[float]]
    centroid: PointResponse
    label_point: PointResponse
    classification_method: str
    needs_review: bool
    is_modifiable: bool


class WallResponse(BaseModel):
    id: str
    start: PointResponse
    end: PointResponse
    width: float
    wall_type: str
    is_structural: bool
    is_modifiable: bool
    confidence: float
    rooms: list[str] = Field(default_factory=list)


class OpeningResponse(BaseModel):
    id: str
    type: str
    width_cm: float
    position: PointResponse
    wall_id: str = ""
    rooms: list[str] = Field(default_factory=list)
    swing_direction: Optional[str] = None


class AnalyzeResponse(BaseModel):
    rooms: list[RoomResponse]
    walls: list[WallResponse]
    openings: list[OpeningResponse]
    texts: list[TextResponse]
    confidence: int
    page_size: PageSizeResponse
    scale_factor: float
    metadata: MetadataResponse
    page_num: int = 0
    page_count: int = 1
    pipeline_stats: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok")


@router.post("/extract", response_model=ExtractResponse)
async def extract_pdf(file: UploadFile, page_num: int = Form(0)):
    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error="INVALID_FILE",
                message_he="יש להעלות קובץ PDF בלבד.",
                message_en="Please upload a PDF file.",
            ).model_dump(),
        )

    tmp_path = None
    try:
        # Write uploaded file to temp location
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp_path = tmp.name
            content = await file.read()
            tmp.write(content)

        # Get page count
        doc = fitz.open(tmp_path)
        page_count = len(doc)
        doc.close()

        if page_num < 0 or page_num >= page_count:
            raise ValueError(
                f"Page {page_num} does not exist (PDF has {page_count} pages)"
            )

        # Extract → metadata (before crop!) → crop → histogram
        raw = extract_vectors(tmp_path, page_num=page_num)
        pre_crop_metadata = extract_metadata(raw["texts"])
        cropped = crop_legend(raw)
        histogram = compute_stroke_histogram(cropped["segments"])

        # Serialize segments
        segments = [
            SegmentResponse(
                x1=s["start"][0],
                y1=s["start"][1],
                x2=s["end"][0],
                y2=s["end"][1],
                width=s["stroke_width"],
                color=list(s["color"]),
                dash_pattern=str(s["dash_pattern"]) if s["dash_pattern"] else None,
            )
            for s in cropped["segments"]
        ]

        # Serialize texts
        texts = [
            TextResponse(
                content=t["content"],
                x=t["bbox"][0],
                y=t["bbox"][1],
                font_size=t["font_size"],
            )
            for t in cropped["texts"]
        ]

        # Crop report
        crop_bbox = cropped["crop_report"].get("crop_bbox")
        crop_report = CropReportResponse(
            original_segments=cropped["crop_report"]["original_segments"],
            kept_segments=cropped["crop_report"]["kept_segments"],
            crop_bbox=list(crop_bbox) if crop_bbox else None,
        )

        # Serialize metadata
        metadata = MetadataResponse(
            scale_notation=pre_crop_metadata["scale_notation"],
            scale_value=pre_crop_metadata["scale_value"],
            total_area_sqm=pre_crop_metadata["total_area_sqm"],
            balcony_area_sqm=pre_crop_metadata["balcony_area_sqm"],
            area_values=[
                AreaValueResponse(
                    value=av["value"],
                    context=av["context"],
                    bbox=list(av["bbox"]),
                )
                for av in pre_crop_metadata["area_values"]
            ],
            fixture_labels=[
                FixtureLabelResponse(
                    label=fl["label"],
                    bbox=list(fl["bbox"]),
                    font_size=fl["font_size"],
                )
                for fl in pre_crop_metadata["fixture_labels"]
            ],
        )

        return ExtractResponse(
            segments=segments,
            texts=texts,
            page_size=PageSizeResponse(
                width=cropped["page_size"][0],
                height=cropped["page_size"][1],
            ),
            histogram=StrokeHistogramResponse(**histogram),
            crop_report=crop_report,
            metadata=metadata,
            page_num=page_num,
            page_count=page_count,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error="EXTRACTION_FAILED",
                message_he="שגיאה בעיבוד הקובץ.",
                message_en=str(e),
            ).model_dump(),
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error="EXTRACTION_FAILED",
                message_he="שגיאה בעיבוד הקובץ.",
                message_en=f"Extraction failed: {e}",
            ).model_dump(),
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_pdf(file: UploadFile, page_num: int = Form(0)):
    """Full pipeline: extract → crop → heal → graph → rooms → structural."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error="INVALID_FILE",
                message_he="יש להעלות קובץ PDF בלבד.",
                message_en="Please upload a PDF file.",
            ).model_dump(),
        )

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp_path = tmp.name
            content = await file.read()
            tmp.write(content)

        doc = fitz.open(tmp_path)
        page_count = len(doc)
        doc.close()

        if page_num < 0 or page_num >= page_count:
            raise ValueError(f"Page {page_num} out of range (0-{page_count - 1})")

        # 1. Extract
        raw = extract_vectors(tmp_path, page_num=page_num)
        pre_crop_metadata = extract_metadata(raw["texts"])
        cropped = crop_legend(raw)
        histogram = compute_stroke_histogram(cropped["segments"])

        # Derive scale factor
        scale_value = pre_crop_metadata.get("scale_value") or 50
        scale_factor = (0.0254 / 72) * scale_value  # PDF pt → metres

        # 2. Pre-filter: keep wall-width segments
        thresholds = histogram["suggested_thresholds"]
        wall_thresh = thresholds[0] if thresholds else 0.5
        wall_segs = [
            s for s in cropped["segments"] if s["stroke_width"] >= wall_thresh
        ]

        # 3. Heal
        healed, heal_stats = heal_geometry(wall_segs, HealingConfig())

        # 3b. Keep only the largest connected component (the apartment).
        # Discards legend elements, neighbor outlines, and disconnected fragments.
        healed = filter_largest_component(healed)

        # 4. Graph
        G, embedding, graph_stats = build_planar_graph(healed)

        # 5. Room detection + classification
        rooms, room_stats = detect_rooms(G, embedding, scale_factor=scale_factor)
        rooms = classify_rooms(
            rooms, cropped["texts"], healed, scale_factor=scale_factor,
        )

        # 6. Structural classification
        ext_walls = detect_exterior_walls(healed, rooms)
        mamad = detect_mamad(rooms, healed, scale_factor=scale_factor)
        classified_walls = classify_structural(healed, ext_walls, mamad)
        openings, opening_report = detect_doors_and_windows(
            healed, rooms, scale_factor=scale_factor,
        )

        # Serialize rooms
        room_responses = []
        for i, r in enumerate(rooms):
            coords = list(r.polygon.exterior.coords)
            rep = r.polygon.representative_point()
            room_responses.append(RoomResponse(
                id=f"room_{i}",
                type=r.room_type,
                type_he=r.room_type_he,
                confidence=r.confidence,
                area_sqm=r.area_sqm,
                perimeter_m=r.perimeter_m,
                polygon=[[c[0], c[1]] for c in coords],
                centroid=PointResponse(x=r.centroid[0], y=r.centroid[1]),
                label_point=PointResponse(x=rep.x, y=rep.y),
                classification_method=r.classification_strategy,
                needs_review=r.needs_review,
                is_modifiable=r.is_modifiable,
            ))

        # Serialize walls
        wall_responses = []
        for i, w in enumerate(classified_walls):
            s = w.segment
            wall_responses.append(WallResponse(
                id=f"wall_{i}",
                start=PointResponse(x=s["start"][0], y=s["start"][1]),
                end=PointResponse(x=s["end"][0], y=s["end"][1]),
                width=s.get("stroke_width", 1.0),
                wall_type=w.wall_type,
                is_structural=w.is_structural,
                is_modifiable=w.is_modifiable,
                confidence=w.confidence,
            ))

        # Serialize openings
        opening_responses = []
        for i, o in enumerate(openings):
            opening_responses.append(OpeningResponse(
                id=f"opening_{i}",
                type=o.opening_type,
                width_cm=o.width_cm,
                position=PointResponse(x=o.position[0], y=o.position[1]),
                swing_direction=o.swing_direction,
            ))

        # Texts
        texts = [
            TextResponse(
                content=t["content"], x=t["bbox"][0], y=t["bbox"][1],
                font_size=t["font_size"],
            )
            for t in cropped["texts"]
        ]

        # Metadata
        metadata = MetadataResponse(
            scale_notation=pre_crop_metadata.get("scale_notation"),
            scale_value=pre_crop_metadata.get("scale_value"),
            total_area_sqm=pre_crop_metadata.get("total_area_sqm"),
            balcony_area_sqm=pre_crop_metadata.get("balcony_area_sqm"),
            area_values=[
                AreaValueResponse(
                    value=av["value"], context=av["context"],
                    bbox=list(av["bbox"]),
                )
                for av in pre_crop_metadata.get("area_values", [])
            ],
            fixture_labels=[
                FixtureLabelResponse(
                    label=fl["label"], bbox=list(fl["bbox"]),
                    font_size=fl["font_size"],
                )
                for fl in pre_crop_metadata.get("fixture_labels", [])
            ],
        )

        # Overall confidence
        room_confs = [r.confidence for r in rooms] if rooms else [0]
        overall = int(sum(room_confs) / len(room_confs))

        return AnalyzeResponse(
            rooms=room_responses,
            walls=wall_responses,
            openings=opening_responses,
            texts=texts,
            confidence=overall,
            page_size=PageSizeResponse(
                width=cropped["page_size"][0], height=cropped["page_size"][1],
            ),
            scale_factor=scale_factor,
            metadata=metadata,
            page_num=page_num,
            page_count=page_count,
            pipeline_stats={
                "segments_extracted": len(raw["segments"]),
                "after_crop": len(cropped["segments"]),
                "wall_segments": len(wall_segs),
                "after_healing": len(healed),
                "rooms_detected": len(rooms),
                "openings": opening_report,
                "heal": {
                    "largest_component": heal_stats["validation"]["largest_component_ratio"],
                    "dead_ends": heal_stats["validation"]["dead_end_count"],
                    "components": heal_stats["validation"]["connected_components"],
                },
            },
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error="ANALYSIS_FAILED",
                message_he="שגיאה בניתוח התוכנית.",
                message_en=str(e),
            ).model_dump(),
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error="ANALYSIS_FAILED",
                message_he="שגיאה בניתוח התוכנית.",
                message_en=f"Analysis failed: {e}",
            ).model_dump(),
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
