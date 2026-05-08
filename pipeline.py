"""
wayfinder/pipeline.py
──────────────────────
Orchestrates the full pipeline:
  fetch → filter → rank → pin required → attach links → hotel search → gap check

This is the single function the CLI (main.py) calls.
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
from .ranking_gemini import GeminiRanker as Ranker


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

    Parameters
    ----------
    city                 : destination city / region
    preferences          : free-form strings merged into vibe (CLI compat)
    k                    : number of attractions to return
    budget               : "budget" | "mid-range" | "luxury"
    vibe                 : short description of travel style
    dietary_restrictions : e.g. ["vegan", "gluten-free"]
    required_attractions : attraction names that must appear in output
    travel_dates         : ("YYYY-MM-DD", "YYYY-MM-DD")
    num_travelers        : group size
    categories           : TA categories to search (default: attractions + restaurants)
    check_completeness   : run LLM gap analysis on the final shortlist
    include_hotels       : also return hotel recommendations

    Returns
    -------
    dict with keys:
      attractions : list[dict]   – ranked, top-k
      hotels      : list[dict]   – top 5 hotels (empty if include_hotels=False)
      gaps        : str          – LLM completeness note (empty string if skipped)
      api_calls   : int          – TripAdvisor API calls consumed this run
    """
    # merge CLI preferences list into vibe string
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

    # ── 1. fetch ─────────────────────────────────────────────────────────────
    print(f"\n🔍 Fetching attractions for: {city}")
    raw = fetch_attractions(ta, prefs, categories=categories)

    # ── 2. filter ────────────────────────────────────────────────────────────
    filtered = AttractionFilter(prefs).filter(raw)

    # ── 3. rank ──────────────────────────────────────────────────────────────
    ranker = Ranker()
    print(f"🤖 Ranking {len(filtered)} attractions with {ranker.__class__.__name__}…")
    ranked = ranker.rank(filtered, prefs)

    # ── 4. pin required attractions to top ───────────────────────────────────
    req_lower  = {n.lower() for n in prefs.required_attractions}
    pinned     = [a for a in ranked if a.name.lower() in req_lower]
    rest       = [a for a in ranked if a.name.lower() not in req_lower]
    top: list[Attraction] = (pinned + rest)[:k]

    # ── 5. attach booking links ───────────────────────────────────────────────
    for a in top:
        links          = generate_booking_links(a, prefs)
        a.booking_links = links
        # also set the primary booking_url field for convenience
        if not a.booking_url and links.get("TripAdvisor"):
            a.booking_url = links["TripAdvisor"]

    # ── 6. LLM completeness check ─────────────────────────────────────────────
    gaps = ""
    if check_completeness and isinstance(ranker, Ranker) and hasattr(ranker, "check_completeness"):
        print("🔎 Checking completeness…")
        gaps = ranker.check_completeness(top, prefs)

    # ── 7. hotels ─────────────────────────────────────────────────────────────
    hotel_list: list[Attraction] = []
    if include_hotels:
        hotel_list = HotelFinder(ta).find_hotels(prefs)

    print(f"\n✨ Done. {ta._call_count} TripAdvisor API calls used.")

    return {
        "attractions": [a.to_dict() for a in top],
        "hotels":      [h.to_dict() for h in hotel_list],
        "gaps":        gaps,
        "api_calls":   ta._call_count,
    }
