# Room Classification Rules

## Classification Strategy (3 tiers, descending confidence)

### Strategy 1: Text Label Matching (Highest Confidence: 90-95%)

Match Hebrew text labels found inside or near room polygons.

```python
ROOM_LABELS = {
    # Primary labels
    'סלון': 'salon',
    'חדר שינה': 'bedroom',
    'חדר שינה הורים': 'master_bedroom',
    'חדר ילדים': 'bedroom',
    'מטבח': 'kitchen',
    'שירותים': 'bathroom',
    'אמבטיה': 'bathroom',
    'מקלחת': 'bathroom',
    'ממ"ד': 'mamad',
    'מרפסת': 'balcony',
    'מרפסת שירות': 'service_balcony',
    'מחסן': 'storage',
    'מסדרון': 'hallway',
    'כניסה': 'entrance',
    'פרוזדור': 'corridor',
    'חדר עבודה': 'study',
    'חדר כביסה': 'laundry',

    # Abbreviations and variations
    'ח. שינה': 'bedroom',
    'ח. רחצה': 'bathroom',
    'ח. עבודה': 'study',
    'חד. שינה': 'bedroom',
    'מרפ.': 'balcony',
    'שרות': 'bathroom',
}
```

**Algorithm**:
1. Extract text elements with positions from PDF
2. For each text: find which room polygon contains its position
3. Match text against `ROOM_LABELS` (fuzzy matching for OCR artifacts)
4. Confidence: 95% for exact match, 90% for fuzzy match

### Strategy 2: Fixture Analysis (Medium Confidence: 70-85%)

Identify rooms by the fixtures drawn inside them.

```python
FIXTURE_SIGNATURES = {
    'bathroom': {
        'required_any': ['toilet', 'shower', 'bathtub'],
        'optional': ['sink', 'bidet'],
        'confidence': 85,
    },
    'kitchen': {
        'required_any': ['stove', 'cooktop', 'oven'],
        'optional': ['sink', 'refrigerator', 'counter'],
        'confidence': 80,
    },
    'laundry': {
        'required_any': ['washing_machine'],
        'optional': ['dryer', 'sink'],
        'confidence': 75,
    },
}
```

**Fixture Detection Heuristics**:
- **Toilet**: Small rectangle ~40x60cm, often with circle inside
- **Bathtub**: Rectangle ~70x170cm
- **Shower**: Square/rectangle ~80x80 to ~100x100cm, corner placement
- **Stove**: Rectangle with 4 circles (burners) ~60x60cm
- **Sink**: Small rectangle ~50x40cm, any room
- **Refrigerator**: Rectangle ~70x70cm, kitchen context

### Strategy 3: Area Heuristics (Lowest Confidence: 50-70%)

When text and fixtures are absent, classify by area and shape.

```python
AREA_HEURISTICS = {
    'bathroom':  {'min': 3.0, 'max': 12.0, 'typical': 5.0, 'confidence': 55},
    'bedroom':   {'min': 8.0, 'max': 25.0, 'typical': 12.0, 'confidence': 60},
    'salon':     {'min': 18.0, 'max': 50.0, 'typical': 25.0, 'confidence': 65},
    'kitchen':   {'min': 6.0, 'max': 20.0, 'typical': 10.0, 'confidence': 55},
    'mamad':     {'min': 9.0, 'max': 15.0, 'typical': 12.0, 'confidence': 50},
    'storage':   {'min': 1.0, 'max': 4.0, 'typical': 2.0, 'confidence': 60},
    'hallway':   {'min': 2.0, 'max': 15.0, 'typical': 6.0, 'confidence': 50},
    'balcony':   {'min': 3.0, 'max': 25.0, 'typical': 10.0, 'confidence': 55},
    'entrance':  {'min': 2.0, 'max': 6.0, 'typical': 3.0, 'confidence': 50},
}
```

**Shape heuristics**:
- Hallways: long and narrow (aspect ratio > 3:1)
- Bathrooms: small and roughly square
- Balconies: adjacent to exterior, long and shallow
- Salon: largest interior room

## Combined Classification

```python
def classify_room(room, text_labels, fixtures, area_sqm):
    """
    Combine all strategies. Highest confidence wins.
    """
    candidates = []

    # Strategy 1: Text
    text_match = match_text_label(room, text_labels)
    if text_match:
        candidates.append((text_match.type, text_match.confidence))

    # Strategy 2: Fixtures
    fixture_match = match_fixtures(room, fixtures)
    if fixture_match:
        candidates.append((fixture_match.type, fixture_match.confidence))

    # Strategy 3: Area
    area_match = match_by_area(room, area_sqm)
    if area_match:
        candidates.append((area_match.type, area_match.confidence))

    if not candidates:
        return RoomClassification('unknown', 0)

    # Sort by confidence, take highest
    candidates.sort(key=lambda x: x[1], reverse=True)
    best_type, best_conf = candidates[0]

    # Cross-validate: if top two strategies agree, boost confidence
    if len(candidates) >= 2 and candidates[0][0] == candidates[1][0]:
        best_conf = min(best_conf + 10, 100)

    # Low confidence: flag for user review
    if best_conf < 70:
        return RoomClassification(best_type, best_conf, needs_review=True)

    return RoomClassification(best_type, best_conf)
```

## Validation Rules

After classifying all rooms in an apartment:

```python
def validate_apartment_rooms(rooms):
    issues = []

    # Must have exactly 1 mamad
    mamads = [r for r in rooms if r.type == 'mamad']
    if len(mamads) != 1:
        issues.append(f"Expected 1 mamad, found {len(mamads)}")

    # Must have at least 1 bathroom
    bathrooms = [r for r in rooms if r.type == 'bathroom']
    if len(bathrooms) < 1:
        issues.append("No bathroom detected")

    # Must have exactly 1 kitchen
    kitchens = [r for r in rooms if r.type == 'kitchen']
    if len(kitchens) != 1:
        issues.append(f"Expected 1 kitchen, found {len(kitchens)}")

    # Must have exactly 1 salon
    salons = [r for r in rooms if r.type == 'salon']
    if len(salons) != 1:
        issues.append(f"Expected 1 salon, found {len(salons)}")

    # Area sanity check per room
    for room in rooms:
        expected = AREA_HEURISTICS.get(room.type)
        if expected and not (expected['min'] <= room.area_sqm <= expected['max']):
            issues.append(
                f"{room.type} area {room.area_sqm:.1f} outside "
                f"expected range {expected['min']}-{expected['max']}"
            )

    return issues
```

## Israeli Room Naming for Display

```python
DISPLAY_NAMES_HE = {
    'salon': 'סלון',
    'bedroom': 'חדר שינה',
    'master_bedroom': 'חדר שינה הורים',
    'kitchen': 'מטבח',
    'bathroom': 'חדר רחצה',
    'mamad': 'ממ"ד',
    'balcony': 'מרפסת',
    'service_balcony': 'מרפסת שירות',
    'storage': 'מחסן',
    'hallway': 'מסדרון',
    'entrance': 'כניסה',
    'corridor': 'פרוזדור',
    'study': 'חדר עבודה',
    'laundry': 'חדר כביסה',
}
```
