"""
wayfinder/trip_store.py
────────────────────────
Persistent per-trip state.

WHY
  The frontend (and the swap-candidates feature) need to load a trip back
  later. Right now everything is in-memory and dies with the CLI process.

LAYOUT
  Each trip → {WAYFINDER_TRIPS_DIR or ./wayfinder/trips}/{trip_id}.json
  Format mirrors PipelineResult.to_dict() so the file IS the trip.

MANDATORY PROTECTION
  swap_candidates() refuses to suggest replacements for a mandatory slot.
  apply_swap() refuses to overwrite a mandatory slot. The UI should hide /
  disable the swap button when is_mandatory=True, but defense-in-depth
  matters — never let a mandatory pick get silently dropped.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from .models import PipelineResult, SOURCE_SWAP


def _trips_dir() -> Path:
    override = os.environ.get("WAYFINDER_TRIPS_DIR")
    base = Path(override) if override else Path("wayfinder/trips")
    base.mkdir(parents=True, exist_ok=True)
    return base


def make_trip_id() -> str:
    return uuid.uuid4().hex[:12]


class TripStore:
    """File-backed CRUD for trip state."""

    def __init__(self, directory: Path | None = None):
        self.directory = directory or _trips_dir()
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, result: PipelineResult) -> str:
        path = self.directory / f"{result.trip_id}.json"
        payload = result.to_dict()
        payload["_saved_at"] = time.time()
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        return result.trip_id

    def load(self, trip_id: str) -> dict[str, Any]:
        path = self.directory / f"{trip_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"No trip with id {trip_id} at {path}")
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def list_trips(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                out.append({
                    "trip_id":     data.get("trip_id", path.stem),
                    "destination": data.get("destination", ""),
                    "saved_at":    data.get("_saved_at", 0),
                    "path":        str(path),
                })
            except Exception:
                continue
        return out

    # ── swap candidates ──────────────────────────────────────────────────────
    def swap_candidates(self, trip_id: str,
                        replace_idx: int, n: int = 5) -> list[dict[str, Any]]:
        """
        Suggest n replacements for the attraction at position replace_idx.

        Pulls from candidate_pool — NO new API calls happen at swap time.
        REFUSES to suggest swaps for mandatory slots (raises ValueError).
        """
        data = self.load(trip_id)
        active = data.get("attractions", [])
        pool   = data.get("candidate_pool", [])

        if replace_idx < 0 or replace_idx >= len(active):
            raise IndexError(f"replace_idx {replace_idx} out of range "
                             f"(active list has {len(active)} items)")
        if active[replace_idx].get("is_mandatory"):
            raise ValueError(
                f"Slot {replace_idx} is mandatory "
                f"('{active[replace_idx].get('name')}') — cannot suggest swaps."
            )

        active_ids = {a.get("location_id") for a in active}
        # also skip any candidates that are mandatory (those are already pinned)
        candidates = [
            c for c in pool
            if c.get("location_id") not in active_ids
            and not c.get("is_mandatory")
        ]
        return candidates[:n]

    def apply_swap(self, trip_id: str,
                   replace_idx: int, new_location_id: str) -> dict[str, Any]:
        """
        Persistently swap the attraction at replace_idx with candidate
        new_location_id. REFUSES to overwrite mandatory slots.
        """
        data = self.load(trip_id)
        active = data.get("attractions", [])
        pool   = data.get("candidate_pool", [])

        if replace_idx < 0 or replace_idx >= len(active):
            raise IndexError(f"replace_idx {replace_idx} out of range")
        if active[replace_idx].get("is_mandatory"):
            raise ValueError(
                f"Slot {replace_idx} is mandatory — cannot swap "
                f"'{active[replace_idx].get('name')}'."
            )

        replacement = next(
            (c for c in pool if c.get("location_id") == new_location_id),
            None,
        )
        if replacement is None:
            raise ValueError(f"No candidate with location_id {new_location_id}")
        if replacement.get("is_mandatory"):
            raise ValueError("Cannot swap in a mandatory item (it's already pinned).")

        # tag the swapped-in attraction so the UI can show provenance
        replacement = dict(replacement)
        replacement["selection_source"] = SOURCE_SWAP

        active[replace_idx] = replacement
        data["attractions"] = active
        data["_saved_at"] = time.time()

        path = self.directory / f"{trip_id}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return data