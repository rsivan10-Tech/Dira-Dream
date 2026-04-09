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

ROOM_LABELS_HE_TO_EN = {
    # Primary labels
    'סלון': 'salon',
    'חדר שינה': 'bedroom',
    'חדר שינה הורים': 'master_bedroom',
    'חדר ילדים': 'bedroom',
    'מטבח': 'kitchen',
    'שירותים': 'bathroom',
    'אמבטיה': 'bathroom',
    'מקלחת': 'bathroom',
    'ממ"ד': 'mamad',
    'מרפסת': 'balcony',
    'מרפסת שירות': 'service_balcony',
    'מחסן': 'storage',
    'מסדרון': 'hallway',
    'כניסה': 'entrance',
    'פרוזדור': 'corridor',
    'חדר עבודה': 'study',
    'חדר כביסה': 'laundry',
    # Abbreviations
    'ח. שינה': 'bedroom',
    'ח. רחצה': 'bathroom',
    'ח. עבודה': 'study',
    'חד. שינה': 'bedroom',
    'מרפ.': 'balcony',
    'שרות': 'bathroom',
}

DISPLAY_NAMES_EN_TO_HE = {
    'salon': 'סלון',
    'bedroom': 'חדר שינה',
    'master_bedroom': 'חדר שינה הורים',
    'kitchen': 'מטבח',
    'bathroom': 'חדר רחצה',
    'mamad': 'ממ"ד',
    'balcony': 'מרפסת',
    'service_balcony': 'מרפסת שירות',
    'storage': 'מחסן',
    'hallway': 'מסדרון',
    'entrance': 'כניסה',
    'corridor': 'פרוזדור',
    'study': 'חדר עבודה',
    'laundry': 'חדר כביסה',
    'unknown': 'חדר',
}

# Area heuristics for Strategy C classification (sqm)
AREA_HEURISTICS = {
    'bathroom':  {'min': 3.0, 'max': 12.0, 'typical': 5.0},
    'bedroom':   {'min': 8.0, 'max': 25.0, 'typical': 12.0},
    'salon':     {'min': 18.0, 'max': 50.0, 'typical': 25.0},
    'kitchen':   {'min': 6.0, 'max': 20.0, 'typical': 10.0},
    'mamad':     {'min': 9.0, 'max': 15.0, 'typical': 12.0},
    'storage':   {'min': 1.0, 'max': 4.0, 'typical': 2.0},
    'hallway':   {'min': 2.0, 'max': 15.0, 'typical': 6.0},
    'balcony':   {'min': 3.0, 'max': 25.0, 'typical': 10.0},
    'entrance':  {'min': 2.0, 'max': 6.0, 'typical': 3.0},
}

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
