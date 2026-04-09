# Interior Design Standards

## Standard Furniture Dimensions (cm)

### Beds
| Type | Width | Depth/Length | Height | Clearance |
|------|-------|-------------|--------|-----------|
| Single bed | 90 | 200 | 45 | 60cm sides, 80cm foot |
| Double bed (Israeli standard) | 140 | 200 | 45 | 60cm both sides, 80cm foot |
| Queen bed | 160 | 200 | 45 | 60cm both sides, 80cm foot |
| King bed | 180 | 200 | 45 | 60cm both sides, 80cm foot |
| Baby crib | 60 | 120 | 90 | 60cm one side minimum |
| Nightstand | 45 | 40 | 55 | Adjacent to bed |

### Seating
| Type | Width | Depth | Height | Clearance |
|------|-------|-------|--------|-----------|
| 2-seat sofa | 150 | 85 | 85 | 80cm in front |
| 3-seat sofa | 220 | 85 | 85 | 80cm in front |
| L-shaped sofa | 250+170 | 85 | 85 | 80cm open side |
| Armchair | 80 | 80 | 85 | 60cm in front |
| Dining chair | 45 | 50 | 85 | 60cm behind (pullback) |
| Office chair | 60 | 60 | 90-110 | 80cm behind (rolling) |

### Tables
| Type | Width | Depth | Height | Clearance |
|------|-------|-------|--------|-----------|
| Dining table (4 person) | 120 | 80 | 75 | 60cm all sides (chairs) |
| Dining table (6 person) | 160 | 90 | 75 | 60cm all sides |
| Dining table (8 person) | 200 | 100 | 75 | 60cm all sides |
| Round table (4 person) | 100 dia | — | 75 | 60cm all around |
| Coffee table | 120 | 60 | 45 | 40cm from sofa |
| Desk | 120-160 | 60-80 | 75 | 80cm behind (chair) |
| Console table | 100 | 35 | 80 | Against wall |

### Storage
| Type | Width | Depth | Height | Notes |
|------|-------|-------|--------|-------|
| Wardrobe (sliding doors) | 180-300 | 60 | 240 | No door swing clearance needed |
| Wardrobe (hinged doors) | 120-200 | 60 | 240 | 60cm door swing clearance |
| Bookshelf | 80-120 | 30-40 | 180-240 | Against wall |
| Shoe cabinet | 80 | 30 | 120 | Entrance area |
| TV stand / media console | 150-200 | 45 | 50 | 200cm minimum viewing distance |

### Kitchen
| Type | Width | Depth | Height | Notes |
|------|-------|-------|--------|-------|
| Base cabinet | 60 | 60 | 85-90 | Standard counter height |
| Wall cabinet | 60 | 35 | 70 | Mounted at 140cm from floor |
| Refrigerator | 70 | 70 | 180 | 5cm clearance sides + back |
| Stove/Cooktop | 60 | 60 | 85 | Requires hood above |
| Oven (built-in) | 60 | 55 | 60 | In tall cabinet |
| Dishwasher | 60 | 60 | 85 | Adjacent to sink |
| Sink | 80 | 50 | 85 | In counter |
| Kitchen island | 120-240 | 80-100 | 90 | 100cm clearance all sides |

### Bathroom
| Type | Width | Depth | Height | Notes |
|------|-------|-------|--------|-------|
| Toilet | 40 | 65 | 40 | 20cm from wall sides, 60cm front |
| Bathtub | 70 | 170 | 60 | Access from one long side |
| Shower (square) | 80-100 | 80-100 | — | Corner placement common |
| Shower (rectangular) | 80 | 120 | — | Walk-in style |
| Vanity (single) | 60-80 | 45 | 85 | Mirror above |
| Vanity (double) | 120 | 50 | 85 | Master bathroom |
| Washing machine | 60 | 60 | 85 | Service balcony or bathroom |
| Dryer | 60 | 60 | 85 | Stacked or side-by-side |

## Clearance Rules

### Minimum Walkways
- **Main pathway**: 80cm (pass comfortably)
- **Between furniture**: 60cm (squeeze through)
- **Kitchen work zone**: 100cm (open cabinets/appliances)
- **Bedroom around bed**: 60cm (access)
- **Chair pullback**: 60cm behind dining/desk chair
- **Door swing**: Full arc must be clear of furniture

### Door Clearances
```
Door swing radius = door_width (typically 80-90cm)
Arc must be unobstructed:
  - No furniture within arc
  - No other door arcs overlapping
  - 80cm clear passage when door is open 90°
```

## Kitchen Work Triangle

The distance between sink, stove, and refrigerator:
- Each leg: 120-270cm
- Total perimeter: < 700cm (7m)
- No leg should cross a major traffic path

```
        Fridge
       /      \
      /        \
   Sink------Stove

Leg 1 (Sink-Stove): 120-180cm ideal
Leg 2 (Stove-Fridge): 120-270cm ideal
Leg 3 (Fridge-Sink): 120-210cm ideal
Total: < 700cm
```

## Israeli Home Conventions

### Salon (Living Room)
- Sofa facing TV wall
- Coffee table in front of sofa
- TV on wall or media console (200cm minimum viewing distance for 55" TV)
- Dining area adjacent (open plan common)
- Balcony access from salon
- Largest room in apartment

### Master Bedroom
- Double/queen bed centered on one wall
- Nightstands on both sides
- Wardrobe along longest wall (usually opposite bed)
- En-suite bathroom door
- Window for natural light (building code)

### Children's Room
- Bed(s) — single for each child, or bunk beds
- Desk for homework
- Wardrobe/storage
- Play area if space permits
- Minimum 8 sqm per child (building code)

### Kitchen
- Israeli kitchens increasingly open to salon
- Milchig/Fleischig separation: Some religious households need double sinks, separate counter areas
- Common layout: L-shaped or U-shaped with counter
- Service balcony access for laundry/utility

### Mamad (Safe Room)
- **Freestanding furniture ONLY** — cannot drill into reinforced concrete walls
- Common uses: study, nursery, storage, guest room
- Typically: desk + bookshelf or single bed + nightstand
- No heavy items mounted on walls
- Steel door must be accessible (not blocked)

## Room Furnishing Essentials vs Optional

See [room-furnishing-rules.md](room-furnishing-rules.md) for detailed per-room furniture lists.

## Validation Rules for Furniture Placement

```python
def validate_placement(item, room, other_items):
    """Validate furniture placement in room."""
    errors = []

    # 1. Item fully within room polygon
    if not room.polygon.contains(item.polygon):
        errors.append("פריט חורג מגבולות החדר")  # Item outside room

    # 2. No overlap with other furniture
    for other in other_items:
        if item.polygon.intersects(other.polygon):
            errors.append(f"חפיפה עם {other.name_he}")  # Overlap with...

    # 3. Clearance from walls
    wall_distance = room.polygon.exterior.distance(item.polygon)
    if wall_distance < 5:  # 5cm minimum from wall
        errors.append("קרוב מדי לקיר")  # Too close to wall

    # 4. Door swing clear
    for door in room.doors:
        if item.polygon.intersects(door.swing_arc):
            errors.append("חוסם פתיחת דלת")  # Blocking door swing

    # 5. Window access
    for window in room.windows:
        if item.polygon.intersects(window.access_zone):
            errors.append("חוסם גישה לחלון")  # Blocking window access

    # 6. Walkway maintained
    if not check_walkway(room, other_items + [item], min_width=80):
        errors.append("אין מעבר מספיק (מינימום 80 ס\"מ)")  # Insufficient walkway

    return errors
```
