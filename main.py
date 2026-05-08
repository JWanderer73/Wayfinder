"""
main.py
────────
CLI entry point for the Wayfinder travel recommendation pipeline.

Usage examples
──────────────
# Basic city search
python main.py --city "Tokyo" --preferences culture food --k 10 --pretty

# Full preference set
python main.py --city "Paris" \
    --budget mid-range \
    --vibe "romance, art" \
    --dietary vegetarian \
    --required "Eiffel Tower" "Louvre Museum" \
    --dates 2025-08-01 2025-08-07 \
    --travelers 2 \
    --k 12 \
    --pretty

# Load everything from a JSON file
python main.py --input trip.json --pretty

JSON file format (trip.json):
{
  "destination": "Tokyo",
  "preferences": ["culture", "food"],
  "budget": "mid-range",
  "vibe": "anime, street food",
  "dietary_restrictions": ["vegetarian"],
  "required_attractions": ["Senso-ji Temple"],
  "travel_dates": ["2025-07-10", "2025-07-17"],
  "num_travelers": 2,
  "k": 10
}

Environment variables required
───────────────────────────────
  TRIPADVISOR_API_KEY   – from https://www.tripadvisor.com/developers
  ANTHROPIC_API_KEY     – from https://console.anthropic.com
                          (only needed if using LLMRanker, which is the default)
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from wayfinder.pipeline import generate_recommendations


# ── CLI parser ────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wayfinder",
        description="Generate ranked travel recommendations using TripAdvisor API + ML/LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # --- input source (mutually exclusive) ---
    src = parser.add_argument_group("Input source (pick one)")
    src.add_argument(
        "--input", metavar="FILE",
        help="Path to a JSON file with destination and preferences",
    )
    src.add_argument(
        "--city", metavar="CITY",
        help="Destination city / region (e.g. 'Tokyo' or 'Paris, France')",
    )

    # --- preferences ---
    pref = parser.add_argument_group("Preferences (ignored when --input is used)")
    pref.add_argument(
        "--preferences", nargs="*", default=[],
        metavar="TAG",
        help="Free-form preference tags, e.g. culture food adventure",
    )
    pref.add_argument(
        "--budget", default="mid-range",
        choices=["budget", "mid-range", "luxury"],
        help="Budget tier (default: mid-range)",
    )
    pref.add_argument(
        "--vibe", default="",
        help="Short description of travel style, e.g. 'romantic, art'",
    )
    pref.add_argument(
        "--dietary", nargs="*", default=[], dest="dietary_restrictions",
        metavar="RESTRICTION",
        help="Dietary restrictions, e.g. vegan gluten-free",
    )
    pref.add_argument(
        "--required", nargs="*", default=[], dest="required_attractions",
        metavar="NAME",
        help="Must-include attraction names (quoted if multi-word)",
    )
    pref.add_argument(
        "--dates", nargs=2, default=["", ""], dest="travel_dates",
        metavar=("START", "END"),
        help="Travel dates as YYYY-MM-DD YYYY-MM-DD",
    )
    pref.add_argument(
        "--travelers", type=int, default=2, dest="num_travelers",
        help="Number of travelers (default: 2)",
    )

    # --- output ---
    out = parser.add_argument_group("Output")
    out.add_argument(
        "--k", type=int, default=10,
        help="Number of attraction recommendations to return (default: 10)",
    )
    out.add_argument(
        "--pretty", action="store_true",
        help="Pretty-print JSON output",
    )
    out.add_argument(
        "--no-hotels", action="store_true",
        help="Skip hotel search (saves API calls)",
    )
    out.add_argument(
        "--no-completeness", action="store_true",
        help="Skip LLM completeness check (saves one API call)",
    )
    out.add_argument(
        "--output", metavar="FILE",
        help="Save JSON results to this file (in addition to stdout)",
    )

    return parser


# ── main ──────────────────────────────────────────────────────────────────────
def main() -> int:
    args = build_parser().parse_args()

    # ── env-var checks ────────────────────────────────────────────────────────
    if not os.getenv("TRIPADVISOR_API_KEY"):
        print(
            "Error: TRIPADVISOR_API_KEY is not set.\n"
            "Get a free key at https://www.tripadvisor.com/developers",
            file=sys.stderr,
        )
        return 1

    # LLM ranker needs Anthropic key; give a helpful message if missing
    if not os.getenv("ANTHROPIC_API_KEY"):
        print(
            "Warning: ANTHROPIC_API_KEY is not set.\n"
            "The LLM ranker will fail. Set the key or switch to MLRanker in pipeline.py.",
            file=sys.stderr,
        )

    # ── load from JSON file or CLI args ──────────────────────────────────────
    if args.input:
        try:
            with open(args.input, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as exc:
            print(f"Error reading {args.input}: {exc}", file=sys.stderr)
            return 1

        city = payload.get("destination")
        if not city:
            print("JSON file must include a 'destination' field.", file=sys.stderr)
            return 1

        call_kwargs = dict(
            city                 = city,
            preferences          = payload.get("preferences", []),
            k                    = payload.get("k", args.k),
            budget               = payload.get("budget", "mid-range"),
            vibe                 = payload.get("vibe", ""),
            dietary_restrictions = payload.get("dietary_restrictions", []),
            required_attractions = payload.get("required_attractions", []),
            travel_dates         = tuple(payload.get("travel_dates", ["", ""])),
            num_travelers        = payload.get("num_travelers", 2),
        )
    else:
        if not args.city:
            print("Error: provide --input FILE or --city CITY.", file=sys.stderr)
            return 1

        call_kwargs = dict(
            city                 = args.city,
            preferences          = args.preferences,
            k                    = args.k,
            budget               = args.budget,
            vibe                 = args.vibe,
            dietary_restrictions = args.dietary_restrictions,
            required_attractions = args.required_attractions,
            travel_dates         = tuple(args.travel_dates),
            num_travelers        = args.num_travelers,
        )

    # ── run pipeline ──────────────────────────────────────────────────────────
    results = generate_recommendations(
        **call_kwargs,
        check_completeness = not args.no_completeness,
        include_hotels     = not args.no_hotels,
    )

    # ── format output ─────────────────────────────────────────────────────────
    output = {
        "destination": call_kwargs["city"],
        "preferences": call_kwargs.get("preferences", []),
        "results":     results,
    }

    indent = 2 if args.pretty else None
    output_str = json.dumps(output, indent=indent, ensure_ascii=False)
    print(output_str)

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output_str)
            print(f"\n💾 Saved to {args.output}", file=sys.stderr)
        except Exception as exc:
            print(f"Warning: could not save to {args.output}: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
