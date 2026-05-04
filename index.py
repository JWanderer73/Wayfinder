from __future__ import annotations

import argparse
import json
import os
import sys

from wayfinder.pipeline import generate_recommendations


# build cli parser
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate ranked travel recommendations using Tripadvisor API + ML"
    )

    parser.add_argument(
        "--input",
        help="Path to JSON file with destination and preferences",
    )

    parser.add_argument(
        "--city",
        help="Destination city",
    )

    parser.add_argument(
        "--preferences",
        nargs="*",
        default=[],
        help="User preferences",
    )

    parser.add_argument(
        "--k",
        type=int,
        default=5,
        help="Number of recommendations",
    )

    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty print output",
    )

    return parser


# main entry
def main() -> int:
    args = build_parser().parse_args()

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

    results = generate_recommendations(
        city=city,
        preferences=preferences,
        k=k
    )

    output = {
        "destination": city,
        "preferences": preferences,
        "results": results
    }

    if args.pretty:
        print(json.dumps(output, indent=2))
    else:
        print(json.dumps(output))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())