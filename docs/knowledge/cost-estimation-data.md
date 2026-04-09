# Cost Estimation Data — Israeli Residential Modifications

## Base Costs (2024-2026 Israeli Market, ILS)

All prices are ranges. NEVER quote a single number.

### Wall Modifications

| Modification | Min ILS | Max ILS | Notes |
|-------------|---------|---------|-------|
| Remove partition wall (standard) | 15,000 | 40,000 | Non-structural, 10-12cm block |
| Remove structural wall | 80,000 | 200,000 | Requires engineer + steel beam + permit |
| Build new partition wall | 8,000 | 25,000 | New block wall with plaster/paint |
| Move partition wall | 20,000 | 50,000 | Remove + rebuild + finishes |
| Widen doorway | 5,000 | 15,000 | Non-structural wall only |
| Close doorway | 5,000 | 12,000 | Block up + plaster + paint |
| Add new doorway (partition) | 8,000 | 20,000 | Cut opening + frame + door |
| Add new doorway (structural) | 40,000 | 80,000 | Lintel + engineering |

### Kitchen Modifications

| Modification | Min ILS | Max ILS | Notes |
|-------------|---------|---------|-------|
| Kitchen relocation (full) | 50,000 | 120,000 | Plumbing + electrical + gas + finishes |
| Kitchen expansion (into adjacent room) | 30,000 | 70,000 | Wall removal + extension |
| Open kitchen to salon | 15,000 | 45,000 | Wall removal + counter/island |
| Kitchen island addition | 10,000 | 30,000 | Countertop + plumbing if sink |
| Upgrade kitchen finishes only | 25,000 | 80,000 | Cabinets + counters + backsplash |

### Bathroom Modifications

| Modification | Min ILS | Max ILS | Notes |
|-------------|---------|---------|-------|
| Bathroom relocation (full) | 40,000 | 100,000 | Waterproofing + plumbing + drainage |
| Bathroom expansion | 25,000 | 60,000 | Wall + plumbing + waterproofing |
| Add en-suite bathroom | 50,000 | 120,000 | New room + all plumbing + finishes |
| Bathroom renovation (same footprint) | 20,000 | 50,000 | Fixtures + tiles + plumbing |
| Convert bath to shower | 8,000 | 20,000 | Plumbing + waterproofing + tiles |
| Add second toilet | 15,000 | 35,000 | Plumbing + finishes |

### Balcony Modifications

| Modification | Min ILS | Max ILS | Notes |
|-------------|---------|---------|-------|
| Enclose balcony (standard) | 30,000 | 80,000 | Windows + insulation + permit |
| Enclose balcony (premium) | 60,000 | 150,000 | Full room conversion + permit |
| Merge balcony with room | 40,000 | 100,000 | Remove wall/door + insulate + permit |
| Add balcony railing upgrade | 5,000 | 15,000 | Glass/metal railing |

### Room Modifications

| Modification | Min ILS | Max ILS | Notes |
|-------------|---------|---------|-------|
| Merge 2 rooms into 1 | 20,000 | 50,000 | Wall removal + finishes |
| Split 1 room into 2 | 15,000 | 40,000 | New wall + door + electrical |
| Convert study to bedroom | 5,000 | 15,000 | May need window (code requirement) |
| Add storage room | 8,000 | 20,000 | New walls + door + shelving |

### Electrical & Plumbing

| Modification | Min ILS | Max ILS | Notes |
|-------------|---------|---------|-------|
| Electrical panel upgrade | 3,000 | 8,000 | Required for major renovations |
| Move electrical outlets (per room) | 2,000 | 5,000 | Chase walls + rewire |
| Move plumbing point | 5,000 | 15,000 | Per fixture point |
| Gas line extension | 3,000 | 10,000 | For kitchen relocation |
| AC preparation (per point) | 2,000 | 5,000 | Piping + drainage + electrical |

## Adjustment Factors

Apply multipliers to base costs:

