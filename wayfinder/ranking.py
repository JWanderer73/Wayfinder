"""
wayfinder/ranking.py
─────────────────────
GeminiRanker – uses the free Gemini API (gemini-2.5-flash) to score attractions.

HOW TO GET YOUR GEMINI API KEY:
  1. Go to https://aistudio.google.com
  2. Sign in with your Google account
  3. Click "Get API key" → "Create API key"
  4. Set it: export GEMINI_API_KEY="your_key_here"

Free tier: 1,500 requests/day — more than enough for this project.
"""
from __future__ import annotations
import json
import os

from google import genai
from google.genai import types

from .models import Attraction, UserPreferences


class GeminiRanker:
    """
    Ranks attractions using Gemini 2.5 Flash (free tier).

    Public interface:
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

    def rank(self, attractions: list[Attraction],
             prefs: UserPreferences,
             batch_size: int = 10) -> list[Attraction]:
        for i in range(0, len(attractions), batch_size):
            self._score_batch(attractions[i : i + batch_size], prefs)
        for a in attractions:
            a.ranker_used = "gemini"
        return sorted(attractions, key=lambda a: a.score, reverse=True)

    def check_completeness(self, top_k: list[Attraction],
                           prefs: UserPreferences) -> str:
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
        resp = self.client.models.generate_content(model=self.model, contents=prompt)
        return resp.text.strip()

    def _score_batch(self, batch: list[Attraction],
                     prefs: UserPreferences,
                     max_retries: int = 3) -> None:
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
                if "```" in raw:
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                    raw = raw.strip()

                start = raw.find("[")
                end   = raw.rfind("]") + 1
                if start != -1 and end > start:
                    raw = raw[start:end]

                scored = json.loads(raw)
                if not isinstance(scored, list) or len(scored) == 0:
                    raise ValueError(f"Expected a list, got: {type(scored)}")

                for r in scored:
                    idx = int(r["idx"])
                    if 0 <= idx < len(batch):
                        batch[idx].score        = float(r.get("score", 0))
                        batch[idx].score_reason = r.get("reason", "")
                return

            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"    [Gemini] parse error (attempt {attempt+1}/{max_retries}), retrying... ({e})")
                else:
                    print(f"    [Gemini] all {max_retries} attempts failed, using heuristic scores. Error: {e}")
                    self._apply_heuristic_scores(batch)

    def _apply_heuristic_scores(self, batch: list[Attraction]) -> None:
        import math
        for a in batch:
            rating_score = (a.rating / 5.0) * 7.0
            pop_score    = min(math.log1p(a.num_reviews) / math.log1p(50000), 1.0) * 3.0
            a.score        = round(rating_score + pop_score, 2)
            a.score_reason = f"Heuristic: rating {a.rating}/5, {a.num_reviews:,} reviews"
            a.ranker_used  = "heuristic"


# ── MLRanker (optional alternative — uncomment to use) ───────────────────────
# In wayfinder/pipeline.py change:
#     from .ranking import GeminiRanker as Ranker
# to:
#     from .ranking import MLRanker as Ranker
#
# import math, pickle
# from pathlib import Path
# try:
#     import numpy as np
#     from sklearn.linear_model import LogisticRegression
#     from sklearn.preprocessing import StandardScaler
#     from sklearn.pipeline import Pipeline
#     _SKLEARN_AVAILABLE = True
# except ImportError:
#     _SKLEARN_AVAILABLE = False
#
# PRICE_LEVEL_MAP = {"$": 0, "$$": 1, "$$$": 2, "$$$$": 3, "": 1}
# BUDGET_MAP      = {"budget": 0, "mid-range": 1, "luxury": 2}
#
# class MLRanker:
#     MODEL_PATH = Path("wayfinder_ml_model.pkl")
#     def __init__(self):
#         if not _SKLEARN_AVAILABLE:
#             raise ImportError("pip install scikit-learn numpy")
#         self._model = None
#         if self.MODEL_PATH.exists():
#             with open(self.MODEL_PATH, "rb") as f:
#                 self._model = pickle.load(f)
#     def rank(self, attractions, prefs, batch_size=10):
#         if self._model is None:
#             return self._heuristic_rank(attractions, prefs)
#         X = np.array([self._featurize(a, prefs) for a in attractions])
#         scores = self._model.predict_proba(X)[:, 1]
#         for a, s in zip(attractions, scores):
#             a.score = round(float(s) * 10, 2)
#             a.score_reason = "ML model prediction"
#             a.ranker_used = "ml"
#         return sorted(attractions, key=lambda a: a.score, reverse=True)
#     def _featurize(self, a, prefs):
#         import math
#         from .filters import AttractionFilter
#         rating_norm = a.rating / 5.0
#         pop_norm = math.log1p(a.num_reviews) / math.log1p(100_000)
#         price_fit = 1.0 - abs(PRICE_LEVEL_MAP.get(a.price_level, 1) - BUDGET_MAP.get(prefs.budget, 1)) / 3.0
#         all_tags = " ".join(a.subcategories + a.cuisine_types).lower()
#         vibe_score = min(sum(1 for kw in prefs.vibe.lower().split(",") if kw.strip() in all_tags), 1.0)
#         conflict = 0.0 if AttractionFilter(prefs).passes(a) else 1.0
#         return [rating_norm, pop_norm, price_fit, vibe_score, conflict,
#                 1.0 if "attraction" in a.category.lower() else 0.0,
#                 1.0 if "restaurant" in a.category.lower() else 0.0]
#     def _heuristic_rank(self, attractions, prefs):
#         for a in attractions:
#             feats = self._featurize(a, prefs)
#             weights = [0.35, 0.20, 0.15, 0.20, -0.30, 0.05, 0.05]
#             a.score = round(max(0.0, min(10.0, sum(f*w for f,w in zip(feats,weights)) * 10)), 2)
#             a.score_reason = "heuristic score"
#             a.ranker_used = "heuristic"
#         return sorted(attractions, key=lambda a: a.score, reverse=True)
