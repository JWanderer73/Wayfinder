"""
wayfinder/tripadvisor/fetcher.py
─────────────────────────────────
Fetching + parsing logic for TripAdvisor results.

FIXES in this version:
  - parse_attraction(): passes name to is_outdoor/is_indoor so name-based
    heuristics fire correctly (e.g. "Aire Ancient Baths" → is_indoor=True).
  - fetch_required_attractions(): mandatory food/market venues are returned
    with is_mandatory=True so the pipeline keeps them in attractions[], not
    restaurants[]. The pipeline uses is_mandatory to override the split.
"""
from __future__ import annotations

import math
import time
from typing import Iterable

from ..categories import estimate_duration, is_indoor, is_outdoor
from ..models import Attraction, SOURCE_USER_REQUIRED, UserPreferences
from .client import TripAdvisorClient


def parse_attraction(raw: dict, details: dict) -> Attraction:
    """Merge a search-result stub + a details response into an Attraction."""
    addr_obj = details.get("address_obj", {})
    subcats  = [s.get("localized_name", "") for s in details.get("subcategory", [])]
    cuisines = [c.get("localized_name", "") for c in details.get("cuisine", [])]
    category = (details.get("category") or {}).get("localized_name", "")
    loc_id   = details.get("location_id") or raw.get("location_id", "")
    name     = details.get("name") or raw.get("name", "")

    hours_raw       = details.get("hours", {})
    open_hours_text = hours_raw.get("weekday_text", [])

    return Attraction(
        location_id      = loc_id,
        name             = name,
        category         = category,
        subcategories    = subcats,
        rating           = float(details.get("rating")      or 0),
        num_reviews      = int(  details.get("num_reviews") or 0),
        address          = addr_obj.get("address_string", ""),
        latitude         = float(details.get("latitude")  or 0),
        longitude        = float(details.get("longitude") or 0),
        web_url          = details.get("web_url", ""),
        price_level      = details.get("price_level", ""),
        cuisine_types    = cuisines,
        hours            = hours_raw,
        open_hours_text  = open_hours_text,
        duration_minutes = estimate_duration(category, subcats),
        place_id         = loc_id,
        booking_url      = (details.get("booking") or {}).get("url", ""),
        # FIX: pass name so heuristics like "baths", "aquarium" work
        is_outdoor       = is_outdoor(category, subcats, name=name),
        is_indoor        = is_indoor(category, subcats, name=name),
    )


def _has_valid_coords(a: Attraction) -> bool:
    return not (a.latitude == 0.0 and a.longitude == 0.0)


def _has_enough_reviews(a: Attraction, threshold: int = 10) -> bool:
    return a.num_reviews >= threshold


