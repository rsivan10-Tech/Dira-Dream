# Google Maps API Reference for DiraDream

## APIs Used

1. **Street View Static API** — Window view images
2. **Elevation API** — Building height for camera position
3. **Geocoding API** — Address → coordinates

## Street View Static API

Generate view-from-window images based on building address, floor, and window direction.

### Endpoint
```
GET https://maps.googleapis.com/maps/api/streetview
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `location` | string | Latitude,longitude OR address |
| `size` | string | Image size, max `640x640` (free tier) |
| `heading` | number | 0–360°. 0=North, 90=East, 180=South, 270=West |
| `pitch` | number | -90 to 90°. 0=horizontal, positive=up, negative=down |
| `fov` | number | 10–120°. Field of view. Default 90° |
| `key` | string | API key |
| `source` | string | `outdoor` to prefer outdoor imagery |

### Example Request
```
https://maps.googleapis.com/maps/api/streetview
  ?location=32.0853,34.7818
  &size=640x480
  &heading=180
  &pitch=5
  &fov=90
  &source=outdoor
  &key=API_KEY
```

### Calculating Heading from Window

```python
def calculate_window_heading(
    wall_normal_angle: float,  # Degrees, outward from wall
    building_north: float       # Degrees, compass north relative to plan top
) -> float:
    """
    Calculate Google Street View heading for a window.

    wall_normal_angle: The outward-facing direction of the wall
                       in plan coordinates (0=right, 90=up)
    building_north: Compass north direction relative to plan top
                    (0=top is north, 90=top is east)
    """
    # Convert plan angle to compass heading
    heading = (building_north + 90 - wall_normal_angle) % 360
    return heading
```

### Calculating Pitch from Floor

```python
def calculate_pitch(
    floor_number: int,
    floor_height: float = 3.0,  # meters per floor
    street_view_height: float = 2.5  # meters (Google car camera)
) -> float:
    """
    Calculate pitch angle based on viewing floor.
    Higher floors look more downward toward horizon.
    """
    camera_height = floor_number * floor_height
    height_diff = camera_height - street_view_height

    if height_diff <= 0:
        return 0  # Ground floor or below

    # Small positive pitch to simulate looking out and slightly down
    # Approximate: buildings across the street are ~20m away
    import math
    distance_to_opposite = 20.0  # meters (typical Israeli street width)
    pitch = math.degrees(math.atan2(height_diff, distance_to_opposite))

    return min(pitch, 30)  # Cap at 30°
```

### FOV Recommendations
- Standard window: `fov=90`
- Narrow window (mamad): `fov=60`
- Panoramic/corner window: `fov=120`
- Balcony: `fov=110`

## Elevation API

Get ground elevation at building location.

### Endpoint
```
GET https://maps.googleapis.com/maps/api/elevation/json
  ?locations=32.0853,34.7818
  &key=API_KEY
```

### Response
```json
{
  "results": [{
    "elevation": 25.3,  // meters above sea level
    "location": { "lat": 32.0853, "lng": 34.7818 },
    "resolution": 4.77
  }],
  "status": "OK"
}
```

### Usage
```python
def get_camera_elevation(lat: float, lng: float, floor: int) -> float:
    """Get elevation for window view camera position."""
    ground_elevation = get_elevation(lat, lng)  # API call
    floor_height = floor * 3.0  # meters per floor
    return ground_elevation + floor_height
```

## Geocoding API

Convert Israeli addresses to coordinates.

### Endpoint
```
GET https://maps.googleapis.com/maps/api/geocode/json
  ?address=רחוב+הרצל+50,+תל+אביב
  &language=he
  &region=il
  &key=API_KEY
```

### Response
```json
{
  "results": [{
    "formatted_address": "הרצל 50, תל אביב-יפו, ישראל",
    "geometry": {
      "location": { "lat": 32.0623, "lng": 34.7697 },
      "location_type": "ROOFTOP"
    },
    "address_components": [
      { "long_name": "50", "types": ["street_number"] },
      { "long_name": "הרצל", "types": ["route"] },
      { "long_name": "תל אביב-יפו", "types": ["locality"] }
    ]
  }],
  "status": "OK"
}
```

### Israeli Address Notes
- Use `region=il` for better results
- Use `language=he` for Hebrew responses
- Israeli addresses: Street Name + Number, City
- Some new projects don't have street addresses yet — use project name + city
- Kibbutz/moshav addresses may not geocode well

## Israeli-Specific Coverage

### Street View Coverage
- **Tel Aviv**: Excellent coverage, updated frequently
- **Jerusalem**: Good coverage, some old city gaps
- **Haifa**: Good coverage
- **Beer Sheva**: Moderate coverage
- **Peripheral areas**: Variable — check availability
- **New developments**: May not have coverage (construction sites)
- **Military zones**: No coverage

### Fallback Strategy

```python
def get_window_view(lat, lng, heading, pitch, fov):
    """
    Get window view with fallback.

    T1: Street View image
    T2: Nearby Street View (within 50m radius)
    T3: Gradient sky fallback
    """
    # Try exact location
    image = fetch_streetview(lat, lng, heading, pitch, fov)

    if image.status == 'ZERO_RESULTS':
        # Try nearby with radius
        metadata = fetch_streetview_metadata(lat, lng, radius=50)
        if metadata.status == 'OK':
            image = fetch_streetview(
                metadata.location.lat,
                metadata.location.lng,
                heading, pitch, fov
            )

    if image.status == 'ZERO_RESULTS':
        # Fallback: generate gradient sky
        return generate_sky_gradient(heading, pitch)

    return image
```

## API Quotas and Caching

### Free Tier Limits (verify current pricing)
- Street View Static: 28,500 free loads/month
- Geocoding: 40,000 free requests/month
- Elevation: 40,000 free requests/month

### Caching Strategy
```python
import hashlib

def cache_key(lat, lng, heading, pitch, fov):
    """Generate cache key for Street View request."""
    # Round to reduce near-duplicate requests
    key = f"{lat:.4f},{lng:.4f},{heading:.0f},{pitch:.0f},{fov:.0f}"
    return hashlib.md5(key.encode()).hexdigest()

# Cache responses in DB or filesystem
# Street View images change infrequently — cache for 30 days
# Geocoding results change rarely — cache for 90 days
# Elevation is permanent — cache indefinitely
```

## Sun Position (suncalc)

For sun simulation on window views:

```typescript
import SunCalc from 'suncalc';

function getSunPosition(
  lat: number, lng: number,
  date: Date = new Date()
): { azimuth: number; altitude: number } {
  const pos = SunCalc.getPosition(date, lat, lng);
  return {
    azimuth: pos.azimuth * 180 / Math.PI + 180,  // Convert to 0-360°
    altitude: pos.altitude * 180 / Math.PI         // Degrees above horizon
  };
}

// Determine if window gets direct sunlight
function windowGetsSun(
  windowHeading: number,  // Compass heading window faces
  sunAzimuth: number      // Sun compass heading
): boolean {
  const diff = Math.abs(windowHeading - sunAzimuth);
  return diff < 90 || diff > 270;  // Window faces within 90° of sun
}
```
