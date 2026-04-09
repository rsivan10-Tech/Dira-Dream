import os
import tempfile
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, Field

from geometry.extraction import (
    compute_stroke_histogram,
    crop_legend,
    extract_vectors,
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


class ExtractResponse(BaseModel):
    segments: list[SegmentResponse]
    texts: list[TextResponse]
    page_size: PageSizeResponse
    histogram: StrokeHistogramResponse
    crop_report: CropReportResponse


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok")


@router.post("/extract", response_model=ExtractResponse)
async def extract_pdf(file: UploadFile):
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

        # Extract → crop → histogram
        raw = extract_vectors(tmp_path)
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

        return ExtractResponse(
            segments=segments,
            texts=texts,
            page_size=PageSizeResponse(
                width=cropped["page_size"][0],
                height=cropped["page_size"][1],
            ),
            histogram=StrokeHistogramResponse(**histogram),
            crop_report=crop_report,
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
