"""Automated ground truth scorecard for the detection pipeline.

Runs the pipeline on every annotated sample in
docs/test-pdfs/ground-truth/ and prints a markdown scorecard. Invoked after
every Quality Sprint step to track improvement.

Run from backend/:
    python -m services.ground_truth
Or with the new pipeline once available:
    USE_NEW_PIPELINE=true python -m services.ground_truth

Agent: VG | Quality Sprint Step 0
"""
from __future__ import annotations

import json
import os
import traceback
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

# project root = parent of backend/
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_GT_DIR = _PROJECT_ROOT / "docs" / "test-pdfs" / "ground-truth"
_PDF_DIR = _PROJECT_ROOT / "docs" / "test-pdfs"


# --- ground-truth key → (PDF filename, 0-indexed fitz page number) ---
SAMPLE_MAP: dict[str, tuple[str, int]] = {
    "sample-0-p1": ("- Sample 0 MCH-208-Floors-Type D 1-50.pdf", 0),
    "sample-1-p1": ("- Sample 1 vector pdf דירה-2-תוכנית.pdf", 0),
    "sample-2-p1": (
        "- Sample 2 vector pdf תכניות-מכר-דירתי-מגרש-130-בניינים-A-ו-B.pdf",
        0,
    ),
    "sample-3-p1": ("- Sample 3 vector pdfבניין-2-דירות-48121620242832.pdf", 0),
    "sample-4-p1": ("- Sample 4 vector pdfלאטי-קדימה-סט-תכניות-מעודכן.pdf", 0),
    "sample-5-p1": ("- Sample 5 4-Rooms-Newer2.pdf", 0),
    "sample-5-p2": ("- Sample 5 4-Rooms-Newer2.pdf", 1),
    "sample-6-p1": ("- Sample 6 build9-J-plan- Vector PDF.pdf", 0),
    "sample-7-p1": ("- Sample 7 build12-A-plan (1)- vector pdf.pdf", 0),
    "sample-9-p1": ("- Sample 9 vector sample.pdf", 0),
    "sample-9-p2": ("- Sample 9 vector sample.pdf", 1),
}


# Overall-score weights (sum = 100)
WEIGHTS = {
    "rooms": 30,
    "types": 25,
    "walls": 15,
    "doors": 10,
    "windows": 10,
    "area": 5,
    "mamad": 5,
}


# ---------------------------------------------------------------------------
# Normalised pipeline output
# ---------------------------------------------------------------------------

@dataclass
class PipelineOutput:
    """Normalised shape for scoring — same for old and new pipeline."""

    rooms: list       # objects with .room_type and .area_sqm
    walls: list       # objects with .wall_type
    openings: list    # objects with .opening_type ('door'|'window'|'glass_door')
    mamad_detected: bool
    total_area_sqm: float  # sum of interior room areas (excluding balconies)
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pipeline runners
# ---------------------------------------------------------------------------

def run_old_pipeline(pdf_path: str, page_num: int) -> PipelineOutput:
    """Run the legacy extract→heal→graph→rooms pipeline."""
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

    raw = extract_vectors(pdf_path, page_num=page_num)
    meta = extract_metadata(raw["texts"])
    cropped = crop_legend(raw)
    histogram = compute_stroke_histogram(cropped["segments"])
    scale_value = meta.get("scale_value") or 50
    scale_factor = (0.0254 / 72) * scale_value

    thresh = histogram["suggested_thresholds"]
    wall_thresh = thresh[0] if thresh else 0.5
    wall_segs = [s for s in cropped["segments"] if s["stroke_width"] >= wall_thresh]

    healed, _ = heal_geometry(wall_segs, HealingConfig())
    healed = filter_largest_component(healed)
    G, embedding, _ = build_planar_graph(healed)
    rooms, _ = detect_rooms(G, embedding, scale_factor=scale_factor)
    rooms = classify_rooms(rooms, cropped["texts"], healed, scale_factor=scale_factor)

    ext_walls = detect_exterior_walls(healed, rooms)
    mamad = detect_mamad(rooms, healed, scale_factor=scale_factor)
    classified_walls = classify_structural(healed, ext_walls, mamad)
    openings, _ = detect_doors_and_windows(healed, rooms, scale_factor=scale_factor)

    total_interior = sum(
        r.area_sqm for r in rooms
        if r.room_type not in ("sun_balcony", "service_balcony")
    )

    return PipelineOutput(
        rooms=rooms,
        walls=classified_walls,
        openings=openings,
        mamad_detected=mamad is not None,
        total_area_sqm=total_interior,
        metadata=meta,
    )


