# DiraDream v1 — Technical Postmortem

**Date:** 2026-04-14
**Author:** Independent audit (outside-consultant mode)
**Scope:** Full codebase, knowledge base, agent system, tests, scorecard
**Disposition:** Project is being archived and rebuilt. This document is the foundation for v2.

---

## 0. Executive Summary

DiraDream v1 set out to parse Israeli residential floor-plan PDFs (vector, Hebrew RTL) and produce structured data — rooms, walls, openings, and a 2D/3D viewer — for a renovation-planning product. Over ~82 commits and two architectural iterations (`geometry/*` → `services/*`), the team built a working end-to-end demo but never reached production accuracy.

**The honest numbers.** On the 10-PDF test set, the current new pipeline detects mamad rooms on 6/10 samples, but **mamad walls on zero samples** (a Wave A regression introduced 2026-04-14). Door counts swing from 0 (Sample 7) to 29 (Sample 0) — an instability pattern, not a single bug. Sample 9 page 1, the vector reference, gets 8 rooms (matching ground truth) but only 1 of 8 is correctly typed. Sample 2 gets 5 rooms against a ground truth of 9. Nothing in the test set is robustly "solved".

**What went right.** Three things. (1) The decision to switch from planar-graph face enumeration to **negative-space room extraction** (`services/room_detection.py`) was correct and should carry into v2 unchanged in spirit. (2) The decision to switch wall classification from **absolute stroke-width thresholds** to **parallel-line centerline pairing with measured thickness** (`services/wall_detection.py`) was also correct. (3) The type-safe frontend domain model (`frontend/src/types/floorplan.ts`) and the React Three Fiber 3D scene with wall-splitting-based openings are both worth keeping.

**What went wrong.** Four things. (1) **Two full pipelines live in the repo at once** — `backend/geometry/*` (legacy) and `backend/services/*` (new) — with duplicated classification logic and no cutover plan. (2) **Plan-Execute-Verify was enforced for humans, not for agents** — we let PDF assumptions in `/docs/knowledge/` drift from reality for weeks, and they seeded bad constants. (3) **The 10-agent system is mostly decoration** — only VG and 3D left fingerprints on the code; the rest are persona prose with no enforcement. (4) **Hard problems were deferred in loops** — staircase exclusion, dense-graph fragmentation, arc tagging, fixture extraction. Each was marked "open" three times and never resolved.

**V2 should be a fundamentally simpler stack** — one pipeline, one classifier, one test harness, three agents at most, and a hard gate: no UI work until the minimum-viable backend consistently hits 80% on 3 reference PDFs. Estimated path to 80% accuracy is **8-12 weeks** if the team keeps v1's good decisions and discards its bad ones.

---

## 1. Project Metrics

| Metric | Value |
|---|---:|
| Total git commits | 82 |
| Python source LOC (backend, excl. tests) | 6,774 |
| Python test LOC | 2,461 |
| TypeScript/TSX LOC (frontend) | 5,952 |
| Python files (33), test files (10) | 33 / 10 |
| TS/TSX files | 18 |
| Knowledge base files | 25 |
| Agent persona files | 10 |
| Planning .docx files (never read by Claude) | 5 |
| Test PDFs | 10 (9 unique + 1 duplicate) |
| Largest backend file | [healing.py](../backend/geometry/healing.py) @ 1,277 LOC |
| Largest frontend file | [FloorplanViewer.tsx](../frontend/src/canvas/FloorplanViewer.tsx) @ 1,281 LOC |

Two files above 1,200 LOC in a codebase this size is a structural signal. Both hold 5+ concerns in one module and both are on the "rewrite" list below.

---

## 2. Architecture Review — Pipeline Step by Step

The pipeline (new path, `USE_NEW_PIPELINE=true`) looks like this:

```
PDF ──▶ extract_vectors ──▶ crop_legend ──▶ compute_stroke_histogram
                                                    │
                                                    ▼
                                      find_centerline_walls
                                                    │
                                                    ▼
                                detect_rooms_negative_space
                                                    │
                                                    ▼
                                      refine_mamad_walls
                                                    │
                                                    ▼
                                detect_openings_from_gaps
                                                    │
                                                    ▼
                                        AnalyzeResponse
                                              │
                            ┌─────────────────┴─────────────────┐
                            ▼                                   ▼
                       2D (Konva)                        3D (R3F)
```

### 2.1 Extraction — `geometry/extraction.py` (739 LOC)

**Approach.** PyMuPDF to walk the PDF drawing stream, collect line/curve operators as segments, flatten Béziers to polylines, collect text, compute page size, auto-detect scale (1:50 / 1:100) from text.

**Did it work?** Mostly yes. The raw segment count is reliable (Sample 0: 15,936 segments, Sample 9: ~4,600). Scale detection via text pattern works when the PDF has real text (Samples 3, 4 had hundreds of extractable texts). It silently fails when PDFs render text as vector outlines — the gotcha we learned only after Sample 0 produced zero extractable texts in the apartment area.

**What should change in v2.**
- Flatten Béziers **with arc tags** (currently: "arc_segments not passed from extraction pipeline" per [CLAUDE.md](../CLAUDE.md)). Without arc tags, door detection has no ground truth signal and has to reverse-engineer them from "short collinear fragments", which fires on furniture outlines.
- Separate "extraction" from "legend cropping" — currently both live in this file.
- Add a pre-flight check: does `get_text()` return non-trivial content? If not, flag the PDF as "vector-label only" and route to a different room-classification path.

**Recommendation:** Keep the extraction core; split into two modules, add arc tagging.

### 2.2 Legend cropping — `crop_legend()` in extraction.py

**Approach.** Density-grid spatial clustering (adaptive 40-80th percentile + 2×2 morphological closing) to find the dense "apartment" region and drop legend/kartisiyyah.

**Did it work?** Per CLAUDE.md: "Works well on 3/10 PDFs, no separation needed on 4/10, partial on 3/10." The 3 partial cases (Samples 0, 1, 6) never got rooms detected on the legacy pipeline for this reason. A user-assisted manual crop was planned for Sprint 4 and not delivered.

**What should change in v2.**
- Accept that fully-automatic legend detection is a research problem. Ship a **required** user-confirmation step: UI shows the detected apartment bbox + legend bbox and asks "is this right?" before the expensive stages run.
- Use the confirmed bbox everywhere downstream instead of repeatedly re-detecting.

### 2.3 Healing — `geometry/healing.py` (1,277 LOC, 5 passes)

