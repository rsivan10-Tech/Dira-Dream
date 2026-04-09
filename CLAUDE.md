# DiraDream — AI Apartment Planning (Hebrew RTL)

## Stack
Backend: Python 3.12+FastAPI | Frontend: React 18+TS+Vite | 2D: Konva.js
3D: Three.js+R3F | PDF: PyMuPDF | Geometry: Shapely+SciPy+NetworkX
AI: Claude Opus 4.6 | DB: PostgreSQL+PostGIS | Auth: Supabase

## Current Phase
Phase: 1 | Sprint: 1 | Module: pdf-extraction | Branch: feature/phase1-pdf-extraction

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
- [2026-04-09] crop_legend replaced with density-grid spatial clustering (adaptive threshold + morphological closing). Works on most PDFs. Samples 7/8 still unseparable (apartment and legend merge in density grid). Status: mostly resolved, Sprint 4 may add user-assisted crop fallback.
- [2026-04-09] Samples 7 and 8 are identical files. Use only one for testing.
- [2026-04-09] Sample 0 has 15,936 segments — confirmed single apartment (Type D, 6 rooms) with large kartisiyyah.
- [2026-04-09] Sample 5 is 2 pages (two 4-room variants). Split into Sample 5.0 and 5.1 locally (not in git — PDFs are gitignored).

## Test PDF Inventory
| # | File | Segments | Texts | Width Range | Peaks | Crop % | Status |
|---|------|----------|-------|-------------|-------|--------|--------|
| 0 | MCH-208-Floors-Type D 1-50 | 15,936 | 212 | 0.10–0.72 | 4 | 35.8% | Pass — crops top+right kartisiyyah. Room labels are vector-drawn (0 extractable texts in apt area) |
| 1 | דירה-2-תוכנית | 3,846 | 168 | 0.10–2.16 | 5 | 8.8% | Pass — density-grid now crops legend (was 0% with old approach) |
| 2 | תכניות-מכר-דירתי | 7,134 | 185 | 0.10–1.70 | 7 | 0.0% | Pass — no separation needed (multi-page, page 0) |
| 3 | בניין-2-דירות | 3,406 | 351 | 0.10–1.12 | 5 | 0.3% | Pass — apartment fills page |
| 4 | לאטי-קדימה | 10,203 | 1,140 | 0.10–1.15 | 7 | 0.1% | Pass — 67 pages, page 0 |
| 5.0 | 4-Rooms-Newer2 (page 0) | 3,781 | 44 | 0.10–1.10 | 8 | 0.0% | Pass — split from 2-page PDF |
| 5.1 | 4-Rooms-Newer2 (page 1) | 3,988 | 46 | 0.10–1.10 | 8 | 6.9% | Pass — split from 2-page PDF |
| 6 | build9-J-plan | 7,887 | 123 | 0.10–2.76 | 8 | 16.2% | Pass — density-grid crops legend (was 11%) |
| 7 | build12-A-plan (1) | 4,239 | 492 | 0.10–1.71 | 9 | 0.0% | Pass — no separation possible, duplicate of 8 |
| 8 | build12-A-plan | 4,239 | 492 | 0.10–1.71 | 9 | 0.0% | Pass — no separation possible, duplicate of 7 |
| 9 | vector sample | 4,673 | 212 | 0.10–1.64 | 6 | 19.9% | Pass — density-grid now crops legend (was 0%) |
