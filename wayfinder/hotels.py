"""
wayfinder/hotels.py
────────────────────
Hotel search via TripAdvisor, soft-scored by budget tier.

CHANGES vs. previous version:
  - Uses new cached client automatically.
  - Soft-scoring on budget keywords instead of binary keep/drop.
  - Photos fetched ONLY for final top-N.
  - Booking links come from the shared booking_links module.
"""
from __future__ import annotations

import time

from .filtering.booking_links import generate_hotel_booking_links
from .models import Attraction, UserPreferences
from .tripadvisor import TripAdvisorClient, parse_attraction


BUDGET_HOTEL_SUBCATS: dict[str, list[str]] = {
    "budget":    ["hostel", "motel", "budget hotel", "inn", "guesthouse"],
    "mid-range": ["hotel", "boutique hotel", "bed and breakfast", "inn"],
    "luxury":    ["resort", "luxury hotel", "5-star", "spa hotel", "villa"],
}


class HotelFinder:
    def __init__(self, ta: TripAdvisorClient):
        self.ta = ta

    def find_hotels(self, prefs: UserPreferences,
                    top_n: int = 5, max_fetch: int = 15) -> list[Attraction]:
        print(f"  [hotels] searching in {prefs.destination}…")
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

        target_cats = BUDGET_HOTEL_SUBCATS.get(prefs.budget, [])
        def budget_score(h: Attraction) -> int:
            tags = " ".join(h.subcategories).lower()
            return sum(1 for kw in target_cats if kw in tags)

        hotels.sort(
            key=lambda h: (budget_score(h), h.rating, h.num_reviews),
            reverse=True,
        )
        ranked = hotels[:top_n]

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