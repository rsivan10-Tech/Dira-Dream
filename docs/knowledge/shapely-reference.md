# Shapely Reference for Architectural Geometry

## Core Functions

### `polygonize(lines)`
Construct polygons from a collection of lines that form closed rings.

```python
from shapely.ops import polygonize

lines = [LineString([(0,0),(10,0)]), LineString([(10,0),(10,10)]),
         LineString([(10,10),(0,10)]), LineString([(0,10),(0,0)])]
polygons = list(polygonize(lines))
# Returns list of Polygon objects formed by closed line arrangements
```

**Use in DiraDream**: After healing, pass all wall segments to `polygonize()` to detect room polygons. Only works if segments form proper closed rings — hence healing is critical.

**Common issues**:
- Gaps > tolerance → polygon not formed (room missing)
- Dangling edges ignored (good — removes orphan segments)
- Returns only minimal polygons, not nested

### `polygonize_full(lines)`
Returns `(polygons, dangles, cut_edges, invalid_rings)` — useful for debugging.

```python
from shapely.ops import polygonize_full
polys, dangles, cuts, invalids = polygonize_full(healed_segments)
# dangles = segments not part of any polygon
# cut_edges = segments that would need to be cut
# invalids = rings that aren't valid polygons
```

### `snap(geom, reference, tolerance)`
Snap vertices of `geom` to `reference` within `tolerance`.

```python
from shapely.ops import snap

snapped = snap(segment, target_segment, tolerance=3.0)
# Moves endpoints of segment to match target if within 3.0 units
```

**Use in DiraDream**: First pass of healing — snap nearby endpoints together. Use `SNAP_TOLERANCE = 3.0` PDF points.

### `unary_union(geoms)`
Merge a collection of geometries, resolving overlaps and shared boundaries.

```python
from shapely.ops import unary_union

merged = unary_union(wall_segments)
# Returns a MultiLineString or GeometryCollection
```

**Use in DiraDream**: Merge collinear, overlapping segments. Combine with `linemerge()` for best results.

### `linemerge(lines)`
Merge connected LineStrings into longer LineStrings where possible.

```python
from shapely.ops import linemerge

merged = linemerge(MultiLineString(segments))
# Joins segments that share endpoints into continuous lines
```

### `buffer(distance)`
Expand or contract geometry by a distance.

```python
wall_polygon = wall_line.buffer(thickness / 2, cap_style='flat')
# Creates a rectangular polygon from a line (wall with thickness)
```

**Use in DiraDream**: Convert wall centerlines to wall polygons for rendering and 3D extrusion.

### `representative_point()`
Returns a point guaranteed to be inside the polygon (unlike centroid which may be outside for concave shapes).

```python
room_polygon.representative_point()
# Good for placing room labels
```

## Geometric Predicates

| Method | Use Case |
|--------|----------|
| `intersects(other)` | Do two walls cross? |
| `crosses(other)` | Does a wall cross another (not just touch)? |
| `touches(other)` | Do walls share a boundary point? |
| `within(other)` | Is furniture inside a room? |
| `contains(other)` | Does a room contain a point? |
| `distance(other)` | Gap between two segment endpoints |
| `hausdorff_distance(other)` | Max distance between two geometries (similarity) |

## Spatial Analysis

### `nearest_points(geom1, geom2)`
```python
from shapely.ops import nearest_points
p1, p2 = nearest_points(seg1, seg2)
gap = p1.distance(p2)
```

### `split(geom, splitter)`
```python
from shapely.ops import split
result = split(wall_line, intersection_point.buffer(0.01))
```

**Use in DiraDream**: Split wall segments at intersection points for proper graph construction.

## Coordinate Operations

```python
from shapely.affinity import scale, translate, rotate

# Flip Y for PDF→screen coordinate conversion
flipped = scale(geom, xfact=1, yfact=-1, origin=(0, page_height/2))

# Scale from PDF points to cm (depends on plan scale)
scaled = scale(geom, xfact=scale_factor, yfact=scale_factor, origin=(0,0))
```

## Performance Tips
- Use `STRtree` for spatial indexing when checking many geometries:
  ```python
  from shapely import STRtree
  tree = STRtree(all_segments)
  nearby = tree.query(target_segment, predicate='dwithin', distance=5.0)
  ```
- Prefer `prepared` geometries for repeated predicate checks:
  ```python
  from shapely.prepared import prep
  prepared_room = prep(room_polygon)
  items_inside = [f for f in furniture if prepared_room.contains(f)]
  ```
- Use `scipy.spatial.KDTree` for endpoint proximity (O(n log n) vs O(n²)):
  ```python
  from scipy.spatial import KDTree
  endpoints = [(seg.coords[0], seg.coords[-1]) for seg in segments]
  tree = KDTree(all_points)
  pairs = tree.query_pairs(r=SNAP_TOLERANCE)
  ```

## Validation Utilities

```python
def validate_room(polygon):
    """Validate a detected room polygon."""
    assert polygon.is_valid, f"Invalid polygon: {explain_validity(polygon)}"
    assert not polygon.is_empty, "Empty polygon"
    assert polygon.area > MIN_ROOM_AREA, f"Too small: {polygon.area}"
    assert polygon.exterior.is_simple, "Self-intersecting boundary"
    return True
```
