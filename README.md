# DiraDream — דירה דרים

AI-powered apartment planning for the Israeli market. Upload a vector PDF floorplan, get interactive 2D/3D visualization with room detection, wall classification, and renovation planning.

## Structure

```
backend/        FastAPI + Python geometry pipeline
frontend/       React 18 + TypeScript + Vite (Hebrew RTL)
agents/         AI agent personas (10 .md files)
docs/knowledge/ Knowledge base for agents (25 .md files)
docs/plan/      Project planning documents
docs/test-pdfs/ Sample Israeli contractor PDFs
```

## Quick Start

```bash
# Backend
cd backend && pip install -r requirements.txt
uvicorn main:app --reload

# Frontend
cd frontend && npm install && npm run dev

# Or via Docker
docker compose up
```

## Stack

Backend: Python 3.12 + FastAPI | Frontend: React 18 + TS + Vite | 2D: Konva.js
3D: Three.js + R3F | PDF: PyMuPDF | Geometry: Shapely + SciPy + NetworkX
AI: Claude Opus 4.6 | DB: PostgreSQL + PostGIS
