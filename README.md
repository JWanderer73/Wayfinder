# Wayfinder

# Wayfinder

Wayfinder is an AI-assisted trip planner. This repo now includes a first working backend slice for the spatial and routing layer:

- geocode user-selected attractions
- build a Google travel-time matrix
- cluster attractions into day groups
- order each day with graph heuristics

## What This Starter Solves

This version focuses on the part you said you are owning: `routing/spatial`.

Current flow:

1. Load a trip request from JSON.
2. Resolve each stop into coordinates with `Geocoding API` when needed.
3. Build an `N x N` travel-time matrix with `Routes API`.
4. Estimate day count from dates or budget.
5. Cluster stops into day buckets with a geography-aware greedy assignment.
6. Order each day using:
- nearest neighbor to get a fast initial route
- 2-opt to improve the path

This is a strong beginner-friendly baseline because it is simple to explain and good enough to demo.

## Project Structure

- [index.py](/Users/jackgui/Desktop/Wayfinder/index.py)
- [sample_trip.json](/Users/jackgui/Desktop/Wayfinder/sample_trip.json)
- [wayfinder/models.py](/Users/jackgui/Desktop/Wayfinder/wayfinder/models.py)
- [wayfinder/google_maps.py](/Users/jackgui/Desktop/Wayfinder/wayfinder/google_maps.py)
- [wayfinder/spatial.py](/Users/jackgui/Desktop/Wayfinder/wayfinder/spatial.py)

## Setup

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Export your Google Maps API key:

```bash
export GOOGLE_MAPS_API_KEY='your-key-here'
```

Run the sample:

```bash
python3 index.py sample_trip.json --pretty
```

## Input Format

Example request:

```json
{
  "destination": "New York City",
  "start_date": "2026-06-10",
  "end_date": "2026-06-12",
  "daily_minutes_budget": 480,
  "travel_mode": "DRIVE",
  "stops": [
    {
      "name": "Statue of Liberty Ferry",
      "address": "Battery Park, New York, NY",
      "visit_minutes": 150,
      "required": true
    }
  ]
}
```

Each stop can be given by:

- `address`
- or `latitude` and `longitude`

## Algorithm Notes

The spatial layer uses simple, explainable heuristics:

- `Farthest-first seeds`: spreads day clusters across the city before assignment
- `Budget-aware clustering`: tries to keep daily visit time within a soft budget
- `Nearest neighbor`: fast initial route construction
- `2-opt`: local improvement pass to reduce zig-zagging

- `index.py`
- `sample_trip.json`
- `wayfinder/models.py`
- `wayfinder/google_maps.py`
- `wayfinder/spatial.py`