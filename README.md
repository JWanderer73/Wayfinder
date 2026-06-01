# Wayfinder

Wayfinder is an AI-assisted travel planning backend. It turns a destination,
travel constraints, candidate attractions, and optional hotel data into a
day-by-day itinerary with ordered stops, estimated travel time, booking links,
and warnings when a day is too rushed or a stop is far away.

The current project has two command-line paths:

- `python3 index.py plan`: build a spatial itinerary from an existing trip JSON.
- `python3 index.py recommend`: fetch and rank attractions, then return a recommendation payload.

Most current development is focused on the graph, clustering, and spatial
routing part of the planner. The planner can run completely without Google API
calls when the input already includes latitude and longitude.

## Current Status

Implemented in the main codebase:

- Trip JSON normalization for both planner-native inputs and teammate-generated recommendation payloads.
- Activity filtering by disabled stops, excluded stop names, preferred categories, and excluded categories.
- Required attraction preservation during filtering and ranking normalization.
- Visit-duration estimation using category and keyword heuristics with redundancy.
- Optional OpenAI duration estimation for missing durations.
- Optional OpenAI review notes for final cluster quality.
- Geocoding only for stops or hotel anchors missing coordinates.
- Time-cap clustering for recommendation payloads.
- Best-point clustering for hand-authored planner payloads.
- Local latitude/longitude distance matrices to avoid route-matrix API costs.
- Automatic transportation choice: walk, transit, or drive based on distance.
- Lunch, dinner, daily slack, and per-leg travel buffers.
- Hotel or home-base anchor support.
- Return-to-anchor support at the end of each day.
- Soft meal/activity time anchors such as lunch at `12:30`.
- Overloaded-day, time-intensive-activity, and out-of-the-way-stop warnings.
- Compact reference outputs for the two teammate sample trips.

Still future or optional:

- Live Google route duration and traffic-aware routing.
- Full opening-hours validation.
- A production frontend connected to the backend.
- A true optimization solver for hard time windows.
- Real reservation integrations.

## Quick Start

