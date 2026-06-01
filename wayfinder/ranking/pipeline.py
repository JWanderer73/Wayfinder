"""
wayfinder/pipeline.py
──────────────────────
Orchestrates the full pipeline:
  fetch → filter → rank → diversify → pin required → photos → hotels → save

FIXES in this version:
  1. Mandatory items ALWAYS go into attractions[], even if they are food venues.
     La Boqueria requested via --required belongs in the routing cluster,
     not the restaurant injection pool. The split now exempts mandatory items.
  2. mandatory_count in summary now counts mandatory items across both
     attractions[] and restaurants[] so the number is always accurate.
  3. Low-score filter: suggested items with score < MIN_SCORE_THRESHOLD (3.5)
     are dropped from the active list — they waste routing slots.
  4. Hotel score field set to None instead of 0.0 so the routing team does
     not mistake unscored hotels for low-quality ones.
  5. gaps field is now both a raw string AND a structured list of dicts
     for programmatic parsing by the frontend.

SWAP YOUR RANKER:
  from .ranking import GeminiRanker as Ranker      # default
  from .ranking import HeuristicRanker as Ranker   # zero-API fallback
  from .ranking import MLRanker as Ranker          # trained model
"""
from __future__ import annotations

import os

from .filtering import (
    AttractionFilter,
    diversify,
    generate_booking_links,
)
from .hotels import HotelFinder
from .models import (
    Attraction,
    PipelineResult,
    SOURCE_COMPLETENESS,
    UserPreferences,
)
from .ranking import GeminiRanker as Ranker   # ← swap here
from .tripadvisor import TripAdvisorClient, attach_photos, fetch_attractions
from .trip_store import TripStore, make_trip_id
from .weather import get_weather_summary

# FIX 3: minimum score for suggested items to make the active list.
# Mandatory items are exempt — they always survive regardless of score.
MIN_SCORE_THRESHOLD = 3.5


# ── restaurant detection ──────────────────────────────────────────────────────
def _is_restaurant(a: Attraction) -> bool:
    """
    True if this is a food/drink venue rather than a sightseeing attraction.

    FIX 1: mandatory items are NEVER classified as restaurants here — they
    always go into attractions[] so the routing stage clusters them into days.
    """
    if a.is_mandatory:
        return False   # FIX 1: mandatory items stay in attractions[]

    cat = a.category.lower()
    if "restaurant" in cat or "food" in cat or "dining" in cat:
        return True
    subs_lower = " ".join(a.subcategories).lower()
    if "restaurant" in subs_lower or "food & drink" in subs_lower or "dining" in subs_lower:
        return True
    if a.cuisine_types:
        return True
    return False


# ── gaps parser ───────────────────────────────────────────────────────────────
def _parse_gaps(gaps_text: str) -> list[dict]:
    """
    FIX 5: Convert the Gemini gap string into a structured list for the frontend.

    Input:  "* Missing Picasso Museum\n* No beach activity\n"
    Output: [{"text": "Missing Picasso Museum"}, {"text": "No beach activity"}]
    """
    if not gaps_text or gaps_text.strip().lower() == "looks complete.":
        return []
    lines = []
    for line in gaps_text.splitlines():
        cleaned = line.strip().lstrip("*•-#").strip()
        if cleaned:
            lines.append({"text": cleaned})
    return lines


