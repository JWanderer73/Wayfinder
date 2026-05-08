# Wayfinder 🗺️
### AI-Powered Travel Attraction Recommender

Wayfinder takes a destination, your travel preferences, and any dietary restrictions, then automatically fetches real attractions from TripAdvisor, filters and ranks them using an AI model, finds hotels, and generates booking links — all from the command line.

---

## Table of Contents
1. [Project Overview](#project-overview)
2. [How It Works](#how-it-works)
3. [File Structure](#file-structure)
4. [Setup](#setup)
5. [Getting Your API Keys](#getting-your-api-keys)
6. [Running the Code](#running-the-code)
7. [Testing the Code](#testing-the-code)
8. [Switching the AI Ranker](#switching-the-ai-ranker)
9. [Output Format](#output-format)
10. [API Usage & Cost](#api-usage--cost)
11. [Troubleshooting](#troubleshooting)

---

## Project Overview

Wayfinder is one component of a larger AI travel planning system. Its responsibility is:

- **Input:** Destination city, travel dates, budget, vibe, dietary restrictions, must-see attractions
- **Output:** A ranked list of top attractions + hotels + booking links, ready for the routing/map stage

The system is designed so the **AI ranker is swappable** — you can use Claude (Anthropic), Gemini (Google, free), or a custom ML model, all with a one-line change.

---

## How It Works

The pipeline runs in 7 steps every time you make a request:

```
User Input (city, preferences, dietary restrictions)
        │
        ▼
① FETCH — TripAdvisor Content API
   • Searches for attractions + restaurants in the destination
   • Fetches full details for each: rating, coordinates, price, hours, photos
   • Explicitly searches for any "required" attractions not in results
        │
        ▼
② FILTER — Rule-Based Pre-Filter (fast, no API cost)
   • Drops places rated under 3.5 stars with 50+ reviews (clearly bad)
   • Drops restaurants outside the user's budget price tier
   • Drops restaurants with cuisines that conflict with dietary restrictions
     (e.g. steakhouse blocked for vegans)
        │
        ▼
③ RANK — AI Scoring (LLM or ML model)
   • Each attraction gets a score 0–10 based on how well it fits the
     traveler's vibe, budget, and dietary needs
   • Batched in groups of 10 to reduce API calls
        │
        ▼
④ PIN — Required Attractions Locked to Top
   • Any attraction the user listed as "must-see" is always included,
     regardless of its AI score
        │
        ▼
⑤ BOOKING LINKS — Generated for Each Attraction
   • TripAdvisor direct booking (if available)
   • Viator (tours & experiences)
   • GetYourGuide (tours & experiences)
   • Google Maps (navigation)
   • OpenTable (restaurants only)
        │
        ▼
⑥ COMPLETENESS CHECK — Optional LLM Gap Analysis
   • AI reviews the final shortlist and flags anything obviously missing
   • e.g. "No breakfast spots included" or "Required attraction X is absent"
        │
        ▼
⑦ HOTELS — Separate TripAdvisor Search
   • Fetches hotels, soft-filters by budget subcategory
   • Returns top 5 by rating
        │
        ▼
Output: JSON with ranked attractions, hotels, gaps, API call count
```

---

## File Structure

```
wayfinder/              ← main Python package
│
├── __init__.py         ← exports: Attraction, UserPreferences, generate_recommendations
├── models.py           ← data classes: Attraction, UserPreferences
├── tripadvisor.py      ← TripAdvisor API client + fetch_attractions()
├── filters.py          ← rule-based filter + booking link generator
├── hotels.py           ← hotel search, filtered by budget tier
├── pipeline.py         ← orchestrates all 7 steps, called by main.py
├── ranking.py          ← LLMRanker (Claude) + MLRanker (commented out)
└── ranking_gemini.py   ← GeminiRanker (free alternative to Claude)

main.py                 ← CLI entry point (the file you run)
example_trip.json       ← sample input file for testing
```

---

## Setup

### 1. Prerequisites
- Python 3.11 or higher
- A TripAdvisor API key (free)
- Either a Gemini API key (free) OR an Anthropic API key (~$5 free credits)

### 2. Install dependencies

```bash
pip install requests anthropic google-genai
```

> If you get a permissions error on Linux/Mac, add `--break-system-packages` or use a virtual environment.

### 3. Clone / download the project

Make sure your folder looks like this before running anything:

```
your-project/
├── main.py
├── example_trip.json
└── wayfinder/
    ├── __init__.py
    ├── models.py
    ├── tripadvisor.py
    ├── filters.py
    ├── hotels.py
    ├── pipeline.py
    ├── ranking.py
    └── ranking_gemini.py
```

---

## Getting Your API Keys

### TripAdvisor API Key (required)

1. Go to **https://www.tripadvisor.com/developers**
2. Click **"Get Started"** and create an account
3. Create a new project — you can put your project name and a basic description
4. For "API key restriction" leave it **blank** for development (or add your IP addresses)
5. Copy the key

Free tier: **5,000 requests/month**

### Gemini API Key (recommended — completely free)

> Use this if you don't want to pay anything. Your Gemini Pro subscription does NOT include API access — this is a separate free product.

1. Go to **https://aistudio.google.com**
2. Sign in with your Google account
3. Click **"Get API key"** in the top left → **"Create API key"**
4. Copy the key

Free tier: **1,500 requests/day** — more than enough for this project.

### Setting Your Keys

**Mac / Linux:**
```bash
export TRIPADVISOR_API_KEY="paste-your-key-here"
export GEMINI_API_KEY="paste-your-key-here"
```

**Windows (Command Prompt):**
```cmd
set TRIPADVISOR_API_KEY=paste-your-key-here
set GEMINI_API_KEY=paste-your-key-here
```

**Windows (PowerShell):**
```powershell
$env:TRIPADVISOR_API_KEY="paste-your-key-here"
$env:GEMINI_API_KEY="paste-your-key-here"
```

> **Important:** Never paste your API keys directly into the code files. Always use environment variables so you don't accidentally commit them to GitHub.

---

## Running the Code

### Option A — Run with a JSON input file

This is the cleanest way. Edit `example_trip.json` with your destination and preferences, then run:

```bash
python main.py --input example_trip.json --pretty
```

The JSON file format:
```json
{
  "destination": "Tokyo, Japan",
  "preferences": ["culture", "food", "anime"],
  "budget": "mid-range",
  "vibe": "cultural exploration, street food",
  "dietary_restrictions": ["vegetarian"],
  "required_attractions": ["Senso-ji Temple", "Shibuya Crossing"],
  "travel_dates": ["2025-07-10", "2025-07-17"],
  "num_travelers": 2,
  "k": 10
}
```

### Option B — Run with command-line flags

```bash
python main.py --city "Tokyo, Japan" --pretty
```

With full preferences:
```bash
python main.py \
  --city "Tokyo, Japan" \
  --budget mid-range \
  --vibe "food, culture" \
  --dietary vegetarian \
  --required "Senso-ji Temple" "Shibuya Crossing" \
  --dates 2025-07-10 2025-07-17 \
  --travelers 2 \
  --k 10 \
  --pretty
```

### All available flags

| Flag | Description | Default |
|------|-------------|---------|
| `--input FILE` | Path to JSON input file | — |
| `--city "CITY"` | Destination city | — |
| `--budget` | `budget`, `mid-range`, or `luxury` | `mid-range` |
| `--vibe "TEXT"` | Travel style description | — |
| `--dietary RESTRICTION` | e.g. `vegetarian gluten-free` | — |
| `--required "NAME"` | Must-include attractions (quoted) | — |
| `--dates START END` | Travel dates as `YYYY-MM-DD` | — |
| `--travelers N` | Number of travelers | `2` |
| `--k N` | Number of attractions to return | `10` |
| `--pretty` | Pretty-print the JSON output | off |
| `--no-hotels` | Skip hotel search (saves API calls) | off |
| `--no-completeness` | Skip AI gap analysis (saves API calls) | off |
| `--output FILE` | Also save results to a JSON file | — |

### Save results to a file

```bash
python main.py --input example_trip.json --pretty --output results.json
```

---

## Testing the Code

### Step 1 — Test imports only (no API keys needed)

This confirms the code is set up correctly before you even have keys:

```bash
python -c "
from wayfinder.models import Attraction, UserPreferences
from wayfinder.tripadvisor import TripAdvisorClient
from wayfinder.filters import AttractionFilter, generate_booking_links
from wayfinder.hotels import HotelFinder
from wayfinder.ranking import LLMRanker
from wayfinder.ranking_gemini import GeminiRanker
from wayfinder.pipeline import generate_recommendations
print('All imports OK')
"
```

Expected output: `All imports OK`

### Step 2 — Test the filter logic (no API keys needed)

```bash
python -c "
from wayfinder.models import Attraction, UserPreferences
from wayfinder.filters import AttractionFilter, generate_booking_links

prefs = UserPreferences(destination='Tokyo', budget='mid-range', vibe='culture')

# a good attraction — should pass
good = Attraction('1', 'Senso-ji Temple', 'Attraction', ['Temple'],
                  4.8, 50000, 'Asakusa', 35.71, 139.79, 'http://example.com')

# a bad restaurant for a vegan — should be blocked
bad = Attraction('2', 'Tokyo Steakhouse', 'Restaurant', ['Steakhouse'],
                 4.5, 2000, 'Shinjuku', 35.69, 139.70, 'http://example.com',
                 cuisine_types=['Steakhouse'])
prefs.dietary_restrictions = ['vegan']

filt = AttractionFilter(prefs)
assert filt.passes(good) == True,  'Good attraction should pass'
assert filt.passes(bad)  == False, 'Steakhouse should fail for vegan'

# test booking links
links = generate_booking_links(good, prefs)
assert 'Viator' in links
assert 'Google Maps' in links
print('Filter tests passed')
print('Booking links:', list(links.keys()))
"
```

Expected output:
```
Filter tests passed
Booking links: ['Viator', 'GetYourGuide', 'Google Maps']
```

### Step 3 — Test the CLI help (no API keys needed)

```bash
python main.py --help
```

### Step 4 — Test with real API keys

Once you have both keys set, do a quick smoke test with `--no-completeness` and `--no-hotels` to minimize API calls:

```bash
python main.py \
  --city "New York" \
  --budget mid-range \
  --vibe "culture, food" \
  --k 5 \
  --no-hotels \
  --no-completeness \
  --pretty
```

You should see progress logs, then a JSON block with 5 ranked attractions.

### Step 5 — Full run with your example file

```bash
python main.py --input example_trip.json --pretty --output test_output.json
```

Check `test_output.json` — it should contain `attractions`, `hotels`, `gaps`, and `api_calls`.

---

## Switching the AI Ranker

One line in `wayfinder/pipeline.py` (line 21) controls which ranker runs:

```python
# Use Gemini (Google) — free, 1500 req/day
from .ranking_gemini import GeminiRanker as Ranker

# Use custom ML model — totally free, no internet needed at runtime
# from .ranking import MLRanker as Ranker
# (scroll down in ranking_gemini.py and uncomment the MLRanker class)
```


---

## Output Format

The JSON output always has this structure:

```json
{
  "destination": "Tokyo, Japan",
  "preferences": ["culture", "food"],
  "results": {
    "attractions": [
      {
        "location_id": "123456",
        "name": "Senso-ji Temple",
        "category": "Attraction",
        "subcategories": ["Temple", "Historic Site"],
        "rating": 4.8,
        "num_reviews": 52000,
        "address": "2-3-1 Asakusa, Taito City, Tokyo",
        "latitude": 35.7148,
        "longitude": 139.7967,
        "web_url": "https://www.tripadvisor.com/...",
        "photo_url": "https://...",
        "price_level": "$",
        "score": 9.2,
        "score_reason": "Perfect match for cultural exploration vibe",
        "ranker_used": "gemini",
        "booking_url": "https://www.tripadvisor.com/...",
        "booking_links": {
          "TripAdvisor": "https://...",
          "Viator": "https://...",
          "GetYourGuide": "https://...",
          "Google Maps": "https://..."
        }
      }
    ],
    "hotels": [ ... ],
    "gaps": "Looks complete.",
    "api_calls": 87
  }
}
```

This JSON is designed to be consumed by the next stage of the pipeline (routing + map display).

---

## API Usage & Cost

### TripAdvisor (free tier: 5,000 calls/month)

Each full run uses approximately:
- 1 call per search query (2 categories = 2 calls)
- 1 call per attraction detail fetch (~20 per category)
- 1 call per photo fetch (~20 per category)
- ~15 calls for hotel search

**Total per run: ~100–130 calls** → you can run ~40 full searches per month for free.

To reduce usage, use `--no-hotels` (saves ~15 calls) and lower `--k`.

### Gemini (free tier: 1,500 requests/day)

Each full run uses:
- 2–4 calls for ranking (batches of 10 attractions)
- 1 call for completeness check

**Total per run: 3–5 calls** — the free tier is essentially unlimited for this project.
---

## Troubleshooting

**`Missing TRIPADVISOR_API_KEY`**
You forgot to set the environment variable. Run `export TRIPADVISOR_API_KEY="your_key"` in the same terminal window before running the script.

**`GEMINI_API_KEY is not set`**
Same issue — run `export GEMINI_API_KEY="your_key"` first.

**`ModuleNotFoundError: No module named 'wayfinder'`**
You're running `main.py` from the wrong directory. Make sure you `cd` into the folder that contains both `main.py` and the `wayfinder/` folder before running.

**`ModuleNotFoundError: No module named 'google.genai'`**
Run `pip install google-genai` first.

**TripAdvisor returns 401 Unauthorized**
Your API key is wrong or not set correctly. Double-check it has no extra spaces or quotes.

**TripAdvisor returns 429 Too Many Requests**
You've hit the rate limit. Wait a minute and try again, or reduce the number of attractions fetched by lowering the `results[:20]` limit in `tripadvisor.py`.

**JSON decode error from the ranker**
The AI returned malformed JSON. This is rare but can happen. Just re-run — it's non-deterministic and usually works on the next attempt.