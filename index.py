from __future__ import annotations

import argparse
import json
import os
import sys

from wayfinder.google_maps import GoogleMapsClient, GoogleMapsError
from wayfinder.models import TripRequest
from wayfinder.spatial import SpatialPlanner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a starter day-by-day spatial plan for Wayfinder."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="sample_trip.json",
        help="Path to a JSON trip request file.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the resulting itinerary JSON.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print(
            "Missing GOOGLE_MAPS_API_KEY. Export it before running this script.",
            file=sys.stderr,
        )
        return 1

    with open(args.input, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    trip = TripRequest.from_dict(payload)
    planner = SpatialPlanner(GoogleMapsClient(api_key=api_key))

    try:
        itinerary = planner.build_plan(trip)
    except GoogleMapsError as exc:
        print(f"Google Maps error: {exc}", file=sys.stderr)
        return 1

    output = itinerary.to_dict()
    if args.pretty:
        print(json.dumps(output, indent=2))
    else:
        print(json.dumps(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
