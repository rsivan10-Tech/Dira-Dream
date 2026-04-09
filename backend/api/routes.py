from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

router = APIRouter(prefix="/api")


class HealthResponse(BaseModel):
    status: str


class UploadResponse(BaseModel):
    filename: str
    status: str


class ErrorResponse(BaseModel):
    error: str
    message_he: str
    message_en: str


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok")


@router.post("/upload-pdf", response_model=UploadResponse)
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error="INVALID_FILE",
                message_he="יש להעלות קובץ PDF בלבד.",
                message_en="Please upload a PDF file.",
            ).model_dump(),
        )
    return UploadResponse(filename=file.filename, status="stub")
