# Room Classification Rules — 10 Valid Israeli Apartment Types

## The 10 Valid Room Types

Israeli apartments contain ONLY these 10 room types. Any detected room must
be classified as one of these or merged/deleted as an artifact.

| # | Type (EN) | Hebrew | Area (sqm) | Notes |
|---|-----------|--------|------------|-------|
| 1 | bedroom | חדר שינה | 8-15 | Includes master, children's, study |
| 2 | mamad | ממ"ד | 9-12 | Safe room. Thickest walls. NEVER modifiable. Also functions as bedroom |
| 3 | guest_toilet | שירותי אורחים | 2-4 | Toilet + sink, no shower |
| 4 | bathroom | אמבטיה | 4-8 | Shower/bathtub + toilet + sink |
| 5 | sun_balcony | מרפסת שמש | 8-50 | OUTSIDE envelope. NOT counted in interior area |
| 6 | service_balcony | מרפסת שירות | 3-8 | Near kitchen. Washing machine connection |
| 7 | storage | מחסן | 1.5-4 | No plumbing, no windows |
| 8 | utility | חדר שירות | 2-5 | Water heater, electrical panel |
| 9 | kitchen | מטבח | 6-15 | Has stove/oven/sink fixtures |
| 10 | salon | סלון / חדר דיור | 20-45 | Largest room. Often open to kitchen/dining |

## Merge Rules

These are NOT separate rooms — merge into the nearest valid type:

| Detected | Merge Into | Reason |
|----------|-----------|--------|
| hallway (מסדרון) | salon | Circulation space, not a room |
| corridor (פרוזדור) | salon | Circulation space |
| entrance (כניסה) | salon | Entry area, not a room |
| dining (פינת אוכל) | salon | Part of living area |
| study (חדר עבודה) | bedroom | Functions as bedroom in Israeli counting |
| laundry (חדר כביסה) | utility | Same function |
| master_bedroom | bedroom | No separate type needed |

## Artifact Rules

- Any room < 1.5 sqm → DELETE (detection artifact)
- Any room > 45 sqm → FLAG for review (likely merged rooms)
- Max realistic room count: 3-room apt = 7-8, 4-room = 9-10, 5-room = 11-12

## Area Display (Israeli Standard)

Per Israeli regulations, apartment area is split:
- **שטח דירה פנימי** (interior area): all rooms EXCEPT balconies
- **שטח מרפסות** (balcony area): sun_balcony + service_balcony
- The sidebar shows both separately

## Sun Balcony Detection

Sun balconies (מרפסת שמש) are visually distinct on Israeli PDFs:
- Located OUTSIDE the apartment envelope (exterior walls on 3 sides)
- Often have cross-hatch or tiled floor pattern
- Connected to interior via glass door or large opening
- Area 8-50 sqm (can be very large on penthouses)

## Classification Strategy (3 tiers)

### Strategy 1: Text Label Matching (Confidence: 90-95%)
Match Hebrew text labels found inside room polygons against ROOM_LABELS_HE_TO_EN.

### Strategy 2: Fixture Analysis (Confidence: 70-85%)
Identify rooms by drawn fixtures (toilet, shower, stove, etc.).

### Strategy 3: Area Heuristics (Confidence: 50-70%)
Classify by area when text and fixtures are absent.

## Validation Rules

After classifying all rooms:
1. Exactly 1 mamad (if multiple, keep highest-confidence candidate)
2. At least 1 bathroom or guest_toilet
3. Exactly 1 kitchen
4. Exactly 1 salon
5. Each room area within its type's expected range
