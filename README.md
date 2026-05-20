# Wayfinder

AI-powered travel planning: attraction recommendations + day-by-day spatial routing.

---

## Two Pipelines

| Command | What it does | Key API |
|---------|-------------|---------|
| `python index.py recommend` | Fetch attractions from TripAdvisor, rank with Gemini AI, return hotels + booking links | TripAdvisor + Gemini |
| `python index.py plan` | Build a day-by-day spatial itinerary, geocode stops, cluster by time/distance | Google Maps + OpenAI (optional) |

---

## Setup

### Prerequisites
- Python 3.11+
- API keys for the pipelines you want to use (see below)

### Install dependencies

```bash
pip install requests google-genai scikit-learn
```

### API keys

**Recommend pipeline:**
```bash
export TRIPADVISOR_API_KEY="your_key"   # tripadvisor.com/developers (free: 5k/month)
export GEMINI_API_KEY="your_key"        # aistudio.google.com (free: 1500/day)
```

**Plan pipeline:**
```bash
export GOOGLE_MAPS_API_KEY="your_key"   # only needed for stops missing coordinates
export OPENAI_API_KEY="your_key"        # optional: LLM duration estimates
```

---

## Recommend – Travel Attraction Recommender

Fetches real attractions from TripAdvisor, filters and ranks them with Gemini AI, finds hotels, and generates booking links.

### Quick start

```bash
# by city
python index.py recommend --city "Tokyo, Japan" --pretty

# from JSON file
python index.py recommend --input example_trip.json --pretty
```

### Input JSON format

```json
{
  "destination": "Tokyo, Japan",
  "preferences": ["culture", "food", "anime"],
  "budget": "mid-range",
  "vibe": "cultural exploration, street food",
  "dietary_restrictions": ["vegetarian"],
  "required_attractions": ["Senso-ji Temple", "Shibuya Crossing"],
  "k": 10
}
```

### Pipeline steps

1. **Fetch** — TripAdvisor search (attractions + restaurants)
2. **Filter** — drop low-rated places; filter dietary conflicts
3. **Rank** — Gemini scores each attraction 0–10 for fit
4. **Pin** — required attractions always appear in output
5. **Links** — TripAdvisor, Viator, GetYourGuide, Google Maps, OpenTable
6. **Completeness** — Gemini checks for obvious gaps
7. **Hotels** — top 5 by rating, filtered by budget tier

### Switching the ranker

In `wayfinder/pipeline.py`, change the import line marked `← SWAP HERE` to use the offline ML ranker instead of Gemini.

---

## Plan – Spatial Itinerary Planner

Builds a day-by-day schedule from a list of stops, geocoding missing coordinates and clustering by geography + time budget.

### Quick start

```bash
python index.py plan sample_trip.json --pretty
```

### Input JSON format

```json
{
  "destination": "New York City",
  "daily_minutes_budget": 480,
  "day_start_time": "09:00",
  "transport_mode": "auto",
  "anchor_location": {
    "name": "Hotel Beacon",
    "latitude": 40.7807066,
    "longitude": -73.9810319
  },
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

### What it produces

- Day-by-day schedule with arrival/departure times
- Local distance matrix (no Google API calls when coordinates are provided)
- Transport mode selection: walk / transit / drive based on distance
- Warnings for overloaded days and out-of-the-way stops

---

## Tests

```bash
python3 -m unittest discover
```

---

## File Structure

```
index.py                    ← CLI entry point (subcommands: plan / recommend)
sample_trip.json            ← sample input for the plan pipeline
example_trip.json           ← sample input for the recommend pipeline
wayfinder/
├── models.py               ← data classes for both pipelines
├── tripadvisor.py          ← TripAdvisor API client
├── filters.py              ← rule-based filter + booking link generator
├── hotels.py               ← hotel search
├── pipeline.py             ← recommend pipeline orchestration
├── ranking.py              ← GeminiRanker (+ commented MLRanker)
├── spatial.py              ← plan pipeline: clustering + scheduling
├── routing.py              ← graph-based route ordering
├── google_maps.py          ← Google Maps geocoding client
├── duration.py             ← visit duration estimator
└── review.py               ← LLM cluster review
```
