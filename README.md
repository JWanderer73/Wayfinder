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

The system is designed so the **AI ranker is swappable** — you can use Gemini (Google, free) or a custom ML model, all with a one-line change.

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
③ RANK — AI Scoring (Gemini or custom ML model)
   • Each attraction gets a score 0–10 based on how well it fits the
     traveler's vibe, budget, and dietary needs
   • Batched in groups of 10 to reduce API calls
   • Retries up to 3 times if Gemini returns malformed JSON
   • Falls back to heuristic scoring if all retries fail
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
└── ranking.py          ← GeminiRanker (active) + MLRanker (commented out)

main.py                 ← CLI entry point (the file you run)
example_trip.json       ← sample input file for testing
.env                    ← your API keys (never commit this)
.gitignore              ← ensures .env and other junk never gets committed
```

---

## Setup

### 1. Prerequisites
- Python 3.11 or higher
- A TripAdvisor API key (free)
- A Gemini API key (free)

### 2. Install dependencies

```bash
pip install requests google-genai
```

### 3. Clone the project

```bash
git clone https://github.com/JWanderer73/Wayfinder.git
cd Wayfinder
```

Make sure your folder looks like this before running anything:

```
Wayfinder/
├── main.py
├── example_trip.json
├── .env
├── .gitignore
├── README.md
└── wayfinder/
    ├── __init__.py
    ├── models.py
    ├── tripadvisor.py
    ├── filters.py
    ├── hotels.py
    ├── pipeline.py
    └── ranking.py
```

---

## Getting Your API Keys

### TripAdvisor API Key (required)

1. Go to **https://www.tripadvisor.com/developers**
2. Click **"Get Started"** and create an account
3. Create a new project
4. Leave the "API key restriction" field **blank** for development
5. Copy the key

Free tier: **5,000 requests/month**

### Gemini API Key (required — completely free)

1. Go to **https://aistudio.google.com**
2. Sign in with your Google account
3. Click **"Get API key"** in the top left → **"Create API key"**
4. Copy the key

Free tier: **1,500 requests/day** — more than enough for this project.

> Note: Your Gemini Pro consumer subscription does NOT include API access. This is a separate free product at aistudio.google.com.

### Setting Your Keys

Create a `.env` file in the project root:

```
TRIPADVISOR_API_KEY=your_tripadvisor_key_here
GEMINI_API_KEY=your_gemini_key_here
```

Then load it into your terminal before running:

**Mac / Linux:**
```bash
export TRIPADVISOR_API_KEY="your_key"
export GEMINI_API_KEY="your_key"
```

**Windows (PowerShell):**
```powershell
Get-Content .env | ForEach-Object {
    $parts = $_ -split '=', 2
    if ($parts.Count -eq 2 -and -not $parts[0].StartsWith('#')) {
        [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim())
    }
}
```

> **Important:** Never paste API keys directly into code files or share them in chat. The `.gitignore` blocks `.env` from ever being committed to GitHub.

---

## Running the Code

### Option A — Run with a JSON input file (recommended)

Edit `example_trip.json` with your destination and preferences, then run:

```powershell
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

```powershell
python main.py --city "Tokyo, Japan" --pretty
```

With full preferences:
```powershell
python main.py --city "Tokyo, Japan" --budget mid-range --vibe "food, culture" --dietary vegetarian --required "Senso-ji Temple" "Shibuya Crossing" --k 10 --pretty
```

### What `--pretty` does

`--pretty` formats the JSON output with indentation so it's readable in the terminal. Without it, everything prints on one line — useful when the output is being piped into another script or stage of the pipeline.

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

```powershell
python main.py --input example_trip.json --pretty --output results.json
```

---

## Testing the Code

### Step 1 — Test imports only (no API keys needed)

```powershell
python -c "
from wayfinder.models import Attraction, UserPreferences
from wayfinder.tripadvisor import TripAdvisorClient
from wayfinder.filters import AttractionFilter, generate_booking_links
from wayfinder.hotels import HotelFinder
from wayfinder.ranking import GeminiRanker
from wayfinder.pipeline import generate_recommendations
print('All imports OK')
"
```

Expected output: `All imports OK`

### Step 2 — Test the filter logic (no API keys needed)

```powershell
python -c "
from wayfinder.models import Attraction, UserPreferences
from wayfinder.filters import AttractionFilter, generate_booking_links

prefs = UserPreferences(destination='Tokyo', budget='mid-range', vibe='culture')

good = Attraction('1', 'Senso-ji Temple', 'Attraction', ['Temple'],
                  4.8, 50000, 'Asakusa', 35.71, 139.79, 'http://example.com')

bad = Attraction('2', 'Tokyo Steakhouse', 'Restaurant', ['Steakhouse'],
                 4.5, 2000, 'Shinjuku', 35.69, 139.70, 'http://example.com',
                 cuisine_types=['Steakhouse'])
prefs.dietary_restrictions = ['vegan']

filt = AttractionFilter(prefs)
assert filt.passes(good) == True
assert filt.passes(bad)  == False

links = generate_booking_links(good, prefs)
assert 'Viator' in links
assert 'Google Maps' in links
print('All filter tests passed')
print('Booking links:', list(links.keys()))
"
```

