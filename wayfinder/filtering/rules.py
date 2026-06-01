"""
wayfinder/filtering/rules.py
─────────────────────────────
Rule-based pre-filter that runs before any ML/LLM ranker.

CHANGES vs. previous version:
  - Mandatory attractions (is_mandatory=True) ALWAYS pass the filter,
    no matter what their rating, price level, or cuisine. The user typed
    this name; we don't second-guess.
"""
from __future__ import annotations

from ..models import Attraction, UserPreferences


class AttractionFilter:
    """
    Hard rules that remove obviously bad matches before ranking.

    Rules applied (in order, only for non-mandatory items):
      1. Quality gate – low-rated places with enough reviews are excluded
      2. Budget        – restaurants outside the price band are excluded
      3. Dietary       – cuisine types blocklisted for a dietary restriction
                         are excluded
    """

    BUDGET_PRICE_MAP: dict[str, list[str]] = {
        "budget":    ["$", "$$"],
        "mid-range": ["$$", "$$$"],
        "luxury":    ["$$$", "$$$$", ""],
    }

    DIETARY_CUISINE_BLOCKLIST: dict[str, list[str]] = {
        "vegan":       ["steakhouse", "seafood", "sushi", "bbq", "barbecue"],
        "vegetarian":  ["steakhouse", "bbq", "barbecue"],
        "gluten-free": [],
        "halal":       ["bar", "pub", "brewery"],
        "kosher":      ["seafood", "shellfish", "pork"],
    }

    def __init__(self, prefs: UserPreferences):
        self.prefs = prefs

    def passes(self, a: Attraction) -> bool:
        # MANDATORY attractions bypass every filter. User asked by name.
        if a.is_mandatory:
            return True

        if a.rating < 3.5 and a.num_reviews > 50:
            return False

        if a.category.lower() in ("restaurant", "restaurants") and a.price_level:
            allowed = self.BUDGET_PRICE_MAP.get(self.prefs.budget, [])
            if allowed and a.price_level not in allowed:
                return False

        cuisine_str = " ".join(a.cuisine_types).lower()
        for diet in self.prefs.dietary_restrictions:
            for blocked in self.DIETARY_CUISINE_BLOCKLIST.get(diet.lower(), []):
                if blocked in cuisine_str:
                    return False

        return True

    def filter(self, attractions: list[Attraction]) -> list[Attraction]:
        kept = [a for a in attractions if self.passes(a)]
        mandatory_count = sum(1 for a in kept if a.is_mandatory)
        print(f"  [filter] {len(attractions)} → {len(kept)} after rules "
              f"({mandatory_count} mandatory)")
        return kept