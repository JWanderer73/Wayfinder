from __future__ import annotations

import urllib.parse

from .models import Attraction, UserPreferences


class AttractionFilter:
    """Fast rule-based filtering before ranking recommendations."""

    BUDGET_PRICE_MAP: dict[str, list[str]] = {
        "budget": ["$", "$$"],
        "mid-range": ["$$", "$$$"],
        "luxury": ["$$$", "$$$$", ""],
    }

    DIETARY_CUISINE_BLOCKLIST: dict[str, list[str]] = {
        "vegan": ["steakhouse", "seafood", "sushi", "bbq", "barbecue"],
        "vegetarian": ["steakhouse", "bbq", "barbecue"],
        "gluten-free": [],
        "halal": ["bar", "pub", "brewery"],
        "kosher": ["seafood", "shellfish", "pork"],
    }

    def __init__(self, prefs: UserPreferences):
        self.prefs = prefs

    def passes(self, attraction: Attraction) -> bool:
        if attraction.latitude == 0.0 and attraction.longitude == 0.0:
            return False
        if attraction.num_reviews < 10:
            return False
        if attraction.rating < 3.5 and attraction.num_reviews > 50:
            return False

        if attraction.category.lower() in {"restaurant", "restaurants"} and attraction.price_level:
            allowed_prices = self.BUDGET_PRICE_MAP.get(self.prefs.budget, [])
            if allowed_prices and attraction.price_level not in allowed_prices:
                return False

        cuisine_text = " ".join(attraction.cuisine_types).lower()
        for diet in self.prefs.dietary_restrictions:
            for blocked in self.DIETARY_CUISINE_BLOCKLIST.get(diet.lower(), []):
                if blocked in cuisine_text:
                    return False

        return True

    def filter(self, attractions: list[Attraction]) -> list[Attraction]:
        kept = [attraction for attraction in attractions if self.passes(attraction)]
        print(f"  [filter] {len(attractions)} -> {len(kept)} after rule-based filter")
        return kept


def generate_booking_links(
    attraction: Attraction,
    prefs: UserPreferences,
) -> dict[str, str]:
    """Generate useful outbound booking/navigation links for one attraction."""

    name_enc = urllib.parse.quote(attraction.name)
    dest_enc = urllib.parse.quote(prefs.destination)
    links: dict[str, str] = {}

    if attraction.booking_url:
        links["TripAdvisor"] = attraction.booking_url
    elif attraction.web_url:
        links["TripAdvisor"] = attraction.web_url

    links["Viator"] = f"https://www.viator.com/search?text={name_enc}&destId={dest_enc}"
    links["GetYourGuide"] = f"https://www.getyourguide.com/s/?q={name_enc}&searchSource=1"
    links["Google Maps"] = (
        "https://www.google.com/maps/search/?api=1&query="
        f"{attraction.latitude},{attraction.longitude}"
    )

    if "restaurant" in attraction.category.lower():
        links["OpenTable"] = (
            f"https://www.opentable.com/s?term={name_enc}&covers={prefs.num_travelers}"
        )

    return links
