"""
wayfinder/hotels.py
────────────────────
Hotel search via TripAdvisor, filtered by budget tier.
"""
from __future__ import annotations
import time
import requests

from .models import Attraction, UserPreferences
from .tripadvisor import TripAdvisorClient, parse_attraction
from .filters import generate_booking_links

# Maps budget string → subcategory keywords we prefer
BUDGET_HOTEL_SUBCATS: dict[str, list[str]] = {
    "budget":    ["hostel", "motel", "budget hotel", "inn", "guesthouse"],
    "mid-range": ["hotel", "boutique hotel", "bed and breakfast", "inn"],
    "luxury":    ["resort", "luxury hotel", "5-star", "spa hotel", "villa"],
}


class HotelFinder:
    def __init__(self, ta: TripAdvisorClient):
        self.ta = ta

    def find_hotels(self, prefs: UserPreferences,
                    top_n: int = 5,
                    max_fetch: int = 15) -> list[Attraction]:
        """
        Search TripAdvisor for hotels in the destination,
        soft-filter by budget subcategory, return top_n by rating.
        """
        print(f"  [hotels] searching in {prefs.destination}…")
        raw_results = self.ta.search_locations(prefs.destination, category="hotels")
        hotels: list[Attraction] = []

        for r in raw_results[:max_fetch]:
            try:
                details = self.ta.get_location_details(r["location_id"])
                h = parse_attraction(r, details)
                hotels.append(h)
                time.sleep(0.1)
            except Exception as exc:
                print(f"    skip hotel '{r.get('name', '?')}': {exc}")

        # soft filter – if budget-matching subcategories exist, prefer them
        target_cats = BUDGET_HOTEL_SUBCATS.get(prefs.budget, [])
        if target_cats:
            preferred = [
                h for h in hotels
                if any(tc in " ".join(h.subcategories).lower() for tc in target_cats)
            ]
            if preferred:
                hotels = preferred


        ranked = sorted(hotels, key=lambda h: h.rating, reverse=True)[:top_n]

        # attach booking links to hotels too
        for h in ranked:
            h.booking_links = {
                "TripAdvisor": h.web_url,
                "Google Maps": f"https://www.google.com/maps/search/?api=1&query={h.latitude},{h.longitude}",
                "Booking.com": f"https://www.booking.com/search.html?ss={requests.utils.quote(h.name)}",
                "Hotels.com": f"https://www.hotels.com/search.do?q-destination={requests.utils.quote(h.name)}",
            }
            h.booking_url = h.web_url

        print(f"  [hotels] returning {len(ranked)} hotels")
        return ranked
