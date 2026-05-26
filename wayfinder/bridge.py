"""
wayfinder/bridge.py
────────────────────
Converts TripAdvisor pipeline output → Google Maps routing stage input.
Also provides restaurant injection AFTER clustering (called by routing stage).

CHANGES vs. previous version:
  - Uses the shared `categories` module for normalisation (no more drift).
  - Reads trip_shape and applies TRIP_SHAPE_PRESETS.
  - Forwards is_mandatory + selection_source to the routing stage so it can:
      * Always include mandatory stops in some day
      * Render them with a 📌 badge in any frontend
      * Refuse to drop them during route optimization
  - inject_restaurants_into_days() — the seam Krish's team calls after
    forming daily clusters. Picks ~1 restaurant per meal window near each
    cluster's centroid.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from typing import Any

from .categories import normalise_to_routing
from .models import TRIP_SHAPE_PRESETS


# ── hours parsers ────────────────────────────────────────────────────────────
def parse_opening_time(open_hours_text: list[str]) -> str | None:
    if not open_hours_text:
        return None
    for line in open_hours_text:
        if "closed" in line.lower():
            continue
        if "00:00 - 23:59" in line or "0:00 - 23:59" in line:
            continue
        parts = line.split(":", maxsplit=1)
        if len(parts) < 2:
            continue
        time_range = parts[1].strip()
        if " - " in time_range:
            open_str = time_range.split(" - ")[0].strip()
            if ":" in open_str and len(open_str) <= 5:
                return open_str
    return None


def parse_closing_time(open_hours_text: list[str]) -> str | None:
    if not open_hours_text:
        return None
    for line in open_hours_text:
        if "closed" in line.lower():
            continue
        if "00:00 - 23:59" in line or "0:00 - 23:59" in line:
            continue
        parts = line.split(":", maxsplit=1)
        if len(parts) < 2:
            continue
        time_range = parts[1].strip()
        if " - " in time_range:
            close_str = time_range.split(" - ")[1].strip()
            if ":" in close_str and len(close_str) <= 5:
                return close_str
    return None


# ── attraction → routing stop ────────────────────────────────────────────────
def attraction_to_stop(attraction: dict[str, Any]) -> dict[str, Any]:
    """
    Convert one Attraction dict into a StopInput dict for the routing stage.

    MANDATORY HANDLING
      A mandatory attraction (is_mandatory=True) is forwarded with:
        - required=True        → routing stage MUST include it
        - priority=10          → maximum priority for tie-breaking
        - selection_source     → forwarded for UI display
    """
    open_hours = attraction.get("open_hours_text", [])
    is_mandatory = bool(attraction.get("is_mandatory", False))

    stop: dict[str, Any] = {
        "id":            attraction.get("location_id", ""),
        "name":          attraction.get("name", ""),
        "address":       attraction.get("address") or None,
        "latitude":      attraction.get("latitude") or None,
        "longitude":     attraction.get("longitude") or None,
        "visit_minutes": attraction.get("duration_minutes", 90),
        "category":      normalise_to_routing(
                            attraction.get("category", ""),
                            attraction.get("subcategories", []),
                         ),
        # mandatory items get top priority and required=True
        "priority":      10 if is_mandatory else int(round(attraction.get("score", 0))),
        "notes":         _build_notes(attraction),
        "required":      is_mandatory,
        "enabled":       True,

        # weather flags forwarded to routing stage
        "is_outdoor":    attraction.get("is_outdoor", False),
        "is_indoor":     attraction.get("is_indoor", False),

        # provenance / UI metadata
        "is_mandatory":      is_mandatory,
        "selection_source":  attraction.get("selection_source", "ranked"),
        "confidence":        attraction.get("confidence", 0.7),
    }

    open_time  = parse_opening_time(open_hours)
    close_time = parse_closing_time(open_hours)
    if open_time:
        stop["time_window_start"] = open_time
    if close_time:
        stop["time_window_end"] = close_time

    return stop


def _build_notes(attraction: dict[str, Any]) -> str:
    parts: list[str] = []
    if attraction.get("is_mandatory"):
        parts.append("📌 Mandatory (user-requested)")
    reason = (attraction.get("score_reason") or "").strip()
    if reason:
        parts.append(reason)
    subcats = attraction.get("subcategories", [])
    if subcats:
        parts.append(f"Tags: {', '.join(subcats)}")
    rating = attraction.get("rating")
    reviews = attraction.get("num_reviews")
    if rating and reviews:
        parts.append(f"⭐ {rating}/5 ({reviews:,} reviews)")
    conf = attraction.get("confidence")
    if conf is not None and conf < 0.5 and not attraction.get("is_mandatory"):
        parts.append(f"low-confidence pick ({conf:.2f})")
    return " | ".join(parts)


def hotel_to_anchor(hotel: dict[str, Any]) -> dict[str, Any]:
    return {
        "id":            hotel.get("location_id", "anchor-hotel"),
        "name":          hotel.get("name", "Hotel"),
        "address":       hotel.get("address") or None,
        "latitude":      hotel.get("latitude") or None,
        "longitude":     hotel.get("longitude") or None,
        "anchor_kind":   "hotel",
        "visit_minutes": 0,
    }


# ── main converter ───────────────────────────────────────────────────────────
def convert(
    ta_output: dict[str, Any],
    start_date: str = "",
    end_date: str = "",
    travel_mode: str = "DRIVE",
    end_each_day_at_anchor: bool = True,
    daily_minutes_budget: int | None = None,
    day_start_time: str | None = None,
    max_stops_per_day: int | None = None,
) -> dict[str, Any]:
    """Convert pipeline output → TripRequest. trip_shape preset wins unless overridden."""
    destination = ta_output.get("destination", "")
    preferences = ta_output.get("preferences", {}) or {}
    trip_shape  = preferences.get("trip_shape", "balanced")

    preset = TRIP_SHAPE_PRESETS.get(trip_shape, TRIP_SHAPE_PRESETS["balanced"])
    daily_minutes_budget = daily_minutes_budget or preset["daily_minutes_budget"]
    day_start_time       = day_start_time       or preset["day_start_time"]
    if max_stops_per_day is None:
        max_stops_per_day = preset["max_stops_per_day"]

    attractions = ta_output.get("attractions", [])
    hotels      = ta_output.get("hotels", [])

    if not attractions:
        raise ValueError("Pipeline output contains no attractions to convert.")

    stops  = [attraction_to_stop(a) for a in attractions]
    anchor = hotel_to_anchor(hotels[0]) if hotels else None

    trip_request: dict[str, Any] = {
        "destination":            destination,
        "trip_shape":             trip_shape,
        "daily_minutes_budget":   daily_minutes_budget,
        "day_start_time":         day_start_time,
        "max_stops_per_day":      max_stops_per_day,
        "travel_mode":            travel_mode,
        "end_each_day_at_anchor": end_each_day_at_anchor,
        "use_llm_duration_estimates": False,
        "stops": stops,
        # summary for the routing stage to display:
        "mandatory_stop_count":   sum(1 for s in stops if s["is_mandatory"]),
        "suggested_stop_count":   sum(1 for s in stops if not s["is_mandatory"]),
    }

    if start_date:
        trip_request["start_date"] = start_date
    if end_date:
        trip_request["end_date"] = end_date
    if anchor:
        trip_request["anchor_location"] = anchor

    return trip_request


# ── restaurant injection (called BY routing stage AFTER clustering) ─────────
def inject_restaurants_into_days(
    days: list[dict[str, Any]],
    restaurants: list[dict[str, Any]],
    meals_per_day: int = 2,
) -> list[dict[str, Any]]:
    """
    Pick the best restaurant(s) near each day's geographic centroid.

    Parameters
    ----------
    days          : list of day dicts from the routing stage. Each must have
                    a "stops" list with lat/lon, and ideally a "centroid".
                    If centroid is missing we compute one from stops.
    restaurants   : list of restaurant dicts (PipelineResult.restaurants,
                    or its restaurant_pool for more breadth).
    meals_per_day : how many restaurants to inject per day (default 2 = lunch + dinner).

    Returns
    -------
    A new `days` list with each day having a "restaurants" key (sorted by score).

    BEHAVIOUR
      - A restaurant is used at most once across the whole trip.
      - Selection picks highest-scoring within 3 km of centroid first,
        expanding to 6 km then 12 km if none qualify.
    """
    if not restaurants:
        return [{**day, "restaurants": []} for day in days]

    used_ids: set[str] = set()
    out: list[dict[str, Any]] = []

    for day in days:
        centroid = day.get("centroid") or _compute_centroid(day.get("stops", []))
        picks: list[dict[str, Any]] = []

        if centroid is None:
            out.append({**day, "restaurants": []})
            continue

        for radius_km in (3.0, 6.0, 12.0):
            candidates = [
                (r, _haversine_km(centroid["lat"], centroid["lon"],
                                  r.get("latitude") or 0,
                                  r.get("longitude") or 0))
                for r in restaurants
                if r.get("location_id") not in used_ids
                and r.get("latitude") and r.get("longitude")
            ]
            in_radius = [(r, d) for r, d in candidates if d <= radius_km]
            if in_radius:
                in_radius.sort(
                    key=lambda rd: (-float(rd[0].get("score", 0)), rd[1])
                )
                while in_radius and len(picks) < meals_per_day:
                    r, _d = in_radius.pop(0)
                    picks.append(r)
                    used_ids.add(r.get("location_id"))
                if picks:
                    break

        out.append({**day, "restaurants": picks})

    return out


def _compute_centroid(stops: list[dict[str, Any]]) -> dict[str, float] | None:
    coords = [(s.get("latitude"), s.get("longitude"))
              for s in stops
              if s.get("latitude") and s.get("longitude")]
    if not coords:
        return None
    lat = sum(c[0] for c in coords) / len(coords)
    lon = sum(c[1] for c in coords) / len(coords)
    return {"lat": lat, "lon": lon}


def _haversine_km(lat1: float, lon1: float,
                  lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


# ── CLI ──────────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Convert TripAdvisor pipeline output → Google Maps routing input.\n\n"
            "Workflow:\n"
            "  Step 1:  python main.py --input trip.json --output ta_output.json\n"
            "  Step 2:  python -m wayfinder.bridge ta_output.json --dates 2025-07-10 2025-07-17\n"
            "  Step 3:  python index.py trip_request.json --pretty\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("input", help="Path to TripAdvisor pipeline output JSON")
    p.add_argument("--output", default="trip_request.json")
    p.add_argument("--dates", nargs=2, metavar=("START", "END"), default=["", ""])
    p.add_argument("--travel-mode", default="DRIVE",
                   choices=["DRIVE", "WALK", "TRANSIT", "BICYCLE"])
    p.add_argument("--no-return-to-hotel", action="store_true")
    p.add_argument("--budget", type=int, default=None,
                   help="Override daily_minutes_budget from trip_shape preset")
    p.add_argument("--start-time", default=None,
                   help="Override day_start_time from trip_shape preset")
    p.add_argument("--max-stops", type=int, default=None,
                   help="Override max_stops_per_day from trip_shape preset")
    p.add_argument("--pretty", action="store_true")
    p.add_argument("--run-routing", action="store_true")
    return p


def main() -> int:
    args = build_parser().parse_args()
    try:
        with open(args.input, "r", encoding="utf-8") as f:
            ta_output = json.load(f)
    except FileNotFoundError:
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON in {args.input}: {exc}", file=sys.stderr)
        return 1

    try:
        trip_request = convert(
            ta_output,
            start_date             = args.dates[0],
            end_date               = args.dates[1],
            travel_mode            = args.travel_mode,
            end_each_day_at_anchor = not args.no_return_to_hotel,
            daily_minutes_budget   = args.budget,
            day_start_time         = args.start_time,
            max_stops_per_day      = args.max_stops,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    indent = 2 if args.pretty else None
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(trip_request, f, indent=indent, ensure_ascii=False)

    print(f"✅ Wrote {len(trip_request['stops'])} stops → {args.output}")
    print(f"   {trip_request['mandatory_stop_count']} mandatory, "
          f"{trip_request['suggested_stop_count']} suggested")
    print(f"   Shape: {trip_request['trip_shape']}, "
          f"{trip_request['daily_minutes_budget']} min/day, "
          f"max {trip_request['max_stops_per_day']} stops/day")

    if args.run_routing:
        if not os.getenv("GOOGLE_MAPS_API_KEY"):
            print("Error: GOOGLE_MAPS_API_KEY not set.", file=sys.stderr)
            return 1
        return subprocess.call(
            [sys.executable, "index.py", args.output, "--pretty"]
        )

    print(f"\nNext step:  python index.py {args.output} --pretty")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())