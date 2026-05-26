"""
wayfinder/tripadvisor/cache.py
───────────────────────────────
Disk-based cache for TripAdvisor responses.

WHY THIS EXISTS
  TripAdvisor's free tier is 5,000 calls/month. A single test run with two
  categories and 20 results each was eating ~120 calls. Two iterations of
  testing wiped out 5% of the monthly budget.

  Most calls re-fetch the same data: Senso-ji Temple's details don't change
  between runs. Caching them on disk turns repeat dev runs into zero-cost runs.

DESIGN
  - Keyed by SHA-256 of (endpoint, sorted-params) so identical calls hit cache.
  - JSON files under ~/.wayfinder_cache/ (override with WAYFINDER_CACHE_DIR).
  - TTL is per-endpoint: search 7d, details 30d, photos 90d.
  - Opt-out via use_cache=False on the client constructor.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

_TTL_BY_ENDPOINT: dict[str, int] = {
    "location/search":         7  * 24 * 3600,
    "location/nearby_search":  7  * 24 * 3600,
    "details":                 30 * 24 * 3600,
    "photos":                  90 * 24 * 3600,
    "reviews":                 7  * 24 * 3600,
}
_DEFAULT_TTL = 7 * 24 * 3600


def _cache_dir() -> Path:
    override = os.environ.get("WAYFINDER_CACHE_DIR")
    base = Path(override) if override else Path.home() / ".wayfinder_cache"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _ttl_for(endpoint: str) -> int:
    for key, ttl in _TTL_BY_ENDPOINT.items():
        if key in endpoint:
            return ttl
    return _DEFAULT_TTL


def _key(endpoint: str, params: dict[str, Any]) -> str:
    """Stable cache key — excludes API key so cache survives key rotation."""
    safe_params = {k: v for k, v in params.items() if k != "key"}
    payload = json.dumps({"endpoint": endpoint, "params": safe_params},
                         sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _path_for(endpoint: str, params: dict[str, Any]) -> Path:
    prefix = endpoint.replace("/", "_").split("_")[0][:16]
    return _cache_dir() / f"{prefix}_{_key(endpoint, params)}.json"


class ResponseCache:
    """File-backed cache for TripAdvisor responses."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.hits = 0
        self.misses = 0

    def get(self, endpoint: str, params: dict[str, Any]) -> dict | None:
        if not self.enabled:
            return None
        path = _path_for(endpoint, params)
        if not path.exists():
            self.misses += 1
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                wrapper = json.load(f)
        except (json.JSONDecodeError, OSError):
            self.misses += 1
            return None
        if time.time() - wrapper.get("stored_at", 0) > _ttl_for(endpoint):
            self.misses += 1
            return None
        self.hits += 1
        return wrapper.get("payload")

    def set(self, endpoint: str, params: dict[str, Any], payload: dict) -> None:
        if not self.enabled:
            return
        path = _path_for(endpoint, params)
        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump({
                    "stored_at": time.time(),
                    "endpoint":  endpoint,
                    "payload":   payload,
                }, f, ensure_ascii=False)
        except OSError:
            pass

    def stats(self) -> dict[str, int]:
        return {"hits": self.hits, "misses": self.misses}