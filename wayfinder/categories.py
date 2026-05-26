"""
wayfinder/categories.py
────────────────────────
Single source of truth for category vocabulary.

PURPOSE
  Previously, tripadvisor.py had _CATEGORY_DURATION and bridge.py had
  _TA_CATEGORY_TO_ROUTING — two parallel maps that would drift out of sync
  whenever someone added a category to one but not the other.

  This file centralises both, plus outdoor/indoor flags for weather-aware
  ranking, so any new category is added in exactly one place.
"""
from __future__ import annotations

# ── canonical routing-stage vocabulary ────────────────────────────────────────
ROUTING_CATEGORIES: frozenset[str] = frozenset({
    "landmark", "museum", "restaurant", "food", "nightlife",
    "park", "beach", "shopping", "market", "tour", "relaxation",
    "hike", "viewpoint", "religious", "entertainment",
})


# ── duration estimates (minutes) ──────────────────────────────────────────────
CATEGORY_DURATION_MIN: dict[str, int] = {
    "attraction": 75, "attractions": 75, "sights & landmarks": 60, "landmark": 75,
    "museum": 150, "art museum": 150, "gallery": 120, "historic site": 90,
    "religious site": 60, "temple": 60, "shrine": 60,
    "church": 45, "cathedral": 60, "mosque": 45,
    "park": 75, "nature & parks": 75, "garden": 75,
    "beach": 150, "hike": 180, "trail": 180,
    "viewpoint": 60, "observation deck": 60,
    "zoo": 180, "aquarium": 150,
    "shopping": 90, "market": 90,
    "food & drink": 75, "restaurant": 75, "restaurants": 75,
    "cafe": 45, "bar": 60, "nightlife": 120,
    "tour": 120, "tours": 120, "activities": 90,
    "spa": 120, "entertainment": 90,
    "water park": 240, "amusement park": 300,
    "theater": 150, "concert": 150,
}


# ── TripAdvisor → routing-stage category map ─────────────────────────────────
TA_TO_ROUTING_CATEGORY: dict[str, str] = {
    "attraction": "landmark", "attractions": "landmark",
    "sights & landmarks": "landmark", "historic site": "landmark", "landmark": "landmark",
    "observation deck": "viewpoint", "viewpoint": "viewpoint",
    "museum": "museum", "art museum": "museum", "gallery": "museum",
    "religious site": "religious", "temple": "religious", "shrine": "religious",
    "church": "religious", "cathedral": "religious", "mosque": "religious",
    "restaurant": "restaurant", "restaurants": "restaurant",
    "food & drink": "food", "cafe": "food",
    "bar": "nightlife", "nightlife": "nightlife",
    "park": "park", "nature & parks": "park", "garden": "park",
    "beach": "beach", "hike": "hike", "trail": "hike",
    "shopping": "shopping", "market": "market",
    "tour": "tour", "tours": "tour", "activities": "tour",
    "spa": "relaxation",
    "entertainment": "entertainment", "theater": "entertainment", "concert": "entertainment",
    "amusement park": "entertainment", "water park": "entertainment",
    "zoo": "entertainment", "aquarium": "entertainment",
}


# ── seasonality flags ────────────────────────────────────────────────────────
OUTDOOR_CATEGORIES: frozenset[str] = frozenset({
    "beach", "park", "garden", "hike", "trail",
    "viewpoint", "observation deck", "nature & parks",
    "water park", "amusement park",
})

INDOOR_CATEGORIES: frozenset[str] = frozenset({
    "museum", "art museum", "gallery", "aquarium",
    "shopping", "market", "theater", "spa",
    "restaurant", "cafe", "bar",
})


# ── helpers ──────────────────────────────────────────────────────────────────
def estimate_duration(category: str, subcategories: list[str] | None = None) -> int:
    """Best-guess visit time in minutes. Falls back to 90."""
    subs = subcategories or []
    for label in [category, *subs]:
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


def is_outdoor(category: str, subcategories: list[str] | None = None) -> bool:
    """True if this attraction is primarily outdoor (weather-sensitive)."""
    subs = subcategories or []
    for label in [category, *subs]:
        if (label or "").strip().lower() in OUTDOOR_CATEGORIES:
            return True
    return False


def is_indoor(category: str, subcategories: list[str] | None = None) -> bool:
    """True if this attraction is primarily indoor (weather-safe)."""
    subs = subcategories or []
    for label in [category, *subs]:
        if (label or "").strip().lower() in INDOOR_CATEGORIES:
            return True
    return False