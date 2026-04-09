"""
Run heal_geometry on the 3 cleanest test PDFs and report stats.
Sprint 2 validation script — temporary.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from geometry.extraction import extract_vectors, crop_legend, compute_stroke_histogram
from geometry.healing import heal_geometry, HealingConfig


SAMPLES = {
    0: "docs/test-pdfs/- Sample 0 MCH-208-Floors-Type D 1-50.pdf",
    6: "docs/test-pdfs/- Sample 6 build9-J-plan- Vector PDF.pdf",
    9: "docs/test-pdfs/- Sample 9 vector sample.pdf",
}

# Previous run dead-end counts (before fix) for comparison
PREV_DEAD_ENDS = {0: 1898, 6: 495, 9: 659}

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def run_one(sample_id: int, rel_path: str):
    pdf_path = os.path.join(PROJECT_ROOT, rel_path)
    print(f"\n{'='*60}")
    print(f"SAMPLE {sample_id}: {os.path.basename(rel_path)}")
    print(f"{'='*60}")

    # Extract
    data = extract_vectors(pdf_path, page_num=0)
    print(f"  Extracted: {len(data['segments'])} segments, {len(data['texts'])} texts")

    # Crop legend
    cropped = crop_legend(data)
    crop_rpt = cropped.get("crop_report", {})
    print(f"  After crop: {len(cropped['segments'])} segments "
          f"(removed {crop_rpt.get('original_segments', 0) - crop_rpt.get('kept_segments', 0)})")

    # Stroke histogram for auto-tune context
    histo = compute_stroke_histogram(cropped["segments"])
    peaks = histo.get("peaks", [])
    thresholds = histo.get("suggested_thresholds", [])
    print(f"  Stroke peaks: {[round(p, 3) for p in peaks]}")
    print(f"  Thresholds:   {[round(t, 3) for t in thresholds]}")

    # Heal (now with suggested_thresholds for pre-filter)
    config = HealingConfig(
        snap_tolerance=3.0,
        collinear_angle=2.0,
        collinear_distance=2.0,
        overlap_threshold=0.9,
        extend_tolerance=10.0,
    )
    healed, report = heal_geometry(
        cropped["segments"], config=config,
        histogram_peaks=peaks,
        suggested_thresholds=thresholds,
    )

    # Print report
    flt = report.get("filter", {})
    print(f"\n  --- PRE-FILTER ---")
    print(f"  Original segments:        {flt.get('original', '?')}")
    print(f"  Removed (dashed):         {flt.get('removed_dashed', '?')}")
    print(f"  Removed (thin):           {flt.get('removed_thin', '?')}")
    print(f"  Wall threshold:           {flt.get('wall_threshold', '?')}")
    print(f"  Kept for healing:         {flt.get('kept', '?')}")

    print(f"\n  --- HEALING REPORT ---")
    print(f"  Segments before healing:  {report['segments_before']}")
    print(f"  Segments after healing:   {report['segments_after']}")
    print(f"  Snap clusters merged:     {report['snap']['clusters_found']}")
    print(f"  Points merged (snap):     {report['snap']['points_merged']}")
    print(f"  Avg cluster size:         {report['snap']['avg_cluster_size']:.1f}")
    print(f"  Collinear merges:         {report['merge_collinear']['merges_performed']}")
    print(f"  Merge passes needed:      {report['merge_collinear']['passes_needed']}")
    print(f"  Duplicates removed:       {report['remove_duplicates']['duplicates_removed']}")
    print(f"  Extensions made:          {report['extend_to_intersect']['extensions_made']}")
    print(f"  Doors preserved:          {report['extend_to_intersect']['doors_preserved']}")
    print(f"  Intersections found:      {report['split_at_intersections']['intersections_found']}")
    print(f"  Splits made:              {report['split_at_intersections']['splits_made']}")

    gap = report.get("gap_fill", {})
    print(f"\n  --- GAP FILL (2nd pass) ---")
    print(f"  Dead ends snapped:        {gap.get('dead_ends_snapped', '?')}")
    print(f"  Tolerance used:           {gap.get('tolerance_used', '?')}")

    val = report["validation"]
    prev = PREV_DEAD_ENDS.get(sample_id, "?")
    reduction = ""
    if isinstance(prev, int) and val['dead_end_count'] > 0:
        pct = (1 - val['dead_end_count'] / prev) * 100
        reduction = f" ({pct:+.1f}% vs previous {prev})"

    print(f"\n  --- VALIDATION ---")
    print(f"  Total segments:           {val['total_segments']}")
    print(f"  Orphan count:             {val['orphan_count']}")
    print(f"  Dead end count:           {val['dead_end_count']}{reduction}")
    print(f"  Connected components:     {val['connected_components']}")
    print(f"  Largest component ratio:  {val['largest_component_ratio']}")
    print(f"  Degree distribution:      {val['degree_distribution']}")

    return report


if __name__ == "__main__":
    all_reports = {}
    for sid, path in SAMPLES.items():
        all_reports[sid] = run_one(sid, path)

    print(f"\n{'='*60}")
    print("COMPARISON: Dead ends BEFORE vs AFTER fix")
    print(f"{'='*60}")
    for sid in SAMPLES:
        rpt = all_reports[sid]
        after = rpt["validation"]["dead_end_count"]
        before = PREV_DEAD_ENDS[sid]
        pct = (1 - after / before) * 100 if before > 0 else 0
        print(f"  Sample {sid}: {before:>5} → {after:>5}  ({pct:+.1f}%)")
