"""
wayfinder/categories.py
────────────────────────
Single source of truth for category vocabulary, durations, and indoor/outdoor flags.

FIXES in this version:
  - duration: "sights & landmarks" bumped to 90 min (was 60 — too short)
  - duration: "attraction" / "attractions" default bumped to 90 min (was 75)
  - duration: added "zoos & aquariums" → 180 min
  - duration: added "spas & wellness" → 120 min
  - duration: added "outdoor activities" → 120 min
  - is_indoor: added "spas & wellness", "zoos & aquariums" (aquarium is indoor)
  - is_outdoor: added "outdoor activities", "zoo" (outdoor enclosures)
  - is_indoor: added "cathedral", "basilica" (large religious buildings = indoor)
  - Both flags now also check a name-based heuristic for common misses:
    words like "bath", "baths", "aquarium", "museum", "gallery" in the name
    trigger is_indoor=True even when TripAdvisor miscategorises the place.
"""
from __future__ import annotations

# ── canonical routing-stage vocabulary ────────────────────────────────────────
ROUTING_CATEGORIES: frozenset[str] = frozenset({
    "landmark", "museum", "restaurant", "food", "nightlife",
    "park", "beach", "shopping", "market", "tour", "relaxation",
    "hike", "viewpoint", "religious", "entertainment",
})


# ── duration estimates (minutes) ──────────────────────────────────────────────
# FIX: more realistic durations — "attraction" generic default raised to 90.
# Specific high-engagement categories now have their own entries.
CATEGORY_DURATION_MIN: dict[str, int] = {
    # generic
    "attraction":         90,
    "attractions":        90,
    "sights & landmarks": 90,   # FIX: was 60 — too short for most landmarks
    "landmark":           90,

    # museums & galleries
    "museum":             150,
    "art museum":         150,
    "gallery":            120,
    "historic site":      90,

    # religious
    "religious site":     60,
    "temple":             60,
    "shrine":             60,
    "church":             60,
    "cathedral":          75,
    "mosque":             45,
    "basilica":           90,   # FIX: added — large basilicas need more time

    # outdoor / nature
    "park":               90,
    "nature & parks":     90,
    "garden":             75,
    "beach":              150,
    "hike":               180,
    "trail":              180,
    "viewpoint":          60,
    "observation deck":   60,
    "outdoor activities": 120,  # FIX: added

    # animals
    "zoo":                180,
    "zoos & aquariums":   180,  # FIX: added
    "aquarium":           150,

    # commerce
    "shopping":           90,
    "market":             90,

    # food & drink
    "food & drink":       75,
    "restaurant":         75,
    "restaurants":        75,
    "cafe":               45,
    "bar":                60,
    "nightlife":          120,

    # tours & activities
    "tour":               120,
    "tours":              120,
    "activities":         90,

    # wellness
    "spa":                120,
    "spas & wellness":    120,  # FIX: added

    # entertainment
    "entertainment":      90,
    "water park":         240,
    "amusement park":     300,
    "theater":            150,
    "concert":            150,
}


# ── TripAdvisor → routing-stage category map ─────────────────────────────────
TA_TO_ROUTING_CATEGORY: dict[str, str] = {
    "attraction":         "landmark",
    "attractions":        "landmark",
    "sights & landmarks": "landmark",
    "historic site":      "landmark",
    "landmark":           "landmark",
    "observation deck":   "viewpoint",
    "viewpoint":          "viewpoint",
    "museum":             "museum",
    "art museum":         "museum",
    "gallery":            "museum",
    "religious site":     "religious",
    "temple":             "religious",
    "shrine":             "religious",
    "church":             "religious",
    "cathedral":          "religious",
    "mosque":             "religious",
    "basilica":           "religious",
    "restaurant":         "restaurant",
    "restaurants":        "restaurant",
    "food & drink":       "food",
    "cafe":               "food",
    "bar":                "nightlife",
    "nightlife":          "nightlife",
    "park":               "park",
    "nature & parks":     "park",
    "garden":             "park",
    "beach":              "beach",
    "hike":               "hike",
    "trail":              "hike",
    "outdoor activities": "hike",
    "shopping":           "shopping",
    "market":             "market",
    "tour":               "tour",
    "tours":              "tour",
    "activities":         "tour",
    "spa":                "relaxation",
    "spas & wellness":    "relaxation",
    "entertainment":      "entertainment",
    "theater":            "entertainment",
    "concert":            "entertainment",
    "amusement park":     "entertainment",
    "water park":         "entertainment",
    "zoo":                "entertainment",
    "zoos & aquariums":   "entertainment",
    "aquarium":           "entertainment",
}


