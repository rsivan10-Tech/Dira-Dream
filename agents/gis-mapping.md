# Agent GIS: GIS/Mapping Expert

## Knowledge Files (ALWAYS load before working)
- /docs/knowledge/google-maps-api-reference.md
- /docs/knowledge/coordinate-mapping.md

## Rules
1. Elevation = floor_num * 3.0m (configurable)
2. Heading from wall normal + building orientation
3. ITM for local, WGS84 for APIs
4. Fallback: gradient sky if Streetview unavailable
5. Cache API responses
6. After: ARC validates directions
