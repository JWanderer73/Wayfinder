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

    def __init__(self, model: str = "gemini-2.0-flash"):
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
                     prefs: UserPreferences) -> None:
        """Mutate each Attraction in batch with .score and .score_reason."""
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
            f"Attractions:\n{json.dumps(items, indent=2)}\n\n"
            "Return ONLY a JSON array – no markdown, no explanation.\n"
            'Each element: {"idx": <int>, "score": <float 0-10>, '
            '"reason": <one sentence>}\n'
            "Higher score = better fit for this traveler."
        )

        resp = self.client.models.generate_content(
            model    = self.model,
            contents = prompt,
            config   = types.GenerateContentConfig(
                # tell Gemini to respond in JSON
                response_mime_type = "application/json",
            ),
        )

        raw = resp.text.strip()

        # strip accidental markdown fences just in case
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1]
            if raw.startswith("json"):
                raw = raw[4:]

        scored = json.loads(raw)
        for r in scored:
            idx = int(r["idx"])
            batch[idx].score        = float(r.get("score", 0))
            batch[idx].score_reason = r.get("reason", "")
