"""
Data models for the room detection and structural analysis pipeline.

Agent: VG (Vector/Geometry Specialist)
Phase 1, Sprint 3 — Room, WallInfo, Opening dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from shapely.geometry import Polygon


# ---------------------------------------------------------------------------
# Hebrew room label mappings
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 10 valid Israeli apartment room types
# ---------------------------------------------------------------------------

ROOM_LABELS_HE_TO_EN = {
    # Primary labels → canonical type
    'סלון': 'salon',
    'חדר דיור': 'salon',
    'סלון / חדר דיור': 'salon',
    'פינת אוכל': 'salon',            # dining area → part of salon
    'חדר שינה': 'bedroom',
    'חדר שינה הורים': 'bedroom',     # master = bedroom (no separate type)
    'חדר ילדים': 'bedroom',
    'חדר עבודה': 'bedroom',          # study → bedroom in Israeli counting
    'מטבח': 'kitchen',
    'מטבחון': 'kitchen',
    'שירותים': 'guest_toilet',
    'שירותי אורחים': 'guest_toilet',
    'אמבטיה': 'bathroom',
    'חדר רחצה': 'bathroom',
    'מקלחת': 'bathroom',
    'ממ"ד': 'mamad',
    'ממ״ד': 'mamad',                  # Hebrew gershayim ״
    'ממ\u201dד': 'mamad',             # right double quotation mark "
    'ממד': 'mamad',                   # no quotes at all
    'מרפסת': 'sun_balcony',
    'מרפסת שמש': 'sun_balcony',
    'מרפסת שירות': 'service_balcony',
    'מרפסת כביסה': 'service_balcony',
    'מחסן': 'storage',
    'חדר שירות': 'utility',
    'חדר כביסה': 'utility',
    # Merge targets: hallway/entrance/corridor → salon (circulation)
    'מסדרון': 'salon',
    'כניסה': 'salon',
    'פרוזדור': 'salon',
    # Abbreviations
    'ח. שינה': 'bedroom',
    'ח. רחצה': 'bathroom',
    'ח. עבודה': 'bedroom',
    'חד. שינה': 'bedroom',
    'מרפ.': 'sun_balcony',
    'שרות': 'guest_toilet',
    'ח. שירות': 'utility',
}

DISPLAY_NAMES_EN_TO_HE = {
    'salon': 'סלון / חדר דיור',
    'bedroom': 'חדר שינה',
    'kitchen': 'מטבח',
    'guest_toilet': 'שירותי אורחים',
    'bathroom': 'אמבטיה',
    'mamad': 'ממ"ד',
    'sun_balcony': 'מרפסת שמש',
    'service_balcony': 'מרפסת שירות',
    'storage': 'מחסן',
    'utility': 'חדר שירות',
    'unknown': 'חדר',
}

# The 10 valid types (anything else is an artifact to merge/delete)
VALID_ROOM_TYPES = {
    'salon', 'bedroom', 'kitchen', 'guest_toilet', 'bathroom',
    'mamad', 'sun_balcony', 'service_balcony', 'storage', 'utility',
}

# Area heuristics for classification (sqm)
AREA_HEURISTICS = {
    'guest_toilet': {'min': 1.5, 'max': 4.0, 'typical': 3.0},
    'utility':      {'min': 1.5, 'max': 5.0, 'typical': 3.0},
    'storage':      {'min': 1.5, 'max': 4.0, 'typical': 2.5},
    'bathroom':     {'min': 4.0, 'max': 8.0, 'typical': 5.5},
    'service_balcony': {'min': 3.0, 'max': 8.0, 'typical': 5.0},
    'kitchen':      {'min': 6.0, 'max': 15.0, 'typical': 10.0},
    'bedroom':      {'min': 8.0, 'max': 15.0, 'typical': 12.0},
    'mamad':        {'min': 7.0, 'max': 15.0, 'typical': 10.0},
    'sun_balcony':  {'min': 8.0, 'max': 50.0, 'typical': 12.0},
    'salon':        {'min': 20.0, 'max': 45.0, 'typical': 30.0},
}

# Rooms < this are artifacts — delete
MIN_VALID_ROOM_AREA = 1.5  # sqm
# Rooms > this need review — likely merged rooms
MAX_NORMAL_ROOM_AREA = 45.0  # sqm

# Structural disclaimer (mandatory per structural-rules.md)
STRUCTURAL_DISCLAIMER = (
    'סיווג זה הינו הערכה בלבד ואינו מהווה חוות דעת הנדסית. '
    'יש להתייעץ עם מהנדס מבנים מוסמך לפני ביצוע כל שינוי.\n'
    'This classification is an estimate only and does not constitute '
    'an engineering opinion. Consult a licensed structural engineer '
    'before making any modifications.'
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Room:
    """A detected room polygon with classification metadata."""
    polygon: Polygon
    area_sqm: float
    perimeter_m: float
    centroid: tuple[float, float]
    room_type: str = 'unknown'           # e.g. 'salon', 'bedroom', 'mamad'
    room_type_he: str = 'חדר'            # Hebrew display name
    confidence: float = 0.0              # 0-100
    needs_review: bool = True
    classification_strategy: str = 'none'  # 'text', 'fixture', 'heuristic', 'none'
    is_modifiable: bool = True           # False for mamad
    warnings: list[str] = field(default_factory=list)  # Hebrew QC notes


@dataclass
class WallInfo:
    """Structural classification for a wall segment."""
    segment: dict                        # Original segment dict
    wall_type: str = 'unknown'           # 'exterior', 'mamad', 'structural', 'partition', 'unknown'
    is_structural: bool = False
    is_modifiable: bool = True
    confidence: float = 0.0              # 0-100
    disclaimer: str = STRUCTURAL_DISCLAIMER


@dataclass
class Opening:
    """A detected door or window opening."""
    position: tuple[float, float]        # Midpoint of the opening
    width_cm: float                      # Opening width in cm
    opening_type: str = 'door'           # 'door' or 'window'
    swing_direction: Optional[str] = None  # 'left', 'right', 'inward', 'outward'
    connects_rooms: Optional[tuple[int, int]] = None  # Indices of connected rooms
    endpoints: Optional[tuple[tuple[float, float], tuple[float, float]]] = None
