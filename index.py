from __future__ import annotations

import argparse
import json
import os
import sys

from wayfinder.duration import DurationEstimator, OpenAIDurationClient
from wayfinder.google_maps import GoogleMapsClient, GoogleMapsError
from wayfinder.models import TripRequest
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
    planner = SpatialPlanner(
        GoogleMapsClient(api_key=os.getenv("GOOGLE_MAPS_API_KEY")),
        duration_estimator=build_duration_estimator(trip),
        planning_reviewer=build_planning_reviewer(trip),
    )

    try:
        itinerary = planner.build_plan(trip)
    except GoogleMapsError as exc:
        print(f"Google Maps error: {exc}", file=sys.stderr)
        return 1

    output = itinerary.to_dict()
    print(json.dumps(output, indent=2 if args.pretty else None))
    return 0


def cmd_recommend(args: argparse.Namespace) -> int:
    if not os.getenv("TRIPADVISOR_API_KEY"):
        print("Missing TRIPADVISOR_API_KEY", file=sys.stderr)
        return 1
    if not os.getenv("GEMINI_API_KEY"):
        print("Missing GEMINI_API_KEY", file=sys.stderr)
        return 1

    from wayfinder.pipeline import generate_recommendations

    if args.input:
        try:
            with open(args.input, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception as exc:
            print(f"Error reading input file: {exc}", file=sys.stderr)
            return 1

        city = payload.get("destination")
        if not city:
            print("JSON must include 'destination'", file=sys.stderr)
            return 1

        call_kwargs = {
            "city": city,
            "preferences": payload.get("preferences", []),
            "k": payload.get("k", args.k),
            "budget": payload.get("budget", "mid-range"),
            "vibe": payload.get("vibe", ""),
            "dietary_restrictions": payload.get("dietary_restrictions", []),
            "required_attractions": payload.get("required_attractions", []),
            "travel_dates": tuple(payload.get("travel_dates", ["", ""])),
            "num_travelers": payload.get("num_travelers", 2),
        }
    else:
        if not args.city:
            print("Provide --input or --city", file=sys.stderr)
            return 1
        call_kwargs = {
            "city": args.city,
            "preferences": args.preferences,
            "k": args.k,
            "budget": args.budget,
            "vibe": args.vibe,
            "dietary_restrictions": args.dietary_restrictions,
            "required_attractions": args.required_attractions,
            "travel_dates": tuple(args.travel_dates),
            "num_travelers": args.num_travelers,
        }

    results = generate_recommendations(
        **call_kwargs,
        check_completeness=not args.no_completeness,
        include_hotels=not args.no_hotels,
    )
    output = {
        "destination": call_kwargs["city"],
        "preferences": call_kwargs.get("preferences", []),
        "results": results,
    }
    print(json.dumps(output, indent=2 if args.pretty else None, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wayfinder travel planning CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Build a spatial itinerary")
    plan_parser.add_argument(
        "input",
        nargs="?",
        default="sample_trip.json",
        help="Path to a JSON trip request file.",
    )
    plan_parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")

    recommend_parser = subparsers.add_parser(
        "recommend",
        help="Fetch and rank travel recommendations.",
    )
    recommend_parser.add_argument("--input", help="Path to recommendation JSON.")
    recommend_parser.add_argument("--city", help="Destination city.")
    recommend_parser.add_argument("--preferences", nargs="*", default=[])
    recommend_parser.add_argument(
        "--budget",
        default="mid-range",
        choices=["budget", "mid-range", "luxury"],
    )
    recommend_parser.add_argument("--vibe", default="")
    recommend_parser.add_argument(
        "--dietary",
        nargs="*",
        default=[],
        dest="dietary_restrictions",
    )
    recommend_parser.add_argument(
        "--required",
        nargs="*",
        default=[],
        dest="required_attractions",
    )
    recommend_parser.add_argument(
        "--dates",
        nargs=2,
        default=["", ""],
        dest="travel_dates",
        metavar=("START", "END"),
    )
    recommend_parser.add_argument("--travelers", type=int, default=2, dest="num_travelers")
    recommend_parser.add_argument("--k", type=int, default=10)
    recommend_parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    recommend_parser.add_argument("--no-hotels", action="store_true")
    recommend_parser.add_argument("--no-completeness", action="store_true")

    return parser


def normalize_legacy_plan_args(argv: list[str]) -> list[str]:
    if len(argv) <= 1:
        return [argv[0], "plan"]
    if argv[1] in {"plan", "recommend", "-h", "--help"}:
        return argv
    return [argv[0], "plan", *argv[1:]]


def main() -> int:
    parser = build_parser()
    args = parser.parse_args(normalize_legacy_plan_args(sys.argv)[1:])
    if args.command == "plan":
        return cmd_plan(args)
    return cmd_recommend(args)


if __name__ == "__main__":
    raise SystemExit(main())
