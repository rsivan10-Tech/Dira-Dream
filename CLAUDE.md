# DiraDream — AI Apartment Planning (Hebrew RTL)

## Stack
Backend: Python 3.12+FastAPI | Frontend: React 18+TS+Vite | 2D: Konva.js
3D: Three.js+R3F | PDF: PyMuPDF | Geometry: Shapely+SciPy+NetworkX
AI: Claude Opus 4.6 | DB: PostgreSQL+PostGIS | Auth: Supabase

## Current Phase
Phase: 2 IN PROGRESS | Sprint: 5B | Tag: v0.2.0-sprint5b | Branch: feature/phase2-3d-extrusion

## Sprint 5B Status (2026-04-09)

### What IS Working
- Mamad shows orange in 3D (page 1) ✓
- Exterior walls show dark red in 2D (page 2) ✓
- Floor surfaces rendered ✓
- Wall extrusion at correct height (2.60m) ✓
- Page selector works ✓
- 3D view integrated with view switcher ✓
- Largest component filter removes most legend noise ✓
- Opening matching logic implemented (openingUtils.ts)
- ExtrudeGeometry with Shape holes for walls with openings
- GlassPane and DoorPanel components wired in

### Open Issues
1. **No door openings visible in 3D** — holes in walls not cut (matching may not find walls, or ExtrudeGeometry holes not rendering)
2. **No window openings visible in 3D** — same root cause as doors
3. **Glass doors (balcony) are solid walls** — not transparent
4. **Black walls appearing** — unknown wall type defaulting to black instead of a valid color
5. **Cannot walk through 3D model** — first-person controls not yet implemented (Sprint 6)
6. **Floating geometry on some PDFs** — page 2 has stairwell elements on the right
7. **2D still showing too many doors (34) and 13 rooms** — should be ~8-10 rooms

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
- [2026-04-09] heal_geometry doors_preserved=0 on all test PDFs — arc_segments not passed from extraction pipeline (Bézier curves extracted as polyline fragments, not tagged as arcs). Door detection needs arc tagging in extract_vectors() or a post-hoc arc classifier. Status: open, Sprint 3. Update [2026-04-09]: detect_doors_and_windows() finds doors from gaps (9 on Sample 9) but still 0 arc confirmations. Arc tagging remains open.
- [2026-04-09] Dead-end counts after healing are 10-100x higher than expected (1,898 / 495 / 659 vs expected 20-50 for door openings). Root cause: many near-miss endpoints beyond SNAP_TOLERANCE=3.0, plus dimension lines and annotation fragments surviving crop. Needs: (a) second-pass gap-fill for 3-15pt endpoints, (b) pre-healing filter for dimension/annotation lines by stroke width. Status: fixed in Sprint 2 (dead ends reduced 83-92%).
- [2026-04-09] Room detection produced 0 rooms on Samples 0 and 6 due to graph fragmentation. Fix applied: reconnect_components() bridges nearby disconnected fragments (5× SNAP_TOLERANCE). LC% improved: Sample 0: 46.9%→71.5%, Sample 6: 44.6%→81.2%, Sample 9: 79.8%→90.3%. However, Samples 0/1/6 still have 0 rooms because the graph topology is too dense (1000+ wall segments form tiny faces ≤2317 pt² vs 38,564 pt² for a real 3×4m room). Root cause: wall-only filter keeps too many short fragments that create mesh-like intersections. Fix: more aggressive segment merging or wall-count reduction before split_at_intersections. Status: partially fixed (connectivity solved, topology still open).
- [2026-04-09] Mamad detector identifies Sample 9 bedroom (10.9 sqm, text says "חדר שינה") as mamad by wall thickness. Text classification (95% confidence) and mamad detection (95% confidence) conflict. Need priority resolution: if text says bedroom, mamad detector should require additional evidence (single door, no standard window). Status: open.
- [2026-04-09] Window detector finds 24 windows on Sample 9 — too many for a small apartment. Parallel-line heuristic is over-sensitive, matching furniture outlines and annotation lines. Needs: restrict to exterior-wall-adjacent segments only, require minimum line thickness. Status: open.
- [2026-04-09] Signed-area outer-face detection uses global minority sign, which works for a single connected component but discards legitimate rooms in multi-component graphs. Need per-component outer-face detection. Status: open (low priority — resolves itself when graph fragmentation is fixed).
- [2026-04-09] split_at_intersections can inflate segment count significantly (Sample 0: 10K→17K). This is correct for planar graph construction but means the pre-split healing steps (snap, merge, dedup) must be aggressive enough to reduce count first.
- [2026-04-09] Dense PDFs (Samples 0/1/6, 10K+ raw segments) produce tiny mesh faces instead of room-sized polygons after split_at_intersections. Largest face ≤2,317 pt² vs 38,564 pt² for a real 3×4m room. Need segment reduction or clustering before splitting. Deferred — will address with user-assist crop in Sprint 4 or pre-processing filter. Status: deferred.

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

