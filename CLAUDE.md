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

## Architecture Decisions
- Monorepo: project root is the repo root (backend/, frontend/, agents/, docs/)
- 10 AI agent personas in /agents/*.md — each declares knowledge file dependencies
- 25 knowledge base files in /docs/knowledge/ — living reference docs agents load before work
- Planning docs in /docs/plan/*.docx — human reference only, never read by Claude
- CLAUDE.md at repo root — Claude Code reads it automatically
- Local Python is 3.9.6 — will need Docker or pyenv for Python 3.12 requirement

## Known Edge Cases
- Real PDFs max stroke width 0.72–2.76pt — no sample reaches mamad range (3.0–5.0pt). Wall classification must use relative histogram thresholds, not absolute ranges.
- crop_legend ineffective when thick segments span full page (Samples 5, 9). Needs fallback strategy (spatial clustering or legend border detection) in future sprint.

## Test PDF Inventory
(track: file, source, rooms, issues, status)
