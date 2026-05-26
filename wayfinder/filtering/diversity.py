"""
wayfinder/filtering/diversity.py
─────────────────────────────────
MMR-style diversity reranking.

WHY
  Without this, Tokyo's top 6 ramen spots all rank above any museum.
  Users asking for "food" still want variety.

HOW
  Walk the ranked list once. For each item, apply a penalty proportional
  to how many already-accepted items share its (sub)category. Re-sort.

  Simple "Maximal Marginal Relevance" using subcategory similarity — no
  embedding model needed.

MANDATORY EXEMPTION
  Items with is_mandatory=True are NEVER penalised and NEVER hit the
  cap_per_category limit. They're also placed at the front of the output
  list regardless of score, so the routing stage sees them first.
"""
from __future__ import annotations

from ..models import Attraction


def diversify(
    ranked: list[Attraction],
    penalty_per_dup: float = 0.6,
    cap_per_category: int | None = None,
) -> list[Attraction]:
    """
    Return a re-sorted copy of `ranked` with category diversity penalties applied.

    Mandatory items are placed first (in their original order), then suggested
    items follow, sorted by penalised score.
    """
    mandatory  = [a for a in ranked if a.is_mandatory]
    suggested  = [a for a in ranked if not a.is_mandatory]

    # mandatory items DO count toward duplicate seen-categories — so suggested
    # items that duplicate them get penalised. This is what "diversity" means
    # here: don't pile up the same category around the locked picks.
    seen_categories: dict[str, int] = {}
    for a in mandatory:
        key = _category_key(a)
        seen_categories[key] = seen_categories.get(key, 0) + 1

    out_suggested: list[Attraction] = []
    for a in suggested:
        cat_key = _category_key(a)
        dup_count = seen_categories.get(cat_key, 0)

        if cap_per_category is not None and dup_count >= cap_per_category:
            continue

        penalty = penalty_per_dup * dup_count
        a.diversity_penalty = round(penalty, 3)
        a.score = round(max(0.0, a.score - penalty), 3)

        seen_categories[cat_key] = dup_count + 1
        out_suggested.append(a)

    out_suggested.sort(key=lambda x: x.score, reverse=True)

    # mandatory at front (in original order), then sorted suggested
    return mandatory + out_suggested


def _category_key(a: Attraction) -> str:
    """Coarse category bucket for diversity counting."""
    if a.subcategories:
        return a.subcategories[0].strip().lower()
    return (a.category or "unknown").strip().lower()