"""
swap.py
────────
CLI utility for the activity-replacement feature.

Usage
─────
# Show candidate replacements for slot 3 of trip abc123
python swap.py candidates abc123 3 --n 5 --pretty

# Apply a swap — slot 3 → location_id 8675309
python swap.py apply abc123 3 8675309

# List all saved trips
python swap.py list

WHY THIS EXISTS
  The pipeline saves the FULL ranked list as candidate_pool inside each
  trip's JSON. This script reads from that pool — no TripAdvisor/Gemini
  calls happen here, so swapping is instant and free.

  Mandatory slots are protected: TripStore raises ValueError if you try to
  see candidates for or swap into a mandatory slot.
"""
from __future__ import annotations

import argparse
import json
import sys

from wayfinder.trip_store import TripStore


def cmd_list(_args) -> int:
    store = TripStore()
    trips = store.list_trips()
    if not trips:
        print("No saved trips.")
        return 0
    for t in trips:
        print(f"  {t['trip_id']}  {t['destination']:30s}  {t['path']}")
    return 0


def cmd_candidates(args) -> int:
    store = TripStore()
    try:
        cands = store.swap_candidates(args.trip_id, args.replace_idx, n=args.n)
    except (FileNotFoundError, IndexError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not cands:
        print("No candidates available.")
        return 0

    indent = 2 if args.pretty else None
    # surface just the user-facing fields
    summary = [
        {
            "location_id":      c["location_id"],
            "name":             c["name"],
            "category":         c["category"],
            "score":            c.get("score"),
            "confidence":       c.get("confidence"),
            "rating":           c.get("rating"),
            "num_reviews":      c.get("num_reviews"),
            "selection_source": c.get("selection_source"),
            "score_reason":     c.get("score_reason"),
        }
        for c in cands
    ]
    print(json.dumps(summary, indent=indent, ensure_ascii=False))
    return 0


def cmd_apply(args) -> int:
    store = TripStore()
    try:
        store.apply_swap(args.trip_id, args.replace_idx, args.new_location_id)
    except (FileNotFoundError, IndexError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"✅ Swapped slot {args.replace_idx} in trip {args.trip_id}.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="swap")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List saved trips")
    p_list.set_defaults(func=cmd_list)

    p_cand = sub.add_parser("candidates",
                            help="Show replacement candidates for a slot")
    p_cand.add_argument("trip_id")
    p_cand.add_argument("replace_idx", type=int,
                        help="0-indexed slot in active attractions list")
    p_cand.add_argument("--n", type=int, default=5)
    p_cand.add_argument("--pretty", action="store_true")
    p_cand.set_defaults(func=cmd_candidates)

    p_apply = sub.add_parser("apply", help="Apply a swap")
    p_apply.add_argument("trip_id")
    p_apply.add_argument("replace_idx", type=int)
    p_apply.add_argument("new_location_id")
    p_apply.set_defaults(func=cmd_apply)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())