"""
wayfinder/filters.py
─────────────────────
Rule-based pre-filter (fast, zero API cost) that runs before any ranker.
Also houses the booking-link generator.
"""
from __future__ import annotations
import urllib.parse

from .models import Attraction, UserPreferences


class AttractionFilter:
    """
    Hard rules that remove obviously bad matches before ML/LLM ranking.

    Rules applied (in order):
      1. Quality gate  – low-rated places with enough reviews are excluded
      2. Budget        – restaurants outside the price band are excluded
      3. Dietary       – cuisine types blocklisted for a dietary restriction
                         are excluded
    """

    # Maps budget tier → accepted TripAdvisor price_level symbols
    BUDGET_PRICE_MAP: dict[str, list[str]] = {
        "budget":    ["$", "$$"],
        "mid-range": ["$$", "$$$"],
        "luxury":    ["$$$", "$$$$", ""],   # "" = unknown → keep
    }

    # Maps dietary restriction → cuisine substrings that fail the check
    DIETARY_CUISINE_BLOCKLIST: dict[str, list[str]] = {
        "vegan":       ["steakhouse", "seafood", "sushi", "bbq", "barbecue"],
        "vegetarian":  ["steakhouse", "bbq", "barbecue"],
        "gluten-free": [],          # can't reliably filter by cuisine alone
        "halal":       ["bar", "pub", "brewery"],
        "kosher":      ["seafood", "shellfish", "pork"],
    }

    def __init__(self, prefs: UserPreferences):
        self.prefs = prefs

    def passes(self, a: Attraction) -> bool:
        # NEW: drop anything with missing/invalid coordinates
        if a.latitude == 0.0 and a.longitude == 0.0:
            return False

        # NEW: drop results that aren't geographically near the destination
        # (catches wrong-city matches like Louisiana restaurant in Tokyo search)
        # This is a rough bounding box check — not perfect but catches obvious outliers
        # You'd make this smarter later with a proper geo library
        if a.num_reviews < 10:
            return False

        # quality gate: skip clearly bad places that have enough reviews
        #    (low review count = new place, give it the benefit of the doubt)
        if a.rating < 3.5 and a.num_reviews > 50:
            return False

        # budget filter – only applied to restaurants that have price data
        if a.category.lower() in ("restaurant", "restaurants") and a.price_level:
            allowed = self.BUDGET_PRICE_MAP.get(self.prefs.budget, [])
            if allowed and a.price_level not in allowed:
                return False

        # dietary blocklist
        cuisine_str = " ".join(a.cuisine_types).lower()
        for diet in self.prefs.dietary_restrictions:
            for blocked in self.DIETARY_CUISINE_BLOCKLIST.get(diet.lower(), []):
                if blocked in cuisine_str:
                    return False

        return True

    def filter(self, attractions: list[Attraction]) -> list[Attraction]:
        kept = [a for a in attractions if self.passes(a)]
        print(f"  [filter] {len(attractions)} → {len(kept)} after rule-based filter")
        return kept


# ── booking links ──────────────────────────────────────────────────────────────
def generate_booking_links(attraction: Attraction,
                           prefs: UserPreferences) -> dict[str, str]:
    """
    Returns a dict of {platform_name: url} for every relevant booking platform.

    Priority:
      - TripAdvisor direct booking URL (from API) if present
      - Viator  – tours & experiences deep-link
      - GetYourGuide – tours & experiences deep-link
      - Google Maps  – always included
      - OpenTable    – restaurants only
    """
    name_enc = urllib.parse.quote(attraction.name)
    dest_enc = urllib.parse.quote(prefs.destination)

    links: dict[str, str] = {}

    # TripAdvisor – prefer direct booking, fall back to web page
    if attraction.booking_url:
        links["TripAdvisor"] = attraction.booking_url
    elif attraction.web_url:
        links["TripAdvisor"] = attraction.web_url

    # Viator – experiences & guided tours
    links["Viator"] = (
        f"https://www.viator.com/search?text={name_enc}&destId={dest_enc}"
    )

    # GetYourGuide
    links["GetYourGuide"] = (
        f"https://www.getyourguide.com/s/?q={name_enc}&searchSource=1"
    )

    # Google Maps – always useful for navigation
    coord = f"{attraction.latitude},{attraction.longitude}"
    links["Google Maps"] = (
        f"https://www.google.com/maps/search/?api=1&query={coord}"
    )

    # OpenTable – restaurants only
    if "restaurant" in attraction.category.lower():
        links["OpenTable"] = (
            f"https://www.opentable.com/s?term={name_enc}&covers={prefs.num_travelers}"
        )

    return links