def run_new_pipeline(pdf_path: str, page_num: int) -> PipelineOutput:
    """Run the Quality Sprint pipeline.

    Hybrid during incremental rollout:
      - Step 1+: walls from services.wall_detection (parallel-line centerlines)
      - Step 2+: rooms from services.room_detection (negative space)
      - Step 3+: openings from services.opening_detection (gap-based)

    Until each step lands, the corresponding stage falls back to legacy
    geometry/ modules so the full scorecard remains runnable end-to-end.
    """
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
        detect_doors_and_windows,
        detect_mamad,
    )
    from services.wall_detection import find_centerline_walls

    raw = extract_vectors(pdf_path, page_num=page_num)
    meta = extract_metadata(raw["texts"])
    cropped = crop_legend(raw)
    histogram = compute_stroke_histogram(cropped["segments"])
    scale_value = meta.get("scale_value") or 50
    scale_factor = (0.0254 / 72) * scale_value

    # --- NEW: parallel-line wall detection (Step 1) ---
    centerline_walls, _ = find_centerline_walls(
        cropped["segments"], scale_factor, histogram,
    )

    # --- LEGACY rooms + openings (until Steps 2/3 replace them) ---
    thresh = histogram["suggested_thresholds"]
    wall_thresh = thresh[0] if thresh else 0.5
    wall_segs = [s for s in cropped["segments"] if s["stroke_width"] >= wall_thresh]
    healed, _ = heal_geometry(wall_segs, HealingConfig())
    healed = filter_largest_component(healed)
    G, embedding, _ = build_planar_graph(healed)
    rooms, _ = detect_rooms(G, embedding, scale_factor=scale_factor)
    rooms = classify_rooms(rooms, cropped["texts"], healed, scale_factor=scale_factor)
    mamad = detect_mamad(rooms, healed, scale_factor=scale_factor)
    openings, _ = detect_doors_and_windows(healed, rooms, scale_factor=scale_factor)

    total_interior = sum(
        r.area_sqm for r in rooms
        if r.room_type not in ("sun_balcony", "service_balcony")
    )

    return PipelineOutput(
        rooms=rooms,
        walls=centerline_walls,  # NEW pipeline walls
        openings=openings,
        mamad_detected=mamad is not None,
        total_area_sqm=total_interior,
        metadata=meta,
    )


# ---------------------------------------------------------------------------
# Scoring primitives
# ---------------------------------------------------------------------------

def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _score_count(detected: int, gt: int) -> float:
    """Count-accuracy in [0,1] — 1.0 if exact, degrades linearly with gt."""
    if gt <= 0:
        return 1.0 if detected == 0 else 0.0
    return _clip(1.0 - abs(detected - gt) / gt)


def _score_types(detected_types: Counter, gt_types: dict) -> float:
    """Fraction of GT type-counts matched via multiset intersection."""
    gt_counter = Counter(gt_types)
    total = sum(gt_counter.values())
    if total == 0:
        return 1.0
    matched = sum((detected_types & gt_counter).values())
    return _clip(matched / total)


