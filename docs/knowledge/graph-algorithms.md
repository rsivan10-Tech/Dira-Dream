# Graph Algorithms for Room Detection

## Planar Graph Construction

After healing, wall segments form a planar graph where:
- **Nodes** = segment endpoints (intersection points)
- **Edges** = wall segments between nodes

```python
import networkx as nx

G = nx.Graph()
for seg in healed_segments:
    p1 = (round(seg.x1, 2), round(seg.y1, 2))
    p2 = (round(seg.x2, 2), round(seg.y2, 2))
    G.add_edge(p1, p2, width=seg.width, classification=seg.wall_type)
```

## Planar Face Enumeration (Room Detection)

Rooms correspond to **bounded faces** of the planar graph. The unbounded (exterior) face is not a room.

### Method 1: Shapely Polygonize (Recommended for DiraDream)

```python
from shapely.ops import polygonize
from shapely.geometry import LineString

lines = [LineString([e[0], e[1]]) for e in G.edges()]
rooms = list(polygonize(lines))
# Each polygon is a candidate room
# Filter by MIN_ROOM_AREA (1.0 sqm after scale conversion)
```

### Method 2: NetworkX Planar Embedding

```python
# Check planarity and get embedding
is_planar, embedding = nx.check_planarity(G)

if is_planar:
    # Traverse faces using the planar embedding
    faces = list(embedding.traverse_faces())
    # Each face is a list of nodes forming the boundary
    # The largest face is typically the exterior (discard)
```

### Method 3: Minimum Cycle Basis

```python
cycles = nx.minimum_cycle_basis(G)
# Each cycle is a list of nodes forming a minimal closed loop
# Minimal cycles correspond to individual rooms (not composite spaces)
```

**Comparison**:
| Method | Pros | Cons |
|--------|------|------|
| Polygonize | Robust, handles non-planar edges, returns Shapely polygons | May miss rooms if segments have gaps |
| Planar Embedding | Theoretically exact | Requires strict planarity, complex API |
| Min Cycle Basis | Finds minimal rooms | Expensive O(V·E²), may find non-room cycles |

## Room Polygon Processing

After detection, for each polygon:

```python
for room in rooms:
    if room.area * scale_factor**2 < MIN_ROOM_AREA:
        continue  # Too small, likely artifact

    # Compute properties
    area_sqm = room.area * scale_factor**2
    perimeter = room.length * scale_factor
    centroid = room.representative_point()  # For label placement
    bbox = room.bounds  # (minx, miny, maxx, maxy)

    # Classify room type (see room-classification-rules.md)
    room_type = classify_room(room, text_labels, fixtures, area_sqm)
```

## Graph Validation

Before room detection, validate the graph:

```python
def validate_graph(G):
    """Validate graph properties for room detection."""
    issues = []

    # 1. Connected components
    components = list(nx.connected_components(G))
    if len(components) > 1:
        issues.append(f"Graph has {len(components)} disconnected components")
        # Largest component is likely the apartment
        # Others may be balconies, storage

    # 2. Degree check
    for node in G.nodes():
        deg = G.degree(node)
        if deg == 1:
            issues.append(f"Dangling node at {node} (degree 1)")
            # May indicate incomplete healing
        if deg > 6:
            issues.append(f"Suspicious high-degree node at {node} (degree {deg})")

    # 3. Planarity
    is_planar, _ = nx.check_planarity(G)
    if not is_planar:
        issues.append("Graph is not planar — crossing edges exist")

    return issues
```

## Handling Nested Spaces

Some rooms contain sub-spaces:
- Closet inside bedroom
- Toilet stall inside bathroom
- Kitchen island creating inner loop

```python
# Detect containment
for i, room_a in enumerate(rooms):
    for j, room_b in enumerate(rooms):
        if i != j and room_a.contains(room_b):
            # room_b is inside room_a
            # room_b is a sub-space (closet, alcove)
            # room_a's effective area = room_a.area - room_b.area
```

## Door/Opening Detection from Graph

Gaps in wall segments indicate doors/openings:

```python
def find_openings(G, all_segments):
    """Find door-sized gaps between rooms."""
    openings = []
    for node in G.nodes():
        if G.degree(node) == 1:  # Dangling end
            # Find nearest other dangling end
            other_dangles = [n for n in G.nodes()
                          if G.degree(n) == 1 and n != node]
            for other in other_dangles:
                gap = distance(node, other)
                if DOOR_WIDTH_MIN <= gap <= DOOR_WIDTH_MAX:
                    openings.append({
                        'p1': node, 'p2': other,
                        'width': gap,
                        'type': 'door'  # or 'window' based on context
                    })
    return openings
```

## Room Adjacency Graph

Build a higher-level graph of room connections:

```python
def build_adjacency(rooms, openings):
    """Build room-to-room adjacency graph via openings."""
    adj = nx.Graph()
    for room in rooms:
        adj.add_node(room.id, type=room.room_type, area=room.area_sqm)

    for opening in openings:
        room_a = find_room_containing_edge(opening.p1, rooms)
        room_b = find_room_containing_edge(opening.p2, rooms)
        if room_a and room_b:
            adj.add_edge(room_a.id, room_b.id, opening=opening)

    return adj
    # Validation: all rooms should be reachable from entrance
```
