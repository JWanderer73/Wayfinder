"""
wayfinder/ranking_gemini.py
────────────────────────────
Drop-in replacement for ranking.py that uses Google Gemini instead of Claude.
Uses the FREE Gemini API (gemini-2.0-flash) — no credit card needed.

HOW TO GET YOUR GEMINI API KEY:
  1. Go to https://aistudio.google.com
  2. Sign in with your Google account (the one that has Gemini Pro)
  3. Click "Get API key" in the top left → "Create API key"
  4. Copy the key and set it as an environment variable:
       Mac/Linux:  export GEMINI_API_KEY="your_key_here"
       Windows:    set GEMINI_API_KEY=your_key_here

HOW TO SWITCH TO THIS FILE:
  In wayfinder/pipeline.py, find this line at the top:

      from .ranking import LLMRanker as Ranker

  Replace it with:

      from .ranking_gemini import GeminiRanker as Ranker

  Then install the Google library:
      pip install google-genai

  That's it — no other changes needed anywhere.

NOTE ON YOUR GEMINI PRO SUBSCRIPTION:
  Gemini Pro (the consumer subscription) does NOT give you API access.
  The API is a separate free product called "Google AI Studio".
  You still get generous free limits:
    - 1,500 requests/day
    - 1,000,000 tokens/minute
  That is more than enough for this project at no cost.
"""

from __future__ import annotations
import json
import os

from google import genai
from google.genai import types

from .models import Attraction, UserPreferences


class GeminiRanker:
    """
    Drop-in replacement for LLMRanker.
    Uses Gemini 2.0 Flash — free tier, 1500 req/day.

    Same public interface as LLMRanker:
      .rank(attractions, prefs) → sorted list[Attraction]
      .check_completeness(top_k, prefs) → str
    """

    def __init__(self, model: str = "gemini-2.5-flash"):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY is not set.\n"
                "Get a free key at https://aistudio.google.com\n"
                "Then run: export GEMINI_API_KEY='your_key_here'"
            )
        self.client = genai.Client(api_key=api_key)
        self.model  = model

    # ── public (same interface as LLMRanker) ──────────────────────────────────
    def rank(self, attractions: list[Attraction],
             prefs: UserPreferences,
             batch_size: int = 10) -> list[Attraction]:
        """Score all attractions in batches, return sorted high → low."""
        for i in range(0, len(attractions), batch_size):
            batch = attractions[i : i + batch_size]
            self._score_batch(batch, prefs)

        for a in attractions:
            a.ranker_used = "gemini"

        return sorted(attractions, key=lambda a: a.score, reverse=True)

    def check_completeness(self, top_k: list[Attraction],
                           prefs: UserPreferences) -> str:
        """Ask Gemini if the shortlist is missing anything important."""
        names = [a.name for a in top_k]
        prompt = (
            f"A traveler is visiting {prefs.destination} "
            f"with a \"{prefs.vibe}\" vibe and a {prefs.budget} budget.\n"
            f"Their shortlisted attractions:\n{json.dumps(names)}\n"
            f"Required must-sees: {json.dumps(prefs.required_attractions)}\n\n"
            "Are any iconic experiences, meal types, or required attractions "
            "missing from this list?\n"
            "Respond with short bullet points for gaps only. "
            "If the list looks complete, say exactly: Looks complete."
        )
        resp = self.client.models.generate_content(
            model    = self.model,
            contents = prompt,
        )
        return resp.text.strip()

    # ── internal ──────────────────────────────────────────────────────────────
    def _score_batch(self, batch: list[Attraction],
                     prefs: UserPreferences,
                     max_retries: int = 3) -> None:
        """
        Mutate each Attraction in batch with .score and .score_reason.
        Retries up to max_retries times if Gemini returns malformed JSON.
        Falls back to heuristic scores if all retries fail.
        """
        items = [
            {
                "idx":           idx,
                "name":          a.name,
                "category":      a.category,
                "subcategories": a.subcategories,
                "rating":        a.rating,
                "num_reviews":   a.num_reviews,
                "price_level":   a.price_level,
                "cuisine_types": a.cuisine_types,
            }
            for idx, a in enumerate(batch)
        ]

        prompt = (
            f"You are a travel planning assistant. "
            f"Score each attraction for a traveler with these preferences:\n\n"
            f"Destination : {prefs.destination}\n"
            f"Budget      : {prefs.budget}\n"
            f"Vibe        : {prefs.vibe}\n"
            f"Dietary     : {', '.join(prefs.dietary_restrictions) or 'none'}\n"
            f"Travelers   : {prefs.num_travelers}\n\n"
            f"Attractions to score:\n{json.dumps(items, indent=2)}\n\n"
            f"You MUST return a valid JSON array with exactly {len(batch)} elements.\n"
            "No markdown, no explanation, no trailing commas, just pure JSON.\n"
            'Format: [{"idx": 0, "score": 7.5, "reason": "one sentence"}, ...]\n'
            "Score range: 0.0 to 10.0. Higher = better fit for this traveler."
        )

        last_error = None
        for attempt in range(max_retries):
            try:
                resp = self.client.models.generate_content(
                    model    = self.model,
                    contents = prompt,
                    config   = types.GenerateContentConfig(
                        response_mime_type = "application/json",
                    ),
                )

                raw = resp.text.strip()

                # strip markdown fences if Gemini adds them anyway
                if "```" in raw:
                    # extract content between first ``` and last ```
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                    raw = raw.strip()

                # find the JSON array bounds in case there's extra text
                start = raw.find("[")
                end   = raw.rfind("]") + 1
                if start != -1 and end > start:
                    raw = raw[start:end]

                scored = json.loads(raw)

                # validate we got back the right number of results
                if not isinstance(scored, list) or len(scored) == 0:
                    raise ValueError(f"Expected a list, got: {type(scored)}")

                for r in scored:
                    idx = int(r["idx"])
                    if 0 <= idx < len(batch):
                        batch[idx].score        = float(r.get("score", 0))
                        batch[idx].score_reason = r.get("reason", "")
                return  # success — exit retry loop

            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    print(f"    [Gemini] JSON parse error (attempt {attempt+1}/{max_retries}), retrying… ({e})")
                else:
                    print(f"    [Gemini] All {max_retries} attempts failed. Using heuristic scores. Error: {e}")
                    self._apply_heuristic_scores(batch)

    def _apply_heuristic_scores(self, batch: list[Attraction]) -> None:
        """Fallback scoring based purely on rating + review count when Gemini fails."""
        import math
        for a in batch:
            rating_score = (a.rating / 5.0) * 7.0          # up to 7 points for rating
            pop_score    = min(math.log1p(a.num_reviews) / math.log1p(50000), 1.0) * 3.0  # up to 3 for popularity
            a.score        = round(rating_score + pop_score, 2)
            a.score_reason = f"Heuristic score based on rating ({a.rating}/5) and {a.num_reviews:,} reviews"
            a.ranker_used  = "heuristic"