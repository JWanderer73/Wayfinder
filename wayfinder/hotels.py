from __future__ import annotations

import time

import requests

from .filters import generate_booking_links
from .models import Attraction, UserPreferences
from .tripadvisor import TripAdvisorClient, parse_attraction


BUDGET_HOTEL_SUBCATEGORIES: dict[str, list[str]] = {
    "budget": ["hostel", "motel", "budget hotel", "inn", "guesthouse"],
    "mid-range": ["hotel", "boutique hotel", "bed and breakfast", "inn"],
    "luxury": ["resort", "luxury hotel", "5-star", "spa hotel", "villa"],
}


class HotelFinder:
    def __init__(self, ta: TripAdvisorClient):
        self.ta = ta

    def find_hotels(
        self,
        prefs: UserPreferences,
        top_n: int = 5,
        max_fetch: int = 15,
    ) -> list[Attraction]:
        print(f"  [hotels] searching in {prefs.destination}...")
        raw_results = self.ta.search_locations(prefs.destination, category="hotels")
        hotels: list[Attraction] = []

        for result in raw_results[:max_fetch]:
            try:
                details = self.ta.get_location_details(result["location_id"])
                hotels.append(parse_attraction(result, details))
                time.sleep(0.1)
            except Exception as exc:
                print(f"    skip hotel '{result.get('name', '?')}': {exc}")

        target_subcategories = BUDGET_HOTEL_SUBCATEGORIES.get(prefs.budget, [])
        if target_subcategories:
            preferred = [
                hotel
                for hotel in hotels
                if any(
                    target in " ".join(hotel.subcategories).lower()
                    for target in target_subcategories
                )
            ]
            if preferred:
                hotels = preferred

        ranked = sorted(hotels, key=lambda hotel: hotel.rating, reverse=True)[:top_n]

        for hotel in ranked:
            hotel.booking_links = generate_booking_links(hotel, prefs)
            hotel.booking_links["Booking.com"] = (
                "https://www.booking.com/search.html?ss="
                f"{requests.utils.quote(hotel.name)}"
            )
            hotel.booking_links["Hotels.com"] = (
                "https://www.hotels.com/search.do?q-destination="
                f"{requests.utils.quote(hotel.name)}"
            )
            hotel.booking_url = hotel.web_url

        print(f"  [hotels] returning {len(ranked)} hotels")
        return ranked
