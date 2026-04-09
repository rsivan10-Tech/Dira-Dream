# Fixture Catalog Schema

## Data Format

Each catalog item follows this schema:

```typescript
interface CatalogItem {
  id: string;               // Unique ID, e.g., "sofa_3seat_standard"
  name_he: string;          // Hebrew display name, e.g., "ספה תלת מושבית"
  name_en: string;          // English name, e.g., "3-Seat Sofa"
  category: FurnitureCategory;
  subcategory: string;      // e.g., "seating", "sleeping"
  room_types: RoomType[];   // Which rooms this item belongs in
  
  // Dimensions (cm)
  width_cm: number;         // X dimension (left-right)
  depth_cm: number;         // Z dimension (front-back)  
  height_cm: number;        // Y dimension (floor to top)
  
  // Clearances (cm) — minimum clear space around item
  clearances: {
    front: number;          // Primary access side
    back: number;           // Against-wall side (usually 0)
    left: number;
    right: number;
  };
  
  // Display
  icon: string;             // Icon name or SVG path
  color_2d: string;         // Fill color for 2D canvas, e.g., "#E3F2FD"
  outline_2d: string;       // Stroke color for 2D canvas
  model_3d?: string;        // Path to 3D model file (optional)
  
  // Constraints
  wall_mounted: boolean;    // Must be against a wall?
  freestanding: boolean;    // Can stand alone?
  blocks_window: boolean;   // Placement in front of window is a warning
  blocks_door: boolean;     // Placement in door swing is an error
  stackable: boolean;       // Can stack on another item (e.g., dryer on washer)
  
  // Interaction
  draggable: boolean;       // Can user drag in 2D view
  rotatable: boolean;       // Can user rotate
  resizable: boolean;       // Can user resize (custom dimensions)
  snap_to_wall: boolean;    // Auto-snap to nearest wall when placed
  
  // Metadata
  essential: boolean;       // Is this a must-have for the room type?
  sort_order: number;       // Display order in catalog panel
  tags: string[];           // Search tags
}

type FurnitureCategory = 
  | 'seating'    // Sofas, chairs
  | 'sleeping'   // Beds, cribs
  | 'storage'    // Wardrobes, shelves, cabinets
  | 'tables'     // Dining, coffee, desk
  | 'kitchen'    // Appliances, counters
  | 'bathroom'   // Fixtures
  | 'laundry'    // Washing machine, dryer
  | 'decor'      // Rugs, plants, mirrors
  | 'outdoor';   // Balcony furniture

type RoomType =
  | 'salon' | 'bedroom' | 'master_bedroom' | 'kitchen'
  | 'bathroom' | 'mamad' | 'balcony' | 'service_balcony'
  | 'entrance' | 'hallway' | 'storage';
```

## Example Catalog Items

