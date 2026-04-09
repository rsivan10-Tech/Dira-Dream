# Healing Algorithms for Vector Floorplan Geometry

## Pipeline Overview

```
Raw Segments → Snap Endpoints → Merge Collinear → Remove Duplicates
→ Extend to Intersect → Split at Intersections → Validate → Healed Segments
```

Each step produces stats: segments in → segments out, operations performed.

---

## 1. Snap Endpoints

**Goal**: Move nearby endpoints to the same coordinate.

**Algorithm**:
```
SNAP_TOLERANCE = 3.0  # PDF points (configurable)

1. Collect all endpoints into array: points[]
2. Build KDTree from points[]
3. Find all pairs within SNAP_TOLERANCE: pairs = tree.query_pairs(SNAP_TOLERANCE)
4. Build Union-Find over pairs (transitive closure)
5. For each group: compute centroid of all points in group
6. Replace all endpoints in group with centroid
7. Skip groups where snap would create zero-length segment
```

**Edge Cases**:
- **T-junction**: Wall end meets middle of another wall. Snap the endpoint to the nearest point ON the other segment (perpendicular projection), not to the other segment's endpoint.
- **Near-miss corner**: Two walls almost meet. Snap both endpoints to their average position.
- **Door gap**: Two endpoints 60-120cm apart across a doorway. Do NOT snap these — preserve the opening. Check: if gap width matches door width range AND there's a door arc nearby, skip snap.
- **Cluster of 3+**: Multiple walls meeting at one point. All must converge to single centroid.

**Complexity**: O(n log n) with KDTree.

---

## 2. Merge Collinear Segments

**Goal**: Join segments that are parts of the same wall.

**Algorithm**:
```
COLLINEAR_ANGLE = 2.0  # degrees (configurable)
COLLINEAR_GAP = 2.0    # PDF points (configurable)

1. For each pair of segments (s1, s2) sharing an endpoint:
   a. Compute angle between s1 and s2
   b. If angle < COLLINEAR_ANGLE or > (180 - COLLINEAR_ANGLE):
      - If gap between non-shared endpoints <= COLLINEAR_GAP:
        - Merge into single segment from s1.far_end to s2.far_end
        - Inherit max(s1.width, s2.width)
2. Repeat until no more merges possible
```

**Edge Cases**:
- **3+ collinear fragments**: Wall broken into many pieces. Merge iteratively — each pass may enable new merges.
- **Almost-collinear with offset**: Parallel segments offset by < tolerance. These are the SAME wall drawn twice — merge by taking the average centerline.
- **Collinear different widths**: Wall transitions from interior to exterior. Do NOT merge — the width change is meaningful information.

---

## 3. Remove Duplicates

**Goal**: Eliminate segments drawn more than once.

**Algorithm**:
```
OVERLAP_THRESHOLD = 0.9  # fraction of overlap (configurable)

1. For each pair of segments with similar angle (< COLLINEAR_ANGLE):
   a. Project both onto common axis
   b. Compute overlap ratio = overlap_length / min(len(s1), len(s2))
   c. If overlap_ratio > OVERLAP_THRESHOLD:
      - Keep the segment with greater width (more structural info)
      - Remove the other
```

**Edge Cases**:
- **Partial overlap**: Two segments overlap by 80%. Keep both but trim to eliminate overlap.
- **Same line, different widths**: May represent wall + dimension line. Keep both (different classification).
- **Exact duplicate**: Identical endpoints and width. Remove one.

---

## 4. Extend to Intersect

**Goal**: Close small gaps where walls should meet but don't.

**Algorithm**:
```
EXTEND_TOLERANCE = 10.0  # PDF points (configurable)

1. For each segment endpoint that is "dangling" (not connected):
   a. Extend the segment along its direction by EXTEND_TOLERANCE
   b. Check if extended segment intersects any other segment
   c. If yes: trim to intersection point
   d. If no: leave as-is (orphan endpoint)
2. Prioritize extending toward the nearest segment
```

**Edge Cases**:
- **T-junction formation**: Wall extends to meet perpendicular wall. Create proper T by splitting the crossed wall at the new intersection.
- **L-corner gap**: Two walls nearly form a corner. Extend both to meet at computed intersection point.
- **Ambiguous direction**: Dangling end could extend to meet multiple walls. Choose the nearest intersection.
- **Over-extension**: Don't extend beyond EXTEND_TOLERANCE — would create false walls.
- **Door openings**: If extending would close a 60-120cm gap with a door arc nearby, do NOT extend. Preserve the opening.

---

## 5. Split at Intersections

**Goal**: Ensure all segment crossings produce proper graph nodes.

**Algorithm**:
```
1. Find all intersection points between all segment pairs
   (Use sweep-line algorithm or spatial index for efficiency)
2. For each intersection point P:
   a. If P is not an endpoint of both segments:
      - Split each segment at P into two sub-segments
      - Both sub-segments inherit parent's width/classification
3. Remove zero-length segments created by splits
```

**Edge Cases**:
- **Near-intersection**: Two segments cross within tolerance but don't exactly intersect. Snap to exact intersection.
- **Multiple crossings**: One long wall crossed by several perpendicular walls. Split into n+1 segments.
- **Endpoint on segment**: Wall endpoint lands on middle of another wall. Split the other wall.

---

## 6. Validation

After healing, verify:
```
1. No zero-length segments
2. No duplicate segments
3. All intersections are at endpoints (planar graph property)
4. Connected components: ideally 1 (entire apartment)
   - Multiple components → possible gap or disconnected balcony
5. No self-intersecting segments
6. Total wall length within 10% of pre-healing (no major data loss)
7. Door openings preserved (count should match pre-healing)
```

## Stats to Report
```json
{
  "segments_before": 847,
  "segments_after": 312,
  "snaps_performed": 156,
  "merges_performed": 234,
  "duplicates_removed": 89,
  "extensions_performed": 45,
  "splits_performed": 67,
  "orphan_segments": 12,
  "connected_components": 1,
  "door_openings_preserved": 8,
  "confidence": 87
}
```
