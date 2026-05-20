"""
wayfinder/pipeline.py
──────────────────────
Orchestrates the full recommendation pipeline:
  fetch → filter → rank → pin required → attach links → hotel search → gap check

Swap rankers by changing the import line marked with ← SWAP HERE.
"""
from __future__ import annotations
import os
from dataclasses import asdict

from .models import Attraction, UserPreferences
from .tripadvisor import TripAdvisorClient, fetch_attractions
from .filters import AttractionFilter, generate_booking_links
from .hotels import HotelFinder

# ← SWAP HERE to use the ML ranker instead:
#   from .ranking import MLRanker as Ranker
from .ranking import GeminiRanker as Ranker


def generate_recommendations(
    city: str,
    preferences: list[str] | None = None,
    k: int = 10,
    budget: str = "mid-range",
    vibe: str = "",
    dietary_restrictions: list[str] | None = None,
    required_attractions: list[str] | None = None,
    travel_dates: tuple[str, str] = ("", ""),
    num_travelers: int = 2,
    categories: list[str] | None = None,
    check_completeness: bool = True,
    include_hotels: bool = True,
) -> dict:
    """
    Full pipeline entry point.

    Returns dict with keys: attractions, hotels, gaps, api_calls.
    """
    if preferences:
        combined_vibe = ", ".join(filter(None, [vibe] + list(preferences)))
    else:
        combined_vibe = vibe

    prefs = UserPreferences(
        destination          = city,
        travel_dates         = travel_dates,
        budget               = budget,
        vibe                 = combined_vibe,
        dietary_restrictions = list(dietary_restrictions or []),
        required_attractions = list(required_attractions or []),
        num_travelers        = num_travelers,
    )

    api_key = os.environ["TRIPADVISOR_API_KEY"]
    ta      = TripAdvisorClient(api_key)

    print(f"\n Fetching attractions for: {city}")
    raw = fetch_attractions(ta, prefs, categories=categories)

    filtered = AttractionFilter(prefs).filter(raw)

    ranker = Ranker()
    print(f" Ranking {len(filtered)} attractions with {ranker.__class__.__name__}...")
    ranked = ranker.rank(filtered, prefs)

    req_lower  = {n.lower() for n in prefs.required_attractions}
    pinned     = [a for a in ranked if a.name.lower() in req_lower]
    rest       = [a for a in ranked if a.name.lower() not in req_lower]
    top: list[Attraction] = (pinned + rest)[:k]

    for a in top:
        links          = generate_booking_links(a, prefs)
        a.booking_links = links
        if not a.booking_url and links.get("TripAdvisor"):
            a.booking_url = links["TripAdvisor"]

    gaps = ""
    if check_completeness and isinstance(ranker, Ranker) and hasattr(ranker, "check_completeness"):
        print(" Checking completeness...")
        gaps = ranker.check_completeness(top, prefs)

    hotel_list: list[Attraction] = []
    if include_hotels:
        hotel_list = HotelFinder(ta).find_hotels(prefs)

    print(f"\n Done. {ta._call_count} TripAdvisor API calls used.")

    return {
        "attractions": [a.to_dict() for a in top],
        "hotels":      [h.to_dict() for h in hotel_list],
        "gaps":        gaps,
        "api_calls":   ta._call_count,
    }
