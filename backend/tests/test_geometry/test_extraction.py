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
