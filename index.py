from __future__ import annotations

import argparse
import json
import os
import sys

from wayfinder.duration import DurationEstimator, OpenAIDurationClient
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


def build_duration_estimator(trip: TripRequest) -> DurationEstimator:
    if not trip.use_llm_duration_estimates:
        return DurationEstimator(use_llm=False)

    openai_api_key = os.getenv("OPENAI_API_KEY")
    model = trip.llm_duration_model or os.getenv("WAYFINDER_DURATION_MODEL")
    if not openai_api_key or not model:
        return DurationEstimator(use_llm=True, llm_client=None)

    return DurationEstimator(
        use_llm=True,
        llm_client=OpenAIDurationClient(
            api_key=openai_api_key,
            model=model,
        ),
    )


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
    duration_estimator = build_duration_estimator(trip)
    planner = SpatialPlanner(
        GoogleMapsClient(api_key=api_key),
        duration_estimator=duration_estimator,
    )

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