**Approach.** Snap → merge_collinear → remove_duplicates → extend_to_intersect → split_at_intersections, plus `reconnect_components` (169 LOC, longest function in the codebase) and `_second_pass_gap_fill` (104 LOC).

**Did it work?** Technically yes — the Sprint 2 metrics showed 83-92% dead-end reduction (Sample 0: 1,898 → 226 dead ends). But the output feeds a planar graph that still fragments into tiny mesh faces on dense PDFs (Samples 0, 1, 6). Healing solved its own metric (dead ends) without solving the consumer's problem (detectable rooms).

**What should change in v2.**
- **Delete the entire file.** The new pipeline uses `_extend_centerlines` (in [services/room_detection.py](../backend/services/room_detection.py)) and a single morphological closing of the wall mass. These two operations together do the same job as the 5-pass healing cascade.
- The 639-LOC test file ([test_healing.py](../backend/tests/test_geometry/test_healing.py)) exercises synthetic cases; it is not evidence that healing helps real PDFs. The ground-truth tests are better evidence and don't depend on healing.

**Recommendation:** Discard. The new pipeline doesn't need it.

### 2.4 Planar graph + room detection — `geometry/graph.py` + `geometry/rooms.py`

**Approach.** Build a planar embedding from healed segments, enumerate faces, filter by area, classify rooms by text / fixture / area-heuristic.

**Did it work?** No. The ceiling is documented in CLAUDE.md: "Samples 0/1/6 still have 0 rooms because the graph topology is too dense (1000+ wall segments form tiny faces ≤2317 pt² vs 38,564 pt² for a real 3×4m room)." The root cause is that `split_at_intersections` inflates segment count (Sample 0: 10K → 17K) into a mesh-like structure, and filtering by face area discards most real rooms.

**What should change in v2.**
- **Discard this entire branch.** The negative-space approach in `services/room_detection.py` is strictly better — it never cared about planar embeddings, never needed the mesh, and solved the Samples 0/1/6 class of problems in a different way (it just uses the wall mass directly).
- Keep the classification logic (`_classify_by_text`, `_classify_by_fixtures`, `_classify_by_area`) — it's currently duplicated across `geometry/rooms.py` and `services/room_detection.py`. Extract to one shared module.

### 2.5 Parallel-line wall detection — `services/wall_detection.py` (550 LOC)

**Approach.** For each segment, find nearby parallel segments within distance 6-40cm, angle < 5°, overlap ≥ 50%. Each confirmed pair becomes a `CenterlineWall` with a measured `thickness_cm`. Classify via relative thickness ranking (mamad ≥ exterior ≥ partition, top-decile gating).

**Did it work?** **Yes — this is one of v1's best decisions.** It replaces the broken stroke-width classifier and gives you real thickness in cm, which is what downstream code actually needs. `refine_mamad_walls` (added 2026-04-14 as Wave A Fix 2) is a follow-on to strip false mamad tags when no mamad room exists.

**Known issue after Wave A Fix 2.** The refinement is now **too aggressive** — endpoint-on-ring matching tolerance (≤8pt) is smaller than the morphological closing offset in the room polygon (60cm ≈ 34pt at 1:50), so real mamad walls fail the check. Across all 10 samples the current scorecard shows **0 mamad walls classified even when the mamad room is detected**. This is a bug introduced during the final session, not a deep design flaw.

**What should change in v2.**
- Keep the algorithm and parameters.
- Fix the ring-matching bug properly: match mamad walls against the **pre-closed wall mass** or against the original parallel-pair source segments, not the closed-and-offset room polygon.
- Add a single-line fallback for unpaired thick segments (the `ENABLE_SINGLE_LINE_FALLBACK` flag is currently hardcoded False).

**Recommendation:** Keep this file almost as-is.

### 2.6 Negative-space room detection — `services/room_detection.py` (722 LOC)

**Approach.** Envelope = concave hull of wall endpoints, buffered outward. Wall mass = union of centerlines buffered to their measured thickness, then morphological closing (dilate 60cm, erode 60cm) to seal door gaps. Room polygons = `envelope.difference(wall_mass)`, filtered by area and perimeter-hugging test.

**Did it work?** **This is v1's best technical decision.** It cleanly sidesteps the entire planar-graph fragmentation disaster. On Samples 0 and 6 — which legacy room detection gave up on — the new pipeline produces non-zero rooms (Sample 0: 9 rooms, Sample 6: 8 rooms).

**Known issues.**
- Room count is **correct-ish but over-segments balconies and bathrooms** into multiple tiny polygons (see the `guest_toilet` multiplicity across all samples in the scorecard).
- **Text-label-to-polygon allocation is fragile** when the apartment's "real" salon polygon is split into two halves; the label falls into the smaller half (Sample 9 page 1: 7.9 sqm "salon" with size warning).
- **Morphological closing radius is a single global constant** (60cm). Door gaps sometimes need 90cm+; narrow partitions sometimes fuse when closing is too aggressive.

**What should change in v2.**
- Replace the single closing radius with **adaptive closing per wall segment** based on actual gaps detected.
- Add a **polygon-merge step** that reunites rooms split by a short false-positive wall or by a through-corridor.
- Move the fixture-and-text classification into a separate module that `room_detection` calls — currently inlined.

**Recommendation:** Keep, refactor classification out, add a polygon-repair stage.

### 2.7 Opening detection — `services/opening_detection.py` (453 LOC)

**Approach.** Per the docstring and CLAUDE.md: "find gaps in parallel-line wall pairs." Per the code: **it's a wrapper around the legacy `detect_doors_and_windows` in `geometry/structural.py`**. The spec'd gap-based approach was attempted and dropped because "short-segment clusters fire on furniture edges and produce hundreds of false doors per sample."

**Did it work?** Variably. Windows are OK when the exterior-wall proximity filter catches (Sample 9: 63 → 10 windows). Doors are wildly unstable: Sample 0 detects 29 doors (vs ground-truth ~8), Sample 7 detects 0, Sample 9 page 1 detects 15 (vs ground-truth 6). The scorecard column looks like noise.

**What should change in v2.**
- **Go back to arc-based detection** using properly-tagged arcs from extraction. The Sprint 3 note "arc_segments not passed from extraction pipeline" is the real blocker. Fix it at the source.
- Short-segment clustering is the wrong primary signal; furniture outlines defeat it. Use it only as a secondary confirmation.
- Build a minimum test: if `arc_segments == 0`, raise a warning and refuse to report door counts. Don't silently return noise.

