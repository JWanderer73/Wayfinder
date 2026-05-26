"""
wayfinder/models.py
────────────────────
Shared dataclasses used across the entire pipeline.

CHANGES vs. previous version:
  - Attraction: added `confidence` (0.0–1.0)
  - Attraction: added `is_outdoor` / `is_indoor` flags for weather logic
  - Attraction: added `diversity_penalty` (set during reranking)
  - Attraction: added `is_mandatory` and `selection_source` — see notes below
  - UserPreferences: added `trip_shape`, `weather_summary`
  - PipelineResult: new dataclass — clean return with candidate pools for swap

MANDATORY vs SUGGESTED — the new UI distinction
─────────────────────────────────────────────
Every attraction in the output is one of two kinds:

  📌 MANDATORY  – the user explicitly typed this name in their request
                   (e.g. "Eiffel Tower"). These attractions:
                     - are always pinned to the top of the active list
                     - are never penalised by diversity reranking
                     - cannot be removed by the swap-candidates flow
                     - get rendered with a lock badge in the UI

  ⭐ SUGGESTED  – the system picked these for the user based on ranking.
                   These are freely swappable through the candidate-pool flow.

`is_mandatory` is the boolean the UI checks. `selection_source` records WHY
the attraction is in the list, so the UI can show context like "you asked
for this" vs. "we picked this because it matches your vibe."
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any


# ── selection source enum-like constants ─────────────────────────────────────
# These are strings (not an enum) for JSON-friendliness — the routing stage
# and a future frontend can read them without importing Python types.
SOURCE_USER_REQUIRED = "user_required"   # user typed this name in
SOURCE_RANKED        = "ranked"          # made the cut via scoring
SOURCE_COMPLETENESS  = "completeness"    # LLM gap check suggested it
SOURCE_SWAP          = "swap"            # user manually swapped it in
SOURCE_RESTAURANT_INJECT = "restaurant_inject"  # injected near a cluster centroid


# ── user-side input ──────────────────────────────────────────────────────────
@dataclass
class UserPreferences:
    """All user-supplied inputs in one place."""
    destination: str
    travel_dates: tuple[str, str] = ("", "")
    budget: str = "mid-range"                    # "budget" | "mid-range" | "luxury"
    vibe: str = ""
    dietary_restrictions: list[str] = field(default_factory=list)
    required_attractions: list[str] = field(default_factory=list)
    num_travelers: int = 2

    # NEW: trip pace — separate from budget. Controls daily_minutes_budget,
    # max_stops_per_day, and day_start_time when handed to the routing stage.
    trip_shape: str = "balanced"                 # "relaxed" | "balanced" | "packed"

    # NEW: short human-readable weather summary for the trip dates, fetched
    # by pipeline.py from a free weather API. Empty string if unknown.
    weather_summary: str = ""


# ── attraction / restaurant / hotel (same shape, different roles) ────────────
@dataclass
class Attraction:
    """
    One point of interest returned from TripAdvisor + enriched by our pipeline.

    Used for attractions, restaurants, AND hotels — the shape is identical;
    they differ only in `category` and how downstream code routes them.
    """
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

    # ── ranking outputs ──────────────────────────────────────────────────
    score: float = 0.0
    score_reason: str = ""
    ranker_used: str = ""               # "gemini" | "ml" | "heuristic"

    # confidence (0.0–1.0). Low confidence → "you might like this" treatment
    # in the UI. Defaults to 0.7 so heuristic fallbacks aren't overconfident.
    confidence: float = 0.7

    # ── derived weather/diversity flags ──────────────────────────────────
    is_outdoor: bool = False
    is_indoor: bool = False
    diversity_penalty: float = 0.0

    # ── MANDATORY vs SUGGESTED (see module docstring) ────────────────────
    is_mandatory: bool = False
    selection_source: str = SOURCE_RANKED

    def to_dict(self) -> dict:
        return asdict(self)


# ── full pipeline result ─────────────────────────────────────────────────────
@dataclass
class PipelineResult:
    """
    Structured return type for the whole pipeline.

    NEW in this version — replaces the loose dict from before.
    Has separate lists for attractions / restaurants / hotels and saves the
    full ranked pool so the swap-candidates feature works without re-fetching.
    """
    trip_id: str
    destination: str
    preferences: dict[str, Any]

    # the active top-k that goes to the routing stage
    attractions: list[Attraction]

    # separated out — routing stage clusters attractions first, then the
    # bridge injects restaurants near each cluster's centroid
    restaurants: list[Attraction]

    # hotels (top N by rating, filtered by budget tier)
    hotels: list[Attraction]

    # the FULL ranked list (not just top-k). Used by the swap-candidates
    # endpoint — when the user rejects activity #4, we serve #11, #12, …
    # from this list without re-hitting any APIs.
    candidate_pool: list[Attraction] = field(default_factory=list)
    restaurant_pool: list[Attraction] = field(default_factory=list)

    # LLM gap analysis
    gaps: str = ""

    # diagnostics
    api_calls: int = 0
    cache_hits: int = 0
    weather_summary: str = ""

    # ── derived counts for the UI ────────────────────────────────────────
    @property
    def mandatory_count(self) -> int:
        return sum(1 for a in self.attractions if a.is_mandatory)

    @property
    def suggested_count(self) -> int:
        return sum(1 for a in self.attractions if not a.is_mandatory)

    def to_dict(self) -> dict:
        return {
            "trip_id":         self.trip_id,
            "destination":     self.destination,
            "preferences":     self.preferences,
            "attractions":     [a.to_dict() for a in self.attractions],
            "restaurants":     [r.to_dict() for r in self.restaurants],
            "hotels":          [h.to_dict() for h in self.hotels],
            "candidate_pool":  [a.to_dict() for a in self.candidate_pool],
            "restaurant_pool": [r.to_dict() for r in self.restaurant_pool],
            "gaps":            self.gaps,
            "api_calls":       self.api_calls,
            "cache_hits":      self.cache_hits,
            "weather_summary": self.weather_summary,
            # helpful for the UI to show at a glance:
            "summary": {
                "mandatory_count": self.mandatory_count,
                "suggested_count": self.suggested_count,
                "restaurant_count": len(self.restaurants),
                "hotel_count":     len(self.hotels),
            },
        }


# ── trip-shape presets ───────────────────────────────────────────────────────
# Centralised here so the CLI, bridge, and frontend agree on the values.
TRIP_SHAPE_PRESETS: dict[str, dict[str, Any]] = {
    "relaxed": {
        "daily_minutes_budget":  360,    # 6 hours of "doing things"
        "max_stops_per_day":     3,
        "day_start_time":        "10:00",
    },
    "balanced": {
        "daily_minutes_budget":  480,    # 8 hours
        "max_stops_per_day":     5,
        "day_start_time":        "09:00",
    },
    "packed": {
        "daily_minutes_budget":  600,    # 10 hours
        "max_stops_per_day":     7,
        "day_start_time":        "08:00",
    },
}