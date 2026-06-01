# WayFinder

AI-powered travel planning pipeline. Given a destination and preferences, WayFinder fetches real attractions and restaurants from TripAdvisor, ranks them using Gemini, builds a full candidate pool, and hands a structured trip request off to a Google Maps routing stage that turns it into a day-by-day itinerary.

Built as a UCSD data science project. TripAdvisor pipeline by Pranav; clustering and routing by Krish, Jack, and Abhishai.

---

## Table of contents

1. [How it works](#how-it-works)
2. [Project structure](#project-structure)
3. [Setup](#setup)
4. [Running the pipeline](#running-the-pipeline)
5. [CLI reference](#cli-reference)
6. [JSON input format](#json-input-format)
7. [Output format](#output-format)
8. [Mandatory vs. suggested attractions](#mandatory-vs-suggested-attractions)
9. [The swap-candidates feature](#the-swap-candidates-feature)
10. [Bridge — handing off to the routing stage](#bridge--handing-off-to-the-routing-stage)
11. [Restaurant injection](#restaurant-injection)
12. [Trip shapes](#trip-shapes)
13. [Ranker system](#ranker-system)
14. [API cost management](#api-cost-management)
15. [Weather awareness](#weather-awareness)
16. [Diversity reranking](#diversity-reranking)
17. [Persistent trip storage](#persistent-trip-storage)
18. [Data models](#data-models)
19. [Environment variables](#environment-variables)
20. [Dev workflow](#dev-workflow)
21. [Adding a new feature](#adding-a-new-feature)

---

## How it works

```
User preferences
      │
      ▼
┌─────────────────────────────────────────────────────┐
│  TRIPADVISOR PIPELINE  (this codebase)              │
│                                                     │
│  1. Fetch   → TripAdvisor Content API               │
│               (attractions + restaurants + hotels)  │
│  2. Filter  → quality gate, budget, dietary         │
│  3. Rank    → Gemini 2.5 Flash (or ML / heuristic)  │
│  4. Diversify → MMR-style category penalty          │
│  5. Photos  → fetch only for top-k                  │
│  6. Gaps    → LLM completeness check                │
│  7. Save    → trip JSON to disk                     │
└─────────────────────────────────────────────────────┘
      │
      │  bridge.py  (convert + restaurant injection)
      ▼
┌─────────────────────────────────────────────────────┐
│  GOOGLE MAPS ROUTING STAGE  (separate codebase)     │
│                                                     │
│  index.py / spatial.py                              │
│  Clusters stops → day-by-day itinerary              │
│  bridge.inject_restaurants_into_days() called here  │
└─────────────────────────────────────────────────────┘
```

The two stages are fully decoupled. Neither imports from the other. `bridge.py` is the only translation layer.

---

## Project structure

```
wayfinder/                      ← root
├── main.py                     ← CLI entry point
├── swap.py                     ← activity-replacement CLI
└── wayfinder/                  ← Python package
    ├── __init__.py             ← public exports
    ├── models.py               ← all dataclasses + selection-source constants
    ├── categories.py           ← single source of truth: durations + category maps
    ├── pipeline.py             ← orchestrator (the one function main.py calls)
    ├── bridge.py               ← TA output → routing input + restaurant injection
    ├── weather.py              ← Open-Meteo weather summary (free, no key)
    ├── hotels.py               ← hotel finder (soft-scored by budget tier)
    ├── trip_store.py           ← disk persistence + swap CRUD
    ├── tripadvisor/
    │   ├── cache.py            ← SHA-256-keyed file cache (TTL by endpoint)
    │   ├── client.py           ← TripAdvisor HTTP client (cache-aware)
    │   └── fetcher.py          ← parse + bbox filter + required-attraction fetch
    ├── filtering/
    │   ├── rules.py            ← quality gate / budget / dietary filter
    │   ├── diversity.py        ← MMR-style category reranker
    │   └── booking_links.py    ← URL builders for TripAdvisor, Viator, OpenTable…
    └── ranking/
        ├── base.py             ← Ranker abstract base class
        ├── gemini.py           ← GeminiRanker (default, free tier)
        ├── heuristic.py        ← HeuristicRanker (zero-API fallback)
        └── ml.py               ← MLRanker (scikit-learn, optional)
```

---

## Setup

### Dependencies

```bash
pip install requests google-genai
# optional, only needed for MLRanker:
pip install scikit-learn numpy
```

### API keys

| Key | Where to get it | Required? |
|-----|----------------|-----------|
| `TRIPADVISOR_API_KEY` | https://www.tripadvisor.com/developers | Yes |
| `GEMINI_API_KEY` | https://aistudio.google.com → "Get API key" | Yes (default ranker) |
| `GOOGLE_MAPS_API_KEY` | Google Cloud Console | Only for routing stage |

```bash
export TRIPADVISOR_API_KEY="your_key"
export GEMINI_API_KEY="your_key"
```

Both free tiers are enough for development. TripAdvisor gives 5,000 requests/month. Gemini gives 1,500 requests/day and 1M tokens/minute. The response cache (on by default) means repeat dev runs cost zero API calls.

---

## Running the pipeline

### Quickstart

```bash
python main.py --city "Tokyo" --pretty
```

### With preferences

```bash
python main.py \
  --city "Paris" \
  --budget mid-range \
  --vibe "romance, art" \
  --dietary vegetarian \
  --required "Eiffel Tower" "Louvre Museum" \
  --dates 2025-08-01 2025-08-07 \
  --travelers 2 \
  --trip-shape balanced \
  --k 12 \
  --pretty \
  --output paris_trip.json
```

### From a JSON file

```bash
python main.py --input trip.json --pretty --output result.json
```

### Dev mode (fewer API calls)

```bash
python main.py --city "Tokyo" --max-fetch 5 --no-hotels --no-completeness --pretty
```

### Full two-stage workflow

```bash
# Stage 1: TripAdvisor pipeline
python main.py --input trip.json --output ta_output.json --pretty

# Stage 2: Convert to routing format
python -m wayfinder.bridge ta_output.json \
  --dates 2025-08-01 2025-08-07 \
  --output trip_request.json \
  --pretty

# Stage 3: Google Maps routing (separate codebase)
python index.py trip_request.json --pretty
```

Or run stages 2 and 3 together:

```bash
python -m wayfinder.bridge ta_output.json --dates 2025-08-01 2025-08-07 --run-routing
```

---

## CLI reference

### `main.py`

| Flag | Default | Description |
|------|---------|-------------|
| `--city CITY` | — | Destination city or region |
| `--input FILE` | — | Load preferences from a JSON file (overrides `--city` flags) |
| `--preferences TAG…` | `[]` | Free-form tags merged into vibe (e.g. `culture food`) |
| `--budget` | `mid-range` | `budget` / `mid-range` / `luxury` |
| `--vibe TEXT` | `""` | Short description of travel style |
| `--dietary RESTRICTION…` | `[]` | e.g. `vegan gluten-free` |
| `--required NAME…` | `[]` | Must-include attraction names — these become **mandatory** |
| `--dates START END` | `""` `""` | Travel dates as `YYYY-MM-DD YYYY-MM-DD` |
| `--travelers N` | `2` | Number of travelers |
| `--trip-shape` | `balanced` | `relaxed` / `balanced` / `packed` — see [Trip shapes](#trip-shapes) |
| `--k N` | `10` | Number of attractions to return |
| `--pretty` | off | Pretty-print JSON |
| `--output FILE` | — | Save JSON to file (also prints to stdout) |
| `--no-hotels` | off | Skip hotel search |
| `--no-completeness` | off | Skip LLM gap analysis |
| `--no-weather` | off | Skip weather fetch |
| `--no-persist` | off | Don't save trip to disk |
| `--max-fetch N` | `20` | Results per category to fully expand (use `5` in dev) |
| `--no-cache` | off | Force live API hits, bypass disk cache |
| `--diversity-penalty F` | `0.6` | Score penalty per category duplicate (see [Diversity](#diversity-reranking)) |
| `--diversity-cap N` | none | Hard cap on items per category |

### `swap.py`

```bash
# List all saved trips
python swap.py list

# Show 5 replacement candidates for slot 3 of trip abc123
python swap.py candidates abc123 3 --n 5 --pretty

# Apply a swap — slot 3 becomes location_id 8675309
python swap.py apply abc123 3 8675309
```

### `bridge.py`

```bash
python -m wayfinder.bridge ta_output.json \
  --output trip_request.json \
  --dates 2025-08-01 2025-08-07 \
  --travel-mode DRIVE \
  --pretty
```

| Flag | Default | Description |
|------|---------|-------------|
| `--dates START END` | `""` | Forwarded to the routing stage |
| `--travel-mode` | `DRIVE` | `DRIVE` / `WALK` / `TRANSIT` / `BICYCLE` |
| `--no-return-to-hotel` | off | Don't route back to hotel each evening |
| `--budget N` | from trip_shape | Override `daily_minutes_budget` (minutes) |
| `--start-time HH:MM` | from trip_shape | Override `day_start_time` |
| `--max-stops N` | from trip_shape | Override `max_stops_per_day` |
| `--run-routing` | off | Run `index.py` automatically after conversion |

---

## JSON input format

```json
{
  "destination": "Tokyo",
  "preferences": ["culture", "food", "nightlife"],
  "budget": "mid-range",
  "vibe": "anime, street food, cozy",
  "dietary_restrictions": ["vegetarian"],
  "required_attractions": ["Senso-ji Temple", "Shibuya Crossing"],
  "travel_dates": ["2025-07-10", "2025-07-17"],
  "num_travelers": 2,
  "trip_shape": "balanced",
  "k": 12
}
```

`required_attractions` names become **mandatory** — they are always included, always pinned at the top, and cannot be swapped out. See [Mandatory vs. suggested](#mandatory-vs-suggested-attractions).

---

## Output format

The pipeline returns a JSON object with the following top-level keys:

```json
{
  "trip_id": "a3f9c2b1d4e8",
  "destination": "Tokyo",
  "preferences": { "...": "..." },
  "weather_summary": "Tokyo, July 10–17: highs near 31°C / 88°F, rain likely on 4 of 7 days.",
  "summary": {
    "mandatory_count": 2,
    "suggested_count": 10,
    "restaurant_count": 12,
    "hotel_count": 5
  },
  "attractions": [ "...list of Attraction dicts..." ],
  "restaurants": [ "...list of Attraction dicts, restaurants only..." ],
  "hotels": [ "...list of Attraction dicts, hotels only..." ],
  "candidate_pool": [ "...full ranked list, used for swaps..." ],
  "restaurant_pool": [ "...full ranked restaurant list..." ],
  "gaps": "• No traditional kaiseki restaurant in the list.\n• Consider adding a teamLab digital art experience.",
  "api_calls": 43,
  "cache_hits": 89
}
```

`attractions` and `restaurants` are separate lists. The routing stage clusters `attractions` into daily geographic groups first, then `bridge.inject_restaurants_into_days()` adds the right restaurant(s) near each day's centroid. `candidate_pool` contains the full ranked list beyond the top-k, enabling zero-cost activity swaps.

### Attraction dict shape

Each item in `attractions`, `restaurants`, `candidate_pool` etc. is an `Attraction` serialised to a dict:

| Field | Type | Description |
|-------|------|-------------|
| `location_id` | str | TripAdvisor location ID |
| `name` | str | Attraction name |
| `category` | str | TripAdvisor category string |
| `subcategories` | list[str] | TripAdvisor subcategory labels |
| `rating` | float | TripAdvisor rating (0–5) |
| `num_reviews` | int | Number of reviews |
| `address` | str | Street address |
| `latitude` / `longitude` | float | Coordinates |
| `web_url` | str | TripAdvisor page URL |
| `photo_url` | str | First photo URL (only for top-k) |
| `price_level` | str | `$` / `$$` / `$$$` / `$$$$` |
| `cuisine_types` | list[str] | Cuisine labels (restaurants only) |
| `open_hours_text` | list[str] | e.g. `["Monday: 09:00 - 17:00", ...]` |
| `duration_minutes` | int | Estimated visit time |
| `booking_url` | str | Direct booking URL if available |
| `booking_links` | dict | `{platform: url}` — TripAdvisor, Viator, Google Maps, OpenTable… |
| `score` | float | Ranker score 0–10 |
| `score_reason` | str | One-sentence LLM explanation |
| `confidence` | float | 0–1 — how sure the ranker is (surfaces low-confidence picks in UI) |
| `ranker_used` | str | `"gemini"` / `"ml"` / `"heuristic"` |
| `is_outdoor` / `is_indoor` | bool | For weather-aware routing |
| `diversity_penalty` | float | How much score was deducted by the diversity reranker |
| `is_mandatory` | bool | **True if the user explicitly named this attraction** |
| `selection_source` | str | Why it's in the list — see next section |

---

## Mandatory vs. suggested attractions

Every attraction in the output carries two key fields the UI should use:

### `is_mandatory: bool`

`True` when the user typed this attraction name into `--required` (CLI) or `required_attractions` (JSON). These are things the user specifically asked for — a bucket-list item, something they've been wanting to visit, or a meeting point already booked.

**What mandatory means throughout the system:**

| Layer | Behaviour |
|-------|-----------|
| Fetch | `fetch_required_attractions()` explicitly searches by name; bypasses the min-reviews filter |
| Filter | Always passes, regardless of rating, price tier, or dietary conflict |
| Ranker | Skipped from LLM batch; receives a fixed score floor of 9.5 (saves tokens + prevents LLM from down-weighting user picks) |
| Diversity | Never penalised, never hit by `cap_per_category`, placed at the front of the output |
| Pipeline | Survive even if `k` is smaller than the mandatory count — mandatory items are never dropped |
| Bridge | `required=true`, `priority=10` forwarded to routing stage |
| Swap | `swap_candidates()` raises `ValueError` if you target a mandatory slot; `apply_swap()` refuses to overwrite one |

### `selection_source: str`

Records the provenance of each attraction. The UI can use this for contextual labels like "you asked for this" or "AI suggestion":

| Value | Meaning | UI hint |
|-------|---------|---------|
| `"user_required"` | User typed the name into `--required` | 📌 "You requested this" |
| `"ranked"` | System picked via scoring | ⭐ "Recommended for you" |
| `"completeness"` | LLM gap analysis flagged it as missing | ✨ "AI suggests adding" |
| `"swap"` | User manually swapped it in | 🔄 "You picked this" |
| `"restaurant_inject"` | Injected near a cluster centroid by the bridge | 🍽️ "Near your route" |

### UI implementation guide

```javascript
// Render a 📌 badge and disable the swap button
if (attraction.is_mandatory) {
  showLockedBadge();
  disableSwapButton();
}

// Show provenance label
const label = {
  user_required:      "You requested this",
  ranked:             "Recommended for you",
  completeness:       "AI suggests adding",
  swap:               "You picked this",
  restaurant_inject:  "Near your route",
}[attraction.selection_source] ?? "Suggested";

// Show uncertainty treatment for low-confidence picks
if (!attraction.is_mandatory && attraction.confidence < 0.5) {
  showLabel("You might like this");
}
```

---

## The swap-candidates feature

When a user dislikes an activity and wants to replace it, WayFinder serves alternatives from the pre-computed `candidate_pool` — no new API calls happen at swap time.

### How it works

The pipeline always ranks every filtered attraction (not just the top-k), and saves the full list as `candidate_pool` inside the trip JSON. When the user says "swap slot 3", the system filters out items already in the active list and returns the next best ones.

### Via the CLI

```bash
# See what's at slot 3
python swap.py candidates abc123 3 --n 5 --pretty

# Accept one of the candidates
python swap.py apply abc123 3 <location_id>
```

### Via Python

```python
from wayfinder import TripStore

store = TripStore()

# See candidates for slot 3
candidates = store.swap_candidates("abc123", replace_idx=3, n=5)
for c in candidates:
    print(c["name"], c["score"], c["selection_source"])

# Apply a swap
store.apply_swap("abc123", replace_idx=3, new_location_id="8675309")
```

### Mandatory protection

```python
# This raises ValueError — mandatory slots cannot be swapped
store.swap_candidates("abc123", replace_idx=0)
# ValueError: Slot 0 is mandatory ('Senso-ji Temple') — cannot suggest swaps.
```

---

## Bridge — handing off to the routing stage

`bridge.py` converts the TripAdvisor pipeline output into the `TripRequest` format that `index.py` (the Google Maps routing stage) expects.

### Field mapping

| TripAdvisor (Attraction) | Routing stage (StopInput) |
|--------------------------|--------------------------|
| `location_id` | `id` |
| `name` | `name` |
| `address` | `address` |
| `latitude` / `longitude` | `latitude` / `longitude` |
| `duration_minutes` | `visit_minutes` |
| `category` + `subcategories` | `category` (normalised via `categories.py`) |
| `score` | `priority` (0–10 int) |
| `is_mandatory=True` | `required=true`, `priority=10` |
| `open_hours_text` | `time_window_start` / `time_window_end` |
| `is_outdoor` / `is_indoor` | forwarded as-is |
| `is_mandatory` + `selection_source` + `confidence` | forwarded for UI rendering |

The top hotel from the hotels list becomes `anchor_location` — the routing stage uses this as the daily home base.

### Python usage

```python
from wayfinder.bridge import convert
import json

with open("ta_output.json") as f:
    ta_output = json.load(f)

trip_request = convert(ta_output, start_date="2025-08-01", end_date="2025-08-07")

with open("trip_request.json", "w") as f:
    json.dump(trip_request, f, indent=2)
```

---

## Restaurant injection

Restaurants are kept separate from attractions throughout the pipeline. The routing stage clusters attractions into daily geographic groups first; the bridge then picks the best restaurant(s) close to each day's cluster centroid. This is better than mixing restaurants and attractions together from the start, because it puts lunch/dinner near where the user already is on each day.

### The seam for the routing team

```python
from wayfinder.bridge import inject_restaurants_into_days
import json

with open("ta_output.json") as f:
    ta_output = json.load(f)

# `days` comes from the routing stage's clustering output.
# Each day must have a "stops" list with lat/lon, and optionally "centroid".
days_with_restaurants = inject_restaurants_into_days(
    days=clustered_days,
    restaurants=ta_output["restaurants"],
    meals_per_day=2,       # 2 = lunch + dinner
)

# Each day now has a "restaurants" key with the selected picks.
for day in days_with_restaurants:
    print(day["restaurants"])
```

### Selection logic

1. For each day, compute the centroid of that day's stops.
2. Find the highest-scoring restaurant within 3 km of the centroid.
3. If fewer than `meals_per_day` found, expand to 6 km, then 12 km.
4. A restaurant is used at most once across the whole trip.

Use `ta_output["restaurant_pool"]` instead of `ta_output["restaurants"]` for a wider candidate set (the full ranked list, not just the top-12).

---

## Trip shapes

`--trip-shape` controls the overall pace of the trip. It sets `daily_minutes_budget`, `max_stops_per_day`, and `day_start_time` in the routing stage via `TRIP_SHAPE_PRESETS`.

| Shape | Daily time budget | Max stops/day | Day starts |
|-------|-------------------|---------------|------------|
| `relaxed` | 6 hours | 3 | 10:00 |
| `balanced` | 8 hours | 5 | 09:00 |
| `packed` | 10 hours | 7 | 08:00 |

These values are centralised in `models.TRIP_SHAPE_PRESETS`. You can override any individual value from the bridge CLI:

```bash
python -m wayfinder.bridge ta_output.json --budget 420 --max-stops 4 --start-time 09:30
```

---

## Ranker system

The active ranker is set by one import line in `pipeline.py`:

```python
from .ranking import GeminiRanker as Ranker   # ← swap here
```

Three rankers are available:

### GeminiRanker (default)

Calls Gemini 2.5 Flash in batches of 10. For each attraction it returns a `score` (0–10), a `reason` (one sentence), and a `confidence` (0–1). The prompt includes destination, budget, vibe, dietary restrictions, travel dates, and the weather summary.

**Mandatory items are excluded from the batch entirely** — they receive a fixed score of 9.5 without an API call. This saves tokens and prevents the LLM from accidentally down-weighting something the user explicitly asked for.

Falls back to `HeuristicRanker` if Gemini returns malformed JSON after 3 retries.

### HeuristicRanker

Zero API calls. Score formula:

```
score = (rating / 5) * 7  +  log1p(num_reviews) / log1p(50,000) * 3
```

Up to 7 points for rating, 3 for log-scaled popularity. Confidence is always 0.5 (moderate — it's generic, not personalised). Used as a fallback by both Gemini (on parse failure) and ML (when no model file exists).

Mandatory items get `max(9.5, heuristic_score)` so they always stay near the top.

### MLRanker

Requires `pip install scikit-learn numpy`. A 7-feature logistic regression model:

| Feature | Description |
|---------|-------------|
| Rating | `rating / 5` |
| Popularity | `log1p(num_reviews) / log1p(100,000)` |
| Price fit | Distance from user's budget tier |
| Vibe overlap | Keyword match between vibe string and subcategories |
| Dietary conflict | 1 if cuisine conflicts with dietary restriction |
| Is attraction | Category flag |
| Is restaurant | Category flag |

Train with labelled data:

```python
from wayfinder.ranking import MLRanker

ranker = MLRanker()
ranker.fit(attractions, labels, prefs)
# labels: list[int] — 1 if a real user enjoyed this attraction, 0 otherwise
# auto-saves to wayfinder_ml_model.pkl
```

Falls back to `HeuristicRanker` until a model file exists.

---

## API cost management

TripAdvisor's free tier is 5,000 requests/month. A naive run (2 categories × 20 results × 3 calls each) consumed ~120 calls before any ranking. Several changes address this:

### Response cache

All TripAdvisor responses are cached to disk at `~/.wayfinder_cache/` (override with `WAYFINDER_CACHE_DIR`). Cache is keyed by a SHA-256 hash of the endpoint and parameters (excluding the API key). TTLs:

| Endpoint | TTL |
|----------|-----|
| Search results | 7 days |
| Location details | 30 days |
| Photos | 90 days |
| Reviews | 7 days |

Repeat dev runs on the same city cost zero API calls. Run `rm -rf ~/.wayfinder_cache` to force a full refresh. Disable with `--no-cache`.

### Deferred photo fetching

Photos are fetched **only for the final top-k** after ranking — not for every raw result during the initial fetch. This alone cuts ~30% of calls per run.

### `--max-fetch` knob

Controls how many search results per category are fully expanded (details call). Default is 20 for production. Use 5 in development:

```bash
python main.py --city "Tokyo" --max-fetch 5
```

### Typical call counts

| Scenario | Approximate API calls |
|----------|-----------------------|
| First run, full (2 categories × 20, photos for 10, hotels) | ~110 |
| Second run, same city (cache warm) | ~0–5 |
| Dev run (`--max-fetch 5`, `--no-hotels`) | ~12 |

---

## Weather awareness

When `travel_dates` are provided, the pipeline fetches a weather summary for the destination using [Open-Meteo](https://open-meteo.com) — free, no API key needed.

Within a 14-day forecast window, the summary contains real temperature ranges and rain probability. Beyond that, it falls back to a month-based climatology hint.

Example output:

```
Tokyo, July 10–17: highs near 31°C / 88°F, lows near 24°C. Rain likely on 4 of 7 days.
```

This string is injected into the Gemini ranker prompt, which then down-weights outdoor attractions on rainy days and up-weights seasonal experiences (cherry blossoms in April, etc.). The `is_outdoor` and `is_indoor` flags on each attraction are also forwarded to the routing stage so it can do its own weather-aware reshuffling.

Disable with `--no-weather` to skip this step.

---

## Diversity reranking

Without diversity reranking, a city like Tokyo — which has dozens of top-tier ramen spots — would surface six ramen places before any temple. Users who say "food" still want variety.

After scoring, the pipeline applies a category-diversity penalty to the ranked list:

- Walk the list once.
- For each item, count how many already-accepted items share its first subcategory.
- Deduct `diversity_penalty × dup_count` from the score.
- Re-sort.

Example with the default penalty of 0.6:

| Item | Raw score | Dup count | Penalty | Final score |
|------|-----------|-----------|---------|-------------|
| Ramen place A | 8.5 | 0 | 0 | 8.5 |
| Ramen place B | 8.2 | 1 | 0.6 | 7.6 |
| Museum | 7.8 | 0 | 0 | 7.8 |
| Ramen place C | 8.1 | 2 | 1.2 | 6.9 |

So the museum (7.8) rises above the second ramen spot (7.6) and well above the third (6.9).

`diversity_penalty` is tunable via CLI (`--diversity-penalty 0.4` for gentler diversity, `1.0` for aggressive). `--diversity-cap 3` adds a hard ceiling: no more than 3 items per subcategory, regardless of score.

**Mandatory items are completely exempt** — they contribute to the dup count (so the system penalises suggested items that duplicate them), but are never penalised themselves and always appear first.

---

## Persistent trip storage

Every run is saved to `wayfinder/trips/{trip_id}.json` (override directory with `WAYFINDER_TRIPS_DIR`). The `trip_id` is a 12-character hex string printed to stderr.

The file contains the full pipeline output including `candidate_pool` and `restaurant_pool`. This enables:

- **Frontend page reload** — load the trip back without re-running the pipeline.
- **Swap candidates** — serve alternatives from the pre-ranked pool without new API calls.
- **A/B testing** — run the same raw data through different rankers by loading from the trip file.

Disable persistence with `--no-persist`.

```python
from wayfinder import TripStore

store = TripStore()

# List all saved trips
for trip in store.list_trips():
    print(trip["trip_id"], trip["destination"])

# Load a trip
data = store.load("a3f9c2b1d4e8")
print(data["attractions"][0]["name"])
```

---

## Data models

### `UserPreferences`

```python
@dataclass
class UserPreferences:
    destination: str
    travel_dates: tuple[str, str]   # ("YYYY-MM-DD", "YYYY-MM-DD")
    budget: str                     # "budget" | "mid-range" | "luxury"
    vibe: str                       # "romance, art" etc.
    dietary_restrictions: list[str]
    required_attractions: list[str] # these become mandatory
    num_travelers: int
    trip_shape: str                 # "relaxed" | "balanced" | "packed"
    weather_summary: str            # injected by pipeline from Open-Meteo
```

### `PipelineResult`

```python
@dataclass
class PipelineResult:
    trip_id: str
    destination: str
    preferences: dict

    attractions: list[Attraction]    # top-k, mandatory first
    restaurants: list[Attraction]    # top restaurants, injected by bridge
    hotels: list[Attraction]         # top-N by budget + rating

    candidate_pool: list[Attraction] # full ranked list (for swaps)
    restaurant_pool: list[Attraction]

    gaps: str          # LLM completeness note
    api_calls: int
    cache_hits: int
    weather_summary: str

    # computed properties
    mandatory_count: int  # attractions where is_mandatory=True
    suggested_count: int  # attractions where is_mandatory=False
```

### `categories.py`

The single source of truth for category vocabulary. Both `fetcher.py` (duration estimates) and `bridge.py` (routing-stage category names) import from here, so they can never drift out of sync.

```python
from wayfinder.categories import estimate_duration, normalise_to_routing, is_outdoor

estimate_duration("museum", ["Art Museum"])  # → 150
normalise_to_routing("sights & landmarks")  # → "landmark"
is_outdoor("beach")                          # → True
```

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TRIPADVISOR_API_KEY` | — | Required. https://www.tripadvisor.com/developers |
| `GEMINI_API_KEY` | — | Required for GeminiRanker. https://aistudio.google.com |
| `GOOGLE_MAPS_API_KEY` | — | Required for routing stage only |
| `WAYFINDER_CACHE_DIR` | `~/.wayfinder_cache` | Response cache directory |
| `WAYFINDER_TRIPS_DIR` | `./wayfinder/trips` | Trip persistence directory |

---

## Dev workflow

### Day-to-day development (minimal API calls)

```bash
export TRIPADVISOR_API_KEY="..."
export GEMINI_API_KEY="..."

# First run: fetches and caches everything
python main.py --city "Tokyo" --max-fetch 5 --no-hotels --no-completeness --pretty --output tokyo.json

# Subsequent runs on the same city: ~0 API calls
python main.py --city "Tokyo" --max-fetch 5 --no-hotels --no-completeness --pretty

# Inspect the trip store
python swap.py list
python swap.py candidates <trip_id> 2 --pretty
```

### Testing the ranker swap

In `wayfinder/pipeline.py`, find the `← swap here` comment:

```python
from .ranking import GeminiRanker as Ranker   # ← swap here
# from .ranking import HeuristicRanker as Ranker  # zero-API
# from .ranking import MLRanker as Ranker          # trained model
```

### Testing the mandatory system

```python
python main.py \
  --city "Paris" \
  --required "Eiffel Tower" "Catacombs" \
  --k 5 \
  --max-fetch 5 --no-hotels --no-completeness --pretty \
  | python -c "import sys,json; data=json.load(sys.stdin); [print(a['name'], '📌' if a['is_mandatory'] else '⭐', a['selection_source']) for a in data['attractions']]"
```

Expected: "Eiffel Tower 📌 user_required" and "Catacombs 📌 user_required" at the top, even if their ratings are lower than the suggested items.

---

## Adding a new feature

### Add a new ranker

1. Create `wayfinder/ranking/my_ranker.py` that extends `Ranker` from `base.py`.
2. Implement `rank(attractions, prefs) -> list[Attraction]`. Set `score`, `score_reason`, `confidence`, and `ranker_used` on each item. Never touch `is_mandatory` or `selection_source`.
3. Optionally implement `check_completeness(top_k, prefs) -> str`.
4. Change the import in `pipeline.py`.

### Add a new booking platform

Add a URL builder to `filtering/booking_links.py`. No other file needs to change.

### Add a new category

Edit `categories.py` only — add the duration to `CATEGORY_DURATION_MIN` and the routing mapping to `TA_TO_ROUTING_CATEGORY`. Both the fetcher and bridge will pick it up automatically.

### Add a new filter rule

Add a `passes()` condition to `filtering/rules.py`. Remember: `if a.is_mandatory: return True` must stay as the first line of `passes()`.
---