# DiraDream — AI Apartment Planning (Hebrew RTL)

## Stack
Backend: Python 3.12+FastAPI | Frontend: React 18+TS+Vite | 2D: Konva.js
3D: Three.js+R3F | PDF: PyMuPDF | Geometry: Shapely+SciPy+NetworkX
AI: Claude Opus 4.6 | DB: PostgreSQL+PostGIS | Auth: Supabase

## Current Phase
Phase: 1 | Sprint: 2 | Module: geometry-healing | Branch: feature/phase1-geometry-healing

## Plan-Execute-Verify (MANDATORY)
PLAN: state what you build, files, algorithm, edge cases, tests. WAIT for approval.
EXECUTE: small increments, commit per function.
VERIFY: run ALL tests, show output, delete temp files, update this file.

## Agent System
Load agent persona from /agents/[code].md before domain work.
Load ALL knowledge files listed in the agent persona.
Run validation chain after producing output.

## Agent Routing
PDF/geometry -> VG (validated by ARC)
Rooms/classification -> VG+ARC | Structural -> VG (validated by SE, ARC)
React/API -> FS (validated by UX) | 2D renderer -> FS (validated by UX+ARC)
3D model -> 3D (validated by ARC) | Views -> 3D+GIS (validated by ARC)
Hebrew UI -> FS+UX | AI features -> AI (validated by ARC/PT)
Cost estimation -> AI+PT | Furniture -> ID (validated by ARC+UX)
Marketplace -> FS+PT

## Israeli Conventions
Dimensions: cm | Display: sqm | Scale: 1:50 or 1:100 | Ceiling: 2.60m
Mamad: thickest walls, 9-15sqm, NEVER modifiable | Crop kartisiyyah first

## Working Parameters
SNAP_TOLERANCE: 3.0 | COLLINEAR_ANGLE: 2.0 | EXTEND_TOLERANCE: 10.0 | MIN_ROOM_AREA: 1.0
WALL_WIDTH_RANGES: use histogram-relative, not absolute. Peaks found at ~8 values in sample-01.