## Sprint 3 Room Detection Results (2026-04-09, ARC-validated)

### Pipeline: extract → crop → histogram → heal → reconnect → graph → rooms → classify → structural → doors/windows

### Reconnection impact (reconnect_components at 5× SNAP_TOLERANCE)
| Sample | Components before→after | Bridges | LC% before→after |
|--------|------------------------|---------|-------------------|
| 0 | 41→28 | 13 | 46.9%→**71.5%** |
| 1 | 43→12 | 31 | 16.0%→**82.7%** |
| 6 | 29→13 | 16 | 44.6%→**81.2%** |
| 9 | 15→8 | 7 | 79.8%→**90.3%** |

### Full pipeline results — all 10 PDFs
| Sample | Segs | Healed | Comp | LC% | Rooms | Text-matched | Area (sqm) | Mamad |
|--------|------|--------|------|-----|-------|-------------|-----------|-------|
| 0 | 15,936 | 1,103 | 41→28 | 71.5% | **0** | 0 | — | N |
| 1 | 3,846 | 226 | 43→12 | 82.7% | **0** | 0 | — | N |
| 2 | 7,134 | 282 | 32→26 | 53.2% | **5** | 2 | 1228.6 | N |
| 3 | 3,406 | 142 | 20→18 | 70.8% | **2** | 0 | 7.8 | N |
| 4 | 10,203 | 1,438 | 45→33 | 58.0% | **4** | 0 | 5.9 | N |
| 5.0 | 3,781 | 1,316 | 46→33 | 54.2% | **7** | 1 | 141.0 | N |
| 5.1 | 3,988 | 1,240 | 43→30 | 58.5% | **7** | 1 | 59.9 | N |
| 6 | 7,887 | 296 | 29→13 | 81.2% | **0** | 0 | — | N |
| 7 | 4,239 | 238 | 21→21 | 22.9% | **3** | 1 | 295.8 | N |
| 9 | 4,673 | 264 | 15→8 | 90.3% | **7** | 2 | 46.0 | Y |

**Result: 7/10 PDFs produce rooms (target was 5/10).**

### ARC Verdict — Sprint 3 (updated)
- **Reconnection works**: LC% improved 10-67 percentage points. Connectivity blocker resolved.
- **7/10 PDFs produce rooms**: Samples 2, 3, 4, 5.0, 5.1, 7, 9 all detect rooms.
- **3 PDFs still fail (0, 1, 6)**: Despite high LC% (71-83%), graph topology is too dense (1000+ wall segments form tiny faces ≤2317 pt² vs 38,564 pt² for a real room). Root cause: wall filter keeps too many short fragments that create mesh-like intersections after split_at_intersections.
- **Area anomalies**: Samples 2 (1228 sqm), 7 (296 sqm) have wildly inflated areas — likely scale factor mismatch (assumes 1:50, may be 1:100 or other).
- **Samples 3, 4**: Detect rooms but areas are tiny (7.8 / 5.9 sqm total) — faces forming but too small, similar root cause.
- **Best results**: Sample 9 (7 rooms, 46 sqm, mamad found), Sample 5.0 (7 rooms, 141 sqm).
- **Open issues**: mamad/text conflict, window over-detection, arc tagging, scale auto-detection, dense-graph face merging for Samples 0/1/6.

