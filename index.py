from __future__ import annotations

import argparse
import json
import os
import sys

from wayfinder.duration import DurationEstimator, OpenAIDurationClient
from wayfinder.google_maps import GoogleMapsClient, GoogleMapsError
from wayfinder.models import TripRequest
from wayfinder.pipeline import generate_recommendations
from wayfinder.review import OpenAIPlanningReviewer
from wayfinder.spatial import SpatialPlanner


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


def build_planning_reviewer(trip: TripRequest) -> OpenAIPlanningReviewer | None:
    if not trip.use_llm_cluster_review:
        return None

    openai_api_key = os.getenv("OPENAI_API_KEY")
    model = trip.llm_review_model or os.getenv("WAYFINDER_REVIEW_MODEL")
    if not openai_api_key or not model:
        return None

    return OpenAIPlanningReviewer(
        api_key=openai_api_key,
        model=model,
    )


def cmd_plan(args: argparse.Namespace) -> int:
    with open(args.input, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    trip = TripRequest.from_dict(payload)
    duration_estimator = build_duration_estimator(trip)
    planner = SpatialPlanner(
        GoogleMapsClient(api_key=os.getenv("GOOGLE_MAPS_API_KEY")),
        duration_estimator=duration_estimator,
        planning_reviewer=build_planning_reviewer(trip),
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


def cmd_recommend(args: argparse.Namespace) -> int:
    if not os.getenv("TRIPADVISOR_API_KEY"):
        print("Missing TRIPADVISOR_API_KEY", file=sys.stderr)
        return 1

    if args.input:
        try:
            with open(args.input, "r", encoding="utf-8") as f:
                payload = json.load(f)

            city = payload.get("destination")
            preferences = payload.get("preferences", [])
            k = payload.get("k", args.k)

            if not city:
                print("JSON must include 'destination'", file=sys.stderr)
                return 1

        except Exception as e:
            print(f"Error reading input file: {e}", file=sys.stderr)
            return 1
    else:
        if not args.city:
            print("Provide --input or --city", file=sys.stderr)
            return 1

        city = args.city
        preferences = args.preferences
        k = args.k

    results = generate_recommendations(city=city, preferences=preferences, k=k)

    output = {"destination": city, "preferences": preferences, "results": results}
    if args.pretty:
        print(json.dumps(output, indent=2))
    else:
        print(json.dumps(output))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Wayfinder travel planning CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Build a day-by-day spatial itinerary")
    plan_parser.add_argument(
        "input",
        nargs="?",
        default="sample_trip.json",
        help="Path to a JSON trip request file.",
    )
    plan_parser.add_argument("--pretty", action="store_true", help="Pretty-print output.")

    rec_parser = subparsers.add_parser("recommend", help="Generate ranked travel recommendations")
    rec_parser.add_argument("--input", help="Path to JSON file with destination and preferences")
    rec_parser.add_argument("--city", help="Destination city")
    rec_parser.add_argument("--preferences", nargs="*", default=[], help="User preferences")
    rec_parser.add_argument("--k", type=int, default=5, help="Number of recommendations")
    rec_parser.add_argument("--pretty", action="store_true", help="Pretty-print output.")

    args = parser.parse_args()
    if args.command == "plan":
        return cmd_plan(args)
    return cmd_recommend(args)


if __name__ == "__main__":
    raise SystemExit(main())