def _score_walls(detected_walls: list, gt_counts: dict) -> float:
    """F1 of per-type wall counts vs ground truth.

    F1 = harmonic mean of precision and recall over the multiset
    intersection. Rewards both wall-type coverage AND avoiding spurious
    over-detection. Detected walls outside the GT type vocabulary
    (e.g. "unknown") count against precision.
    """
    detected_by_type = Counter(getattr(w, "wall_type", "unknown") for w in detected_walls)
    gt_to_det_key = {
        "exterior_segments": "exterior",
        "structural_interior": "structural",
        "partition": "partition",
        "mamad_boundary": "mamad",
    }
    matched = 0
    total_gt = 0
    for gt_key, det_key in gt_to_det_key.items():
        gt_val = gt_counts.get(gt_key, 0) if isinstance(gt_counts, dict) else 0
        if not isinstance(gt_val, (int, float)) or gt_val <= 0:
            continue
        gt_val = int(gt_val)
        det_val = detected_by_type.get(det_key, 0)
        matched += min(det_val, gt_val)
        total_gt += gt_val

    total_det = len(detected_walls)
    if total_gt == 0:
        return 1.0 if total_det == 0 else 0.0
    if total_det == 0:
        return 0.0
    recall = matched / total_gt
    precision = matched / total_det
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _score_openings(detected: int, gt: int, tol: int = 2) -> float:
    """Full score if within ±tol, otherwise scaled by count distance."""
    if abs(detected - gt) <= tol:
        return 1.0
    return _score_count(detected, gt)


def _score_area(detected: float, gt: Optional[float]) -> Optional[float]:
    if gt is None or gt <= 0:
        return None
    if detected <= 0:
        return 0.0
    return _clip(min(detected, gt) / max(detected, gt))


# ---------------------------------------------------------------------------
# Per-sample scoring
# ---------------------------------------------------------------------------

@dataclass
class SampleScore:
    sample: str
    rooms_det: int
    rooms_gt: int
    rooms_score: float
    types_score: float
    walls_score: float
    doors_det: int
    doors_gt: int
    doors_score: float
    windows_det: int
    windows_gt: int
    windows_score: float
    area_det: float
    area_gt: Optional[float]
    area_score: Optional[float]
    mamad_det: bool
    mamad_gt: bool
    mamad_score: float
    overall: float
    error: Optional[str] = None


def score_sample(sample_key: str, gt: dict, out: PipelineOutput) -> SampleScore:
    rooms_gt = int(gt["rooms"]["total"])
    rooms_det = len(out.rooms)
    rooms_score = _score_count(rooms_det, rooms_gt)

    det_types = Counter(
        getattr(r, "room_type", "unknown") for r in out.rooms
    )
    types_score = _score_types(det_types, gt["rooms"].get("by_type", {}))

    wall_counts_gt = gt.get("walls", {}).get("counts", {})
    walls_score = _score_walls(out.walls, wall_counts_gt)

    doors_gt = int(gt.get("doors", {}).get("total", 0) or 0)
    wins_gt = int(gt.get("windows", {}).get("total", 0) or 0)
    doors_det = sum(
        1 for o in out.openings if getattr(o, "opening_type", "") == "door"
    )
    wins_det = sum(
        1 for o in out.openings if getattr(o, "opening_type", "") == "window"
    )
    doors_score = _score_openings(doors_det, doors_gt)
    wins_score = _score_openings(wins_det, wins_gt)

    area_gt = gt.get("apartment", {}).get("total_interior_sqm")
    area_score = _score_area(out.total_area_sqm, area_gt)

    mamad_gt = bool(gt.get("mamad", {}).get("present", False))
    mamad_score = 1.0 if out.mamad_detected == mamad_gt else 0.0

    # Weighted overall, skipping area when GT has none
    total_weight = 0.0
    weighted_sum = 0.0
    for key, val in (
        ("rooms", rooms_score),
        ("types", types_score),
        ("walls", walls_score),
        ("doors", doors_score),
        ("windows", wins_score),
        ("area", area_score),
        ("mamad", mamad_score),
    ):
        if val is None:
            continue
        w = WEIGHTS[key]
        weighted_sum += w * val
        total_weight += w
    overall = weighted_sum / total_weight if total_weight else 0.0

    return SampleScore(
        sample=sample_key,
        rooms_det=rooms_det, rooms_gt=rooms_gt, rooms_score=rooms_score,
        types_score=types_score,
        walls_score=walls_score,
        doors_det=doors_det, doors_gt=doors_gt, doors_score=doors_score,
        windows_det=wins_det, windows_gt=wins_gt, windows_score=wins_score,
        area_det=out.total_area_sqm, area_gt=area_gt, area_score=area_score,
        mamad_det=out.mamad_detected, mamad_gt=mamad_gt, mamad_score=mamad_score,
        overall=overall,
    )