## Phase 1 Completion (v0.1.0-phase1, 2026-04-09)

### What works
- **Full pipeline**: PDF upload → extract → crop → heal → graph → rooms → classify → structural → render
- **2D renderer**: Konva.js with walls (colored by type), room polygons + Hebrew labels, doors, windows
- **Interactions**: pan/zoom, hover tooltips, click selection, sidebar details, measurement tool
- **10 Israeli room types**: salon, bedroom, kitchen, guest_toilet, bathroom, mamad, sun_balcony, service_balcony, storage, utility
- **Structural classification**: exterior (dark red), mamad (orange), partition (blue)
- **Scale detection**: auto-detects 1:50 / 1:100 from PDF text
- **Area metadata**: extracts stated area from PDF legend (split-span support)
- **Area display**: interior vs balcony split per Israeli standard
- **Multi-page PDF**: page selector for PDFs with multiple apartment types
- **Confidence dashboard**: overall score, room/wall/opening counts, action items
- **Export**: CSV room schedule, PNG
- **Hebrew RTL**: all UI text via react-intl, sidebar LEFT, canvas RIGHT

### Known limitations (deferred to Phase 2)
- **Room coverage gap**: 7/10 PDFs produce rooms but only ~50-70% of actual rooms detected (unclosed wall polygons)
- **Door over-detection**: 11-42 doors per page (expected 6-10). Stairwell doors included.
- **Legend/kartisiyyah not always cropped**: some PDFs retain legend segments as noise
- **3 PDFs still fail room detection**: Samples 0, 1, 6 (dense graph, 10K+ segments → tiny mesh faces)
- **Dashboard "0 structural" display**: exterior walls render correctly as red but dashboard counts them separately from "structural" category
- **Area accuracy**: ~50% gap between calculated and stated area due to missing rooms

### Architecture
- `/api/extract` — raw extraction only (for debug viewer)
- `/api/analyze` — full pipeline: extract → heal → rooms → structural
- `FloorplanViewer` — controlled component, data lifted to App.tsx
- `floorplanUtils.ts` — shared AnalyzeResponse → FloorplanData converter
- 10 room types defined in `models.py`, enforced in `classify_rooms` post-processing

## Test PDF Inventory

### PASS — rooms detected (7/10)
| # | File | Segments | Rooms | Status |
|---|------|----------|-------|--------|
| 2 | תכניות-מכר-דירתי | 7,134 | 5 (2 text) | Multi-page, page 0. |
| 3 | בניין-2-דירות | 3,406 | 2 | Apartment fills page, no legend. |
| 4 | לאטי-קדימה | 10,203 | 4 | 67-page PDF, one apartment per page. |
| 5.0 | 4-Rooms-Newer2 (page 0) | 3,781 | 7 (1 text) | Clean single apartment. |
| 5.1 | 4-Rooms-Newer2 (page 1) | 3,988 | 7 (1 text) | Light crop, rooms still detected. |
| 7/8 | build12-A-plan | 4,239 | 3 (1 text) | Duplicates. Apartment+legend merged. |
| 9 | vector sample | 4,673 | 7 (2 text) | Best result. Mamad found. LC=90.3%. |

### FAIL — graph too dense, needs segment reduction (deferred)
| # | File | Segments | Healed | LC% | Issue |
|---|------|----------|--------|-----|-------|
| 0 | MCH-208-Floors-Type D 1-50 | 15,936 | 1,103 | 71.5% | 1K+ wall segs → tiny mesh faces, 0 rooms. |
| 1 | דירה-2-תוכנית | 3,846 | 226 | 82.7% | High LC% but 0 rooms. Same dense-face issue. |
| 6 | build9-J-plan | 7,887 | 296 | 81.2% | High LC% but 0 rooms. Same dense-face issue. |
