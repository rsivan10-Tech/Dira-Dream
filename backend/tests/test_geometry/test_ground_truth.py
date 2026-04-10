"""
Regression tests: pipeline output vs annotated ground truth for Sample 9.

Ground truth annotated 2026-04-10 from docs/test-pdfs/sample-9-ground-truth.pdf.
Tolerances are deliberately loose — they catch regressions, not small
fluctuations.  Tighten them as the pipeline improves.

Agent: VG | Phase 2, Sprint 5B
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Skip the entire module when the test PDF is not available (e.g. CI without
# large binaries).
# ---------------------------------------------------------------------------

_PDF_PATH = Path(__file__).resolve().parents[3] / "docs" / "test-pdfs" / "- Sample 9 vector sample.pdf"
_GT_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "sample_9_ground_truth.json"

pytestmark = pytest.mark.skipif(
    not _PDF_PATH.exists(),
    reason="Sample 9 PDF not available (git-ignored binary)",
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ground_truth():
    with open(_GT_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def pipeline_results():
    """Run the full pipeline on Sample 9, both pages.  Cached per module."""
    from geometry.extraction import extract_vectors, crop_legend, compute_stroke_histogram
    from geometry.healing import heal_geometry, HealingConfig, filter_largest_component
    from geometry.graph import build_planar_graph
    from geometry.rooms import detect_rooms, classify_rooms
    from geometry.structural import (
        detect_exterior_walls,
        detect_mamad,
        classify_structural,
        detect_doors_and_windows,
    )
    from api.routes import extract_metadata

    results: dict[int, dict] = {}
    pdf = str(_PDF_PATH)

    for page_num in (0, 1):
        raw = extract_vectors(pdf, page_num=page_num)
        meta = extract_metadata(raw["texts"])
        cropped = crop_legend(raw)
        histogram = compute_stroke_histogram(cropped["segments"])
        scale_value = meta.get("scale_value") or 50
        scale_factor = (0.0254 / 72) * scale_value
        thresholds = histogram["suggested_thresholds"]
        wall_thresh = thresholds[0] if thresholds else 0.5
        wall_segs = [s for s in cropped["segments"] if s["stroke_width"] >= wall_thresh]
        healed, heal_stats = heal_geometry(wall_segs, HealingConfig())
        healed = filter_largest_component(healed)
        G, embedding, _ = build_planar_graph(healed)
        rooms, _ = detect_rooms(G, embedding, scale_factor=scale_factor)
        rooms = classify_rooms(rooms, cropped["texts"], healed, scale_factor=scale_factor)
        ext_walls = detect_exterior_walls(healed, rooms)
        mamad = detect_mamad(rooms, healed, scale_factor=scale_factor)
        classified_walls = classify_structural(healed, ext_walls, mamad)
        openings, report = detect_doors_and_windows(healed, rooms, scale_factor=scale_factor)

        results[page_num] = {
            "rooms": rooms,
            "mamad": mamad,
            "openings": openings,
            "report": report,
            "walls": classified_walls,
        }

    return results


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSample9GroundTruth:
    """Regression: pipeline output stays within ground-truth tolerances."""

    def test_total_rooms_in_range(self, pipeline_results, ground_truth):
        total = sum(len(r["rooms"]) for r in pipeline_results.values())
        tol = ground_truth["tolerances"]
        assert tol["rooms_min"] <= total <= tol["rooms_max"], (
            f"Total rooms {total} outside [{tol['rooms_min']}, {tol['rooms_max']}] "
            f"(ground truth: {ground_truth['totals']['rooms']})"
        )

    def test_total_doors_in_range(self, pipeline_results, ground_truth):
        total = sum(
            sum(1 for o in r["openings"] if o.opening_type == "door")
            for r in pipeline_results.values()
        )
        tol = ground_truth["tolerances"]
        assert tol["doors_min"] <= total <= tol["doors_max"], (
            f"Total doors {total} outside [{tol['doors_min']}, {tol['doors_max']}] "
            f"(ground truth: {ground_truth['totals']['doors']})"
        )

    def test_total_windows_in_range(self, pipeline_results, ground_truth):
        total = sum(
            sum(1 for o in r["openings"] if o.opening_type == "window")
            for r in pipeline_results.values()
        )
        tol = ground_truth["tolerances"]
        assert tol["windows_min"] <= total <= tol["windows_max"], (
            f"Total windows {total} outside [{tol['windows_min']}, {tol['windows_max']}] "
            f"(ground truth: {ground_truth['totals']['windows']})"
        )

    def test_mamad_detected(self, pipeline_results, ground_truth):
        if not ground_truth["tolerances"]["mamad_must_detect"]:
            pytest.skip("Mamad detection not required by ground truth")
        found = any(r["mamad"] is not None for r in pipeline_results.values())
        assert found, "Mamad not detected on any page"

    def test_mamad_on_page_1(self, pipeline_results, ground_truth):
        """Mamad must be present on page 1 (lower floor)."""
        gt_page1 = ground_truth["pages"]["1"]
        if not gt_page1["mamad"]["present"]:
            pytest.skip("Ground truth says no mamad on page 1")
        mamad = pipeline_results[1]["mamad"]
        assert mamad is not None, "Mamad not detected on page 1 (lower floor)"
        assert 7.0 <= mamad.area_sqm <= 15.0, (
            f"Mamad area {mamad.area_sqm:.1f} sqm outside [7, 15]"
        )

    def test_page0_has_rooms(self, pipeline_results, ground_truth):
        gt_count = ground_truth["pages"]["0"]["rooms"]["total"]
        detected = len(pipeline_results[0]["rooms"])
        assert detected >= 2, (
            f"Page 0: only {detected} rooms detected (ground truth: {gt_count})"
        )

    def test_page1_has_rooms(self, pipeline_results, ground_truth):
        gt_count = ground_truth["pages"]["1"]["rooms"]["total"]
        detected = len(pipeline_results[1]["rooms"])
        assert detected >= 4, (
            f"Page 1: only {detected} rooms detected (ground truth: {gt_count})"
        )

    def test_bedroom_detected_both_pages(self, pipeline_results):
        """At least one bedroom on each page."""
        for page in (0, 1):
            bedrooms = [r for r in pipeline_results[page]["rooms"]
                        if r.room_type == "bedroom"]
            assert len(bedrooms) >= 1, f"No bedroom detected on page {page}"

    def test_no_windows_exceed_ground_truth_6x(self, pipeline_results, ground_truth):
        """Catch window over-detection regression (was 6.3x before fix)."""
        gt_windows = ground_truth["totals"]["windows"]
        total = sum(
            sum(1 for o in r["openings"] if o.opening_type == "window")
            for r in pipeline_results.values()
        )
        ratio = total / gt_windows if gt_windows > 0 else total
        assert ratio < 2.5, (
            f"Window over-detection: {total} detected vs {gt_windows} ground truth "
            f"({ratio:.1f}x). Regression from 6.3x fix."
        )

    def test_no_doors_exceed_ground_truth_3x(self, pipeline_results, ground_truth):
        """Catch door over-detection regression (was 2.3x before fix)."""
        gt_doors = ground_truth["totals"]["doors"]
        total = sum(
            sum(1 for o in r["openings"] if o.opening_type == "door")
            for r in pipeline_results.values()
        )
        ratio = total / gt_doors if gt_doors > 0 else total
        assert ratio < 2.0, (
            f"Door over-detection: {total} detected vs {gt_doors} ground truth "
            f"({ratio:.1f}x). Regression from 2.3x fix."
        )
