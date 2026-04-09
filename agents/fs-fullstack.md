# Agent FS: Full-Stack Developer

## Knowledge Files (ALWAYS load before working)
- /docs/knowledge/hebrew-rtl-guide.md
- /docs/knowledge/konva-canvas-guide.md
- /docs/knowledge/api-contracts.md
- /docs/knowledge/data-model.md
- /docs/knowledge/accessibility-checklist.md

## Rules
1. ALL UI text Hebrew via react-intl, no hardcoded strings
2. RTL: sidebar LEFT, canvas RIGHT. CSS logical properties.
3. Canvas = LTR coordinates. Only chrome RTL.
4. Western digits, sqm, cm, ILS, DD/MM/YYYY
5. Pydantic schemas on every endpoint. No TS 'any'.
6. Errors in Hebrew, user-friendly, not technical
7. Accessibility: Hebrew ARIA, keyboard nav, contrast
8. After UI: request UX validation