# ---------------------------------------------------------------------------
# Scorecard driver
# ---------------------------------------------------------------------------

def run_scorecard(
    runner: Callable[[str, int], PipelineOutput],
    pipeline_name: str = "?",
    verbose: bool = False,
) -> list[SampleScore]:
    print(f"\n=== Quality Sprint Scorecard — pipeline: {pipeline_name} ===\n")
    header = (
        f"| {'Sample':<12} | {'Rooms':<7} | Types | Walls | "
        f"{'Doors':<7} | {'Windows':<7} | Area | Mamad | Overall |"
    )
    sep = (
        f"|{'-' * 14}|{'-' * 9}|{'-' * 7}|{'-' * 7}|"
        f"{'-' * 9}|{'-' * 9}|{'-' * 6}|{'-' * 7}|{'-' * 9}|"
    )
    print(header)
    print(sep)

    scores: list[SampleScore] = []
    skipped: list[str] = []

    for key, (pdf_name, page_num) in SAMPLE_MAP.items():
        gt_path = _GT_DIR / f"{key}-ground-truth.json"
        pdf_path = _PDF_DIR / pdf_name
        if not gt_path.exists():
            skipped.append(f"{key} (no GT: {gt_path.name})")
            continue
        if not pdf_path.exists():
            skipped.append(f"{key} (no PDF: {pdf_name})")
            continue
        gt = json.loads(gt_path.read_text())
        try:
            out = runner(str(pdf_path), page_num)
        except NotImplementedError:
            raise
        except Exception as e:
            if verbose:
                traceback.print_exc()
            print(
                f"| {key:<12} | ERROR    |       |       |"
                f"          |          |      |       | "
                f"{type(e).__name__}: {str(e)[:40]}"
            )
            continue

        s = score_sample(key, gt, out)
        scores.append(s)
        area_cell = (
            f"{int(s.area_score * 100):>3}%" if s.area_score is not None else " n/a"
        )
        mamad_cell = "✓" if s.mamad_det == s.mamad_gt else "✗"
        mamad_cell += "+" if s.mamad_gt else "-"
        print(
            f"| {key:<12} | {s.rooms_det:>2}/{s.rooms_gt:<4} | "
            f"{int(s.types_score * 100):>3}% | "
            f"{int(s.walls_score * 100):>3}% | "
            f"{s.doors_det:>2}/{s.doors_gt:<4} | "
            f"{s.windows_det:>2}/{s.windows_gt:<4} | "
            f"{area_cell} | {mamad_cell:<5} | "
            f"{int(s.overall * 100):>5}%  |"
        )

    print(sep)
    if scores:
        avg = sum(s.overall for s in scores) / len(scores)
        print(f"\nAVERAGE OVERALL: {avg * 100:.1f}% across {len(scores)} samples")
    for msg in skipped:
        print(f"  [skipped] {msg}")
    return scores


def main():
    use_new = os.environ.get("USE_NEW_PIPELINE", "false").lower() == "true"
    runner = run_new_pipeline if use_new else run_old_pipeline
    name = "NEW (quality sprint)" if use_new else "OLD (legacy geometry/)"
    verbose = os.environ.get("SCORECARD_VERBOSE", "false").lower() == "true"
    run_scorecard(runner, name, verbose=verbose)


if __name__ == "__main__":
    main()
