import io

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_upload_pdf_rejects_non_pdf():
    file = io.BytesIO(b"not a pdf")
    response = client.post(
        "/api/upload-pdf",
        files={"file": ("test.txt", file, "text/plain")},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error"] == "INVALID_FILE"
    assert "PDF" in detail["message_he"]


def test_upload_pdf_accepts_pdf():
    file = io.BytesIO(b"%PDF-1.4 fake content")
    response = client.post(
        "/api/upload-pdf",
        files={"file": ("plan.pdf", file, "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "plan.pdf"
    assert data["status"] == "stub"