### Step 3 — Quick live test (minimal API calls)

```powershell
python main.py --city "New York" --k 5 --no-hotels --no-completeness --pretty
```

### Step 4 — Full run

```powershell
python main.py --input example_trip.json --pretty --output results.json
```

---

## Switching the AI Ranker

One line in `wayfinder/pipeline.py` controls which ranker runs:

```python
# CURRENT (Gemini — free, 1500 req/day)
from .ranking import GeminiRanker as Ranker

# ALTERNATIVE (custom ML model — free, runs locally, no API needed)
# Uncomment MLRanker at the bottom of ranking.py, then change the line above to:
# from .ranking import MLRanker as Ranker
```

| Ranker | Cost | Requires | Best for |
|--------|------|----------|----------|
| `GeminiRanker` | Free (1,500 req/day) | `GEMINI_API_KEY` | Default — smart, free |
| `MLRanker` | Free forever | Nothing | Offline / no internet |

---

## Output Format

The JSON output always has this structure:

```json
{
  "destination": "Tokyo, Japan",
  "preferences": ["culture", "food", "anime"],
  "results": {
    "attractions": [
      {
        "location_id": "320447",
        "name": "Senso-ji Temple",
        "category": "Attraction",
        "subcategories": ["Sights & Landmarks", "Attractions"],
        "rating": 4.8,
        "num_reviews": 52000,
        "address": "2-3-1 Asakusa, Taito City, Tokyo",
        "latitude": 35.7148,
        "longitude": 139.7967,
        "web_url": "https://www.tripadvisor.com/...",
        "photo_url": "https://...",
        "price_level": "$",
        "hours": { "weekday_text": ["Monday: 06:00 - 17:00", "..."] },
        "score": 9.5,
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
    "hotels": [ "... same structure, top 5 by rating ..." ],
    "gaps": "• Akihabara missing for anime vibe\n• No ramen restaurant included",
    "api_calls": 61
  }
}
```

### What the routing/map stage needs from each attraction
- `latitude` + `longitude` — to plot on map and compute routes
- `name` + `address` — for display labels
- `hours` — to schedule visits in time order
- `score` — to prioritize stops when clustering by day
- `booking_links` — to surface in the final UI

---

## API Usage & Cost

### TripAdvisor (free tier: 5,000 calls/month)

| Action | Calls used |
|--------|-----------|
| Search per category (2 categories) | 2 |
| Detail fetch per attraction (~20 per category) | ~40 |
| Photo fetch per attraction | ~40 |
| Hotel search | ~15 |
| **Total per full run** | **~100 calls** |

You can run ~50 full searches per month on the free tier. Use `--no-hotels` to save ~15 calls per run.

### Gemini (free tier: 1,500 requests/day)

| Action | Calls used |
|--------|-----------|
| Ranking (batches of 10) | 2–4 |
| Completeness check | 1 |
| **Total per full run** | **3–5 calls** |

Essentially unlimited on the free tier for this project.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'wayfinder'`**
You're in the wrong folder or the `wayfinder/` subfolder got renamed. Run `ls` — you should see both `main.py` and a `wayfinder/` folder. If the folder is named `wayfinder_tripadvisor`, rename it:
```powershell
Rename-Item wayfinder_tripadvisor wayfinder
```

**`GEMINI_API_KEY is not set`**
Load your `.env` file first using the PowerShell snippet in the Setup section above, or set it manually:
```powershell
$env:GEMINI_API_KEY="your_key"
```

**`TRIPADVISOR_API_KEY is not set`**
```powershell
$env:TRIPADVISOR_API_KEY="your_key"
```

**`ModuleNotFoundError: No module named 'google.genai'`**
```powershell
pip install google-genai
```

**`404 NOT_FOUND` from Gemini**
The model name in `ranking.py` doesn't match what your account has access to. Run this to see available models:
```powershell
python -c "from google import genai; import os; client = genai.Client(api_key=os.environ['GEMINI_API_KEY']); [print(m.name) for m in client.models.list()]"
```
Then update the model name in `wayfinder/ranking.py`.

**`429 RESOURCE_EXHAUSTED` from Gemini**
You've hit the daily free tier limit. Wait until midnight Pacific time and try again.

**`401 Unauthorized` from TripAdvisor**
Your TripAdvisor key is wrong or expired. Regenerate it at https://www.tripadvisor.com/developers.

**`429 Too Many Requests` from TripAdvisor**
You're hitting the per-minute rate limit. Wait 60 seconds and retry.

**JSON decode error from ranker**
Gemini occasionally returns malformed JSON. The code automatically retries up to 3 times and falls back to heuristic scoring if needed — so the pipeline won't crash from this.

**Git push rejected (non-fast-forward)**
```powershell
git stash
git pull --rebase
git stash pop
git push
```