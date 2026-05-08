"""
wayfinder/tripadvisor.py
─────────────────────────
Thin wrapper around TripAdvisor Content API v1.
Tracks call count vs. the 5 000-request free-tier limit.
"""
from __future__ import annotations
import os
import time

import requests

from .models import Attraction, UserPreferences

TA_BASE = "https://api.content.tripadvisor.com/api/v1"


class TripAdvisorClient:
    """All raw HTTP calls to TripAdvisor live here."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ["TRIPADVISOR_API_KEY"]
        self.session = requests.Session()
        self.session.headers.update({"accept": "application/json"})
        self._call_count = 0   # monitor free-tier usage

    # ── internal ──────────────────────────────────────────────────────────────
    def _get(self, endpoint: str, params: dict) -> dict:
        params = dict(params)          # don't mutate caller's dict
        params["key"] = self.api_key
        url = f"{TA_BASE}/{endpoint}"
        resp = self.session.get(url, params=params, timeout=15)
        self._call_count += 1
        resp.raise_for_status()
        return resp.json()

    # ── public methods ────────────────────────────────────────────────────────
    def search_locations(self, query: str, category: str = "attractions",
                         language: str = "en") -> list[dict]:
        """
        Text search – returns a list of raw location dicts.
        Each dict has at minimum: location_id, name, address_obj.
        """
        data = self._get("location/search", {
            "searchQuery": query,
            "category":    category,
            "language":    language,
        })
        return data.get("data", [])

    def get_location_details(self, location_id: str,
                             language: str = "en") -> dict:
        """Full details for one location: rating, coords, price, hours, etc."""
        return self._get(f"location/{location_id}/details", {
            "language": language,
            "currency": "USD",
        })

    def search_nearby(self, lat: float, lon: float,
                      category: str = "attractions",
                      radius: int = 5, unit: str = "km") -> list[dict]:
        """Proximity search – good fallback when text search returns few hits."""
        data = self._get("location/nearby_search", {
            "latLong":    f"{lat},{lon}",
            "category":   category,
            "radius":     radius,
            "radiusUnit": unit,
        })
        return data.get("data", [])

    def get_photos(self, location_id: str, limit: int = 1) -> list[str]:
        """Return up to `limit` photo URLs (tries original → large → medium)."""
        data = self._get(f"location/{location_id}/photos", {"limit": limit})
        urls: list[str] = []
        for item in data.get("data", []):
            for size in ("original", "large", "medium"):
                img = item.get("images", {}).get(size, {})
                if img.get("url"):
                    urls.append(img["url"])
                    break
        return urls

    def get_reviews(self, location_id: str, limit: int = 5) -> list[str]:
        """Return review text snippets (useful as LLM context)."""
        data = self._get(f"location/{location_id}/reviews", {"limit": limit})
        return [r.get("text", "") for r in data.get("data", [])]


# ── helpers ────────────────────────────────────────────────────────────────────
def parse_attraction(raw: dict, details: dict) -> Attraction:
    """Merge a search-result stub + a details response into an Attraction."""
    addr_obj  = details.get("address_obj", {})
    subcats   = [s.get("localized_name", "") for s in details.get("subcategory", [])]
    cuisines  = [c.get("localized_name", "") for c in details.get("cuisine", [])]

    return Attraction(
        location_id   = details.get("location_id") or raw.get("location_id", ""),
        name          = details.get("name")         or raw.get("name", ""),
        category      = (details.get("category") or {}).get("localized_name", ""),
        subcategories = subcats,
        rating        = float(details.get("rating")      or 0),
        num_reviews   = int(  details.get("num_reviews") or 0),
        address       = addr_obj.get("address_string", ""),
        latitude      = float(details.get("latitude")  or 0),
        longitude     = float(details.get("longitude") or 0),
        web_url       = details.get("web_url", ""),
        price_level   = details.get("price_level", ""),
        cuisine_types = cuisines,
        hours         = details.get("hours", {}),
        booking_url   = (details.get("booking") or {}).get("url", ""),
    )


def fetch_attractions(ta: TripAdvisorClient,
                      prefs: UserPreferences,
                      categories: list[str] | None = None,
                      max_per_category: int = 20,
                      sleep_s: float = 0.15) -> list[Attraction]:
    """
    Fetch raw Attraction objects from TripAdvisor for all requested categories.
    Also ensures required_attractions are always included.
    """
    if categories is None:
        categories = ["attractions", "restaurants"]

    attractions: list[Attraction] = []

    for cat in categories:
        print(f"  [TA] searching '{cat}' in {prefs.destination}…")
        results = ta.search_locations(prefs.destination, category=cat)
        for r in results[:max_per_category]:
            try:
                details = ta.get_location_details(r["location_id"])
                a = parse_attraction(r, details)
                photos = ta.get_photos(r["location_id"], limit=1)
                if photos:
                    a.photo_url = photos[0]
                attractions.append(a)
                time.sleep(sleep_s)
            except Exception as exc:
                print(f"    skip '{r.get('name', '?')}': {exc}")

    # guarantee every required attraction is present
    fetched_names = {a.name.lower() for a in attractions}
    for req in prefs.required_attractions:
        if req.lower() not in fetched_names:
            print(f"  [TA] required '{req}' not in results – explicit search…")
            results = ta.search_locations(req, category="attractions")
            for r in results[:3]:
                try:
                    details = ta.get_location_details(r["location_id"])
                    attractions.append(parse_attraction(r, details))
                    time.sleep(sleep_s)
                except Exception:
                    pass

    print(f"  [TA] fetched {len(attractions)} raw locations "
          f"({ta._call_count} API calls used)")
    return attractions
