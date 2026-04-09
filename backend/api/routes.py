from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api")


class HealthResponse(BaseModel):
    status: str


class ErrorResponse(BaseModel):
    error: str
    message_he: str
    message_en: str


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok")


@router.post("/upload-pdf", status_code=501)
async def upload_pdf():
    raise HTTPException(
        status_code=501,
        detail=ErrorResponse(
            error="NOT_IMPLEMENTED",
            message_he="העלאת PDF עדיין לא מומשה.",
            message_en="PDF upload is not yet implemented.",
        ).model_dump(),
    )
