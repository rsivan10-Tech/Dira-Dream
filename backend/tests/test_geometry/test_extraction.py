"""
Tests for backend/geometry/extraction.py

Uses synthetic PDFs created with PyMuPDF (fitz) — no external fixtures needed.
"""

from __future__ import annotations

import fitz  # PyMuPDF
import pytest


# ---------------------------------------------------------------------------
# Synthetic PDF helpers
# ---------------------------------------------------------------------------

def _create_pdf_with_lines(path: str, lines: list[dict]) -> None:
    """
    Create a single-page PDF with line segments using page.draw_line().

    Each line dict: {start: (x,y), end: (x,y), width: float}
    Coordinates are in PDF space (origin bottom-left).
    """
    doc = fitz.open()
    page = doc.new_page(width=595.28, height=841.89)  # A4
    for ln in lines:
        page.draw_line(
            fitz.Point(*ln["start"]),
            fitz.Point(*ln["end"]),
            color=(0, 0, 0),
            width=ln.get("width", 1.0),
        )
    doc.save(path)
    doc.close()


def _create_pdf_with_text(path: str, texts: list[dict]) -> None:
    """
    Create a single-page PDF with text annotations.

    Each text dict: {content: str, pos: (x, y), font_size: float}
    """
    doc = fitz.open()
    page = doc.new_page(width=595.28, height=841.89)
    for t in texts:
        page.insert_text(
            fitz.Point(*t["pos"]),
            t["content"],
            fontsize=t.get("font_size", 12),
        )
    doc.save(path)
    doc.close()


# ---------------------------------------------------------------------------
# Tests for extract_vectors
# ---------------------------------------------------------------------------

class TestExtractVectors:

    def test_extract_finds_line_segments(self, tmp_path):
        """Three known lines should produce segments with correct metadata."""
        from backend.geometry.extraction import extract_vectors

        pdf_path = str(tmp_path / "lines.pdf")
        lines = [
            {"start": (100, 400), "end": (300, 400), "width": 2.0},
            {"start": (100, 400), "end": (100, 600), "width": 2.0},
            {"start": (50, 100), "end": (550, 100), "width": 1.0},
        ]
        _create_pdf_with_lines(pdf_path, lines)

        result = extract_vectors(pdf_path)

        assert result["page_num"] == 0
        assert result["page_size"] == pytest.approx((595.28, 841.89), abs=0.1)

        # Must find at least 3 segments (synthetic PDFs may produce extras)
        assert len(result["segments"]) >= 3

        # Verify Y-flip: PDF y=400 -> screen y = 841.89 - 400 = 441.89
        page_h = result["page_size"][1]
        found_horiz = False
        for seg in result["segments"]:
            sx, sy = seg["start"]
            ex, ey = seg["end"]
            # Find the horizontal line at PDF y=400
            if (abs(sx - 100) < 1 and abs(ex - 300) < 1
                    and abs(sy - (page_h - 400)) < 1):
                found_horiz = True
                assert seg["stroke_width"] == pytest.approx(2.0, abs=0.01)
                break
        assert found_horiz, "Expected horizontal segment not found"

    def test_extract_finds_text_annotations(self, tmp_path):
        """Text inserted into PDF should be extracted with bbox and font_size."""
        from backend.geometry.extraction import extract_vectors

        pdf_path = str(tmp_path / "text.pdf")
        # Use ASCII text — default PDF font doesn't embed Hebrew glyphs
        _create_pdf_with_text(pdf_path, [
            {"content": "Salon", "pos": (200, 400), "font_size": 14},
            {"content": "320", "pos": (100, 300), "font_size": 10},
        ])

        result = extract_vectors(pdf_path)

        assert len(result["texts"]) >= 2
        contents = [t["content"] for t in result["texts"]]
        assert "Salon" in contents
        assert "320" in contents

        for t in result["texts"]:
            assert t["font_size"] > 0
            assert len(t["bbox"]) == 4


# ---------------------------------------------------------------------------
# Tests for crop_legend
# ---------------------------------------------------------------------------

