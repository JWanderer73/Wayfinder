"""
wayfinder/ranking/gemini.py
────────────────────────────
Gemini-powered ranker (gemini-2.5-flash, free tier).

CHANGES vs. previous version:
  - Prompt includes travel_dates + weather_summary so the LLM can down-weight
    outdoor activities in bad weather and up-weight seasonal experiences.
  - Asks for confidence per item.
  - Falls back to shared HeuristicRanker on parse failure.

MANDATORY HANDLING
  Mandatory items are EXCLUDED from the Gemini batch entirely — they get a
  fixed high score (9.5) plus a marker. We skip the API call for them to
  save tokens, and to guarantee the LLM never down-weights a user-requested
  attraction by accident.
"""
from __future__ import annotations

import json
import os

from google import genai
from google.genai import types

from ..models import Attraction, UserPreferences
from .base import Ranker
from .heuristic import MANDATORY_FLOOR_SCORE, apply_heuristic


class GeminiRanker(Ranker):
    """Production ranker using Gemini 2.5 Flash."""

    name = "gemini"

    def __init__(self, model: str = "gemini-2.5-flash"):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY is not set.\n"
                "Get a free key at https://aistudio.google.com"
            )
        self.client = genai.Client(api_key=api_key)
        self.model  = model

    def rank(self, attractions: list[Attraction],
             prefs: UserPreferences,
             batch_size: int = 10) -> list[Attraction]:
        # split mandatory from suggested — mandatory gets fixed scoring,
        # suggested goes through Gemini in batches.
        mandatory = [a for a in attractions if a.is_mandatory]
        suggested = [a for a in attractions if not a.is_mandatory]

        for a in mandatory:
            a.score        = round(max(MANDATORY_FLOOR_SCORE, a.score) + 0.01 * a.rating, 2)
            a.score_reason = "Mandatory — user-requested attraction"
            a.confidence   = 1.0
            a.ranker_used  = self.name

        for i in range(0, len(suggested), batch_size):
            batch = suggested[i : i + batch_size]
            self._score_batch(batch, prefs)

        return sorted(attractions, key=lambda a: a.score, reverse=True)

    def check_completeness(self, top_k: list[Attraction],
                           prefs: UserPreferences) -> str:
        names = [a.name for a in top_k]
        prompt = (
            f"A traveler is visiting {prefs.destination} "
            f"with a \"{prefs.vibe}\" vibe and a {prefs.budget} budget.\n"
            f"Travel dates: {prefs.travel_dates[0] or 'unspecified'} → "
            f"{prefs.travel_dates[1] or 'unspecified'}\n"
            f"Weather: {prefs.weather_summary or 'unknown'}\n"
            f"Shortlist: {json.dumps(names)}\n"
            f"User-required must-sees: {json.dumps(prefs.required_attractions)}\n\n"
            "Are any iconic experiences, meal types, or required attractions "
            "missing given the season and weather?\n"
            "Bullet points for gaps only. If complete, say exactly: Looks complete."
        )
        resp = self.client.models.generate_content(
            model=self.model, contents=prompt,
        )
        return (resp.text or "").strip()

    # ── internal ──────────────────────────────────────────────────────────
    def _score_batch(self, batch: list[Attraction],
                     prefs: UserPreferences,
                     max_retries: int = 3) -> None:
        items = [{
            "idx":           idx,
            "name":          a.name,
            "category":      a.category,
            "subcategories": a.subcategories,
            "rating":        a.rating,
            "num_reviews":   a.num_reviews,
            "price_level":   a.price_level,
            "cuisine_types": a.cuisine_types,
            "is_outdoor":    a.is_outdoor,
            "is_indoor":     a.is_indoor,
        } for idx, a in enumerate(batch)]

        prompt = self._build_prompt(items, prefs)

        for attempt in range(max_retries):
            try:
                resp = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    ),
                )
                raw = self._extract_json(resp.text or "")
                scored = json.loads(raw)

                if not isinstance(scored, list) or not scored:
                    raise ValueError(f"Expected non-empty list, got: {type(scored)}")

                for r in scored:
                    idx = int(r["idx"])
                    if 0 <= idx < len(batch):
                        batch[idx].score        = float(r.get("score", 0))
                        batch[idx].score_reason = r.get("reason", "")
                        batch[idx].confidence   = float(r.get("confidence", 0.7))
                        batch[idx].ranker_used  = self.name
                return

            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"    [Gemini] parse error attempt {attempt+1}/{max_retries}, retrying… ({e})")
                else:
                    print(f"    [Gemini] all {max_retries} failed → heuristic fallback. {e}")
                    apply_heuristic(batch)

    def _build_prompt(self, items: list[dict], prefs: UserPreferences) -> str:
        weather_line = (
            f"Weather expected: {prefs.weather_summary}\n"
            if prefs.weather_summary
            else "Weather: unknown — assume neutral.\n"
        )
        date_line = ""
        if prefs.travel_dates and prefs.travel_dates[0]:
            date_line = (
                f"Travel dates: {prefs.travel_dates[0]} → "
                f"{prefs.travel_dates[1] or 'unspecified'}\n"
            )

        return (
            f"You are a travel planning assistant. "
            f"Score each attraction for a traveler with these preferences:\n\n"
            f"Destination : {prefs.destination}\n"
            f"Budget      : {prefs.budget}\n"
            f"Vibe        : {prefs.vibe or 'unspecified'}\n"
            f"Dietary     : {', '.join(prefs.dietary_restrictions) or 'none'}\n"
            f"Travelers   : {prefs.num_travelers}\n"
            f"{date_line}"
            f"{weather_line}\n"
            f"Scoring guidelines:\n"
            f"- Down-weight outdoor activities if weather is poor.\n"
            f"- Up-weight seasonal experiences (cherry blossoms in spring etc).\n"
            f"- `confidence` = 0.9 slam-dunk, 0.5 plausible, 0.3 guess.\n\n"
            f"Attractions to score:\n{json.dumps(items, indent=2)}\n\n"
            f"Return a valid JSON array with exactly {len(items)} elements.\n"
            f"No markdown, no explanation, just JSON.\n"
            f'Format: [{{"idx": 0, "score": 7.5, "reason": "...", "confidence": 0.8}}, ...]\n'
            f"Score range: 0.0–10.0. Confidence range: 0.0–1.0."
        )

    @staticmethod
    def _extract_json(raw: str) -> str:
        raw = raw.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        start = raw.find("[")
        end   = raw.rfind("]") + 1
        if start != -1 and end > start:
            raw = raw[start:end]
        return raw