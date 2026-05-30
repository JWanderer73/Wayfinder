"""
wayfinder/models.py
────────────────────
Shared dataclasses used across the entire pipeline.

FIXES in this version:
  - PipelineResult: gaps split into gaps_text (raw string) + gaps_structured
    (list of dicts) so both human readers and the frontend can consume it.
  - PipelineResult: total_mandatory counts mandatory items across both
    attractions[] and restaurants[], fixing the off-by-one in the summary.
  - PipelineResult.to_dict(): mandatory_count in summary now uses total_mandatory.
  - Hotel score: hotels carry score=None to distinguish "not scored" from "bad".
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any


# ── selection source constants ────────────────────────────────────────────────
SOURCE_USER_REQUIRED     = "user_required"
SOURCE_RANKED            = "ranked"
SOURCE_COMPLETENESS      = "completeness"
SOURCE_SWAP              = "swap"
SOURCE_RESTAURANT_INJECT = "restaurant_inject"


# ── user preferences ──────────────────────────────────────────────────────────
@dataclass
class UserPreferences:
    destination: str
    travel_dates: tuple[str, str] = ("", "")
    budget: str = "mid-range"
    vibe: str = ""
    dietary_restrictions: list[str] = field(default_factory=list)
    required_attractions: list[str] = field(default_factory=list)
    num_travelers: int = 2
    trip_shape: str = "balanced"
    weather_summary: str = ""
    travel_mode: str = "DRIVE"


# ── attraction / restaurant / hotel ──────────────────────────────────────────
@dataclass
class Attraction:
    """One point of interest. Used for attractions, restaurants, AND hotels."""
    location_id: str
    name: str
    category: str
    subcategories: list[str]
    rating: float
    num_reviews: int
    address: str
    latitude: float
    longitude: float
    web_url: str
    photo_url: str = ""
    price_level: str = ""
    cuisine_types: list[str] = field(default_factory=list)
    hours: dict = field(default_factory=dict)
    open_hours_text: list[str] = field(default_factory=list)
    booking_url: str = ""
    booking_links: dict = field(default_factory=dict)
    duration_minutes: int = 90
    place_id: str = ""

    # ranking — score is float for attractions, None for hotels
    score: float | None = 0.0
    score_reason: str = ""
    ranker_used: str = ""
    confidence: float = 0.7

    # flags
    is_outdoor: bool = False
    is_indoor: bool = False
    diversity_penalty: float = 0.0
    is_mandatory: bool = False
    selection_source: str = SOURCE_RANKED

    def to_dict(self) -> dict:
        return asdict(self)


# ── pipeline result ───────────────────────────────────────────────────────────
@dataclass
class PipelineResult:
    """Structured return type for the whole pipeline."""
    trip_id: str
    destination: str
    preferences: dict[str, Any]

    attractions: list[Attraction]
    restaurants: list[Attraction]
    hotels: list[Attraction]

    candidate_pool: list[Attraction] = field(default_factory=list)
    restaurant_pool: list[Attraction] = field(default_factory=list)

    # FIX 5: dual gaps representation
    gaps_text: str = ""           # raw string for human reading
    gaps_structured: list[dict] = field(default_factory=list)  # for frontend parsing

    api_calls: int = 0
    cache_hits: int = 0
    weather_summary: str = ""
    travel_mode: str = "DRIVE"

    # FIX 2: counts mandatory across both attractions and restaurants
    total_mandatory: int = 0

    @property
    def mandatory_count(self) -> int:
        """Mandatory attractions only (for routing stage)."""
        return sum(1 for a in self.attractions if a.is_mandatory)

    @property
    def suggested_count(self) -> int:
        return sum(1 for a in self.attractions if not a.is_mandatory)

    @property
    def selected_hotel(self) -> Attraction | None:
        return self.hotels[0] if self.hotels else None

    def to_dict(self) -> dict:
        return {
            "trip_id":          self.trip_id,
            "destination":      self.destination,
            "travel_mode":      self.travel_mode,
            "preferences":      self.preferences,
            "weather_summary":  self.weather_summary,

            "attractions":      [a.to_dict() for a in self.attractions],
            "restaurants":      [r.to_dict() for r in self.restaurants],

            "selected_hotel":   self.selected_hotel.to_dict() if self.selected_hotel else None,
            "hotels":           [h.to_dict() for h in self.hotels],

            "candidate_pool":   [a.to_dict() for a in self.candidate_pool],
            "restaurant_pool":  [r.to_dict() for r in self.restaurant_pool],

            # FIX 5: both representations in output
            "gaps":             self.gaps_text,
            "gaps_structured":  self.gaps_structured,

            "api_calls":        self.api_calls,
            "cache_hits":       self.cache_hits,

            "summary": {
                # FIX 2: total_mandatory is the accurate cross-list count
                "mandatory_count":       self.total_mandatory,
                "mandatory_attractions": self.mandatory_count,
                "suggested_count":       self.suggested_count,
                "restaurant_count":      len(self.restaurants),
                "hotel_count":           len(self.hotels),
                "travel_mode":           self.travel_mode,
                "selected_hotel_name":   self.selected_hotel.name if self.selected_hotel else None,
            },
        }


# ── trip-shape presets ────────────────────────────────────────────────────────
TRIP_SHAPE_PRESETS: dict[str, dict[str, Any]] = {
    "relaxed":  {"daily_minutes_budget": 360, "max_stops_per_day": 3, "day_start_time": "10:00"},
    "balanced": {"daily_minutes_budget": 480, "max_stops_per_day": 5, "day_start_time": "09:00"},
    "packed":   {"daily_minutes_budget": 600, "max_stops_per_day": 7, "day_start_time": "08:00"},
}