## Architecture Decisions
- Monorepo: project root is the repo root (backend/, frontend/, agents/, docs/)
- 10 AI agent personas in /agents/*.md — each declares knowledge file dependencies
- 25 knowledge base files in /docs/knowledge/ — living reference docs agents load before work
- Planning docs in /docs/plan/*.docx — human reference only, never read by Claude
- CLAUDE.md at repo root — Claude Code reads it automatically
- Local Python is 3.9.6 — will need Docker or pyenv for Python 3.12 requirement
- [2026-04-09] Wall classification must use relative stroke width clustering, not hardcoded thresholds. Real Israeli PDFs have much thinner lines than expected.

## Known Edge Cases
- [2026-04-09] Stroke widths in real Israeli PDFs are 0.1-1.1pt, not the 3.0-5.0pt assumed in conventions doc. Must use RELATIVE thresholds from histogram peaks, not absolute values. Status: open.
- [2026-04-09] crop_legend uses density-grid spatial clustering (adaptive threshold 40-80th pct + 2x2 morphological closing). Works well on 3/10 PDFs, no separation needed on 4/10, partial on 3/10. Sprint 4 adds user-assisted manual crop fallback for edge cases.
- [2026-04-09] Samples 7 and 8 are identical files. Use only one for testing.
- [2026-04-09] Sample 0 has 15,936 segments — single apartment (Type D, 6 rooms) with large kartisiyyah + neighbor outline on left. Room labels are vector-drawn (0 extractable texts in apartment area).
- [2026-04-09] Sample 5 is 2 pages (two 4-room variants). Split into Sample 5.0 and 5.1 locally (not in git — PDFs are gitignored).
- [2026-04-09] isolate_apartment() exists in extraction.py (Shapely polygonize) but is NOT wired into the API pipeline. It's experimental — works on Sample 0 but too aggressive on others. Sprint 4 will replace with manual crop rectangle from user.
- [2026-04-09] Many Israeli contractor PDFs render room labels as vector paths (letter outlines), not searchable text. get_text() returns 0 texts for these. Room classification will rely on fixture detection and area heuristics (Strategies B and C), not text matching. Some PDFs do have real text (Samples 3, 4 had 351 and 1,140 texts).
- [2026-04-09] heal_geometry doors_preserved=0 on all test PDFs — arc_segments not passed from extraction pipeline (Bézier curves extracted as polyline fragments, not tagged as arcs). Door detection needs arc tagging in extract_vectors() or a post-hoc arc classifier. Status: open, Sprint 3.
- [2026-04-09] Dead-end counts after healing are 10-100x higher than expected (1,898 / 495 / 659 vs expected 20-50 for door openings). Root cause: many near-miss endpoints beyond SNAP_TOLERANCE=3.0, plus dimension lines and annotation fragments surviving crop. Needs: (a) second-pass gap-fill for 3-15pt endpoints, (b) pre-healing filter for dimension/annotation lines by stroke width. Status: open.
- [2026-04-09] split_at_intersections can inflate segment count significantly (Sample 0: 10K→17K). This is correct for planar graph construction but means the pre-split healing steps (snap, merge, dedup) must be aggressive enough to reduce count first.

## Sprint 2 Healing Results (2026-04-09, ARC-validated)

### Run 2 (with pre-filter + gap fill)

| Metric | Sample 0 | Sample 6 | Sample 9 |
|--------|----------|----------|----------|
| Segments extracted | 15,936 | 7,887 | 4,673 |
| After crop | 10,234 | 6,613 | 3,741 |
| Pre-filter removed (dashed) | 0 | 0 | 0 |
| Pre-filter removed (thin) | 9,223 | 5,975 | 3,137 |
| Wall threshold (auto) | 0.54 | 0.66 | 0.71 |
| Kept for healing | 1,011 | 638 | 604 |
| After healing | 1,090 | 280 | 257 |
| Snap clusters | 428 | 270 | 258 |
| Collinear merges | 172 | 153 | 323 |
| Duplicates removed | 16 | 31 | 43 |
| Extensions made | 111 | 17 | 27 |
| Gap fill (2nd pass) | 452 | 3 | 0 |
| Connected components | 41 | 29 | 15 |
| Largest component % | 46.9% | 44.6% | 79.8% |
| Orphans | 14 | 15 | 6 |
| Dead ends | 226 | 85 | 50 |

### Dead end comparison (before → after fix)
| Sample | Before | After | Reduction |
|--------|--------|-------|-----------|
| 0 | 1,898 | 226 | **-88%** |
| 6 | 495 | 85 | **-83%** |
| 9 | 659 | 50 | **-92%** |

### ARC Verdict (updated)
- Dead ends reduced 83-92% — primary blocker addressed.
- Orphans reduced to 6-15 per sample (was 62-234).
- Largest component % dropped (especially Samples 0, 6) because pre-filter removes many connecting non-wall segments. This is expected — wall-only graph is sparser but structurally cleaner.
- Sample 9 best overall: 15 components, 79.8% largest, only 50 dead ends.
- **Next blocker**: largest component ratio on Samples 0 and 6 is ~45% — may need to relax wall threshold or add a post-filter reconnection step in Sprint 3.
- **Door detection gap** remains: arc_segments not wired in → 0 doors preserved. Sprint 3.

## Test PDF Inventory

### Crop works well (use for Sprint 2 testing)
| # | File | Segments | Texts | Crop % | Status |
|---|------|----------|-------|--------|--------|
| 0 | MCH-208-Floors-Type D 1-50 | 15,936 | 212 | 35.8% | Crops kartisiyyah. Also has neighbor outline (Sprint 4 manual crop). |
| 6 | build9-J-plan | 7,887 | 123 | 16.2% | Clean crop, legend on right side removed. |
| 9 | vector sample | 4,673 | 212 | 19.9% | Legend borders removed effectively. |

### No separation needed (apartment fills page)
| # | File | Segments | Texts | Crop % | Status |
|---|------|----------|-------|--------|--------|
| 3 | בניין-2-דירות | 3,406 | 351 | 0.3% | Apartment fills page, no legend. |
| 4 | לאטי-קדימה | 10,203 | 1,140 | 0.1% | 67-page PDF, one apartment per page. |
| 5.0 | 4-Rooms-Newer2 (page 0) | 3,781 | 44 | 0.0% | Clean single apartment. |
| 7/8 | build12-A-plan | 4,239 | 492 | 0.0% | Duplicates. Apartment+legend merged, no density gap. |

### Needs manual crop fallback (Sprint 4)
| # | File | Segments | Texts | Crop % | Issue |
|---|------|----------|-------|--------|-------|
| 1 | דירה-2-תוכנית | 3,846 | 168 | 8.8% | Legend borders same width as walls, light crop only. |
| 2 | תכניות-מכר-דירתי | 7,134 | 185 | 0.0% | Multi-page (7 pages), page 0 no separation. |
| 5.1 | 4-Rooms-Newer2 (page 1) | 3,988 | 46 | 6.9% | Light crop, most legend content remains. |
