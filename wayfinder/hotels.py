"""
wayfinder/hotels.py
────────────────────
Hotel search via TripAdvisor, filtered and scored by budget tier.

FIX: The old soft-scoring checked subcategory keywords like "boutique hotel"
but TripAdvisor returns all hotels with subcategory="Hotel" — so the keyword
match always scored 0, and every run returned pure top-rated hotels regardless
of budget. Fixed to use price_level ($ / $$ / $$$ / $$$$) directly, which
TripAdvisor does populate on hotels.

Budget mapping:
  budget    → $  / $$          (prefer $, allow $$)
  mid-range → $$ / $$$         (prefer $$, allow $$$)
  luxury    → $$$ / $$$$       (prefer $$$, allow $$$$)

Hotels that exactly match the target tier get the highest priority.
Hotels one tier above/below get partial credit.
Hotels with no price_level data are kept (unknown ≠ wrong).
"""
from __future__ import annotations

import time

from .filtering.booking_links import generate_hotel_booking_links
from .models import Attraction, UserPreferences
from .tripadvisor import TripAdvisorClient, parse_attraction

# Maps budget → (ideal price levels, acceptable price levels)
BUDGET_PRICE_TIERS: dict[str, tuple[list[str], list[str]]] = {
    "budget":    (["$"],        ["$$"]),
    "mid-range": (["$$", "$$$"], ["$", "$$$$"]),
    "luxury":    (["$$$", "$$$$"], ["$$"]),
}


def _hotel_budget_score(h: Attraction, budget: str) -> int:
    """
    Score a hotel against the user's budget:
      2 = ideal tier match
      1 = one tier off (acceptable)
      0 = price unknown (neutral — don't penalise)
     -1 = clearly wrong tier
    """
    if not h.price_level:
        return 0   # unknown → neutral

    ideal, acceptable = BUDGET_PRICE_TIERS.get(budget, (["$$", "$$$"], ["$", "$$$$"]))
    if h.price_level in ideal:
        return 2
    if h.price_level in acceptable:
        return 1
    return -1


class HotelFinder:
    def __init__(self, ta: TripAdvisorClient):
        self.ta = ta

    def find_hotels(self, prefs: UserPreferences,
                    top_n: int = 5, max_fetch: int = 20) -> list[Attraction]:
        print(f"  [hotels] searching in {prefs.destination} (budget: {prefs.budget})…")
        raw_results = self.ta.search_locations(prefs.destination, category="hotels")

        hotels: list[Attraction] = []
        for r in raw_results[:max_fetch]:
            try:
                details = self.ta.get_location_details(r["location_id"])
                h = parse_attraction(r, details)
                if h.latitude == 0.0 and h.longitude == 0.0:
                    continue
                hotels.append(h)
                time.sleep(0.1)
            except Exception as exc:
                print(f"    skip hotel '{r.get('name', '?')}': {exc}")

        if not hotels:
            print("  [hotels] no hotels found")
            return []

        # Sort: budget match first, then by rating, then by review count
        hotels.sort(
            key=lambda h: (
                _hotel_budget_score(h, prefs.budget),
                h.rating,
                h.num_reviews,
            ),
            reverse=True,
        )

        # Log what we found to help debug budget mismatches
        for h in hotels[:top_n]:
            print(f"    {h.name[:40]:40s} {h.price_level or '?':5s} "
                  f"⭐{h.rating} ({h.num_reviews:,} reviews) "
                  f"[budget_score={_hotel_budget_score(h, prefs.budget)}]")

        ranked = hotels[:top_n]

        # Photos + booking links for top N only
        for h in ranked:
            try:
                photos = self.ta.get_photos(h.location_id, limit=1)
                if photos:
                    h.photo_url = photos[0]
                time.sleep(0.1)
            except Exception:
                pass
            h.booking_links = generate_hotel_booking_links(h)
            h.booking_url   = h.web_url

        print(f"  [hotels] returning {len(ranked)} hotels")
        return ranked