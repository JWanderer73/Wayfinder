# Wayfinder

Wayfinder is an AI-assisted travel planner. This repo currently focuses on the `routing / spatial` backend layer and now supports:

- geocoding attractions with Google Maps
- duration estimation with heuristic defaults and an optional OpenAI hook
- clustering by geography, daily minutes, and soft max items per day
- fixed anchor locations like hotels
- meal or activity anchor times such as lunch at `12:30`
- user removal of activities before routing
- warnings for overloaded days and out-of-the-way stops

## Current Planner Flow

1. Load a trip request from JSON.
2. Filter out user-removed or excluded activities.
3. Fill missing visit durations with heuristics or an optional LLM estimate.
4. Geocode stops with `Geocoding API`.
5. Cluster stops into day buckets with geography plus time/item balancing.
6. Build a per-day route matrix with `Routes API`.
7. Order each day with graph heuristics and basic anchored scheduling.
8. Return a day-by-day schedule with warnings and route matrices.

## Project Files

- [index.py](/Users/jackgui/Desktop/Wayfinder/index.py)
- [sample_trip.json](/Users/jackgui/Desktop/Wayfinder/sample_trip.json)
- [wayfinder/models.py](/Users/jackgui/Desktop/Wayfinder/wayfinder/models.py)
- [wayfinder/google_maps.py](/Users/jackgui/Desktop/Wayfinder/wayfinder/google_maps.py)
- [wayfinder/duration.py](/Users/jackgui/Desktop/Wayfinder/wayfinder/duration.py)
- [wayfinder/spatial.py](/Users/jackgui/Desktop/Wayfinder/wayfinder/spatial.py)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export GOOGLE_MAPS_API_KEY='your-google-key'
python3 index.py sample_trip.json --pretty
```

Optional LLM duration estimates:

```bash
export OPENAI_API_KEY='your-openai-key'
export WAYFINDER_DURATION_MODEL='your-openai-model'
```

If `use_llm_duration_estimates` is `true` in the trip request and those environment variables are set, Wayfinder will try to estimate missing activity durations with OpenAI. If not, it falls back to heuristics.

## Input Shape

Minimal example:

```json
{
  "destination": "New York City",
  "daily_minutes_budget": 480,
  "day_start_time": "09:00",
  "max_stops_per_day": 3,
  "anchor_location": {
    "name": "Hotel Beacon",
    "address": "2130 Broadway, New York, NY 10023"
  },
  "excluded_stop_names": ["Top of the Rock"],
  "end_each_day_at_anchor": true,
  "use_llm_duration_estimates": false,
  "stops": [
    {
      "name": "Chelsea Market",
      "address": "75 9th Ave, New York, NY 10011",
      "category": "food",
      "preferred_start_time": "12:30",
      "anchor_kind": "meal"
    },
    {
      "name": "The Metropolitan Museum of Art",
      "address": "1000 5th Ave, New York, NY 10028",
      "visit_minutes": 180,
      "category": "museum",
      "required": true
    }
  ]
}
```

Useful stop-level fields:

- `visit_minutes`: explicit duration from the user
- `enabled`: set to `false` to remove an activity
- `fixed_day`: pin an activity to a specific day number
- `preferred_start_time`: soft anchor like lunch at `12:30`
- `time_window_start` and `time_window_end`: basic visit window
- `anchor_kind`: label such as `meal` or `hotel`

## What The New Heuristics Do

- `Clustering by number of items`: each day now tries to stay near a soft max number of stops as well as the daily time budget.
- `Specific location anchor`: a hotel or home base can be used as the start of each day, and optionally the end too.
- `Activity duration defaults`: missing times use category and keyword defaults such as museums `150` minutes and food stops `75` minutes.
- `Restaurant anchors`: stops with `preferred_start_time` are placed into the day around that target time when possible.
- `Out-of-the-way warnings`: large detours are flagged in the returned schedule.
- `API-cost-aware routing`: route matrices are built per day after filtering and clustering, instead of on every raw candidate globally.

## Current Limits

- This is still a heuristic planner, not a full time-window solver.
- Traffic-aware time-dependent routing is not implemented yet.
- Opening hours are not yet fetched automatically.
- Google `Routes API` still has its normal element limits per matrix request, so very large single-day stop sets should be avoided.