class TestCropLegend:

    def test_crop_legend_filters_outside_elements(self, tmp_path):
        """
        Thick lines in center (apartment) + thin lines far away (legend).
        crop_legend should keep apartment segments and discard legend.
        """
        from backend.geometry.extraction import extract_vectors, crop_legend

        pdf_path = str(tmp_path / "legend.pdf")
        doc = fitz.open()
        page = doc.new_page(width=595.28, height=841.89)

        # "Apartment" — thick lines in center of page
        page.draw_line(fitz.Point(150, 300), fitz.Point(450, 300), color=(0, 0, 0), width=3.0)
        page.draw_line(fitz.Point(150, 300), fitz.Point(150, 600), color=(0, 0, 0), width=3.0)
        page.draw_line(fitz.Point(450, 300), fitz.Point(450, 600), color=(0, 0, 0), width=3.0)
        page.draw_line(fitz.Point(150, 600), fitz.Point(450, 600), color=(0, 0, 0), width=3.0)
        # Interior wall
        page.draw_line(fitz.Point(300, 300), fitz.Point(300, 600), color=(0, 0, 0), width=1.5)

        # "Legend / kartisiyyah" — thin lines far from apartment
        page.draw_line(fitz.Point(500, 750), fitz.Point(580, 750), color=(0, 0, 0), width=0.3)
        page.draw_line(fitz.Point(500, 780), fitz.Point(580, 780), color=(0, 0, 0), width=0.3)
        page.draw_line(fitz.Point(500, 810), fitz.Point(580, 810), color=(0, 0, 0), width=0.3)

        doc.save(pdf_path)
        doc.close()

        data = extract_vectors(pdf_path)
        total_before = len(data["segments"])

        cropped = crop_legend(data)

        assert cropped["crop_report"]["original_segments"] == total_before
        assert cropped["crop_report"]["kept_segments"] < total_before
        assert cropped["crop_report"]["crop_bbox"] is not None
        # Legend segments should be removed
        assert len(cropped["segments"]) < total_before


# ---------------------------------------------------------------------------
# Tests for compute_stroke_histogram
# ---------------------------------------------------------------------------

class TestStrokeHistogram:

    def test_stroke_histogram_finds_clusters(self):
        """Three distinct width groups should produce 3 peaks."""
        import random
        from backend.geometry.extraction import compute_stroke_histogram

        random.seed(42)
        segments = []
        # Simulate realistic width clusters with natural spread:
        # dimension lines (~0.2), interior walls (~1.0), exterior/mamad (~3.5)
        for _ in range(40):
            w = random.gauss(0.2, 0.03)
            segments.append({"stroke_width": w, "start": (0, 0), "end": (10, 0)})
        for _ in range(30):
            w = random.gauss(1.0, 0.1)
            segments.append({"stroke_width": w, "start": (0, 0), "end": (10, 0)})
        for _ in range(20):
            w = random.gauss(3.5, 0.2)
            segments.append({"stroke_width": w, "start": (0, 0), "end": (10, 0)})

        result = compute_stroke_histogram(segments)

        assert len(result["peaks"]) >= 3
        assert len(result["suggested_thresholds"]) >= 2

        # Thresholds should be between adjacent peaks
        for i in range(len(result["suggested_thresholds"])):
            assert result["suggested_thresholds"][i] > result["peaks"][i]
            assert result["suggested_thresholds"][i] < result["peaks"][i + 1]


# ---------------------------------------------------------------------------
# Tests for pre-crop metadata extraction
# ---------------------------------------------------------------------------


class TestDetectScaleFromText:

    def test_detects_1_50_scale(self):
        from backend.geometry.extraction import detect_scale_from_text

        texts = [
            {"content": "some text", "bbox": (0, 0, 50, 10), "font_size": 10},
            {"content": "קנ״מ 1:50", "bbox": (0, 0, 50, 10), "font_size": 8},
        ]
        result = detect_scale_from_text(texts)
        assert result["scale_notation"] == "1:50"
        assert result["scale_value"] == 50

    def test_detects_1_100_scale(self):
        from backend.geometry.extraction import detect_scale_from_text

        texts = [
            {"content": "1:100", "bbox": (0, 0, 50, 10), "font_size": 8},
        ]
        result = detect_scale_from_text(texts)
        assert result["scale_notation"] == "1:100"
        assert result["scale_value"] == 100

    def test_no_scale_returns_none(self):
        from backend.geometry.extraction import detect_scale_from_text

        texts = [
            {"content": "סלון", "bbox": (0, 0, 50, 10), "font_size": 10},
        ]
        result = detect_scale_from_text(texts)
        assert result["scale_notation"] is None
        assert result["scale_value"] is None

    def test_detects_scale_with_spaces(self):
        from backend.geometry.extraction import detect_scale_from_text

        texts = [
            {"content": "1 : 50", "bbox": (0, 0, 50, 10), "font_size": 8},
        ]
        result = detect_scale_from_text(texts)
        assert result["scale_notation"] == "1:50"