def compute_destination_bbox(
    attractions: Iterable[Attraction],
    radius_km: float = 75.0,
) -> tuple[float, float, float, float] | None:
    valid = [(a.latitude, a.longitude) for a in attractions if _has_valid_coords(a)]
    if len(valid) < 3:
        return None
    valid.sort()
    n = len(valid)
    mid_lat = valid[n // 2][0]
    valid_by_lon = sorted(valid, key=lambda p: p[1])
    mid_lon = valid_by_lon[n // 2][1]
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * max(math.cos(math.radians(mid_lat)), 0.1))
    return (mid_lat - dlat, mid_lat + dlat, mid_lon - dlon, mid_lon + dlon)


def _inside_bbox(a: Attraction, bbox: tuple[float, float, float, float]) -> bool:
    min_lat, max_lat, min_lon, max_lon = bbox
    return min_lat <= a.latitude <= max_lat and min_lon <= a.longitude <= max_lon


def fetch_attractions(
    ta: TripAdvisorClient,
    prefs: UserPreferences,
    categories: list[str] | None = None,
    max_per_category: int = 20,
    min_reviews: int = 10,
    sleep_s: float = 0.15,
    geo_filter: bool = True,
) -> list[Attraction]:
    """
    Fetch raw Attraction objects. Required attractions are guaranteed present
    and marked is_mandatory=True regardless of category.
    """
    if categories is None:
        categories = ["attractions", "restaurants"]

    attractions: list[Attraction] = []
    bbox: tuple[float, float, float, float] | None = None

    for cat in categories:
        print(f"  [TA] searching '{cat}' in {prefs.destination}…")
        results = ta.search_locations(prefs.destination, category=cat)
        in_this_category: list[Attraction] = []

        for r in results[:max_per_category]:
            try:
                details = ta.get_location_details(r["location_id"])
                a = parse_attraction(r, details)
                if not _has_valid_coords(a):
                    print(f"    skip '{a.name}': missing coordinates")
                    continue
                if not _has_enough_reviews(a, threshold=min_reviews):
                    print(f"    skip '{a.name}': only {a.num_reviews} reviews")
                    continue
                in_this_category.append(a)
                time.sleep(sleep_s)
            except Exception as exc:
                print(f"    skip '{r.get('name', '?')}': {exc}")

        if geo_filter and bbox is None and in_this_category:
            bbox = compute_destination_bbox(in_this_category)
            if bbox:
                print(f"    [TA] bbox: lat {bbox[0]:.3f}–{bbox[1]:.3f}, "
                      f"lon {bbox[2]:.3f}–{bbox[3]:.3f}")

        if geo_filter and bbox is not None:
            before = len(in_this_category)
            in_this_category = [a for a in in_this_category if _inside_bbox(a, bbox)]
            dropped = before - len(in_this_category)
            if dropped:
                print(f"    [TA] dropped {dropped} out-of-area result(s) in '{cat}'")

        # If the 'restaurants' category came back empty, fall back to a
        # nearby_search around the destination's centroid so the routing team
        # always has restaurants to inject into day clusters.
        if cat == "restaurants" and not in_this_category and bbox is not None:
            mid_lat = (bbox[0] + bbox[1]) / 2
            mid_lon = (bbox[2] + bbox[3]) / 2
            print(f"    [TA] restaurants empty — trying nearby_search at "
                  f"{mid_lat:.4f},{mid_lon:.4f}…")
            try:
                nearby = ta.search_nearby(mid_lat, mid_lon,
                                          category="restaurants",
                                          radius=3, unit="km")
                for r in nearby[:max_per_category]:
                    try:
                        details = ta.get_location_details(r["location_id"])
                        a = parse_attraction(r, details)
                        if not _has_valid_coords(a):
                            continue
                        if not _has_enough_reviews(a, threshold=min_reviews):
                            continue
                        if bbox and not _inside_bbox(a, bbox):
                            continue
                        in_this_category.append(a)
                        time.sleep(sleep_s)
                    except Exception as exc:
                        print(f"    skip nearby restaurant '{r.get('name', '?')}': {exc}")
                print(f"    [TA] nearby fallback found {len(in_this_category)} restaurants")
            except Exception as exc:
                print(f"    [TA] nearby_search failed: {exc}")

        attractions.extend(in_this_category)

    # Required attractions: explicit search, marked mandatory
    required = fetch_required_attractions(ta, prefs, bbox=bbox, sleep_s=sleep_s)

    existing_ids = {a.location_id for a in attractions}
    for req in required:
        if req.location_id in existing_ids:
            for a in attractions:
                if a.location_id == req.location_id:
                    a.is_mandatory = True
                    a.selection_source = SOURCE_USER_REQUIRED
                    break
        else:
            attractions.append(req)

    print(f"  [TA] fetched {len(attractions)} raw locations "
          f"({ta._call_count} API calls, {ta.cache_hits} cache hits)")
    return attractions


def fetch_required_attractions(
    ta: TripAdvisorClient,
    prefs: UserPreferences,
    bbox: tuple[float, float, float, float] | None = None,
    sleep_s: float = 0.15,
) -> list[Attraction]:
    """
    Explicitly search for each name in prefs.required_attractions.
    Marks results is_mandatory=True. Bypasses the min-reviews filter.
    Searches both 'attractions' AND 'restaurants' categories so that
    user-required food venues (e.g. La Boqueria) are always found.
    """
    out: list[Attraction] = []
    for req in prefs.required_attractions:
        print(f"  [TA] required '{req}': explicit search…")
        found = False
        # Search both categories so food markets / restaurants are found too
        for search_cat in ("attractions", "restaurants"):
            if found:
                break
            results = ta.search_locations(req, category=search_cat)
            for r in results[:3]:
                try:
                    details = ta.get_location_details(r["location_id"])
                    a = parse_attraction(r, details)
                    if not _has_valid_coords(a):
                        continue
                    if bbox is not None and not _inside_bbox(a, bbox):
                        print(f"    skip required '{a.name}': outside bbox")
                        continue
                    # MANDATORY — always set regardless of category
                    a.is_mandatory = True
                    a.selection_source = SOURCE_USER_REQUIRED
                    out.append(a)
                    time.sleep(sleep_s)
                    found = True
                    break
                except Exception as exc:
                    print(f"    skip required '{r.get('name', '?')}': {exc}")
        if not found:
            print(f"    WARNING: could not find required '{req}' — skipping")
    return out


def attach_photos(ta: TripAdvisorClient,
                  attractions: list[Attraction],
                  sleep_s: float = 0.1) -> None:
    """Fetch photo URLs in-place. Call AFTER ranking, for top-k only."""
    for a in attractions:
        if a.photo_url:
            continue
        try:
            photos = ta.get_photos(a.location_id, limit=1)
            if photos:
                a.photo_url = photos[0]
            time.sleep(sleep_s)
        except Exception as exc:
            print(f"    photo skip '{a.name}': {exc}")