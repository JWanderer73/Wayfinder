"""
main.py
────────
CLI entry point for the Wayfinder travel recommendation pipeline.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from wayfinder.pipeline import generate_recommendations


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="wayfinder",
        description="Generate ranked travel recommendations (TripAdvisor + Gemini)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    src = p.add_argument_group("Input source (pick one)")
    src.add_argument("--input", metavar="FILE")
    src.add_argument("--city", metavar="CITY")

    pref = p.add_argument_group("Preferences (ignored when --input is used)")
    pref.add_argument("--preferences", nargs="*", default=[], metavar="TAG")
    pref.add_argument("--budget", default="mid-range",
                      choices=["budget", "mid-range", "luxury"])
    pref.add_argument("--vibe", default="")
    pref.add_argument("--dietary", nargs="*", default=[],
                      dest="dietary_restrictions", metavar="RESTRICTION")
    pref.add_argument("--required", nargs="*", default=[],
                      dest="required_attractions", metavar="NAME",
                      help="MUST-INCLUDE attraction names (marked mandatory)")
    pref.add_argument("--dates", nargs=2, default=["", ""],
                      dest="travel_dates", metavar=("START", "END"))
    pref.add_argument("--travelers", type=int, default=2,
                      dest="num_travelers")
    pref.add_argument("--trip-shape", default="balanced",
                      choices=["relaxed", "balanced", "packed"],
                      dest="trip_shape",
                      help="relaxed (3 stops/day), balanced (5), packed (7)")

    out = p.add_argument_group("Output")
    out.add_argument("--k", type=int, default=10)
    out.add_argument("--pretty", action="store_true")
    out.add_argument("--output", metavar="FILE")

    feat = p.add_argument_group("Feature toggles")
    feat.add_argument("--no-hotels", action="store_true")
    feat.add_argument("--no-completeness", action="store_true")
    feat.add_argument("--no-weather", action="store_true")
    feat.add_argument("--no-persist", action="store_true")

    cost = p.add_argument_group("Cost / dev knobs")
    cost.add_argument("--max-fetch", type=int, default=20,
                      dest="max_per_category",
                      help="Results per category (default: 20; use 5 for dev)")
    cost.add_argument("--no-cache", action="store_true")
    cost.add_argument("--diversity-penalty", type=float, default=0.6)
    cost.add_argument("--diversity-cap", type=int, default=None)

    return p


def main() -> int:
    args = build_parser().parse_args()

    if not os.getenv("TRIPADVISOR_API_KEY"):
        print("Error: TRIPADVISOR_API_KEY is not set.", file=sys.stderr)
        return 1

    if args.input:
        try:
            with open(args.input, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as exc:
            print(f"Error reading {args.input}: {exc}", file=sys.stderr)
            return 1

        city = payload.get("destination")
        if not city:
            print("JSON file must include 'destination'.", file=sys.stderr)
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
            trip_shape           = payload.get("trip_shape", "balanced"),
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
            trip_shape           = args.trip_shape,
        )

    result = generate_recommendations(
        **call_kwargs,
        check_completeness = not args.no_completeness,
        include_hotels     = not args.no_hotels,
        fetch_weather      = not args.no_weather,
        persist            = not args.no_persist,
        max_per_category   = args.max_per_category,
        use_cache          = not args.no_cache,
        diversity_penalty  = args.diversity_penalty,
        diversity_cap      = args.diversity_cap,
    )

    indent = 2 if args.pretty else None
    output_str = json.dumps(result, indent=indent, ensure_ascii=False)
    print(output_str)

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output_str)
            print(f"\n💾 Saved to {args.output}", file=sys.stderr)
        except Exception as exc:
            print(f"Warning: could not save: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())