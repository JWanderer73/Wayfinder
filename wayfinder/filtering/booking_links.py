"""
wayfinder/filtering/booking_links.py
─────────────────────────────────────
URL builders for attraction, restaurant, and hotel booking platforms.
"""
from __future__ import annotations

import urllib.parse

from ..models import Attraction, UserPreferences


def generate_booking_links(attraction: Attraction,
                           prefs: UserPreferences) -> dict[str, str]:
    """Build {platform: url} for an attraction or restaurant."""
    name_enc = urllib.parse.quote(attraction.name)
    dest_enc = urllib.parse.quote(prefs.destination)

    links: dict[str, str] = {}

    if attraction.booking_url:
        links["TripAdvisor"] = attraction.booking_url
    elif attraction.web_url:
        links["TripAdvisor"] = attraction.web_url

    links["Viator"]       = f"https://www.viator.com/search?text={name_enc}&destId={dest_enc}"
    links["GetYourGuide"] = f"https://www.getyourguide.com/s/?q={name_enc}&searchSource=1"
    coord = f"{attraction.latitude},{attraction.longitude}"
    links["Google Maps"]  = f"https://www.google.com/maps/search/?api=1&query={coord}"

    if "restaurant" in attraction.category.lower():
        links["OpenTable"] = (
            f"https://www.opentable.com/s?term={name_enc}"
            f"&covers={prefs.num_travelers}"
        )

    return links


def generate_hotel_booking_links(hotel: Attraction) -> dict[str, str]:
    name_enc = urllib.parse.quote(hotel.name)
    coord    = f"{hotel.latitude},{hotel.longitude}"
    return {
        "TripAdvisor": hotel.web_url or "",
        "Booking.com": f"https://www.booking.com/search.html?ss={name_enc}",
        "Hotels.com":  f"https://www.hotels.com/search.do?q-destination={name_enc}",
        "Google Maps": f"https://www.google.com/maps/search/?api=1&query={coord}",
    }