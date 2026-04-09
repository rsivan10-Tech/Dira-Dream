# Israeli Residential Plan Conventions

## Plan Structure

Israeli contractor floor plans (תוכנית דירה) follow consistent conventions:

### Sheet Layout
- **Drawing area**: The apartment plan itself, centered
- **Kartisiyyah (קרטיסייה)**: Title block / legend, typically bottom-right or right side
  - Contains: project name, contractor, architect, scale, date, apartment type
  - MUST be cropped before processing — contains noise (logos, text, borders)
- **North arrow**: Indicates building orientation (critical for window views)
- **Scale notation**: Usually `1:50` or `1:100`, sometimes `1:75`
  - At 1:50: 1cm on paper = 50cm real = ~14.17 PDF points
  - At 1:100: 1cm on paper = 100cm real = ~14.17 PDF points (but rooms are half-size on paper)

### Dimension Notation
- ALL dimensions in **centimeters** (cm)
- Displayed as plain numbers: `320` means 320cm = 3.20m
- Dimension lines: thin dashed or dotted lines with arrows/ticks at ends
- Height dimensions sometimes shown in section views: `260` = 2.60m ceiling
- Area labels: shown in sqm with מ"ר suffix, e.g., `12.5 מ"ר`

## Line Weight Conventions

**IMPORTANT — Real vs. theoretical widths:**
Real Israeli contractor PDFs use stroke widths in the **0.1–1.1 pt** range,
far thinner than textbook assumptions. The table below shows theoretical
ranges; in practice, classify by **relative ranking** from the histogram:
thickest = mamad, thicker = exterior, medium = interior, thinnest = dimensions.
Never use absolute thresholds — always derive from `compute_stroke_histogram()` peaks.

| Element | Theoretical Width (PDF pts) | Real Observed (PDF pts) | Classification Rule | Style |
|---------|---------------------------|------------------------|--------------------:|-------|
| Mamad (ממ"ד) walls | 3.0–5.0 | highest peak | THICKEST in file | Solid, often cross-hatched |
| Exterior walls | 1.5–3.0 | second-highest peak | Thicker than interior | Solid, thick |
| Interior walls | 0.5–1.5 | middle peaks | Medium width | Solid, medium |
| Window marks | 0.3–0.8 | varies | — | Three parallel lines in wall |
| Furniture outlines | 0.2–0.5 | lower peaks | Thin | Solid, thin |
| Door arcs | 0.2–0.5 | lower peaks | Thin | Curved (arc), thin |
| Dimension lines | 0.1–0.3 | lowest peak | Thinnest | Dashed or dotted, thin |
| Grid/construction lines | 0.05–0.15 | near-zero / hairline | Thinnest | Dotted, very thin |

## Room Naming (Hebrew)

| Hebrew | Transliteration | English | Typical Area |
|--------|----------------|---------|-------------|
| סלון | Salon | Living room | 18–50 sqm |
| חדר שינה | Chadar Sheina | Bedroom | 8–25 sqm |
| חדר שינה הורים | Chadar Sheina Horim | Master bedroom | 12–25 sqm |
| מטבח | Mitbach | Kitchen | 6–20 sqm |
| שירותים | Sherutim | Bathroom/WC | 3–8 sqm |
| אמבטיה | Ambatyah | Bathtub bathroom | 4–10 sqm |
| ממ"ד | Mamad | Safe room/shelter | 9–15 sqm |
| מרפסת | Mirpeset | Balcony | 5–20 sqm |
| מרפסת שירות | Mirpeset Sherut | Service balcony | 3–6 sqm |
| מחסן | Machsan | Storage | 1–4 sqm |
| מסדרון | Misderon | Hallway/corridor | varies |
| כניסה | Knisa | Entrance | 2–6 sqm |
| פרוזדור | Prozdor | Corridor | varies |

## Mamad (ממ"ד) — Safe Room

- **THICKEST walls** on the plan — thicker than exterior walls
- Area: 9–15 sqm (regulated by Home Front Command)
- Exactly ONE per apartment
- Single standard door, no standard windows (may have blast-proof window)
- Reinforced concrete construction — NO drilling, NO modifications EVER
- Often hatched or shaded differently
- Located for structural efficiency (stacked across floors)
- Furniture must be freestanding (cannot mount to walls)

## Fixture Symbols

Common symbols found in Israeli plans:

| Symbol | Element | Notes |
|--------|---------|-------|
| Arc from wall gap | Door | Direction indicates swing. 60–100cm opening |
| Three parallel lines in wall | Window | Typically 100–200cm wide |
| Rectangle with X | Toilet | ~40x60cm |
| Oval/rectangle | Bathtub | ~70x170cm |
| Small rectangle | Sink | ~50x40cm |
| Rectangle with circles | Stove/cooktop | 4 burner circles |
| Large rectangle | Refrigerator | ~70x70cm |
| L-shape or rectangle | Kitchen counter | Along walls |
| Rectangle at wall | Wardrobe/closet | Built-in |
| Small circle | Column/pillar | Structural |

## Common Plan Types

Israeli apartments are typically described by room count:
- **3 חדרים** (3 rooms): 2 bedrooms + salon = ~70-85 sqm
- **4 חדרים** (4 rooms): 3 bedrooms + salon = ~85-110 sqm
- **5 חדרים** (5 rooms): 4 bedrooms + salon = ~110-140 sqm
- **מיני פנטהאוז** (mini penthouse): Large apartment, sometimes duplex = ~130-180 sqm
- **פנטהאוז** (penthouse): Top floor, large terrace = ~150-250 sqm

Note: Israeli "room count" includes salon but excludes kitchen, bathrooms, mamad, and balconies.

## Scale Detection

If not explicitly stated, estimate scale from:
1. Dimension labels: If a number like `320` appears near a wall, measure that wall's PDF length, compute ratio
2. Door widths: Standard door opening is 80-90cm. Measure a door gap in PDF points, compute scale
3. Room areas: If labeled `12.5 מ"ר`, measure the polygon area in PDF units, compute scale
4. Page size: A3 plans at 1:50 fit a ~100sqm apartment; A4 at 1:100 fits similar

## Common Issues with Israeli Plans
- Multiple apartments per page (need to identify which one)
- Mirror-image apartments (left/right flip for adjacent units)
- Different floors shown on same page
- Balcony railings drawn with same weight as walls
- AC unit locations drawn outside the envelope
- Parking level plans mixed in
- Hebrew text rendered as curves (not extractable as text)
