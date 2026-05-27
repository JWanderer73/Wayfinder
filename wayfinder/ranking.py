from __future__ import annotations

import json
import math
import os

from .models import Attraction, UserPreferences


class GeminiRanker:
    """Rank attractions with Gemini, falling back to heuristic scores on parse errors."""

    def __init__(self, model: str = "gemini-2.5-flash"):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY is not set.\n"
                "Get a free key at https://aistudio.google.com\n"
                "Then run: export GEMINI_API_KEY='your_key_here'"
            )

        try:
            from google import genai
            from google.genai import types
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "google-genai is required for Gemini ranking. "
                "Install it with: pip install google-genai"
            ) from exc

        self.client = genai.Client(api_key=api_key)
        self.types = types
        self.model = model

    def rank(
        self,
        attractions: list[Attraction],
        prefs: UserPreferences,
        batch_size: int = 10,
    ) -> list[Attraction]:
        for index in range(0, len(attractions), batch_size):
            self._score_batch(attractions[index : index + batch_size], prefs)
        for attraction in attractions:
            attraction.ranker_used = "gemini"
        return sorted(attractions, key=lambda attraction: attraction.score, reverse=True)

    def check_completeness(
        self,
        top_k: list[Attraction],
        prefs: UserPreferences,
    ) -> str:
        names = [attraction.name for attraction in top_k]
        prompt = (
            f"A traveler is visiting {prefs.destination} "
            f'with a "{prefs.vibe}" vibe and a {prefs.budget} budget.\n'
            f"Their shortlisted attractions:\n{json.dumps(names)}\n"
            f"Required must-sees: {json.dumps(prefs.required_attractions)}\n\n"
            "Are any iconic experiences, meal types, or required attractions "
            "missing from this list?\n"
            "Respond with short bullet points for gaps only. "
            "If the list looks complete, say exactly: Looks complete."
        )
        response = self.client.models.generate_content(model=self.model, contents=prompt)
        return response.text.strip()

    def _score_batch(
        self,
        batch: list[Attraction],
        prefs: UserPreferences,
        max_retries: int = 3,
    ) -> None:
        items = [
            {
                "idx": index,
                "name": attraction.name,
                "category": attraction.category,
                "subcategories": attraction.subcategories,
                "rating": attraction.rating,
                "num_reviews": attraction.num_reviews,
                "price_level": attraction.price_level,
                "cuisine_types": attraction.cuisine_types,
            }
            for index, attraction in enumerate(batch)
        ]

        prompt = (
            "You are a travel planning assistant. "
            "Score each attraction for a traveler with these preferences:\n\n"
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

        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=self.types.GenerateContentConfig(
                        response_mime_type="application/json",
                    ),
                )
                scored = json.loads(extract_json_array(response.text.strip()))
                if not isinstance(scored, list) or not scored:
                    raise ValueError(f"Expected a list, got: {type(scored)}")

                for row in scored:
                    idx = int(row["idx"])
                    if 0 <= idx < len(batch):
                        batch[idx].score = float(row.get("score", 0))
                        batch[idx].score_reason = row.get("reason", "")
                return
            except Exception as exc:
                if attempt < max_retries - 1:
                    print(
                        "    [Gemini] parse error "
                        f"(attempt {attempt + 1}/{max_retries}), retrying... ({exc})"
                    )
                else:
                    print(
                        "    [Gemini] all retries failed, using heuristic scores. "
                        f"Error: {exc}"
                    )
                    self._apply_heuristic_scores(batch)

    def _apply_heuristic_scores(self, batch: list[Attraction]) -> None:
        for attraction in batch:
            rating_score = (attraction.rating / 5.0) * 7.0
            popularity_score = min(
                math.log1p(attraction.num_reviews) / math.log1p(50_000),
                1.0,
            ) * 3.0
            attraction.score = round(rating_score + popularity_score, 2)
            attraction.score_reason = (
                f"Heuristic: rating {attraction.rating}/5, "
                f"{attraction.num_reviews:,} reviews"
            )
            attraction.ranker_used = "heuristic"


def extract_json_array(raw: str) -> str:
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    start = raw.find("[")
    end = raw.rfind("]") + 1
    if start != -1 and end > start:
        return raw[start:end]
    return raw
