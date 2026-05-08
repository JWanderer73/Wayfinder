"""
wayfinder/models.py
────────────────────
Shared dataclasses used across the entire pipeline.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict


@dataclass
class UserPreferences:
    """All user-supplied inputs in one place."""
    destination: str
    travel_dates: tuple[str, str] = ("", "")   # ("2025-07-01", "2025-07-07")
    budget: str = "mid-range"                   # "budget" | "mid-range" | "luxury"
    vibe: str = ""                              # "adventure" | "culture" | ...
    dietary_restrictions: list[str] = field(default_factory=list)
    required_attractions: list[str] = field(default_factory=list)
    num_travelers: int = 2


@dataclass
class Attraction:
    """One point of interest returned from TripAdvisor + enriched by our pipeline."""
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
    price_level: str = ""           # "$" | "$$" | "$$$" | "$$$$"
    cuisine_types: list[str] = field(default_factory=list)
    hours: dict = field(default_factory=dict)
    booking_url: str = ""           # direct booking link if TA provides one
    booking_links: dict = field(default_factory=dict)  # all platform links
    # ranking scores – filled in by whichever ranker is active
    score: float = 0.0
    score_reason: str = ""
    ranker_used: str = ""           # "llm" | "ml" | "heuristic"

    def to_dict(self) -> dict:
        return asdict(self)