**Recommendation:** Rewrite. This module is the single biggest accuracy blocker in the pipeline.

### 2.8 API wiring — `backend/api/routes.py` (706 LOC)

**Approach.** One endpoint `/analyze`, branching on `USE_NEW_PIPELINE`. Both branches do the same 7-step extraction-and-serialize dance with different middle steps.

**Problems.**
- **Massive duplication** between `_analyze_with_new_pipeline()` (128 LOC) and the legacy branch (157 LOC). Extract + crop + histogram + scale + serialize are written twice.
- Room and wall serialization helpers exist (`_serialize_rooms`, `_serialize_metadata`) but are only called by one branch.
- No transaction semantics. No observability. No structured logging.

**Recommendation:** In v2, there's one pipeline. This file becomes one page.

### 2.9 2D renderer — `frontend/src/canvas/FloorplanViewer.tsx` (1,281 LOC)

**Approach.** Konva.js Stage → Layers → WallSegment + RoomPolygon + DoorShape + WindowShape + labels + measurement tool + sidebar + toolbar + confidence dashboard.

**Did it work?** Yes, functionally. The 2D view is usable. Hover, selection, measurement, layer toggles, confidence badges, Hebrew labels, split-area display — all work.

**Problems.**
- **One file, eleven responsibilities.** Should be 5+ files. The sidebar alone is ~100 LOC of JSX glued into the main component.
- **29 inline styles** across App.tsx + FloorplanViewer.tsx. Should be CSS classes.
- **Wall stroke thickness vs. window symbol visibility** — the exact bug fixed 2026-04-14 as Wave A Fix 5 — is a symptom of the rendering being too tightly coupled to measured wall thickness without a layout-aware override path.

**Recommendation:** Keep the Konva choice (it was right). Split the file. Extract sub-components: `RoomDetailsPanel`, `WallDetailsPanel`, `CanvasToolbar`, `ConfidenceDashboard`.

### 2.10 3D renderer — `frontend/src/three/FloorplanScene.tsx` (882 LOC) + supporting files

**Approach.** React Three Fiber + Three.js. Walls extruded from 2D plan data with opening cut-outs done via **wall splitting** (not CSG). First-person controller with wall-slide collision. Minimap. Mobile touch controls. Camera transition.

**Did it work?** Partially. The Sprint 5B status in CLAUDE.md lists 6 open issues, including "No door openings visible in 3D", "Glass doors are solid walls", "Black walls appearing" (unknown wall type default). The 2D → 3D handoff works cleanly; the visibility bugs are in the 3D-specific rendering, not in the data path.

**Strong parts to preserve.**
- [FirstPersonController.tsx](../frontend/src/three/FirstPersonController.tsx) (390 LOC) — wall-slide collision math is correct.
- [wallMerger.ts](../frontend/src/three/wallMerger.ts) (514 LOC) — collapses double-line walls into single meshes with door-zone filtering.
- [openingUtils.ts](../frontend/src/three/openingUtils.ts) — door/window matching algorithm.
- [coordinateUtils.ts](../frontend/src/three/coordinateUtils.ts) — PDF↔3D transforms, fully unit-tested.

**Weak parts to rewrite.**
- [FloorplanScene.tsx](../frontend/src/three/FloorplanScene.tsx) — 12+ `console.log` statements, 3 large `useMemo` blocks with fragile dep arrays, the wall-splitting logic tightly coupled to the main component.

---

## 3. Code Quality Assessment

### Keep as-is (v2 candidates)

| File | LOC | Why |
|---|---:|---|
| [services/wall_detection.py](../backend/services/wall_detection.py) | 550 | Parallel-pairing centerline extraction is the right algorithm |
| [services/room_detection.py](../backend/services/room_detection.py) | 722 | Negative-space approach is the right algorithm; refactor classification out |
| [geometry/extraction.py](../backend/geometry/extraction.py) | 739 | PyMuPDF wrapper is stable; needs arc tagging and split from legend crop |
| [frontend/src/three/FirstPersonController.tsx](../frontend/src/three/FirstPersonController.tsx) | 390 | Collision math is sound |
| [frontend/src/three/wallMerger.ts](../frontend/src/three/wallMerger.ts) | 514 | Correct, just needs `console.log` cleanup |
| [frontend/src/three/openingUtils.ts](../frontend/src/three/openingUtils.ts) | 323 | Pure utility, well-scoped |
| [frontend/src/three/coordinateUtils.ts](../frontend/src/three/coordinateUtils.ts) | 100 | Unit-tested transforms |
| [frontend/src/types/floorplan.ts](../frontend/src/types/floorplan.ts) | 158 | Well-typed domain model, discriminated unions, zero `any` |
| [frontend/src/three/Minimap.tsx](../frontend/src/three/Minimap.tsx) | 267 | Focused, self-contained |
| [frontend/src/three/MobileControls.tsx](../frontend/src/three/MobileControls.tsx) | 272 | Clean touch abstraction |

### Rewrite

| File | LOC | Why |
|---|---:|---|
| [geometry/structural.py](../backend/geometry/structural.py) | 901 | 193-LOC door/window function, brittle mamad heuristics, 10 undocumented magic constants |
| [services/opening_detection.py](../backend/services/opening_detection.py) | 453 | Thin wrapper around legacy; spec'd gap detection never delivered |
| [api/routes.py](../backend/api/routes.py) | 706 | Massive legacy/new duplication; needs to become one pipeline |
| [frontend/src/App.tsx](../frontend/src/App.tsx) | 219 | Hardcoded `http://localhost:8000`, 22 `useState`, prop-drilling, mixed concerns |
| [frontend/src/canvas/FloorplanViewer.tsx](../frontend/src/canvas/FloorplanViewer.tsx) | 1,281 | Eleven responsibilities in one file |
| [frontend/src/three/FloorplanScene.tsx](../frontend/src/three/FloorplanScene.tsx) | 882 | `console.log` spam, fragile memoization, coupling |

### Discard