```json
[
  {
    "id": "sofa_3seat_standard",
    "name_he": "ספה תלת מושבית",
    "name_en": "3-Seat Sofa",
    "category": "seating",
    "subcategory": "sofa",
    "room_types": ["salon"],
    "width_cm": 220,
    "depth_cm": 85,
    "height_cm": 85,
    "clearances": { "front": 80, "back": 0, "left": 0, "right": 0 },
    "icon": "sofa",
    "color_2d": "#B3E5FC",
    "outline_2d": "#0288D1",
    "wall_mounted": false,
    "freestanding": true,
    "blocks_window": true,
    "blocks_door": true,
    "stackable": false,
    "draggable": true,
    "rotatable": true,
    "resizable": true,
    "snap_to_wall": true,
    "essential": true,
    "sort_order": 1,
    "tags": ["sofa", "ספה", "ישיבה", "סלון"]
  },
  {
    "id": "bed_double_140",
    "name_he": "מיטה זוגית 140",
    "name_en": "Double Bed 140cm",
    "category": "sleeping",
    "subcategory": "bed",
    "room_types": ["master_bedroom", "bedroom"],
    "width_cm": 140,
    "depth_cm": 200,
    "height_cm": 45,
    "clearances": { "front": 80, "back": 0, "left": 60, "right": 60 },
    "icon": "bed-double",
    "color_2d": "#C8E6C9",
    "outline_2d": "#388E3C",
    "wall_mounted": false,
    "freestanding": true,
    "blocks_window": true,
    "blocks_door": true,
    "stackable": false,
    "draggable": true,
    "rotatable": true,
    "resizable": true,
    "snap_to_wall": true,
    "essential": true,
    "sort_order": 1,
    "tags": ["bed", "מיטה", "זוגית", "שינה"]
  },
  {
    "id": "dining_table_4p",
    "name_he": "שולחן אוכל (4)",
    "name_en": "Dining Table (4-person)",
    "category": "tables",
    "subcategory": "dining",
    "room_types": ["salon"],
    "width_cm": 120,
    "depth_cm": 80,
    "height_cm": 75,
    "clearances": { "front": 60, "back": 60, "left": 60, "right": 60 },
    "icon": "table",
    "color_2d": "#FFE0B2",
    "outline_2d": "#E65100",
    "wall_mounted": false,
    "freestanding": true,
    "blocks_window": false,
    "blocks_door": true,
    "stackable": false,
    "draggable": true,
    "rotatable": true,
    "resizable": true,
    "snap_to_wall": false,
    "essential": true,
    "sort_order": 5,
    "tags": ["table", "שולחן", "אוכל", "dining"]
  },
  {
    "id": "toilet_standard",
    "name_he": "אסלה",
    "name_en": "Toilet",
    "category": "bathroom",
    "subcategory": "fixture",
    "room_types": ["bathroom"],
    "width_cm": 40,
    "depth_cm": 65,
    "height_cm": 40,
    "clearances": { "front": 60, "back": 0, "left": 20, "right": 20 },
    "icon": "toilet",
    "color_2d": "#FFFFFF",
    "outline_2d": "#757575",
    "wall_mounted": true,
    "freestanding": false,
    "blocks_window": false,
    "blocks_door": true,
    "stackable": false,
    "draggable": true,
    "rotatable": true,
    "resizable": false,
    "snap_to_wall": true,
    "essential": true,
    "sort_order": 1,
    "tags": ["toilet", "אסלה", "שירותים"]
  },
  {
    "id": "refrigerator_standard",
    "name_he": "מקרר",
    "name_en": "Refrigerator",
    "category": "kitchen",
    "subcategory": "appliance",
    "room_types": ["kitchen"],
    "width_cm": 70,
    "depth_cm": 70,
    "height_cm": 180,
    "clearances": { "front": 100, "back": 5, "left": 5, "right": 5 },
    "icon": "refrigerator",
    "color_2d": "#E0E0E0",
    "outline_2d": "#616161",
    "wall_mounted": false,
    "freestanding": true,
    "blocks_window": true,
    "blocks_door": true,
    "stackable": false,
    "draggable": true,
    "rotatable": true,
    "resizable": false,
    "snap_to_wall": true,
    "essential": true,
    "sort_order": 3,
    "tags": ["fridge", "מקרר", "מטבח"]
  },
  {
    "id": "wardrobe_sliding_200",
    "name_he": "ארון הזזה 200",
    "name_en": "Sliding Wardrobe 200cm",
    "category": "storage",
    "subcategory": "wardrobe",
    "room_types": ["bedroom", "master_bedroom"],
    "width_cm": 200,
    "depth_cm": 60,
    "height_cm": 240,
    "clearances": { "front": 60, "back": 0, "left": 0, "right": 0 },
    "icon": "wardrobe",
    "color_2d": "#D7CCC8",
    "outline_2d": "#5D4037",
    "wall_mounted": false,
    "freestanding": true,
    "blocks_window": true,
    "blocks_door": true,
    "stackable": false,
    "draggable": true,
    "rotatable": true,
    "resizable": true,
    "snap_to_wall": true,
    "essential": true,
    "sort_order": 3,
    "tags": ["wardrobe", "ארון", "הזזה", "בגדים"]
  },
  {
    "id": "washing_machine",
    "name_he": "מכונת כביסה",
    "name_en": "Washing Machine",
    "category": "laundry",
    "subcategory": "appliance",
    "room_types": ["service_balcony", "bathroom"],
    "width_cm": 60,
    "depth_cm": 60,
    "height_cm": 85,
    "clearances": { "front": 80, "back": 5, "left": 2, "right": 2 },
    "icon": "washing-machine",
    "color_2d": "#E0E0E0",
    "outline_2d": "#616161",
    "wall_mounted": false,
    "freestanding": true,
    "blocks_window": false,
    "blocks_door": true,
    "stackable": true,
    "draggable": true,
    "rotatable": true,
    "resizable": false,
    "snap_to_wall": true,
    "essential": true,
    "sort_order": 1,
    "tags": ["washer", "כביסה", "מכונה"]
  }
]
```

## Catalog Organization for UI

### Category Display Order
1. Essential items for selected room (highlighted)
2. Optional items for selected room
3. Other categories (collapsed)

### Search
- Search by Hebrew name, English name, or tags
- Filter by room type (auto-filtered when room is selected)
- Filter by category

### Drag-and-Drop Flow
1. User selects a room on the canvas
2. Catalog filters to show items valid for that room type
3. User drags item from catalog to canvas
4. Item snaps to wall if `snap_to_wall` is true
5. Clearance zones shown as semi-transparent overlay
6. Red highlight if placement violates rules
7. Green highlight if valid placement

## Custom Dimensions (Photo Upload)

When user uploads a photo of their own furniture:

```typescript
interface CustomItem extends CatalogItem {
  id: `custom_${string}`;
  dimension_source: 'photo_ai' | 'user_input';
  dimension_confidence: number;  // 0-100
  photo_url?: string;
  warning_he?: string;  // "המידות מבוססות על הערכה"
}
```

- Photo dimensions flagged with confidence < 70% → show warning
- User can manually override AI-estimated dimensions
- Custom items saved per apartment, not global catalog