Use Python 3.10 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 index.py plan trips/paris_test.json --pretty
```

Run the Tokyo sample:

```bash
python3 index.py plan trips/tokyo_test.json --pretty
```

If no input file is provided, `plan` defaults to `trips/paris_test.json`:

```bash
python3 index.py plan --pretty
```

Run tests:

```bash
python3 -m unittest discover
```

## Project Structure

- `index.py`: command-line entry point for `plan` and `recommend`.
- `wayfinder/models.py`: dataclasses, JSON parsing, sample trip normalization, recommendation payload conversion.
- `wayfinder/duration.py`: activity duration estimation and optional OpenAI duration client.
- `wayfinder/google_maps.py`: Google Maps geocoding and older route API helper methods.
- `wayfinder/routing.py`: local haversine distance matrix, transport mode choice, travel time estimates.
- `wayfinder/spatial.py`: filtering, day clustering, ordering, scheduling, warning generation.
- `wayfinder/tripadvisor.py`: TripAdvisor Content API wrapper.
- `wayfinder/ranking.py`: Gemini ranking and heuristic fallback scoring.
- `wayfinder/pipeline.py`: full recommendation pipeline.
- `wayfinder/hotels.py`: TripAdvisor hotel search and booking-link enrichment.
- `wayfinder/filters.py`: attraction filtering and generated booking links.
- `wayfinder/review.py`: optional OpenAI itinerary review hook.
- `tests/test_routing.py`: regression tests for routing, clustering, duration, API-free planning, and sample trips.
- `trips/paris_test.json`: teammate-provided Paris recommendation payload.
- `trips/tokyo_test.json`: teammate-provided Tokyo recommendation payload.
- `trips/paris_result.json`: compact Paris reference output.
- `trips/tokyo_result.json`: compact Tokyo reference output.
- `Wayfinder-Abhinav/`: partner reference code only. It is not imported by the running app.

## Main Planner Flow

The `plan` command follows this flow:

1. Load a JSON trip request from disk.
2. Normalize the payload into a `TripRequest`.
3. Convert teammate recommendation payloads from `attractions` and `hotels` into planner-ready `stops` and an optional hotel anchor.
4. Remove disabled stops, user-excluded stops, and optional stops outside the selected category filters.
5. Preserve required stops unless they are explicitly disabled.
6. Estimate missing or recommendation-provided durations.
7. Resolve coordinates locally if latitude and longitude already exist.
8. Geocode only stops or anchors that are missing coordinates.
9. Estimate the number of days needed from visit time, approximate travel time, lunch, dinner, and slack.
10. Cluster stops into day buckets.
11. Build a local distance matrix for each day.
12. Pick a transportation mode per leg.
13. Order stops with a graph-style nearest-neighbor route heuristic and anchor handling.
14. Schedule arrival, start, and departure times.
15. Add warnings and planning notes.
16. Print a structured JSON itinerary.

## Reference Trip Results

The current sample outputs are stored as compact result files so the team can
compare future changes against known behavior.

| Input | Output | Current behavior |
| --- | --- | --- |
| `trips/paris_test.json` | `trips/paris_result.json` | 8 stops, expanded to 5 days, no overloaded-day warnings, hotel anchor `Le Bristol Paris`, local matrix work of 35 pairwise elements. |
| `trips/tokyo_test.json` | `trips/tokyo_result.json` | 11 stops, expanded to 5 days, 2 overloaded single-stop Disney days, hotel anchor `Park Hyatt Tokyo`, local matrix work of 56 pairwise elements. |

Current day totals in the compact outputs:

- Paris: `[531, 434, 540, 398, 457]` minutes against a 540-minute daily budget.
- Tokyo: `[758, 752, 629, 591, 570]` minutes against a 660-minute daily budget.

Tokyo still has two warnings because `Tokyo DisneySea` and `Tokyo Disneyland`
are estimated as full-day activities. The planner correctly gives each of them
a dedicated day rather than mixing them with other attractions.

## Input Formats

Wayfinder accepts two main input styles.

### Planner-Native Input

Use this format when the user or frontend already knows the stop list.

```json
{
  "destination": "New York City",
  "start_date": "2026-06-10",
  "end_date": "2026-06-12",
  "daily_minutes_budget": 480,
  "day_start_time": "09:00",
  "transport_mode": "auto",
  "lunch_minutes": 60,
  "dinner_minutes": 120,
  "daily_redundancy_minutes": 45,
  "travel_buffer_ratio": 0.15,
  "minimum_travel_buffer_minutes": 5,
  "clustering_method": "best_point",
  "preferred_categories": ["museum", "food", "park"],
  "excluded_categories": ["nightlife"],
  "max_stops_per_day": 3,
  "end_each_day_at_anchor": true,
  "anchor_location": {
    "name": "Hotel Beacon",
    "latitude": 40.7807066,
    "longitude": -73.9810319,
    "anchor_kind": "hotel"
  },
  "excluded_stop_names": ["Top of the Rock"],
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

### Recommendation Payload Input

Use this format when the data comes from the recommendation pipeline or a
teammate's generated trip file. This is the shape used by the Paris and Tokyo
sample trips.

```json
{
  "destination": "Tokyo",
  "preferences": {
    "trip_shape": "packed",
    "required_attractions": ["Senso-ji Temple", "Shibuya Crossing"]
  },
  "attractions": [
    {
      "location_id": "320447",
      "name": "Senso-ji Temple",
      "category": "Sights & Landmarks",
      "rating": 4.4,
      "latitude": 35.7147,
      "longitude": 139.79678,
      "duration_minutes": 75,
      "web_url": "https://example.com"
    }
  ],
  "hotels": [
    {
      "location_id": "307368",
      "name": "Park Hyatt Tokyo",
      "latitude": 35.68565,
      "longitude": 139.69109
    }
  ]
}
```

When this shape is loaded, `wayfinder/models.py` automatically:

- Converts `attractions` into `stops`.
- Uses the first hotel with coordinates as the daily anchor.
- Sets `end_each_day_at_anchor` to `true`.
- Converts broad TripAdvisor categories into planner categories such as `museum`, `landmark`, `restaurant`, `shopping`, or `amusement_park`.
- Chooses trip shape `relaxed`: 480 minutes/day, max 2 stops/day, 60 minutes slack.
- Chooses trip shape `balanced`: 540 minutes/day, max 3 stops/day, 45 minutes slack.
- Chooses trip shape `packed`: 660 minutes/day, max 4 stops/day, 30 minutes slack.
- Defaults generated trips to `clustering_method: "time_cap_kmeans"`.

## Useful Stop Fields

- `name`: required display name.
- `id` or `location_id`: stable identifier.
- `address`: used for geocoding when coordinates are missing.
- `latitude` and `longitude`: preferred because they avoid Google geocoding calls.
- `visit_minutes`: explicit user-provided duration.
- `visit_minutes_source`: source label such as `user`, `recommendation`, `heuristic`, or `heuristic_redundancy`.
- `required`: keeps a stop from being removed by category preference filters.
- `category`: used by filters and duration defaults.
- `enabled`: set to `false` to remove an activity before planning.
- `fixed_day`: pins the stop to a specific day number.
- `preferred_start_time`: soft preferred start, for example `"12:30"`.
- `time_window_start` and `time_window_end`: simple visit window.
- `anchor_kind`: labels special stops such as `meal` or `hotel`.
- `priority`: higher-priority stops are assigned earlier during clustering.
- `web_url`, `photo_url`, `booking_url`, `booking_links`: preserved into final outputs.
- `rating`, `score`, `score_reason`, `open_hours_text`: preserved from recommendation results.

## Clustering Algorithms

Wayfinder currently supports three clustering behaviors.

### `time_cap_kmeans`

This is the default for generated recommendation payloads. It is inspired by
Abhinav's KMeans/time-cap idea, but implemented inside the main codebase without
adding `sklearn` or plotting dependencies.

How it works:

- Start with any `fixed_day` attractions already placed in their required day.
- Seed empty days using long activities first, then high-value and geographically separated stops.
- Try multiple deterministic seed layouts.
- Assign remaining stops to the cluster with the best score.
- Score each possible assignment using time overflow, item overflow, total minutes, cluster compactness, and attraction priority.
- Estimate each cluster's time using visit durations plus local route time from the hotel anchor when available.
- Rebalance by moving stops between days when that reduces overload.
- Keep the best scoring cluster layout.

This method is useful for teammate-generated trips because the candidate list
often includes mixed activity lengths. For example, it separates Disneyland and
DisneySea into their own days instead of treating them like normal 75-minute
attractions.

### `best_point`

This is the default for planner-native inputs. It behaves like a lightweight
k-medoids strategy:

- Pick strong seed points for each day.
- Prefer required, high-priority, and long activities as seeds.
- Add nearby attractions to each seed while there is enough time and item capacity.
- If no stop cleanly fits, assign the least-bad overflow candidate.

This is easy to explain in a project presentation: each day starts around a
"best point," then grows by adding nearby stops until the day would become too
rushed.

### Legacy Centroid Mode

Any other `clustering_method` value falls back to a simpler centroid assignment:

- Seed days with fixed stops and farthest-first geography.
- Assign each remaining stop to the closest cluster centroid.
- Penalize clusters that exceed the time budget or item target.

This is kept mostly as a simple baseline for comparison.

## Duration Estimation

The original teammate payloads used `75` minutes for almost every attraction.
That made the output unrealistic, so recommendation-provided durations are now
re-estimated by `wayfinder/duration.py`.

The heuristic uses:

- Category defaults, for example museums, restaurants, parks, landmarks, tours, shopping, and amusement parks.
- Keyword overrides, for example `Disneyland`, `DisneySea`, `teamLab`, `catacombs`, `temple`, `crossing`, or `market`.
- A small redundancy buffer of 10 percent, with a minimum of 10 minutes and maximum of 30 minutes.
- Rounding up to the nearest 5 minutes.

Examples from tests:

- `Tokyo Disneyland`: 450 minutes.
- `Tokyo DisneySea`: 450 minutes.
- `teamLab Planets TOKYO`: 135 minutes.
- `Shibuya Crossing`: 40 minutes.
- `Senso-ji Temple`: 70 minutes.

If `use_llm_duration_estimates` is `true` and OpenAI environment variables are
configured, missing durations can be estimated with an LLM. If the LLM is not
configured or fails, the planner falls back to local heuristics.

## Routing And Scheduling

Routing currently uses local distance estimates, not live Google route calls.

For each day:

- Build a distance matrix using haversine distance between coordinates.
- Include the hotel anchor in the matrix when one exists.
- Choose transport mode automatically unless the user specifies one.
- Use nearest-neighbor route ordering from the anchor or best starting point.
- Respect basic preferred start times and time windows when possible.
- Add travel buffers to avoid rushing.
- Add lunch, dinner, and daily redundancy time to each day total.
- Flag long or far-away activities.

Automatic transport thresholds:

- Walk when the leg is `<= 1,200` meters.
- Transit when the leg is `<= 8,000` meters.
- Drive when the leg is longer than `8,000` meters.

Supported transport aliases include `walking`, `by foot`, `public transport`,
`bus`, `subway`, `train`, `car`, `driving`, `bike`, and `auto`.

## API Usage

### Google Maps

The current `plan` command only needs Google Maps when an active stop or anchor
is missing latitude and longitude.

Set the key only when geocoding is needed:

```bash
export GOOGLE_MAPS_API_KEY='your-google-key'
```

Required Google API for current planning:

- `Geocoding API`: only for missing coordinates.

Not required for the current local planner:

- `Routes API`
- `Distance Matrix API`
- `Directions API`
- `Route Optimization API`

Those route APIs are useful future upgrades, but the current planner avoids
them to reduce cost.

Google API call complexity for `plan`:

```text
O(u)
```

`u` is the number of active stops and anchors missing coordinates. If every stop
already has `latitude` and `longitude`, `u = 0`, so there are no Google calls.
The Paris and Tokyo reference trips include coordinates, so they run without a
Google key.

Local pairwise matrix work:

```text
O(sum(k_i^2))
```

`k_i` is the number of matrix nodes on day `i`, including the hotel anchor when
present. This is local CPU work only. It is not billed by Google.

### TripAdvisor And Gemini

The `recommend` command uses external APIs.

Required environment variables:

```bash
export TRIPADVISOR_API_KEY='your-tripadvisor-key'
export GEMINI_API_KEY='your-gemini-key'
```

Example:

```bash
python3 index.py recommend \
  --city Tokyo \
  --preferences culture food nightlife \
  --required "Senso-ji Temple" "Shibuya Crossing" \
  --k 10 \
  --pretty
```

The recommendation pipeline:

1. Searches TripAdvisor for attractions and restaurants.
2. Fetches details and photos.
3. Adds required attractions if they were missing from the first search.
4. Filters the raw candidates.
5. Scores candidates with Gemini.
6. Falls back to heuristic scoring if Gemini output cannot be parsed.
7. Adds booking links.
8. Optionally checks completeness with Gemini.
9. Optionally searches hotels through TripAdvisor.

TripAdvisor call count is tracked in the returned `api_calls` field and printed
by the command.

### Optional OpenAI Hooks

For duration estimates:

```bash
export OPENAI_API_KEY='your-openai-key'
export WAYFINDER_DURATION_MODEL='your-openai-model'
```

For itinerary review:

```bash
export OPENAI_API_KEY='your-openai-key'
export WAYFINDER_REVIEW_MODEL='your-openai-model'
```

Then enable the corresponding fields in the input JSON:

```json
{
  "use_llm_duration_estimates": true,
  "use_llm_cluster_review": true
}
```

These hooks are optional. The sample trips do not require them.

## Output Shape

The planner prints an `ItineraryPlan` JSON object with:

- `destination`
- `num_days`
- `daily_minutes_budget`
- `resolved_stops`
- `days`
- `removed_stops`
- `planning_notes`
- `anchor_location`
- `matrix_scope`

Each day includes:

- `scheduled_visits`
- `total_visit_minutes`
- `total_travel_minutes`
- `total_travel_buffer_minutes`
- `total_wait_minutes`
- `lunch_minutes`
- `dinner_minutes`
- `redundancy_minutes`
- `total_minutes`
- `warnings`
- `ordered_stop_ids`
- `matrix_stop_order`
- `route_matrix`
- `start_anchor`
- `end_anchor`
- `return_to_anchor_minutes`

The compact files in `trips/*_result.json` keep the presentation-friendly parts
of this output and remove bulky route matrices.

## Warning Types

The planner can warn when:

- A day is overloaded beyond the daily minutes budget.
- A stop is time-intensive and should probably be treated as a major day segment.
- A stop is out of the way and creates a large detour.
- The LLM duration or review hook was requested but not configured.
- All candidates were removed by filters.

Warnings are intentionally not hard failures. They are meant to show the user
where the itinerary may feel unrealistic.

## How Abhinav's Code Was Used

`Wayfinder-Abhinav/` was reviewed as a reference implementation, not copied in
as a dependency.

Useful ideas adapted into the main code:

- KMeans-style thinking for grouping nearby attractions.
- Time-cap scoring so clusters care about day budget, not only geography.
- Trying multiple cluster layouts and keeping the best one.

Changes made in the main code instead of importing Abhinav's files:

- No `sklearn` dependency was added.
- No `matplotlib` plotting requirement was added.
- No hard-coded local file paths were added.
- No hard-coded Google API project or API key was added.
- The planner remains testable from `python3 -m unittest discover`.

## Tests

Run the full test suite:

```bash
python3 -m unittest discover
```

The tests currently cover:

- Transport mode normalization.
- Auto mode choosing walk, transit, or drive.
- Local distance matrix behavior.
- Travel buffer calculation.
- Meal and redundancy buffers.
- API-free planning when coordinates are present.
- Category preference filtering.
- Best-point clustering.
- Paris and Tokyo recommendation payload normalization.
- Required attraction preservation.
- Duration re-estimation for recommendation payloads.
- Paris sample planning with no overloaded days.
- Tokyo sample planning with only unavoidable single-stop Disney overloads.

## Development Notes

Use coordinates whenever possible. Coordinates keep Google usage at `O(u)` for
unresolved places instead of requiring paid route matrix calls.

Do not put real API keys in source files. Use environment variables:

```bash
export GOOGLE_MAPS_API_KEY='...'
export TRIPADVISOR_API_KEY='...'
export GEMINI_API_KEY='...'
export OPENAI_API_KEY='...'
```

The app can safely be shared without exposing your key if the key stays on the
server or in local environment variables. A frontend should call your backend,
and the backend should call Google or TripAdvisor. Do not expose unrestricted
API keys directly in browser JavaScript.

When changing algorithms, compare against:

- `python3 index.py plan trips/paris_test.json --pretty`
- `python3 index.py plan trips/tokyo_test.json --pretty`
- `python3 -m unittest discover`

## Current Limitations

- Travel times are distance-based estimates, not live traffic or exact transit schedules.
- Opening hours are preserved from input when present but are not fully enforced.
- Anchored scheduling is basic and not a full constraint solver.
- Restaurant reservations are represented as links, not live booking availability.
- The recommendation command requires live API keys and network access.
- The frontend is not yet a finished connected product.
- Very large trips may need stronger optimization than the current heuristic route ordering.
