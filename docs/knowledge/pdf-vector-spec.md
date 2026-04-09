# PDF Vector Specification & PyMuPDF Extraction

## PDF Path Operators

| Operator | Name | Parameters | Description |
|----------|------|------------|-------------|
| `m` | moveto | x y | Start new subpath at (x, y) |
| `l` | lineto | x y | Straight line from current point to (x, y) |
| `c` | curveto | x1 y1 x2 y2 x3 y3 | Cubic Bézier curve (2 control + 1 end point) |
| `v` | curveto | x2 y2 x3 y3 | Cubic Bézier, first control = current point |
| `y` | curveto | x1 y1 x3 y3 | Cubic Bézier, second control = endpoint |
| `re` | rectangle | x y w h | Complete rectangle subpath |
| `h` | closepath | — | Close subpath (line back to start of subpath) |
| `S` | stroke | — | Stroke current path (draw lines) |
| `s` | close+stroke | — | Close then stroke |
| `f` / `F` | fill | — | Fill current path |
| `B` | fill+stroke | — | Both fill and stroke |
| `n` | no-op | — | End path without painting (used for clipping) |

## PDF Coordinate System
- Origin: **bottom-left** of page
- Y-axis: increases **upward**
- Units: **points** (1 point = 1/72 inch)
- A4 page: 595.28 x 841.89 points
- Must flip Y when converting to screen coordinates: `screen_y = page_height - pdf_y`

## Graphics State (relevant to floorplans)
- **lineWidth**: Stroke thickness in points — KEY for wall classification
  - Exterior walls: typically 1.5–3.0 pt
  - Interior walls: typically 0.5–1.5 pt
  - Mamad walls: typically 3.0–5.0 pt (THICKEST)
  - Dimension lines: typically 0.1–0.3 pt (thinnest)
  - Furniture outlines: typically 0.2–0.5 pt
- **dash pattern**: `[dash_length gap_length]` — used for dimension lines, hidden edges
- **strokeColor**: RGB tuple, often all black (0,0,0) in Israeli plans
- **fillColor**: Some plans fill rooms with light colors

## PyMuPDF `get_drawings()` API

```python
import fitz  # PyMuPDF

doc = fitz.open("plan.pdf")
page = doc[0]
paths = page.get_drawings()
```

Each path in the returned list is a dict:
```python
{
    "items": [           # List of drawing commands
        ("m", Point),    # moveto
        ("l", Point),    # lineto
        ("c", Point, Point, Point),  # curveto (3 points)
        ("re", Rect),    # rectangle
        ("qu", Quad),    # quad
    ],
    "color": (r, g, b),     # stroke color (0-1 floats), None if no stroke
    "fill": (r, g, b),      # fill color, None if no fill
    "width": float,          # line width in points
    "lineCap": int,          # 0=butt, 1=round, 2=square
    "lineJoin": int,         # 0=miter, 1=round, 2=bevel
    "dashes": str,           # dash pattern e.g. "[] 0" for solid
    "closePath": bool,       # whether path is closed
    "rect": Rect,            # bounding rectangle of the path
    "opacity": float,        # 0-1
    "even_odd": bool,        # fill rule
}
```

## Why Segments Fragment

Israeli contractor PDFs produce fragmented segments because:

1. **CAD export artifacts**: AutoCAD/Revit break continuous walls into segments at intersection points, grid crossings, or layer boundaries
2. **PDF operator segmentation**: Each `m...l` pair creates an independent segment. A single wall may be 3-10 separate segments
3. **Overlapping draws**: Walls drawn once, then redrawn for a hatch or fill pattern
4. **Door/window breaks**: Walls split at openings, creating gaps of 60-120cm
5. **Text interference**: Dimension text placement causes path breaks
6. **Multiple passes**: Different layers (structural, architectural, furniture) drawn independently, sometimes overlapping
7. **Coordinate precision**: Floating-point coordinates may not match exactly at supposed meeting points (e.g., 150.0 vs 149.997)

## Extraction Strategy

1. Extract all paths via `get_drawings()`
2. Convert each `"l"` item to a line segment `(x1, y1, x2, y2)`
3. Convert `"re"` items to 4 line segments
4. Ignore `"c"` curves initially (or approximate with line segments) — curves are typically door arcs
5. Classify segments by `width` into wall categories
6. Filter out very short segments (< 2 PDF points) as noise
7. Build a histogram of line widths to find natural clusters
8. Crop kartisiyyah (title block) region before classification

## Common Gotchas
- `get_drawings()` returns paths, not individual segments — must iterate `items`
- Rectangle items (`re`) encode `(x, y, w, h)`, not 4 points
- Some PDFs embed raster images instead of vectors — detect and reject (T3 block)
- Scanned PDFs have zero paths — must detect and show Hebrew error message
- Color may be in CMYK not RGB — normalize
- Line width 0 means "thinnest possible" (hairline), not invisible