| File | LOC | Why |
|---|---:|---|
| [geometry/healing.py](../backend/geometry/healing.py) | 1,277 | New pipeline doesn't need any of it |
| [geometry/rooms.py](../backend/geometry/rooms.py) | 642 | Superseded by `services/room_detection.py`; planar-face approach fails on real PDFs |
| [geometry/graph.py](../backend/geometry/graph.py) | 142 | Only consumer is `geometry/rooms.py` |
| [docs/plan/*.docx](../docs/plan) | — | CLAUDE.md says "never read by Claude" — delete or move outside repo |
| [frontend/src/canvas/DebugViewer.tsx](../frontend/src/canvas/DebugViewer.tsx) | 628 | Useful for debugging v1 — but it fetches independently from `http://localhost:8000/api/extract`, not wired to App state |

### Duplication between legacy and new

Logic that exists in **two places**, must be consolidated in v2:

1. **Room classification heuristics** (text label → type, fixture → type, area → type). Lives in both `geometry/rooms.py:_classify_by_*` and `services/room_detection.py:_classify_one`. In v1 they have drifted (new pipeline added a "largest interior ≥ 18sqm = salon" rule that legacy doesn't have).
2. **Room size / area enforcement** (the fix I added on 2026-04-14). Lives in both `geometry/rooms.py:_enforce_size_ranges` and `services/room_detection.py:_enforce_size_ranges`. Identical logic, two files.
3. **Mamad single-instance enforcement**. Same pattern.
4. **Extraction/crop/histogram/serialize** code paths in `routes.py`, written twice.

A maintenance crew would let these diverge under pressure within a month.

### Magic constants without rationale

Grep of `geometry/structural.py:39-48`:

```python
EXTERIOR_DISTANCE_TOLERANCE = 3.0
MAMAD_AREA_MIN = 7.0
MAMAD_AREA_MAX = 15.0
MAMAD_THICKNESS_RATIO = 0.8
STRUCTURAL_THICKNESS_RATIO = 2.5
STRUCTURAL_PERCENTILE = 95
DOOR_WIDTH_MIN_CM = 65.0
DOOR_WIDTH_MAX_CM = 95.0
WINDOW_WIDTH_MIN_CM = 80.0
WINDOW_WIDTH_MAX_CM = 200.0
ARC_PROXIMITY_TOLERANCE = 15.0
```

None of these have a reference to a spec or a measurement. They are the calcified residue of earlier sprints. The door-width range of 65-95cm matches Israeli door standards, but the other nine have no documented provenance. In v2, every constant must carry a 1-line comment with its source.

---

## 4. Agent System Assessment

The project has 10 agent persona files in [agents/](../agents/). CLAUDE.md routes tasks to them as a validation chain. Here is the honest audit of how much each one actually contributed.

| Agent | LOC | Knowledge deps | Code/commit fingerprints | Verdict |
|---|---:|---:|---|---|
| **VG** (Vector Geometry) | 20 | 5 active | `Agent: VG` in 5-6 backend modules, 2 doc commits | **Useful** — the only agent that drove actual geometry design |
| **3D** (WebGL) | 16 | 3 active | 20+ commits tagged `feat(3d)` / `fix(3d)` | **Useful** — Sprint 5A/5B were all 3D work |
| **FS** (Full-Stack) | 18 | 5 (3 active) | 1 commit, 69 Hebrew refs | **Partial** — frontend-heavy, unclear backend scope |
| **UX** (UX/UI) | 17 | 4 (3 active) | 1 commit, overlaps FS | **Partial** — design intent stated, enforcement sparse |
| **ARC** (Architect) | 20 | 5 (3 active) | CLAUDE.md "ARC Verdict" blocks only; 0 code refs | **Ceremonial** — manual review dressed up as an agent |
| **SE** (Structural Engineer) | 14 | 2 | 0 code refs — logic merged into VG with wrong byline | **Redundant** — collapsed into VG |
| **GIS** (Mapping) | 13 | 2 | 0 code refs, 0 commits | **Dead** — feature never started |
| **AI** (ML) | 16 | 4 | 0 code refs — Claude Vision / cost estimation unbuilt | **Dead** — aspirational |
| **PT** (Proptech) | 15 | 3 | 0 code refs, 0 commits | **Dead** — Phase 4 territory |
| **ID** (Interior Design) | 19 | 5 (2 active) | 0 code refs, 1 stubbed type field | **Dead** — furniture system never built |

**10 → 2 useful**. Four agents (GIS, AI, PT, ID) are speculative placeholders with zero fingerprints. ARC and SE are ceremonial — they describe review processes that a human performed manually. FS and UX overlap and neither is precisely scoped.

**V2 should drop the agent system.** At this codebase size, specialized personas add ceremony without adding accountability. A single "senior developer" persona with Plan-Execute-Verify and explicit domain knowledge imported per task would accomplish more with less drift. If you really want specialization, **three** agents is enough:

1. **GEO** — everything backend geometry/extraction/classification
2. **WEB** — everything frontend (2D + 3D, state, i18n)
3. **ARC** — a single review pass per PR, with a published checklist

Anything more is theater.

---

## 5. Knowledge Base Assessment

The knowledge base is 25 files totaling ~5,000 LOC. Per the audit:

- **17 files AUTHORITATIVE** — accurate and referenced by code
- **2 files SUSPECT** — contain numerically wrong data
- **4 files SPECULATIVE** — prose without verified facts
- **2 files NEVER_REFERENCED** — zero grep hits

### The two wrong files

**[docs/knowledge/pdf-vector-spec.md:31](../docs/knowledge/pdf-vector-spec.md)** claims "Mamad walls: typically 3.0–5.0 pt (THICKEST)". CLAUDE.md discovered empirically that real Israeli PDFs have **0.1–1.1 pt** strokes. This single wrong table drove the entire Sprint 1-2 thread of "why don't our wall thresholds work?"

**[docs/knowledge/israeli-plan-conventions.md](../docs/knowledge/israeli-plan-conventions.md)** is internally contradictory: its prose says 0.1-1.1pt (correct) and its table says 3.0-5.0pt (wrong). The table was the one copied into code.

### Missing knowledge (facts we learned at runtime)

A v2 knowledge base must include:

1. **PyMuPDF RTL bug** — Hebrew text gets character-order-reversed by the extraction library. Room labels like `ממ"ד` appear as `ד" ממ`. Every text matcher must check both the direct and reversed form. (Discovered mid-Sprint 3.)
2. **Vector-drawn labels** — Many Israeli contractor PDFs render room labels as Bézier path outlines, not searchable text. `get_text()` returns 0 for these files. A PDF must be probed at the start and routed to a different classification path if it has vector-only labels. (Sample 0.)
3. **Bézier → arc tagging** — PyMuPDF returns Bézier curves; doors are conventionally drawn as 90° arcs. If you flatten Béziers to polylines without tagging the original curve operator, door detection has no signal. (Blocked door detection from Sprint 3 onwards.)
4. **Dense graph fragmentation** — PDFs with >10,000 raw segments produce "mesh" topologies after `split_at_intersections`. The ceiling of the planar-graph approach. (Samples 0, 1, 6.)
5. **Mamad-vs-text conflict rules** — When the mamad detector says "this 95% confidence room is mamad" and the text label says "95% confidence bedroom", the bedroom wins. We discovered this only after wrong-classifying a Sample 9 bedroom as mamad.
6. **Scale auto-detection fallback** — When the PDF has no "1:50"/"1:100" text, there is currently no fallback. Sample 2 shows 1,228 sqm because of this (a 4-room apartment).
7. **Morphological closing radius is sample-dependent** — 60cm works on Sample 9, over-fuses on narrower partitions in other samples.

### Most useful 3 files

1. **structural-rules.md** — the only file that correctly advocated relative histogram clustering vs absolute thresholds.
2. **healing-algorithms.md** — blueprint of the snap/merge/extend/split pipeline with parameter values.
3. **room-classification-rules.md** — 10 canonical room types and area ranges, precisely matched by `models.py:AREA_HEURISTICS`.

### Most misleading 3 files

1. **pdf-vector-spec.md** (line 31 stroke-width table) — caused weeks of wall-classifier churn.
2. **israeli-plan-conventions.md** (internally contradictory table vs prose).
3. **threejs-archviz-patterns.md** — shows first-person controller and CSG openings as if they were implemented; they aren't.

---

## 6. Pipeline Performance — Final Scorecard

Run on all 10 samples with `USE_NEW_PIPELINE=true`, no envelope filter flag, current code (2026-04-14).

```
Sample   raw    cl  ext  par  mam  rooms  text  warn  doors  win  mamad  intSQM
S0      10234  583  290  291    0      9     0     0     29   12    Y    65.1
S1       3508   52   26   26    0      6     2     2      4    2    N    53.1
S2       7134   73   37   36    0      5     3     1      1    4    Y    53.5
S3       3396   61   32   29    0      6     4     3      1    1    Y    51.1
S4      10197  257  129  128    0     14    11     7      3    0    Y   166.1
S5       3781  126   64   62    0      6     0     0      3    1    Y    40.7
S6       6613   59   30   29    0      8     5     4      2    4    N    47.5
S7       4239   43   22   21    0      9     4     2      0    6    Y    47.4
S9.p0    3741   67   34   33    0      8     2     1      6    4    N    27.8
S9.p1    4802   88   43   44    0      8     4     3     15    6    N    57.0
```

`cl` = centerline walls found. `ext/par/mam` = walls classified exterior/partition/mamad. `rooms` = detected rooms. `text` = rooms matched by text label. `warn` = rooms carrying a size-range warning. `mamad` = mamad room detected Y/N.

### Per-sample analysis

| Sample | GT rooms | Detected | Accuracy | Root cause of weakness |
|---|---:|---:|---|---|
| S0 | 6 (Type D) | 9 | ~50% recall / poor precision | Extra salons from split polygons; 29 doors = over-detection runaway |
| S1 | ~4 | 6 | Unknown | Was "0 rooms" on legacy; negative-space fixed this but no labels matched (mamad=N) |
| S2 | 9 | 5 | 56% recall, poor types | Dense graph + large polygons merged; 1 door (GT 9) — door detector dead |
| S3 | ~2 | 6 | Over-detection | 3 bathrooms detected; tiny polygons from over-closing |
| S4 | ~4 | 14 | Over-detection 3.5× | Page is large; too many closed regions became "rooms" |
| S5 | ~7 | 6 | OK-ish | One missing room vs ground truth; 3 guest_toilets is classification fallback |
| S6 | 0 on legacy, 8 now | 8 | Improved | But no mamad, no text labels matched |
| S7 | 3 | 9 | Over-detection 3× | Sample 7/8 duplicate kartisiyyah inflates polygons |
| S9.p0 | 6 (upper floor) | 8 | ~80% recall | Mamad not detected (N) even though GT says present |
| S9.p1 | 8 (lower floor) | 8 | Perfect count, wrong types | Salon split into 2 polygons; 4 guest_toilets are balcony/utility artifacts |

### Per-category weakness analysis

**Rooms detected (count only).** 7/10 samples have non-zero rooms, which is an improvement over legacy's 7/10 — but many are over-segmented. Over-detection is now more common than under-detection. **Root cause:** global morphological closing radius + no polygon merge pass.

**Room types.** On Sample 9 page 1 (best case, 8/8 rooms) only 4 are text-matched; the other 4 are area-heuristic guesses. Most samples never get a kitchen, utility, or service_balcony detected correctly. **Root cause:** fixture-based classification was scoped but not implemented. Text matching works when labels are real text; area heuristics are a coin flip.

**Walls.** Partition/exterior classification works. **Mamad walls = 0 across every sample** is a Wave A regression (my Fix 2 is too aggressive). Should be fixed in v2 by matching against original wall-pair centerlines rather than the closed-and-offset room polygon.

**Doors.** Wildly unstable: 0 (S7), 1 (S2, S3), 2 (S6), 3 (S4, S5), 4 (S1), 6 (S9.p0), 15 (S9.p1), 29 (S0). No sample produces a stable door count. **Root cause:** `detect_openings_from_gaps` is a wrapper around abandoned legacy logic. The spec'd arc-based approach was never delivered because arc_segments aren't tagged at extraction time.

**Windows.** Mostly 0-6 per sample. Better than doors. The exterior-wall proximity filter works; the min-length and dedup filters reduced Sample 9 from 63 → 10 (GT 10). **Root cause:** same as doors — parallel-line heuristic fires on furniture when not constrained.

**Area.** Sample 4 shows 166 sqm total; most samples are 27-65 sqm. Sample 2 showed 1228 sqm on an earlier run — that kind of outlier means the scale factor wasn't detected and defaulted wrong. **Root cause:** no scale-detection fallback.

**Mamad rooms.** 6/10 samples detect a mamad room. Sample 9 page 1 — which definitely has a mamad in the ground truth — currently shows **no mamad room**. This is a regression vs CLAUDE.md's Phase 1 completion notes where Sample 9 was the best result. Something in the Quality Sprint cutover broke Sample 9's mamad detection.

### Theoretical ceiling of the current architecture

**Realistic:** 60-70% rooms correct, 50-60% types correct, 30-40% doors correct.

**To reach 80% without rewriting the core**, you would need:
1. Arc tagging at extraction time (unlocks door detection).
2. A polygon-merge pass after room detection (unlocks Sample 9's split salon).
3. An adaptive morphological closing radius (unlocks Sample 4's over-detection).
4. Fixture detection via vector-symbol recognition (unlocks type accuracy).
5. A fallback scale detector (unlocks area accuracy).
6. A working mamad-wall refinement (trivial).

These are all real engineering tasks totalling 4-6 sprint-weeks. The architecture can support them — this is not a "start over from scratch" situation at the algorithm layer. The code-organization reasons for restarting are separate (too many dead files, duplicate pipelines, over-engineered healing, 10-agent theater).

---

## 7. What Worked Well

Every technique below produced demonstrable value and should be preserved:

1. **Negative-space room detection** (`services/room_detection.py`). Sidesteps the planar-graph fragmentation problem that killed legacy. Best single decision in the project.
2. **Parallel-line centerline wall extraction** (`services/wall_detection.py`). Replaces broken absolute stroke-width classification with measured thickness in cm. Gives downstream code real data.
3. **Histogram-based stroke width clustering** (`geometry/extraction.py:compute_stroke_histogram`). The first thing that made wall filtering relative and sample-independent.
4. **Hebrew RTL implementation** with react-intl + Heebo font + `dir="rtl"` CSS. 69 Hebrew references across the frontend, no bugs found in the audit.
5. **TypeScript discriminated-union domain model** (`frontend/src/types/floorplan.ts`). Zero `any` usage across 5,952 LOC of frontend. Exhaustiveness checking on wall types and room types works.
6. **Ground-truth JSON fixtures** with tolerances (`backend/tests/fixtures/sample_9_ground_truth.json`). The regression guards based on these caught the Sprint 5B window over-detection (63 → 10). This pattern is worth generalizing to all 10 samples in v2.
7. **PDF-to-cm transform pipeline** in the 3D coordinate utils. Tested, stable, no bugs.
8. **Wall-splitting opening rendering in 3D** (instead of CSG hole-cutting). CSG was tried, was slow and buggy; wall-splitting is simpler and faster.
9. **Reconnect-components healing step** (`filter_largest_component`). On the legacy path it was the difference between 0 rooms and 7 rooms on Samples 2, 3, 4, 5.
10. **Scale detection from PDF text** (`geometry/extraction.py:extract_metadata`). Works when the PDF has extractable "1:50" text; falls back cleanly when it doesn't.

---

## 8. What Failed

Each entry is: assumption → what actually happened → what to do instead.

1. **Absolute stroke-width thresholds for wall classification.**
   - Assumption: mamad walls are 3-5pt, exterior are 2-3pt, partition are ≤2pt (from `pdf-vector-spec.md`).
   - Reality: real Israeli PDFs have 0.1-1.1pt strokes across all wall types. The absolute thresholds rejected everything as "not a wall".
   - Replacement: histogram-based relative ranking (delivered, working).

2. **Planar-graph face enumeration for room detection.**
   - Assumption: healed walls form a planar graph; enumerating minimal faces gives room polygons.
   - Reality: `split_at_intersections` inflates segment count (10K → 17K on Sample 0), creating a mesh topology where "rooms" become tiny 2000pt² faces instead of the 38,564pt² real rooms.
   - Replacement: negative-space extraction from the wall mass (delivered, working).

3. **CSG hole-cutting for 3D openings.**
   - Assumption: `three-csg-ts` can cleanly subtract door/window volumes from walls.
   - Reality: slow, buggy, NaN vertices on edge cases, visible seams.
   - Replacement: wall-splitting — divide each wall into [solid | lintel | opening | solid] pieces (delivered, working).

4. **Automatic legend/kartisiyyah cropping.**
   - Assumption: spatial density clustering cleanly separates apartment from legend.
   - Reality: Works on 3/10 PDFs, partial on 3/10, fully fails on 3/10. A research problem masquerading as a preprocessing step.
   - Replacement: user-confirmed bbox crop. Show detected boundary, let user drag-to-correct, never run expensive stages on unconfirmed input.

5. **Arc-based door detection from short-segment clusters.**
   - Assumption: doors have distinctive arc signatures; flattened Bézier curves become short collinear fragments that can be clustered.
   - Reality: furniture (cabinet edges, bath fixtures, stove outlines) produces the same short-segment pattern and the detector returns hundreds of false doors.
   - Replacement: tag original Bézier curve operators as arcs at extraction time. Use the tag as a hard filter.

6. **Mamad detection by wall thickness alone.**
   - Assumption: the room with the thickest walls is the mamad.
   - Reality: sometimes the exterior wall is the thickest. The mamad-by-thickness vs text-label-says-bedroom conflict happened on real PDFs.
   - Replacement: text label wins; mamad-by-thickness is only used when no text mamad exists (delivered in `classify_rooms_negative_space`).

7. **Hardcoded parameters for window/door detection.**
   - Assumption: width 65-95cm = door, 80-200cm = window, and that will work universally.
   - Reality: parallel-line detection fires on furniture outlines regardless of width. The width filter only helps after you've already found a "wall gap". On Sample 9, it took 4 cumulative filters (exterior proximity + min length + spatial dedup + width) to reduce windows from 63 → 10.
   - Replacement: arc tags for doors, exterior-proximity for windows, everything else is cosmetic.

8. **Envelope filter by largest-connected-component** (Wave B, 2026-04-14).
   - Assumption: the apartment is the largest connected graph component of walls; stairwells/ghost outlines are smaller components.
   - Reality: at 25cm connectivity tolerance the stairwell fuses with the apartment; at 15cm the apartment fragments into sub-components and the filter deletes the salon. No tolerance works.
   - Replacement: find the dominant **closed outer loop** of exterior walls and keep everything inside it. Geometric, not topological.

9. **10 specialized agents validating each other.**
   - Assumption: a persona chain (VG → ARC → SE) produces higher-quality output than a single developer.
   - Reality: only VG and 3D left measurable fingerprints; the rest are prose. ARC validation happened as CLAUDE.md paragraphs written by a human, not as an enforced pass.
   - Replacement: at most 3 agents in v2, or none.

10. **Planning .docx files as reference material.**
    - Assumption: the 5 planning .docx files in `docs/plan/` are a valuable spec.
    - Reality: CLAUDE.md says "never read by Claude, human reference only". They are dead weight in the repo — 5 files the code-generating agent cannot access.
    - Replacement: markdown in the repo, readable by both humans and agents.

---

## 9. Frontend / UX Assessment

### 2D Konva renderer

**Keep Konva.** It was the right choice for this job. The alternative (SVG or raw Canvas) either doesn't scale or lacks the hit-detection and layering primitives we used. The performance story is fine — Konva batches redraws and the profile shows no hot spots in the current ~100-wall renderings.

**Split FloorplanViewer.tsx.** 1,281 LOC in one file is the single biggest code-quality signal in the frontend. Target structure for v2:
```
frontend/src/canvas/
├── FloorplanViewer.tsx     (≤300 LOC — just the Stage + layer wiring)
├── WallLayer.tsx            (walls + hit detection)
├── RoomLayer.tsx            (polygons + labels)
├── OpeningLayer.tsx         (doors + windows)
├── MeasurementLayer.tsx     (ruler tool)
├── FloorplanToolbar.tsx
├── FloorplanSidebar.tsx     (room/wall details)
└── ConfidenceDashboard.tsx
```

### 3D react-three-fiber renderer

**Keep R3F.** Same reasoning as Konva. For architectural visualization in React, R3F is the default and it's well-supported.

**Clean up FloorplanScene.tsx.** Remove `console.log` calls (12+), split wall-splitting into its own pure utility, fix the dep arrays on the three large `useMemo` blocks.

**Keep** the first-person controller, wall merger, opening utils, coordinate utils, minimap, mobile controls. These are the strongest frontend files.

### Hebrew RTL

Working but partial. `direction: rtl` is set, react-intl is wired, Heebo is loaded, and a 140-key `he.json` exists. **What's missing:** CSS logical properties (`margin-inline-start` etc.) are used in one place only (App.tsx:151); everywhere else uses `margin-left`/`padding-right` which will break if an English variant is ever added. For a Hebrew-only product this is fine; for a bilingual product v2 should migrate to logical properties at the start.

### State management

There is none. 22 `useState` calls in App.tsx plus prop drilling through `FloorplanViewer → Sidebar`. DebugViewer fetches `http://localhost:8000/api/extract` directly, independent of App state — this means uploading a PDF in viewer mode doesn't share it with debug mode.

**V2 should pick Zustand or React Context** from day one. Prop drilling past two levels is a red flag; this codebase has three levels in multiple spots.

### TypeScript

Excellent — **zero `any`** across 5,952 LOC, discriminated unions for selection targets, typed props throughout. This is the single strongest code-quality signal anywhere in the project. Keep doing this.

### Anti-patterns to fix

| Anti-pattern | Evidence | Fix in v2 |
|---|---|---|
| Hardcoded `http://localhost:8000` | [App.tsx:33](../frontend/src/App.tsx#L33), [DebugViewer.tsx:23](../frontend/src/canvas/DebugViewer.tsx#L23) | `env.ts` with `VITE_API_URL` |
| Inline styles | 29 occurrences across App.tsx + FloorplanViewer.tsx | CSS modules or styled components |
| `console.log` spam | 12+ in FloorplanScene.tsx, 7+ in wallMerger.ts | Remove, or guard with `import.meta.env.DEV` |
| No error boundaries | Zero `ErrorBoundary` components | Wrap Canvas + FloorplanScene |
| Frontend tests | Only 3 smoke tests + one geometry util test | Add integration test: upload PDF → render 2D → switch to 3D |

---

## 10. Testing & Process Assessment

### Plan-Execute-Verify

**Worked** for human→Claude interactions (CLAUDE.md mandates "WAIT for approval" and I complied). The feedback memory captures this: "Always plan before executing."

**Didn't scale** to the agent chain. ARC validation happened as CLAUDE.md paragraphs, not as an enforced pass. The plan-approval loop that worked at the top level didn't propagate into subtask delegation.

**Worked well:** I was forced to present the Wave A plan before touching code, which caught at least one scope decision (text-matched salon demotion vs. warning) before it became a bug.

### Ground-truth scorecard

**Worked** when applied regressively (the Sample 9 window dedup test caught the 63 → 10 regression). The JSON-fixture-with-tolerances pattern is worth generalizing.

**Didn't work** when treated as a gate. The test suite does not block PRs and does not run on CI. The scorecard was computed manually at the end of each sprint. This meant:
- Silent accuracy regressions. My Wave A Fix 2 (mamad walls) broke Sample 9 page 1's mamad-wall count from non-zero to 0. No test caught this.
- No historical tracking. There's no `scorecard.csv` with dated runs, so we can't see accuracy-over-time.

**V2 should:** make the scorecard a CI step. Run it on every PR against all 10 samples. Fail if any per-sample accuracy regresses by more than a tunable delta (default 10%). Store results in a checked-in `scorecard_history.jsonl`.

### Sprint prompts

Inspecting commit messages: sprints are named but ambiguously scoped. "Sprint 3 room detection" covers detection + classification + structural + doors. "Sprint 5B" covers 3D integration + opening matching + wall merging. The prompts were too large and let individual "fixes" sneak in non-sprint work.

**V2 should:** cap each sprint at ~5 commits of related work. If you can't describe the goal in one sentence, it's two sprints.

### Communication that worked

- **Specific before-and-after metrics.** "Sample 9 windows 63 → 10" is a clearer report than "fixed window over-detection."
- **Scorecard tables.** Rows per sample, columns per metric — an instant mental model of accuracy.
- **Hebrew warning strings baked into the model.** Structured and user-visible, not just logged.

### Communication that didn't

- **"Sprint 5B complete"** without a scorecard was misleading — the 3D integration was complete but 6 blocking issues were still listed in CLAUDE.md.
- **"ARC Verdict" prose blocks** in CLAUDE.md read like accountability but are just the author's self-review.
- **Docx planning files** hidden from the agent (`docs/plan/*.docx`) broke the feedback loop.

### Biggest time sinks

1. **Healing pipeline iteration.** Five passes, 1,277 LOC, 639 LOC of tests, weeks of work, and then negative-space detection made it optional.
2. **Two full pipelines in parallel** without a cutover date.
3. **Chasing door detection** through three approaches (stroke gaps, arc clusters, dangle endpoints) without ever solving the upstream problem (arc tagging in extraction).
4. **Legend cropping** — same story. Solved for 3/10 samples, open for 3/10, deferred indefinitely.

---

## 11. Recommendations for v2

### Architecture

**One pipeline.** No `USE_NEW_PIPELINE` flag. No `geometry/` vs `services/` split. Pick the new approach and delete the old.

**Pipeline order:**
```
1. PDF probe        (scale? has real text? vector-only labels? stroke histogram)
2. User confirm     (apartment bbox drag-to-correct, mandatory)
3. Extract          (segments + tagged arcs + text)
4. Wall detect      (parallel-line centerline pairing, measured thickness)
5. Room detect      (envelope minus wall mass, adaptive closing, polygon repair)
6. Openings         (arc tags → doors; exterior-proximity → windows)
7. Classify rooms   (text > fixture > size; size validator flags conflicts)
8. Serialize
```

Each step is a pure function. Each step has its own unit tests with real PDFs in ground truth. No global state. No feature flags.

### The first sprint

**Goal:** Minimum viable backend that hits 80% on 3 reference PDFs (Sample 9 p1, Sample 5, Sample 2) before any UI work.

**Tasks:**
1. Extraction with arc tagging.
2. Parallel-line wall detection (copy from v1, it works).
3. Negative-space room detection with polygon repair (copy from v1 + fix the over-segmentation).
4. Arc-based door detection (new).
5. Scorecard harness running in CI with `scorecard_history.jsonl`.
6. No frontend. No UI. Not even the debug viewer.

Ship this in 2-3 weeks. Only start the UI after the scorecard is ≥80% on the 3 reference PDFs.

### Minimum viable pipeline to test

Before touching any UI, the pipeline must be callable like this:
```python
result = analyze("path/to/sample.pdf", apartment_bbox=(x0, y0, x1, y1))
assert result.rooms_correct >= 0.8
assert result.doors_correct >= 0.6
assert result.mamad_detected is True
```

That's the gate. No `localhost:8000`, no React, no Konva, no i18n — just a function that returns structured data and a scorecard that validates it.

### Top 3 highest-impact changes

1. **Arc tagging in extraction.** Unblocks door detection for the entire project. Currently a single comment in the code says "arc_segments not passed from extraction pipeline" and that one sentence is the #1 accuracy blocker in v1.
2. **User-confirmed apartment bbox.** Removes the entire "legend cropping" sub-project from the critical path and solves the Samples 0/1/6 family of problems.
3. **One pipeline, one classifier, one test harness.** Deletes ~4,000 LOC of dead legacy code. Lets the team hold the entire backend in their head.

### Libraries / algorithms to try that v1 didn't

- **`shapely.ops.unary_union` with adaptive buffer** — v1 uses one global buffer radius; v2 should compute per-wall-segment buffer from detected gap widths.
- **`opencv-python` template matching for fixtures** — v1 never tried raster-domain fixture detection. Rasterize the wall mass, template-match toilet/bathtub/stove symbols. This is how the type accuracy problem actually gets solved.
- **Graph-based polygon repair via `networkx`** — v1 uses shapely.polygonize which is all-or-nothing. A graph approach can merge adjacent polygons whose shared wall is short / low-confidence.
- **`scipy.spatial.ConvexHull` with pruning** — v1 uses `shapely.concave_hull(ratio=0.2)` which is a single-parameter knob. Pruning-based outer-loop detection gives better stairwell exclusion.
- **Shapely STRtree for T-junction snapping** — already used in `wall_detection.py`, should be used in room detection too (for polygon-repair-by-shared-edge).

### Agent system

**Keep only 3 agents** or drop agents entirely. My recommendation: **drop them**. A single "senior developer" persona with explicit CLAUDE.md knowledge imports per task works better at this codebase size.

If you insist on specialization: **GEO, WEB, ARC.** Three files, three roles, enforced PR-gate review for ARC. Nothing else.

### Knowledge base

**Start from scratch.** The v1 KB has 25 files, 2 with wrong numbers, 6 never referenced. V2 should have ~10 files max, each with a "last verified YYYY-MM-DD against sample X" footer and a grep-check that its facts still appear in code.

Must-have v2 KB files:
1. `pdf-extraction-gotchas.md` — PyMuPDF RTL, vector labels, arc extraction, real stroke widths
2. `wall-detection-algorithm.md` — parallel-line pairing parameters with the provenance of each
3. `room-detection-algorithm.md` — negative-space approach + polygon-repair rules
4. `israeli-room-conventions.md` — 10 valid types + area ranges + mamad rules + text patterns (including RTL-reversed forms)
5. `openings-algorithm.md` — arc tagging + hosting + width filters
6. `hebrew-rtl-frontend.md` — react-intl + logical CSS + Heebo font setup (keep from v1)
7. `test-pdf-inventory.md` — 10 samples with per-sample known-gotchas

### Timeline to 80% accuracy

Realistic estimate for v2 to reach 80% room-correct on a 10-PDF test set, given v1's lessons:

- **Weeks 1-2:** Scaffold single-pipeline backend. Arc tagging. Scorecard CI. No UI.
- **Weeks 3-4:** Negative-space rooms + polygon repair. Adaptive closing radius. Text+fixture classification.
- **Weeks 5-6:** Arc-based doors. Windows via exterior proximity. Mamad wall refinement (fixed version).
- **Weeks 7-8:** Scorecard tuning + edge cases on Samples 0, 1, 6. User-confirmed bbox flow.
- **Weeks 9-12:** UI (2D only, no 3D). Upload → render → sidebar. Hebrew RTL.

**Total: 8-12 weeks to 80%**, assuming the v1 architectural wins are carried over intact and the v1 dead code is deleted in Week 1.

3D viewer adds 2-3 more weeks, but is not on the critical path to accuracy.

---

## 12. The Short Version

- **The accuracy problem is real but tractable.** Negative-space room detection and parallel-line wall detection were right. Arc tagging, user-confirmed bbox, and fixture detection will close the gap to 80%.
- **The code-organization problem is worse than the accuracy problem.** Two pipelines, 4,000 LOC of dead legacy, 10 ceremonial agents, 5 docx files the AI can't read, and a 1,277-LOC healing module that the new pipeline doesn't need — none of this belongs in v2.
- **The frontend is in better shape than the backend.** TypeScript discipline, Konva choice, R3F choice, coordinate utils, first-person controller — all keepers.
- **V2 is not a rewrite of the algorithms.** It's a deletion pass on the scaffolding followed by a focused sprint on the 3-4 real bottlenecks.

If the team keeps v1's good decisions and has the discipline to delete the bad ones in Week 1, v2 should reach 80% accuracy in 8-12 weeks and ship with ~60% of v1's LOC.

---

*End of postmortem. For questions or challenges to the findings: see commit log and scorecard JSON in `/tmp/scorecard.json`.*
