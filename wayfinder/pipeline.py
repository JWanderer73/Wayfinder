"""
wayfinder/pipeline.py
──────────────────────
Orchestrates the full pipeline:
  fetch → filter → rank → diversify → pin required → photos → hotels → save

KEY DESIGN DECISIONS
  - Mandatory items (user-named in required_attractions) get is_mandatory=True
    at fetch time, BYPASS the rule-based filter, get a guaranteed-high score
    from any ranker, are never diversity-penalised, and always go to the top.
  - Restaurants are SPLIT OUT from attractions early. Attractions form daily
    geographic clusters in the routing stage; the bridge then injects
    restaurants near each cluster's centroid.
  - The FULL ranked list is preserved as candidate_pool so the swap-candidates
    feature can serve replacements without re-hitting any APIs.

SWAP YOUR RANKER HERE:
  from .ranking import GeminiRanker as Ranker      # default (free LLM)
  from .ranking import MLRanker as Ranker          # custom-trained model
  from .ranking import HeuristicRanker as Ranker   # zero-API fallback
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
    """
    Full pipeline entry point. Returns PipelineResult.to_dict().
    """
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
    )

    # ── 2. weather context (free, optional) ──────────────────────────────
    if fetch_weather and travel_dates and travel_dates[0]:
        print("🌤  Fetching weather summary…")
        prefs.weather_summary = get_weather_summary(
            city, travel_dates[0], travel_dates[1]
        )
        if prefs.weather_summary:
            print(f"   {prefs.weather_summary}")

    # ── 3. TripAdvisor client (with cache) ───────────────────────────────
    api_key = os.environ["TRIPADVISOR_API_KEY"]
    ta = TripAdvisorClient(api_key, use_cache=use_cache)

    # ── 4. fetch — required attractions get is_mandatory=True ───────────
    print(f"\n🔍 Fetching for: {city}")
    raw = fetch_attractions(
        ta, prefs,
        categories       = categories or ["attractions", "restaurants"],
        max_per_category = max_per_category,
    )

    # ── 5. rule-based filter (skips mandatory) ───────────────────────────
    filtered = AttractionFilter(prefs).filter(raw)

    # ── 6. split attractions from restaurants ────────────────────────────
    attractions_only = [a for a in filtered
                        if "restaurant" not in a.category.lower()]
    restaurants_only = [a for a in filtered
                        if "restaurant" in a.category.lower()]

    # ── 7. rank both groups (mandatory gets fixed high score) ────────────
    ranker = Ranker()
    print(f"\n🤖 Ranking with {ranker.name}…")
    print(f"   {len(attractions_only)} attractions, {len(restaurants_only)} restaurants")
    mand_count = sum(1 for a in attractions_only if a.is_mandatory)
    if mand_count:
        print(f"   {mand_count} mandatory attraction(s) will be pinned")

    ranked_attractions = ranker.rank(attractions_only, prefs)
    ranked_restaurants = ranker.rank(restaurants_only, prefs)

    # ── 8. diversity rerank (exempts mandatory) ──────────────────────────
    diversified_attractions = diversify(
        ranked_attractions,
        penalty_per_dup  = diversity_penalty,
        cap_per_category = diversity_cap,
    )

    # ── 9. build active list (mandatory first, then suggested) ──────────
    k_active = num_attractions_keep or k
    # diversify() already puts mandatory items first; just slice
    top_attractions = diversified_attractions[:k_active]

    # ensure all mandatory items survive the slice — even if k_active is
    # smaller than the mandatory count, we never drop a mandatory item.
    in_top_ids = {a.location_id for a in top_attractions}
    missing_mandatory = [
        a for a in diversified_attractions
        if a.is_mandatory and a.location_id not in in_top_ids
    ]
    if missing_mandatory:
        print(f"   Pinning {len(missing_mandatory)} extra mandatory item(s) "
              f"beyond k={k_active}")
        top_attractions = top_attractions + missing_mandatory

    top_restaurants = ranked_restaurants[:num_restaurants_keep]

    # ── 10. photos + booking links (top-k only) ─────────────────────────
    print("\n📸 Fetching photos for top picks…")
    attach_photos(ta, top_attractions)
    attach_photos(ta, top_restaurants)

    for a in top_attractions + top_restaurants:
        links = generate_booking_links(a, prefs)
        a.booking_links = links
        if not a.booking_url and links.get("TripAdvisor"):
            a.booking_url = links["TripAdvisor"]

    # ── 11. LLM completeness check ──────────────────────────────────────
    gaps = ""
    if check_completeness and hasattr(ranker, "check_completeness"):
        print("🔎 Checking completeness…")
        try:
            gaps = ranker.check_completeness(top_attractions, prefs)
            # mark any candidates that match the LLM's gap suggestions
            _tag_completeness_suggestions(gaps, diversified_attractions)
        except Exception as exc:
            print(f"   completeness check failed: {exc}")

    # ── 12. hotels ──────────────────────────────────────────────────────
    hotels: list[Attraction] = []
    if include_hotels:
        hotels = HotelFinder(ta).find_hotels(prefs)

    # ── 13. build typed result ──────────────────────────────────────────
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
        },
        attractions     = top_attractions,
        restaurants     = top_restaurants,
        hotels          = hotels,
        candidate_pool  = diversified_attractions,
        restaurant_pool = ranked_restaurants,
        gaps            = gaps,
        api_calls       = ta._call_count,
        cache_hits      = ta.cache_hits,
        weather_summary = prefs.weather_summary,
    )

    # ── 14. persist ─────────────────────────────────────────────────────
    if persist:
        TripStore().save(result)
        print(f"\n💾 Saved trip → wayfinder/trips/{result.trip_id}.json")

    print(f"\n✨ Done. "
          f"{ta._call_count} API calls, {ta.cache_hits} cache hits.")
    print(f"   {result.mandatory_count} mandatory + "
          f"{result.suggested_count} suggested attractions")

    return result.to_dict()


def _tag_completeness_suggestions(gaps: str,
                                   pool: list[Attraction]) -> None:
    """
    If the LLM's gap analysis mentions an attraction name from the candidate
    pool, mark it with selection_source=SOURCE_COMPLETENESS so the UI can
    surface it as "✨ AI suggests adding this".

    Best-effort substring match — doesn't try to be clever.
    """
    if not gaps or gaps.lower().strip() == "looks complete.":
        return
    gaps_low = gaps.lower()
    for a in pool:
        if a.is_mandatory:
            continue
        if a.name and a.name.lower() in gaps_low:
            a.selection_source = SOURCE_COMPLETENESS