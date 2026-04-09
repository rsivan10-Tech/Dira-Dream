# Data Model — PostgreSQL + PostGIS Schema

## Database: PostgreSQL 16 + PostGIS Extension

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

## Tables

### users
```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           VARCHAR(255) UNIQUE,
    phone           VARCHAR(20),
    display_name    VARCHAR(100),
    preferences     JSONB DEFAULT '{}',
    -- preferences: { locale, theme, default_parameters }
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### apartments
```sql
CREATE TABLE apartments (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    name            VARCHAR(255),
    source_pdf_path VARCHAR(500),
    source_pdf_hash VARCHAR(64),          -- SHA-256 for dedup
    page_number     INT DEFAULT 1,
    scale_factor    FLOAT,                -- PDF units to cm
    scale_notation  VARCHAR(10),          -- "1:50", "1:100"

    -- Extracted data (JSONB for flexibility during development)
    raw_segments    JSONB,                -- Original extracted segments
    healed_segments JSONB,                -- After healing pipeline
    extraction_stats JSONB,               -- Segment counts, histograms
    healing_stats   JSONB,                -- Snap/merge/extend counts

    -- Computed properties
    total_area_sqm  FLOAT,
    room_count      INT,
    confidence      INT CHECK (confidence >= 0 AND confidence <= 100),
    envelope        GEOMETRY(Polygon, 0), -- PostGIS polygon (PDF coords)

    -- Metadata
    address         VARCHAR(500),
    city            VARCHAR(100),
    neighborhood    VARCHAR(100),
    floor           INT,
    building_floors INT,
    contractor      VARCHAR(200),
    project_name    VARCHAR(200),
    compass_north   FLOAT,                -- Degrees from top of plan

    status          VARCHAR(20) DEFAULT 'draft',
    -- Status: draft, extracted, healed, rooms_detected, complete

    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_apartments_user ON apartments(user_id);
CREATE INDEX idx_apartments_status ON apartments(status);
```

### rooms
```sql
CREATE TABLE rooms (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    apartment_id    UUID REFERENCES apartments(id) ON DELETE CASCADE,
    room_type       VARCHAR(30) NOT NULL,
    -- Types: salon, bedroom, master_bedroom, kitchen, bathroom,
    --        mamad, balcony, service_balcony, storage, hallway,
    --        entrance, corridor, study, laundry, unknown

    room_type_he    VARCHAR(50),          -- Hebrew display name
    polygon         GEOMETRY(Polygon, 0), -- PostGIS polygon
    area_sqm        FLOAT NOT NULL,
    perimeter_cm    FLOAT,

    -- Classification
    confidence      INT CHECK (confidence >= 0 AND confidence <= 100),
    classification_method VARCHAR(20),
    -- Methods: text_label, fixture, area_heuristic, ai_vision, user_override
    needs_review    BOOLEAN DEFAULT false,

    -- Room-specific data
    label_point     GEOMETRY(Point, 0),   -- For label placement
    properties      JSONB DEFAULT '{}',
    -- properties: { window_count, door_count, has_en_suite, is_open_plan }

    display_order   INT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_rooms_apartment ON rooms(apartment_id);
CREATE INDEX idx_rooms_type ON rooms(room_type);
CREATE INDEX idx_rooms_polygon ON rooms USING GIST(polygon);
```

### walls
```sql
CREATE TABLE walls (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    apartment_id    UUID REFERENCES apartments(id) ON DELETE CASCADE,
    start_point     GEOMETRY(Point, 0),
    end_point       GEOMETRY(Point, 0),
    line            GEOMETRY(LineString, 0), -- Full geometry
    thickness_cm    FLOAT,
    length_cm       FLOAT,

    wall_type       VARCHAR(20) NOT NULL,
    -- Types: WALL_EXTERIOR, WALL_INTERIOR, WALL_MAMAD,
    --        WALL_STRUCTURAL, WALL_PARTITION, WALL_UNKNOWN
    is_structural   BOOLEAN,
    is_modifiable   BOOLEAN,
    confidence      INT CHECK (confidence >= 0 AND confidence <= 100),

    -- Adjacency
    room_ids        UUID[],               -- Adjacent room IDs

    properties      JSONB DEFAULT '{}',
    -- properties: { has_plumbing, original_width_pdf }

    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_walls_apartment ON walls(apartment_id);
CREATE INDEX idx_walls_type ON walls(wall_type);
CREATE INDEX idx_walls_line ON walls USING GIST(line);
```

### openings
```sql
CREATE TABLE openings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    apartment_id    UUID REFERENCES apartments(id) ON DELETE CASCADE,
    wall_id         UUID REFERENCES walls(id) ON DELETE CASCADE,
    opening_type    VARCHAR(20) NOT NULL,
    -- Types: door, window, sliding_door, french_door, mamad_door, blast_window

    width_cm        FLOAT,
    height_cm       FLOAT,
    sill_height_cm  FLOAT,                -- Window sill from floor
    position        GEOMETRY(Point, 0),   -- Center point
    swing_direction VARCHAR(10),          -- in, out, left, right, slide

    -- Connected rooms
    room_ids        UUID[],               -- Rooms connected by this opening

    confidence      INT CHECK (confidence >= 0 AND confidence <= 100),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_openings_apartment ON openings(apartment_id);
CREATE INDEX idx_openings_wall ON openings(wall_id);
```

### modifications
```sql
CREATE TABLE modifications (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    apartment_id    UUID REFERENCES apartments(id) ON DELETE CASCADE,
    mod_type        VARCHAR(30) NOT NULL,
    -- Types: wall_remove, wall_add, wall_move, room_merge, room_split,
    --        opening_add, opening_remove, kitchen_move, bathroom_move,
    --        balcony_enclose

    description_he  TEXT,
    affected_walls  UUID[],
    affected_rooms  UUID[],

    -- Cost estimation
    cost_min_ils    INT,
    cost_max_ils    INT,
    cost_confidence INT CHECK (cost_confidence >= 0 AND cost_confidence <= 100),
    requires_permit BOOLEAN DEFAULT false,
    permit_type     VARCHAR(20),          -- tama, shinuyim, none

    -- Structural impact
    structural_risk VARCHAR(10),          -- low, medium, high, blocked
    disclaimer_he   TEXT,

    status          VARCHAR(20) DEFAULT 'proposed',
    -- Status: proposed, approved, rejected

    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_modifications_apartment ON modifications(apartment_id);
```

### furniture_placements
```sql
CREATE TABLE furniture_placements (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    apartment_id    UUID REFERENCES apartments(id) ON DELETE CASCADE,
    room_id         UUID REFERENCES rooms(id) ON DELETE CASCADE,
    catalog_item_id VARCHAR(50),          -- Reference to fixture catalog

    name_he         VARCHAR(100),
    name_en         VARCHAR(100),
    category        VARCHAR(30),
    -- Categories: seating, sleeping, storage, dining, kitchen, bathroom, decor

    -- Position and dimensions (cm)
    x               FLOAT NOT NULL,
    y               FLOAT NOT NULL,
    rotation        FLOAT DEFAULT 0,      -- Degrees
    width_cm        FLOAT NOT NULL,
    depth_cm        FLOAT NOT NULL,
    height_cm       FLOAT,

    -- Source
    dimension_source VARCHAR(20) DEFAULT 'catalog',
    -- Sources: catalog, user_input, photo_ai
    dimension_confidence INT,

    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_furniture_apartment ON furniture_placements(apartment_id);
CREATE INDEX idx_furniture_room ON furniture_placements(room_id);
```

### listings (Phase 4)
```sql
CREATE TABLE listings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source          VARCHAR(20),          -- yad2, madlan, manual
    external_id     VARCHAR(100),
    external_url    VARCHAR(500),

    project_name    VARCHAR(200),
    contractor      VARCHAR(200),
    city            VARCHAR(100),
    neighborhood    VARCHAR(100),
    address         VARCHAR(500),
    location        GEOMETRY(Point, 4326), -- WGS84 for mapping

    floor           INT,
    total_floors    INT,
    area_sqm        FLOAT,
    rooms_count     FLOAT,                -- 3.5 rooms is valid in Israel
    price_ils       INT,
    price_per_sqm   INT,

    has_mamad       BOOLEAN,
    has_elevator    BOOLEAN,
    has_parking     BOOLEAN,
    has_storage     BOOLEAN,
    balcony_count   INT,

    has_pdf         BOOLEAN DEFAULT false,
    pdf_path        VARCHAR(500),
    apartment_id    UUID REFERENCES apartments(id),

    -- Matching
    match_score     FLOAT,                -- 0-100 match to dream profile
    modification_cost_estimate INT,       -- Estimated ILS to match dream

    status          VARCHAR(20) DEFAULT 'active',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_listings_city ON listings(city);
CREATE INDEX idx_listings_price ON listings(price_ils);
CREATE INDEX idx_listings_location ON listings USING GIST(location);
CREATE INDEX idx_listings_match ON listings(match_score DESC);
```

## JSONB Query Examples

```sql
-- Find apartments with specific room types
SELECT * FROM apartments a
WHERE EXISTS (
    SELECT 1 FROM rooms r
    WHERE r.apartment_id = a.id AND r.room_type = 'mamad'
);

-- Average confidence by extraction method
SELECT classification_method, AVG(confidence)
FROM rooms
GROUP BY classification_method;
```
