from __future__ import annotations

import os

from .filters import AttractionFilter, generate_booking_links
from .hotels import HotelFinder
from .models import Attraction, UserPreferences
from .ranking import GeminiRanker as Ranker
from .tripadvisor import TripAdvisorClient, fetch_attractions


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
    """Fetch, filter, rank, and enrich travel recommendations."""

    combined_vibe = (
        ", ".join(filter(None, [vibe] + list(preferences)))
        if preferences
        else vibe
    )
    prefs = UserPreferences(
        destination=city,
        travel_dates=travel_dates,
        budget=budget,
        vibe=combined_vibe,
        dietary_restrictions=list(dietary_restrictions or []),
        required_attractions=list(required_attractions or []),
        num_travelers=num_travelers,
    )

    api_key = os.environ["TRIPADVISOR_API_KEY"]
    tripadvisor = TripAdvisorClient(api_key)

    print(f"\nFetching attractions for: {city}")
    raw = fetch_attractions(tripadvisor, prefs, categories=categories)
    filtered = AttractionFilter(prefs).filter(raw)

    ranker = Ranker()
    print(f"Ranking {len(filtered)} attractions with {ranker.__class__.__name__}...")
    ranked = ranker.rank(filtered, prefs)

    required_lower = {name.lower() for name in prefs.required_attractions}
    pinned = [item for item in ranked if item.name.lower() in required_lower]
    rest = [item for item in ranked if item.name.lower() not in required_lower]
    top: list[Attraction] = (pinned + rest)[:k]

    for attraction in top:
        links = generate_booking_links(attraction, prefs)
        attraction.booking_links = links
        if not attraction.booking_url and links.get("TripAdvisor"):
            attraction.booking_url = links["TripAdvisor"]

    gaps = ""
    if check_completeness and hasattr(ranker, "check_completeness"):
        print("Checking completeness...")
        gaps = ranker.check_completeness(top, prefs)

    hotels: list[Attraction] = []
    if include_hotels:
        hotels = HotelFinder(tripadvisor).find_hotels(prefs)

    print(f"\nDone. {tripadvisor._call_count} TripAdvisor API calls used.")
    return {
        "attractions": [attraction.to_dict() for attraction in top],
        "hotels": [hotel.to_dict() for hotel in hotels],
        "gaps": gaps,
        "api_calls": tripadvisor._call_count,
    }
