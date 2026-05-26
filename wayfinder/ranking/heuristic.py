"""
wayfinder/ranking/heuristic.py
───────────────────────────────
No-API-needed ranker. Used as a fallback by GeminiRanker and untrained MLRanker.

Score formula:
  rating_component   = (rating / 5) * 7      → up to 7 points
  popularity         = log1p(num_reviews) / log1p(50_000) * 3  → up to 3
  total              = round(rating + popularity, 2)            → 0..10

MANDATORY HANDLING
  Mandatory items get a floor score of 9.5 — they should always be near the
  top of the list. We don't pin them to exactly 10 because the diversity
  reranker reads scores, and we want mandatory items in order of their
  "intrinsic" appeal among themselves.
"""
from __future__ import annotations

import math

from ..models import Attraction, UserPreferences
from .base import Ranker

MANDATORY_FLOOR_SCORE = 9.5


class HeuristicRanker(Ranker):
    """Pure-Python ranker that never calls an API."""

    name = "heuristic"

    def rank(self, attractions: list[Attraction],
             prefs: UserPreferences) -> list[Attraction]:
        for a in attractions:
            self._score_one(a)
        return sorted(attractions, key=lambda a: a.score, reverse=True)

    def _score_one(self, a: Attraction) -> None:
        rating_component = (a.rating / 5.0) * 7.0
        popularity = min(math.log1p(a.num_reviews) / math.log1p(50_000), 1.0)
        base = rating_component + popularity * 3.0

        if a.is_mandatory:
            # mandatory items get a guaranteed floor — but we still let a
            # 5-star mandatory beat a 4-star mandatory by adding a small
            # premium on top of the floor.
            a.score = round(max(MANDATORY_FLOOR_SCORE, base) + 0.01 * a.rating, 2)
            a.score_reason = "Mandatory — user-requested attraction"
            a.confidence = 1.0
        else:
            a.score = round(base, 2)
            a.score_reason = f"Heuristic: {a.rating}/5 rating, {a.num_reviews:,} reviews"
            a.confidence = 0.5

        a.ranker_used = self.name


def apply_heuristic(attractions: list[Attraction]) -> None:
    """In-place heuristic scoring helper (used by GeminiRanker on parse failure)."""
    ranker = HeuristicRanker()
    for a in attractions:
        ranker._score_one(a)