# Wayfinder

Wayfinder is an AI-assisted travel planner. This repo currently focuses on the `routing / spatial` backend layer and now supports:

- geocoding attractions with Google Maps
- duration estimation with heuristic defaults and an optional OpenAI hook
- clustering by geography, daily minutes, and soft max items per day
- local latitude/longitude routing to avoid route-matrix API calls
- fixed anchor locations like hotels
- meal or activity anchor times such as lunch at `12:30`
- fixed meal buffers: `60` minutes for lunch and `120` minutes for dinner
- travel redundancy so the schedule is less rushed
- user removal of activities before routing
- warnings for overloaded days and out-of-the-way stops

## Current Planner Flow

1. Load a trip request from JSON.
2. Filter out user-removed or excluded activities.
3. Fill missing visit durations with heuristics or an optional LLM estimate.
4. Geocode only stops that do not already include `latitude` and `longitude`.
5. Cluster stops into day buckets with geography plus time/item balancing.
6. Build a local per-day distance matrix from coordinates.
7. Pick walking, public transit, or driving estimates from distance and requested mode.
8. Order each day with graph heuristics and basic anchored scheduling.
9. Return a day-by-day schedule with warnings and local distance matrices.

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

`GOOGLE_MAPS_API_KEY` is only required when an input stop is missing coordinates. If every active stop and anchor has `latitude` and `longitude`, the sample can run without Google API calls.

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
  "transport_mode": "auto",
  "lunch_minutes": 60,
  "dinner_minutes": 120,
  "daily_redundancy_minutes": 45,
  "travel_buffer_ratio": 0.15,
  "max_stops_per_day": 3,
  "anchor_location": {
    "name": "Hotel Beacon",
    "latitude": 40.7807066,
    "longitude": -73.9810319
  },
  "excluded_stop_names": ["Top of the Rock"],
  "end_each_day_at_anchor": true,
  "use_llm_duration_estimates": false,
  "stops": [
    {
      "name": "Chelsea Market",
      "latitude": 40.7424509,
      "longitude": -74.0059581,
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
- `latitude` and `longitude`: preferred input because it avoids a geocoding API call
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
- `API-cost-aware routing`: routing uses local distance estimates, so Google API calls scale with unresolved coordinates, not route pairs.
- `Transport selection`: `transport_mode: "auto"` walks for close stops, uses transit for medium distances, and drives for longer distances.
- `Time redundancy`: each day reserves lunch, dinner, daily slack, and a buffer on every travel leg.

## API Complexity

With coordinates provided, routing does not call Google Maps. The Google API call count is:

```text
O(u)
```

where `u` is the number of active stops and anchors missing coordinates.

The local distance matrix still does pairwise work per day:

```text
O(sum(k_i^2))
```

where `k_i` is the number of stops in day `i`, but that work happens locally and is not billed as Google API usage.

## Tests

```bash
python3 -m unittest discover
```

## Current Limits

- This is still a heuristic planner, not a full time-window solver.
- Traffic-aware time-dependent routing is not implemented yet.
- Opening hours are not yet fetched automatically.
- Local travel times are estimates from distance, not live traffic or exact transit schedules.
