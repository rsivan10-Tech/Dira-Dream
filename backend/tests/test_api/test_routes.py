import io
import fitz  # PyMuPDF
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def _make_test_pdf() -> bytes:
    """Create a minimal vector PDF in memory for testing."""
    doc = fitz.open()
    page = doc.new_page(width=400, height=300)
    # Draw a rectangle (4 wall segments)
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(50, 50, 350, 250))
    shape.finish(width=2.0, color=(0, 0, 0))
    # Draw an interior line
    shape.draw_line(fitz.Point(200, 50), fitz.Point(200, 250))
    shape.finish(width=1.0, color=(0, 0, 0))
    shape.commit()
    # Add text (ASCII — Hebrew needs embedded fonts which test PDFs lack)
    page.insert_text(fitz.Point(100, 150), "salon", fontsize=12)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def test_extract_returns_segments():
    pdf_bytes = _make_test_pdf()
    response = client.post(
        "/api/extract",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()

    # Structure checks
    assert "segments" in data
    assert "texts" in data
    assert "page_size" in data
    assert "histogram" in data
    assert "crop_report" in data

    # Should have segments (rectangle = 4 sides + 1 interior line)
    assert len(data["segments"]) >= 4

    # Each segment has required fields
    seg = data["segments"][0]
    assert all(k in seg for k in ("x1", "y1", "x2", "y2", "width", "color"))

    # Page size matches what we created
    assert data["page_size"]["width"] == 400.0
    assert data["page_size"]["height"] == 300.0

    # Histogram has expected keys
    assert "widths" in data["histogram"]
    assert "peaks" in data["histogram"]

    # Crop report present
    assert "original_segments" in data["crop_report"]
    assert "kept_segments" in data["crop_report"]


def test_extract_has_texts():
    pdf_bytes = _make_test_pdf()
    response = client.post(
        "/api/extract",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
    )
    data = response.json()
    assert len(data["texts"]) >= 1
    assert any("salon" in t["content"] for t in data["texts"])


def test_extract_rejects_non_pdf():
    response = client.post(
        "/api/extract",
        files={"file": ("test.txt", b"not a pdf", "text/plain")},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error"] == "INVALID_FILE"


def test_extract_rejects_no_file_extension():
    response = client.post(
        "/api/extract",
        files={"file": ("noext", b"data", "application/octet-stream")},
    )
    assert response.status_code == 400