```python
ADJUSTMENT_FACTORS = {
    # Location
    "tel_aviv": 1.2,      # Most expensive
    "jerusalem": 1.15,
    "haifa": 1.0,          # Baseline
    "beer_sheva": 0.85,
    "periphery": 0.75,

    # Building age
    "new_construction": 0.9,   # Contractor does during build
    "under_5_years": 1.0,
    "5_15_years": 1.1,
    "15_30_years": 1.2,
    "over_30_years": 1.4,     # May need asbestos, old wiring

    # Floor level
    "ground_floor": 1.0,
    "mid_floor": 1.05,        # Material hauling
    "high_floor_no_elevator": 1.2,
    "high_floor_elevator": 1.1,
    "penthouse": 1.15,

    # Scope
    "single_modification": 1.0,
    "multiple_modifications": 0.85,  # Contractor discount for bigger job
    "full_renovation": 0.75,         # Even bigger discount

    # Timing (off-plan vs. existing)
    "shinuyim_during_construction": 0.6,  # MUCH cheaper — contractor does it
    "post_delivery": 1.0,
    "occupied_apartment": 1.15,            # Working around tenants
}
```

## Cost Calculation Formula

```python
def estimate_cost(
    modification_type: str,
    base_costs: dict,
    location: str,
    building_age: str,
    floor_level: str,
    scope: str,
    timing: str
) -> tuple[int, int]:
    """
    Calculate adjusted cost range.
    Returns (min_ils, max_ils).
    """
    base = base_costs[modification_type]
    base_min, base_max = base['min'], base['max']

    factor = (
        ADJUSTMENT_FACTORS[location] *
        ADJUSTMENT_FACTORS[building_age] *
        ADJUSTMENT_FACTORS[floor_level] *
        ADJUSTMENT_FACTORS[scope] *
        ADJUSTMENT_FACTORS[timing]
    )

    adjusted_min = int(base_min * factor)
    adjusted_max = int(base_max * factor)

    # Round to nearest 5K for cleaner numbers
    adjusted_min = round(adjusted_min / 5000) * 5000
    adjusted_max = round(adjusted_max / 5000) * 5000

    return adjusted_min, adjusted_max
```

## Shinuyim (Off-Plan) Pricing

For off-plan purchases, contractor modification pricing is different:

```python
SHINUYIM_CONTRACTOR_COSTS = {
    # Contractors charge standardized rates during construction
    "wall_remove": (5000, 15000),      # Much cheaper during build
    "wall_add": (3000, 10000),
    "wall_move": (8000, 20000),
    "kitchen_move": (20000, 50000),
    "bathroom_add": (25000, 60000),
    "balcony_enclose": (15000, 40000),
    "electrical_point_add": (500, 1500),
    "plumbing_point_move": (2000, 5000),

    # Finishes (per sqm)
    "upgrade_tiles": (200, 800),       # Per sqm above standard
    "upgrade_kitchen": (15000, 50000),  # Above standard allocation
    "upgrade_bathroom": (10000, 30000), # Above standard allocation
}
```

## Common Modification Packages

Typical Israeli buyer modification requests:

1. **Open Kitchen** (most common):
   - Remove wall between kitchen and salon
   - Cost: 15K-45K ILS
   - Structural risk: Usually low (partition wall)

2. **Add Bedroom** (growing family):
   - Split large salon or convert study
   - Cost: 15K-40K ILS
   - May require window addition for code compliance

3. **Master Suite** (upgrade):
   - Expand master bedroom into adjacent room
   - Add en-suite bathroom
   - Cost: 60K-150K ILS

4. **Enclose Balcony** (extra space):
   - Convert balcony to indoor space
   - Cost: 30K-150K ILS
   - ALWAYS requires permit

## Mandatory Disclaimers

Every cost estimate MUST include (in Hebrew):

> "הערכת עלויות בלבד. המחירים מבוססים על ממוצעי שוק ועשויים להשתנות בהתאם לקבלן, למיקום ולמצב הקיים. יש לקבל הצעות מחיר ממספר קבלנים מורשים."

Translation: "Cost estimates only. Prices are based on market averages and may vary by contractor, location, and existing conditions. Obtain quotes from multiple licensed contractors."
