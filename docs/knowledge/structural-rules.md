# Structural Wall Classification Rules

## Classification Algorithm

Wall classification is based on observable properties from the PDF plan. Each wall receives a type and confidence score (0–100).

### Decision Tree

```
Input: wall segment with width, position, context

1. Is wall part of building envelope (outermost boundary)?
   → YES: EXTERIOR (100% confidence, ALWAYS structural)

2. Is wall the thickest type (> all others including exterior)?
   → YES: MAMAD (95% confidence, ALWAYS structural, NEVER modifiable)

3. Is wall width > 1.5× average interior wall width?
   → YES: LIKELY STRUCTURAL (70% confidence)
   → Add: if wall spans full building width → +15% confidence
   → Add: if wall aligns with walls on adjacent floors → +10% confidence

4. Is wall full-width (spans entire building dimension)?
   → YES: LIKELY STRUCTURAL (75% confidence)

5. Is wall standard interior thickness?
   → YES: PARTITION (85% confidence, movable)

6. Unable to classify?
   → UNKNOWN (flag for user review)
```

## Wall Types

| Type | Code | Structural | Modifiable | Typical Width | Confidence |
|------|------|-----------|------------|---------------|------------|
| Exterior | `WALL_EXTERIOR` | ALWAYS | Requires permit | 20-25cm | 100% |
| Mamad | `WALL_MAMAD` | ALWAYS | NEVER | 25-30cm | 95% |
| Structural Interior | `WALL_STRUCTURAL` | LIKELY | Requires engineer | 15-20cm | 70% |
| Partition | `WALL_PARTITION` | NO | Yes (shinuyim) | 10-15cm | 85% |
| Unknown | `WALL_UNKNOWN` | UNCLEAR | Flag for review | varies | <50% |

## Width-Based Classification

```python
def classify_by_width(wall_width, width_histogram):
    """
    Classify wall by its width relative to the plan's width distribution.

    width_histogram: dict of {width_bucket: count} from all segments
    """
    # Find natural clusters in width distribution
    clusters = find_width_clusters(width_histogram)
    # Expect 2-4 clusters: dimension lines, furniture, interior, exterior, mamad

    if wall_width >= clusters['mamad_threshold']:
        return 'WALL_MAMAD', 95
    elif wall_width >= clusters['exterior_threshold']:
        return 'WALL_EXTERIOR', 90
    elif wall_width >= clusters['structural_threshold']:
        return 'WALL_STRUCTURAL', 70
    elif wall_width >= clusters['interior_threshold']:
        return 'WALL_PARTITION', 85
    else:
        return 'FURNITURE', 60  # Too thin for wall
```

## Position-Based Rules

### Exterior Detection
```python
def is_exterior_wall(wall, envelope_polygon):
    """Wall is exterior if it lies on or near the building envelope."""
    wall_line = LineString([wall.start, wall.end])
    distance_to_envelope = wall_line.distance(envelope_polygon.exterior)
    return distance_to_envelope < WALL_THICKNESS_TOLERANCE
```

### Mamad Detection
```python
def detect_mamad_walls(walls, rooms):
    """
    Mamad walls are:
    1. Thickest walls in the plan
    2. Form a single room of 9-15 sqm
    3. Exactly one mamad per apartment
    """
    max_width = max(w.width for w in walls)
    mamad_candidates = [w for w in walls if w.width >= max_width * 0.9]

    # Find room bounded by these walls
    mamad_room = find_enclosed_room(mamad_candidates)
    if mamad_room and 9.0 <= mamad_room.area_sqm <= 15.0:
        return mamad_candidates, 95  # High confidence
    else:
        return mamad_candidates, 50  # Flag for review
```

## Confidence Scoring

```python
def compute_confidence(wall, factors):
    """
    Combine multiple classification signals.

    factors: list of (signal_name, confidence_delta)
    """
    base = 50  # Start neutral
    for signal, delta in factors:
        base += delta

    return min(max(base, 0), 100)  # Clamp to 0-100

# Example factors:
# ("width_matches_exterior", +30)
# ("on_envelope", +20)
# ("spans_full_width", +15)
# ("aligns_vertically", +10)
# ("has_windows", +5)    # Only exterior walls have windows
# ("adjacent_to_wet_room", -5)  # Wet walls may have extra width for plumbing
```

## Special Cases

### Wet Walls
- Walls adjacent to bathrooms/kitchens may be thicker due to plumbing
- Thicker ≠ structural in this case
- Flag as "expensive to move even if not structural"
- Cost implication: moving wet wall = moving plumbing = 40K-100K ILS

### Shear Walls
- Concrete walls providing lateral stability
- Typically full-height, full-width
- Cannot be removed without structural engineer approval
- May appear as standard thickness but are reinforced concrete

### Column-Adjacent Walls
- Walls connected to structural columns
- More likely to be structural (load path)
- Look for small circles/squares in plan indicating columns

## Mandatory Disclaimer

Every structural classification MUST include:

> "סיווג זה הינו הערכה בלבד ואינו מהווה חוות דעת הנדסית. יש להתייעץ עם מהנדס מבנים מוסמך לפני ביצוע כל שינוי."
>
> "This classification is an estimate only and does not constitute an engineering opinion. Consult a licensed structural engineer before making any modifications."
