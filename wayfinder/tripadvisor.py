from __future__ import annotations

import os
import time

import requests

from .models import Attraction, UserPreferences


TA_BASE = "https://api.content.tripadvisor.com/api/v1"


class TripAdvisorClient:
    """Small TripAdvisor Content API wrapper that tracks request count."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ["TRIPADVISOR_API_KEY"]
        self.session = requests.Session()
        self.session.headers.update({"accept": "application/json"})
        self._call_count = 0

    def _get(self, endpoint: str, params: dict) -> dict:
        params = dict(params)
        params["key"] = self.api_key
        response = self.session.get(f"{TA_BASE}/{endpoint}", params=params, timeout=15)
        self._call_count += 1
        response.raise_for_status()
        return response.json()

    def search_locations(
        self,
        query: str,
        category: str = "attractions",
        language: str = "en",
    ) -> list[dict]:
        data = self._get(
            "location/search",
            {
                "searchQuery": query,
                "category": category,
                "language": language,
            },
        )
        return data.get("data", [])

    def get_location_details(self, location_id: str, language: str = "en") -> dict:
        return self._get(
            f"location/{location_id}/details",
            {
                "language": language,
                "currency": "USD",
            },
        )

    def search_nearby(
        self,
        lat: float,
        lon: float,
        category: str = "attractions",
        radius: int = 5,
        unit: str = "km",
    ) -> list[dict]:
        data = self._get(
            "location/nearby_search",
            {
                "latLong": f"{lat},{lon}",
                "category": category,
                "radius": radius,
                "radiusUnit": unit,
            },
        )
        return data.get("data", [])

    def get_photos(self, location_id: str, limit: int = 1) -> list[str]:
        data = self._get(f"location/{location_id}/photos", {"limit": limit})
        urls: list[str] = []
        for item in data.get("data", []):
            for size in ("original", "large", "medium"):
                image = item.get("images", {}).get(size, {})
                if image.get("url"):
                    urls.append(image["url"])
                    break
        return urls

    def get_reviews(self, location_id: str, limit: int = 5) -> list[str]:
        data = self._get(f"location/{location_id}/reviews", {"limit": limit})
        return [review.get("text", "") for review in data.get("data", [])]


def parse_attraction(raw: dict, details: dict) -> Attraction:
    """Merge a TripAdvisor search result and details payload."""

    address_obj = details.get("address_obj", {})
    subcategories = [
        item.get("localized_name", "") for item in details.get("subcategory", [])
    ]
    cuisines = [item.get("localized_name", "") for item in details.get("cuisine", [])]

    return Attraction(
        location_id=details.get("location_id") or raw.get("location_id", ""),
        name=details.get("name") or raw.get("name", ""),
        category=(details.get("category") or {}).get("localized_name", ""),
        subcategories=subcategories,
        rating=float(details.get("rating") or 0),
        num_reviews=int(details.get("num_reviews") or 0),
        address=address_obj.get("address_string", ""),
        latitude=float(details.get("latitude") or 0),
        longitude=float(details.get("longitude") or 0),
        web_url=details.get("web_url", ""),
        price_level=details.get("price_level", ""),
        cuisine_types=cuisines,
        hours=details.get("hours", {}),
        booking_url=(details.get("booking") or {}).get("url", ""),
    )


def fetch_attractions(
    ta: TripAdvisorClient,
    prefs: UserPreferences,
    categories: list[str] | None = None,
    max_per_category: int = 20,
    sleep_s: float = 0.15,
) -> list[Attraction]:
    """Fetch candidate attractions/restaurants from TripAdvisor."""

    categories = categories or ["attractions", "restaurants"]
    attractions: list[Attraction] = []

    for category in categories:
        print(f"  [TA] searching '{category}' in {prefs.destination}...")
        results = ta.search_locations(prefs.destination, category=category)
        for result in results[:max_per_category]:
            try:
                details = ta.get_location_details(result["location_id"])
                attraction = parse_attraction(result, details)
                photos = ta.get_photos(result["location_id"], limit=1)
                if photos:
                    attraction.photo_url = photos[0]
                attractions.append(attraction)
                time.sleep(sleep_s)
            except Exception as exc:
                print(f"    skip '{result.get('name', '?')}': {exc}")

    fetched_names = {attraction.name.lower() for attraction in attractions}
    for required_name in prefs.required_attractions:
        if required_name.lower() in fetched_names:
            continue
        print(f"  [TA] required '{required_name}' not in results - explicit search...")
        results = ta.search_locations(required_name, category="attractions")
        for result in results[:3]:
            try:
                details = ta.get_location_details(result["location_id"])
                attractions.append(parse_attraction(result, details))
                time.sleep(sleep_s)
            except Exception:
                pass

    print(f"  [TA] fetched {len(attractions)} raw locations ({ta._call_count} API calls used)")
    return attractions
