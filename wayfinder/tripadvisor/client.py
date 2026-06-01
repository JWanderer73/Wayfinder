"""
wayfinder/tripadvisor/client.py
────────────────────────────────
Thin wrapper around TripAdvisor Content API v1.

CHANGES vs. previous version:
  - Constructor accepts a ResponseCache (defaults to enabled).
  - _get() checks the cache before hitting the API.
  - Photo fetching is now on-demand (called by the pipeline AFTER ranking,
    for the top-k only — cuts ~30% of API calls per run).
"""
from __future__ import annotations

import os
import requests

from .cache import ResponseCache

TA_BASE = "https://api.content.tripadvisor.com/api/v1"


class TripAdvisorClient:
    """All raw HTTP calls to TripAdvisor live here."""

    def __init__(self, api_key: str | None = None,
                 cache: ResponseCache | None = None,
                 use_cache: bool = True):
        self.api_key = api_key or os.environ["TRIPADVISOR_API_KEY"]
        self.session = requests.Session()
        self.session.headers.update({"accept": "application/json"})
        self._call_count = 0
        self.cache = cache if cache is not None else ResponseCache(enabled=use_cache)

    def _get(self, endpoint: str, params: dict) -> dict:
        # cache check (key is built without the API key)
        cached = self.cache.get(endpoint, params)
        if cached is not None:
            return cached

        params = dict(params)
        params["key"] = self.api_key
        url = f"{TA_BASE}/{endpoint}"
        resp = self.session.get(url, params=params, timeout=15)
        self._call_count += 1
        resp.raise_for_status()
        payload = resp.json()

        # store (excluding API key from the cache key)
        self.cache.set(endpoint, {k: v for k, v in params.items() if k != "key"}, payload)
        return payload

    def search_locations(self, query: str, category: str = "attractions",
                         language: str = "en") -> list[dict]:
        data = self._get("location/search", {
            "searchQuery": query, "category": category, "language": language,
        })
        return data.get("data", [])

    def get_location_details(self, location_id: str,
                             language: str = "en") -> dict:
        return self._get(f"location/{location_id}/details", {
            "language": language, "currency": "USD",
        })

    def search_nearby(self, lat: float, lon: float,
                      category: str = "attractions",
                      radius: int = 5, unit: str = "km") -> list[dict]:
        data = self._get("location/nearby_search", {
            "latLong": f"{lat},{lon}", "category": category,
            "radius": radius, "radiusUnit": unit,
        })
        return data.get("data", [])

    def get_photos(self, location_id: str, limit: int = 1) -> list[str]:
        """Fetch photo URLs. Called ONLY for top-k after ranking."""
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
        data = self._get(f"location/{location_id}/reviews", {"limit": limit})
        return [r.get("text", "") for r in data.get("data", [])]

    @property
    def cache_hits(self) -> int:
        return self.cache.hits