class TestDetectAreaAnnotations:

    def test_detects_total_area(self):
        from backend.geometry.extraction import detect_area_annotations

        texts = [
            {"content": 'שטח דירה 95.5 מ"ר', "bbox": (0, 0, 100, 10), "font_size": 10},
        ]
        result = detect_area_annotations(texts)
        assert result["total_area_sqm"] == 95.5
        assert len(result["area_values"]) == 1

    def test_detects_balcony_area(self):
        from backend.geometry.extraction import detect_area_annotations

        texts = [
            {"content": 'שטח מרפסת 12.0 מ"ר', "bbox": (0, 0, 100, 10), "font_size": 10},
        ]
        result = detect_area_annotations(texts)
        assert result["balcony_area_sqm"] == 12.0

    def test_detects_both_areas(self):
        from backend.geometry.extraction import detect_area_annotations

        texts = [
            {"content": 'שטח דירה 95.5 מ"ר', "bbox": (0, 0, 100, 10), "font_size": 10},
            {"content": 'שטח מרפסת 12.0 מ"ר', "bbox": (0, 20, 100, 30), "font_size": 10},
            {"content": 'חדר שינה 14.2 מ"ר', "bbox": (100, 100, 150, 110), "font_size": 10},
        ]
        result = detect_area_annotations(texts)
        assert result["total_area_sqm"] == 95.5
        assert result["balcony_area_sqm"] == 12.0
        assert len(result["area_values"]) == 3

    def test_no_area_returns_none(self):
        from backend.geometry.extraction import detect_area_annotations

        texts = [
            {"content": "סלון", "bbox": (0, 0, 50, 10), "font_size": 10},
        ]
        result = detect_area_annotations(texts)
        assert result["total_area_sqm"] is None
        assert result["balcony_area_sqm"] is None
        assert len(result["area_values"]) == 0

    def test_area_with_m2_unicode(self):
        from backend.geometry.extraction import detect_area_annotations

        texts = [
            {"content": "שטח כולל 80.3 m²", "bbox": (0, 0, 100, 10), "font_size": 10},
        ]
        result = detect_area_annotations(texts)
        assert result["total_area_sqm"] == 80.3


class TestDetectFixtureLabels:

    def test_finds_room_labels(self):
        from backend.geometry.extraction import detect_fixture_labels

        texts = [
            {"content": "סלון", "bbox": (100, 100, 140, 110), "font_size": 12},
            {"content": "מטבח", "bbox": (200, 200, 240, 210), "font_size": 12},
            {"content": "random text", "bbox": (300, 300, 350, 310), "font_size": 10},
        ]
        result = detect_fixture_labels(texts)
        assert len(result) == 2
        labels = {r["label"] for r in result}
        assert "סלון" in labels
        assert "מטבח" in labels

    def test_finds_fixture_labels(self):
        from backend.geometry.extraction import detect_fixture_labels

        texts = [
            {"content": "כיור", "bbox": (100, 100, 130, 110), "font_size": 8},
            {"content": "אסלה", "bbox": (150, 150, 180, 160), "font_size": 8},
        ]
        result = detect_fixture_labels(texts)
        assert len(result) == 2

    def test_empty_texts_returns_empty(self):
        from backend.geometry.extraction import detect_fixture_labels

        result = detect_fixture_labels([])
        assert result == []


class TestExtractMetadata:

    def test_combined_metadata(self):
        from backend.geometry.extraction import extract_metadata

        texts = [
            {"content": "1:50", "bbox": (500, 700, 530, 710), "font_size": 8},
            {"content": 'שטח דירה 95.5 מ"ר', "bbox": (500, 720, 580, 730), "font_size": 10},
            {"content": 'שטח מרפסת 12.0 מ"ר', "bbox": (500, 740, 580, 750), "font_size": 10},
            {"content": "סלון", "bbox": (200, 300, 230, 310), "font_size": 12},
            {"content": "מטבח", "bbox": (100, 200, 130, 210), "font_size": 12},
        ]
        result = extract_metadata(texts)
        assert result["scale_notation"] == "1:50"
        assert result["scale_value"] == 50
        assert result["total_area_sqm"] == 95.5
        assert result["balcony_area_sqm"] == 12.0
        # 3 fixture labels: "מרפסת" (in balcony area text), "סלון", "מטבח"
        assert len(result["fixture_labels"]) == 3
        assert len(result["area_values"]) == 2