# ── weather flags ─────────────────────────────────────────────────────────────
# FIX: added "outdoor activities", "zoo" to outdoor set
OUTDOOR_CATEGORIES: frozenset[str] = frozenset({
    "beach", "park", "garden", "hike", "trail",
    "viewpoint", "observation deck", "nature & parks",
    "water park", "amusement park", "outdoor activities", "zoo",
})

# FIX: added "spas & wellness", "zoos & aquariums", "cathedral", "basilica"
INDOOR_CATEGORIES: frozenset[str] = frozenset({
    "museum", "art museum", "gallery", "aquarium", "zoos & aquariums",
    "shopping", "market", "theater", "spa", "spas & wellness",
    "restaurant", "cafe", "bar",
    "cathedral", "basilica",               # large enclosed religious buildings
})

# Name-fragment heuristics — catches places TripAdvisor miscategorises.
# If any of these words appear in the attraction name (lowercased), is_indoor=True.
_INDOOR_NAME_HINTS: frozenset[str] = frozenset({
    "aquarium", "museum", "gallery", "bath", "baths", "thermal",
    # English AND Spanish/Catalan variants so local names fire correctly
    "cathedral", "catedral", "basilica", "basílica",
    "palace", "castle", "mall", "cinema",
    "theatre", "theater", "opera", "library",
})

_OUTDOOR_NAME_HINTS: frozenset[str] = frozenset({
    "beach", "park", "garden", "zoo", "safari", "trail", "hike",
    "viewpoint", "lookout", "rooftop", "waterfall", "lake", "river",
    # transport modes that are primarily outdoors
    "bus turistic", "open top bus", "open-top",
})


# ── helpers ──────────────────────────────────────────────────────────────────
def estimate_duration(category: str, subcategories: list[str] | None = None) -> int:
    """
    Best-guess visit time in minutes. Falls back to 90.
    Subcategories checked BEFORE the generic category so specific entries
    like Zoos & Aquariums (180) beat the generic Attraction fallback (90).
    """
    subs = subcategories or []
    for label in [*subs, category]:
        key = (label or "").strip().lower()
        if key in CATEGORY_DURATION_MIN:
            return CATEGORY_DURATION_MIN[key]
    return 90


def normalise_to_routing(category: str, subcategories: list[str] | None = None) -> str:
    """Best-fit routing-stage category. Falls back to 'landmark'."""
    subs = subcategories or []
    for label in [category, *subs]:
        key = (label or "").strip().lower()
        if key in TA_TO_ROUTING_CATEGORY:
            return TA_TO_ROUTING_CATEGORY[key]
    return "landmark"


def is_outdoor(category: str, subcategories: list[str] | None = None,
               name: str = "") -> bool:
    """True if primarily outdoor. Also checks name heuristics (substring match)."""
    subs = subcategories or []
    for label in [category, *subs]:
        if (label or "").strip().lower() in OUTDOOR_CATEGORIES:
            return True
    name_lower = name.lower()
    # substring match — catches "Barcelona Bus Turistic" via "bus turistic"
    return any(hint in name_lower for hint in _OUTDOOR_NAME_HINTS)


def is_indoor(category: str, subcategories: list[str] | None = None,
              name: str = "") -> bool:
    """True if primarily indoor. Also checks name heuristics (substring match)."""
    subs = subcategories or []
    for label in [category, *subs]:
        if (label or "").strip().lower() in INDOOR_CATEGORIES:
            return True
    name_lower = name.lower()
    # substring match — catches "Catedral de Barcelona" via "catedral"
    return any(hint in name_lower for hint in _INDOOR_NAME_HINTS)