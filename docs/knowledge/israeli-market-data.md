# Israeli Off-Plan Apartment Market Data

## Market Overview (2024-2026)

### Typical Apartment Sizes and Prices by Area

| City/Area | 3 Rooms (sqm) | 3 Room Price (ILS) | 4 Rooms (sqm) | 4 Room Price (ILS) | 5 Rooms (sqm) | 5 Room Price (ILS) |
|-----------|---------------|--------------------:|---------------|--------------------:|---------------|--------------------:|
| Tel Aviv | 65-80 | 2.5M-4.5M | 85-110 | 3.5M-6.0M | 110-140 | 5.0M-10M+ |
| Ramat Gan | 65-80 | 2.0M-3.5M | 85-110 | 2.8M-4.5M | 110-140 | 3.5M-6.0M |
| Herzliya | 70-85 | 2.5M-4.0M | 90-115 | 3.5M-5.5M | 115-150 | 5.0M-8.0M |
| Netanya | 65-80 | 1.5M-2.5M | 85-110 | 2.0M-3.5M | 110-140 | 2.5M-4.5M |
| Jerusalem | 65-80 | 2.0M-3.5M | 85-110 | 2.8M-4.5M | 110-140 | 3.5M-6.0M |
| Haifa | 70-85 | 1.2M-2.2M | 90-115 | 1.5M-3.0M | 115-145 | 2.0M-4.0M |
| Beer Sheva | 70-90 | 0.8M-1.5M | 95-120 | 1.0M-2.0M | 120-150 | 1.5M-2.5M |
| Modi'in | 70-85 | 1.8M-2.8M | 90-115 | 2.2M-3.5M | 115-145 | 2.8M-4.5M |
| Petah Tikva | 65-80 | 1.5M-2.5M | 85-110 | 2.0M-3.5M | 110-140 | 2.5M-4.5M |
| Rishon LeZion | 65-80 | 1.5M-2.5M | 85-110 | 2.0M-3.5M | 110-140 | 2.5M-4.5M |

### Price Per Square Meter (New Construction)

| Area | Price/sqm (ILS) |
|------|----------------|
| Tel Aviv Center | 45,000-70,000 |
| Tel Aviv Periphery | 35,000-50,000 |
| Gush Dan (suburbs) | 25,000-40,000 |
| Jerusalem | 30,000-50,000 |
| Haifa | 18,000-30,000 |
| Sharon (Netanya, Kfar Saba) | 20,000-35,000 |
| Negev | 12,000-20,000 |
| Galilee | 12,000-22,000 |

## Buyer Demographics

### Typical Off-Plan Buyers
- **Young couples (25-35)**: First home, Mehir LaMishtaken program, 3-4 rooms
- **Growing families (30-40)**: Upgrading from smaller apartment, 4-5 rooms
- **Investors**: Buy-to-rent, prefer 3-room apartments in high-demand areas
- **Returning Israelis**: Coming back from abroad, often higher budget
- **New immigrants**: Particularly from France, US, UK — sometimes higher-end

### Common Buyer Priorities
1. **Price/budget** — #1 factor always
2. **Location** — proximity to work, schools, public transit
3. **Room count** — driven by family size
4. **Floor level** — higher floors command premium (view, noise)
5. **Direction/orientation** — south/west preferred for sun, affects pricing
6. **Mamad size** — became more important since 2023
7. **Balcony** — almost essential, especially salon balcony
8. **Parking** — required in most new projects
9. **Storage** — dedicated storage room in building
10. **Contractor reputation** — major factor in off-plan purchases

## Major Israeli Contractors

### Tier 1 (Large National)
- Shikun & Binui (שיכון ובינוי)
- Africa Israel (אפריקה ישראל)
- Azorim (אזורים)
- Hagag (חגג)
- Yitzhak Tshuva Group
- Electra / Electra Real Estate
- Ashtrom

### Tier 2 (Large Regional)
- Ashdar (אשדר)
- Netivey Avnat (נתיבי אבנת)
- Gindi (גינדי)
- Rami Levy Real Estate
- BSR Group
- Prashkovsky (פרשקובסקי)
- Kardan Real Estate

### Tier 3 (Medium/Boutique)
- Various local builders
- Boutique developers
- Note: Many Tama 38 projects are smaller developers

## Market Trends (2024-2026)

### Current Dynamics
- **Housing shortage**: Persistent undersupply, especially in Gush Dan
- **Government programs**: Mehir LaMishtaken, Mehir Lamemishtaken (lottery programs for discounted housing)
- **Interest rates**: Rising rates affecting mortgage accessibility
- **Construction costs**: Increasing due to labor and material costs
- **Regulatory changes**: New building codes, safety requirements
- **Urban renewal**: Pinui-Binui (demolish-rebuild) and Tama 38 (seismic strengthening) projects

### Off-Plan Purchase Volume
- Approximately 50,000-70,000 new apartments sold per year
- Off-plan represents roughly 60-70% of new apartment sales
- Average time from purchase to delivery: 3-4 years

## Israeli Room Count Convention

Important: Israeli "room count" (מספר חדרים) differs from international:
- Salon (living room) counts as a room
- Bedrooms count as rooms
- Kitchen does NOT count
- Bathrooms do NOT count
- Mamad does NOT count (sometimes marketed separately)
- Balcony does NOT count
- Storage does NOT count

**Examples**:
- "3 חדרים" = 2 bedrooms + 1 salon + kitchen + bathroom + mamad
- "4 חדרים" = 3 bedrooms + 1 salon + kitchen + bathroom(s) + mamad
- "5 חדרים" = 4 bedrooms + 1 salon + kitchen + bathroom(s) + mamad
- "3.5 חדרים" = 2 bedrooms + 1 salon + small room (study/nursery)

## Dream Profile Matching Criteria

For DiraDream's apartment matching algorithm:

```python
MATCHING_CRITERIA = {
    "bedrooms": {"weight": 15, "type": "exact_or_more"},
    "total_area_sqm": {"weight": 12, "type": "range_tolerance", "tolerance": 10},
    "floor": {"weight": 8, "type": "range"},
    "city": {"weight": 10, "type": "exact"},
    "neighborhood": {"weight": 8, "type": "exact"},
    "price_ils": {"weight": 15, "type": "max_budget"},
    "has_mamad": {"weight": 5, "type": "boolean"},
    "kitchen_type": {"weight": 6, "type": "preference"},  # open/closed
    "balcony": {"weight": 5, "type": "boolean"},
    "direction": {"weight": 4, "type": "preference"},  # south/west/etc
    "parking": {"weight": 4, "type": "boolean"},
    "storage": {"weight": 3, "type": "boolean"},
    "elevator": {"weight": 3, "type": "boolean"},
    "modification_budget": {"weight": 7, "type": "max_cost"},
}
```

## Data Sources

### Primary Listing Sources
- **Yad2 (יד2)**: Largest Israeli classifieds. API/scraping for listings.
- **Madlan (מדלן)**: Real estate platform with project data, price history, neighborhood stats.
- **Gov.il**: Government price index, building permit data.

### Data Available per Listing
- Project name, contractor, city, neighborhood
- Room count, area (sqm), floor, total floors
- Price (ILS), price per sqm
- PDF plan (if available from contractor)
- Photos, virtual tours
- Delivery date estimate
- Amenities (parking, storage, elevator, gym, pool)
