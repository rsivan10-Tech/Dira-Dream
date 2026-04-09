# Coordinate Mapping Reference

## Three Coordinate Systems

### 1. PDF Space (Source)
- **Origin**: Bottom-left of page
- **X-axis**: Right (increases →)
- **Y-axis**: Up (increases ↑)
- **Units**: Points (1pt = 1/72 inch)
- **Typical range**: 0–842 x 0–595 (A4 landscape)

### 2. Canvas Space (2D Display — Konva.js)
- **Origin**: Top-left of canvas
- **X-axis**: Right (increases →)
- **Y-axis**: Down (increases ↓)
- **Units**: Pixels
- **Note**: Y-axis is FLIPPED relative to PDF

### 3. Three.js Space (3D Scene)
- **Origin**: Center of scene (or apartment centroid)
- **X-axis**: Right (increases →)
- **Y-axis**: Up (increases ↑)
- **Z-axis**: Forward/toward camera (increases toward viewer)
- **Units**: Meters
- **Convention**: Y-UP (Three.js default)

## Transformation Formulas

### PDF → Canvas

```
canvas_x = (pdf_x - crop_x) * display_scale + pan_x
canvas_y = (page_height - pdf_y - crop_y) * display_scale + pan_y
```

Where:
- `crop_x, crop_y` = kartisiyyah crop offset
- `display_scale` = zoom level * base_scale
- `pan_x, pan_y` = pan offset from dragging
- `page_height` = PDF page height in points

```typescript
function pdfToCanvas(
  pdfX: number, pdfY: number,
  pageHeight: number,
  cropX: number, cropY: number,
  displayScale: number,
  panX: number, panY: number
): [number, number] {
  const canvasX = (pdfX - cropX) * displayScale + panX;
  const canvasY = (pageHeight - pdfY - cropY) * displayScale + panY;
  return [canvasX, canvasY];
}
```

### Canvas → PDF (Inverse)

```
pdf_x = (canvas_x - pan_x) / display_scale + crop_x
pdf_y = page_height - (canvas_y - pan_y) / display_scale - crop_y
```

```typescript
function canvasToPdf(
  canvasX: number, canvasY: number,
  pageHeight: number,
  cropX: number, cropY: number,
  displayScale: number,
  panX: number, panY: number
): [number, number] {
  const pdfX = (canvasX - panX) / displayScale + cropX;
  const pdfY = pageHeight - (canvasY - panY) / displayScale - cropY;
  return [pdfX, pdfY];
}
```

### PDF → Real World (cm)

```
real_cm = pdf_points * scale_factor
```

Where `scale_factor` depends on plan scale:
- **1:50**: 1cm on paper = 50cm real. 1cm paper = 28.35 points. So `scale_factor = 50 / 28.35 ≈ 1.764`
- **1:100**: `scale_factor = 100 / 28.35 ≈ 3.527`

More precisely: `scale_factor = plan_scale / 28.3465` (points per cm)

```typescript
function pdfToRealCm(pdfPoints: number, planScale: number): number {
  const POINTS_PER_CM = 28.3465;
  return pdfPoints * planScale / POINTS_PER_CM;
}

function realCmToPdf(cm: number, planScale: number): number {
  const POINTS_PER_CM = 28.3465;
  return cm * POINTS_PER_CM / planScale;
}
```

### Real World (cm) → Three.js (meters)

```
three_x = real_x_cm / 100
three_y = height_cm / 100      (elevation above floor)
three_z = real_y_cm / 100      (2D Y becomes 3D Z)
```

```typescript
function realToThreeJS(
  realX: number, realY: number, heightCm: number = 0
): THREE.Vector3 {
  return new THREE.Vector3(
    realX / 100,      // X stays X
    heightCm / 100,   // Height becomes Y (up)
    realY / 100       // 2D Y becomes Z (depth)
  );
}
```

### PDF → Three.js (Combined)

```typescript
function pdfToThreeJS(
  pdfX: number, pdfY: number,
  planScale: number,
  heightCm: number = 0
): THREE.Vector3 {
  const realX = pdfToRealCm(pdfX, planScale);
  const realY = pdfToRealCm(pdfY, planScale);
  return realToThreeJS(realX, realY, heightCm);
}
```

## Scale Detection

If plan scale is unknown, estimate from known dimensions:

```typescript
function estimateScale(
  knownDimensionCm: number,   // Dimension label value (e.g., 320)
  measuredPdfPoints: number    // Measured distance in PDF
): number {
  // scale_factor = real_cm / pdf_points
  // plan_scale = scale_factor * POINTS_PER_CM
  const scaleFactor = knownDimensionCm / measuredPdfPoints;
  const planScale = scaleFactor * 28.3465;

  // Round to nearest common scale
  const commonScales = [50, 75, 100, 150, 200];
  return commonScales.reduce((closest, s) =>
    Math.abs(s - planScale) < Math.abs(closest - planScale) ? s : closest
  );
}
```

## Coordinate System Summary Table

| Property | PDF | Canvas (Konva) | Three.js |
|----------|-----|---------------|----------|
| Origin | Bottom-left | Top-left | Center |
| X direction | → Right | → Right | → Right |
| Y direction | ↑ Up | ↓ Down | ↑ Up |
| Z direction | N/A | N/A | → Toward viewer |
| Units | Points | Pixels | Meters |
| Y flip needed? | — | YES (from PDF) | NO (from real) |

## Common Pitfalls

1. **Forgetting Y-flip**: PDF→Canvas requires flipping Y. Most common bug.
2. **Scale confusion**: PDF points ≠ cm ≠ pixels ≠ meters. Always be explicit.
3. **Crop offset**: After cropping kartisiyyah, coordinates shift. Apply crop offset BEFORE other transforms.
4. **Pan/zoom order**: Apply zoom first, then pan (or use matrix multiplication).
5. **Three.js Y-up**: 2D plan Y coordinate maps to Three.js Z, not Y. Y is height.
6. **Integer rounding**: PDF coordinates are floats. Don't round until final pixel rendering.
7. **Aspect ratio**: Ensure canvas aspect matches PDF page aspect after cropping.

## ITM ↔ WGS84 (Geographic Coordinates)

For Google Maps integration (Phase 2):

- **ITM (Israeli Transverse Mercator)**: Local Israeli coordinate system
  - Used in Israeli government maps and GIS
  - Easting (X): ~100,000–300,000
  - Northing (Y): ~350,000–800,000

- **WGS84**: Global GPS coordinate system
  - Used by Google Maps, OpenStreetMap
  - Latitude: 29.5°–33.3° N (Israel)
  - Longitude: 34.2°–35.9° E (Israel)

```python
# Use pyproj for coordinate conversion
from pyproj import Transformer

itm_to_wgs84 = Transformer.from_crs("EPSG:2039", "EPSG:4326", always_xy=True)
wgs84_to_itm = Transformer.from_crs("EPSG:4326", "EPSG:2039", always_xy=True)

# ITM → WGS84
lon, lat = itm_to_wgs84.transform(easting, northing)

# WGS84 → ITM
easting, northing = wgs84_to_itm.transform(lon, lat)
```