def generate_recommendations(
    city: str,
    preferences: list[str] | None = None,
    k: int = 10,
    budget: str = "mid-range",
    vibe: str = "",
    dietary_restrictions: list[str] | None = None,
    required_attractions: list[str] | None = None,
    travel_dates: tuple[str, str] = ("", ""),
    num_travelers: int = 2,
    trip_shape: str = "balanced",
    travel_mode: str = "DRIVE",
    categories: list[str] | None = None,
    check_completeness: bool = True,
    include_hotels: bool = True,
    max_per_category: int = 20,
    use_cache: bool = True,
    num_restaurants_keep: int = 12,
    num_attractions_keep: int | None = None,
    diversity_penalty: float = 0.6,
    diversity_cap: int | None = None,
    fetch_weather: bool = True,
    persist: bool = True,
) -> dict:
    """Full pipeline entry point. Returns PipelineResult.to_dict()."""

    # ── 1. assemble preferences ──────────────────────────────────────────
    combined_vibe = ", ".join(filter(None, [vibe] + list(preferences or [])))
    prefs = UserPreferences(
        destination          = city,
        travel_dates         = travel_dates,
        budget               = budget,
        vibe                 = combined_vibe,
        dietary_restrictions = list(dietary_restrictions or []),
        required_attractions = list(required_attractions or []),
        num_travelers        = num_travelers,
        trip_shape           = trip_shape,
        travel_mode          = travel_mode,
    )

    # ── 2. weather context ───────────────────────────────────────────────
    if fetch_weather and travel_dates and travel_dates[0]:
        print("🌤  Fetching weather summary…")
        prefs.weather_summary = get_weather_summary(
            city, travel_dates[0], travel_dates[1]
        )
        if prefs.weather_summary:
            print(f"   {prefs.weather_summary}")

    # ── 3. TripAdvisor client ────────────────────────────────────────────
    api_key = os.environ["TRIPADVISOR_API_KEY"]
    ta = TripAdvisorClient(api_key, use_cache=use_cache)

    # ── 4. fetch ─────────────────────────────────────────────────────────
    print(f"\n🔍 Fetching for: {city}")
    raw = fetch_attractions(
        ta, prefs,
        categories       = categories or ["attractions", "restaurants"],
        max_per_category = max_per_category,
    )

    # ── 5. rule-based filter ─────────────────────────────────────────────
    filtered = AttractionFilter(prefs).filter(raw)

    # ── 6. split attractions from restaurants ────────────────────────────
    # FIX 1: _is_restaurant() returns False for mandatory items, so mandatory
    # food venues (e.g. La Boqueria) always land in attractions_only.
    attractions_only = [a for a in filtered if not _is_restaurant(a)]
    restaurants_only = [a for a in filtered if _is_restaurant(a)]

    mand_in_attractions = sum(1 for a in attractions_only if a.is_mandatory)
    print(f"  [split] {len(attractions_only)} attractions "
          f"({mand_in_attractions} mandatory), "
          f"{len(restaurants_only)} restaurants")

    # ── 7. rank ──────────────────────────────────────────────────────────
    ranker = Ranker()
    print(f"\n🤖 Ranking with {ranker.name}…")

    ranked_attractions = ranker.rank(attractions_only, prefs)
    ranked_restaurants = ranker.rank(restaurants_only, prefs) if restaurants_only else []

    # ── 8. diversity rerank ──────────────────────────────────────────────
    diversified_attractions = diversify(
        ranked_attractions,
        penalty_per_dup  = diversity_penalty,
        cap_per_category = diversity_cap,
    )

    # ── 9. build active list ─────────────────────────────────────────────
    k_active = num_attractions_keep or k

    # FIX 3: drop low-scored suggested items before slicing to k
    filtered_for_active = [
        a for a in diversified_attractions
        if a.is_mandatory or a.score >= MIN_SCORE_THRESHOLD
    ]
    dropped_low = len(diversified_attractions) - len(filtered_for_active)
    if dropped_low:
        print(f"  [score filter] dropped {dropped_low} suggested item(s) "
              f"with score < {MIN_SCORE_THRESHOLD}")

    top_attractions = filtered_for_active[:k_active]

    # mandatory items must all survive the slice
    in_top_ids = {a.location_id for a in top_attractions}
    missing_mandatory = [
        a for a in diversified_attractions
        if a.is_mandatory and a.location_id not in in_top_ids
    ]
    if missing_mandatory:
        print(f"   Pinning {len(missing_mandatory)} extra mandatory item(s)")
        top_attractions = top_attractions + missing_mandatory

    top_restaurants = ranked_restaurants[:num_restaurants_keep]

    # ── 10. photos + booking links ────────────────────────────────────────
    print("\n📸 Fetching photos for top picks…")
    attach_photos(ta, top_attractions)
    attach_photos(ta, top_restaurants)

    for a in top_attractions + top_restaurants:
        links = generate_booking_links(a, prefs)
        a.booking_links = links
        if not a.booking_url and links.get("TripAdvisor"):
            a.booking_url = links["TripAdvisor"]

    # ── 11. LLM completeness check ────────────────────────────────────────
    gaps_text = ""
    if check_completeness and hasattr(ranker, "check_completeness"):
        print("🔎 Checking completeness…")
        try:
            gaps_text = ranker.check_completeness(top_attractions, prefs)
            _tag_completeness_suggestions(gaps_text, diversified_attractions)
        except Exception as exc:
            print(f"   completeness check failed: {exc}")

    # ── 12. hotels ────────────────────────────────────────────────────────
    hotels: list[Attraction] = []
    if include_hotels:
        hotels = HotelFinder(ta).find_hotels(prefs)

    # FIX 4: clear the meaningless score=0.0 on hotels so routing team
    # does not mistake it for a quality signal.
    for h in hotels:
        h.score        = None   # type: ignore[assignment]
        h.score_reason = "Hotels are not scored by the ranker"
        h.ranker_used  = "n/a"

    # ── 13. build result ─────────────────────────────────────────────────
    # FIX 2: mandatory_count counts across both attractions and restaurants
    total_mandatory = (
        sum(1 for a in top_attractions if a.is_mandatory)
        + sum(1 for r in top_restaurants if r.is_mandatory)
    )

    result = PipelineResult(
        trip_id        = make_trip_id(),
        destination    = city,
        preferences    = {
            "preferences":          list(preferences or []),
            "budget":               budget,
            "vibe":                 vibe,
            "dietary_restrictions": list(dietary_restrictions or []),
            "required_attractions": list(required_attractions or []),
            "travel_dates":         list(travel_dates),
            "num_travelers":        num_travelers,
            "trip_shape":           trip_shape,
            "travel_mode":          travel_mode,
        },
        attractions      = top_attractions,
        restaurants      = top_restaurants,
        hotels           = hotels,
        candidate_pool   = diversified_attractions,
        restaurant_pool  = ranked_restaurants,
        gaps_text        = gaps_text,
        gaps_structured  = _parse_gaps(gaps_text),   # FIX 5
        api_calls        = ta._call_count,
        cache_hits       = ta.cache_hits,
        weather_summary  = prefs.weather_summary,
        travel_mode      = travel_mode,
        total_mandatory  = total_mandatory,           # FIX 2
    )

    # ── 14. persist ───────────────────────────────────────────────────────
    if persist:
        TripStore().save(result)
        print(f"\n💾 Saved trip → wayfinder/trips/{result.trip_id}.json")

    print(f"\n✨ Done. {ta._call_count} API calls, {ta.cache_hits} cache hits.")
    print(f"   {total_mandatory} mandatory total | "
          f"{result.suggested_count} suggested attractions")
    print(f"   {len(top_restaurants)} restaurants | travel mode: {travel_mode}")
    if result.selected_hotel:
        print(f"   Selected hotel: {result.selected_hotel.name}")

    return result.to_dict()


def _tag_completeness_suggestions(gaps: str,
                                   pool: list[Attraction]) -> None:
    if not gaps or gaps.lower().strip() == "looks complete.":
        return
    gaps_low = gaps.lower()
    for a in pool:
        if a.is_mandatory:
            continue
        if a.name and a.name.lower() in gaps_low:
            a.selection_source = SOURCE_COMPLETENESS