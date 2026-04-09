from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_upload_pdf_returns_501():
    response = client.post("/api/upload-pdf")
    assert response.status_code == 501
    detail = response.json()["detail"]
    assert detail["error"] == "NOT_IMPLEMENTED"
    assert "PDF" in detail["message_he"]
