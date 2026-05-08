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




# ══════════════════════════════════════════════════════════════════════════════
# OPTION 2 – CUSTOM ML RANKER  (alternative – uncomment to use)
# ══════════════════════════════════════════════════════════════════════════════
#
# HOW TO SWITCH:
#   In wayfinder/pipeline.py change:
#       from .ranking import LLMRanker as Ranker
#   to:
#       from .ranking import MLRanker as Ranker
#
# TRAINING YOUR OWN MODEL:
#   Collect (attraction_features, user_enjoyed: bool) pairs from real users.
#   Then call:
#       ranker = MLRanker()
#       ranker.fit(attractions_list, labels)
#       ranker.save("model.pkl")
#   After that, MLRanker.rank() works without any API calls.
#
# ─────────────────────────────────────────────────────────────────────────────
#
# import math
# import pickle
# from pathlib import Path
#
# # sklearn is optional – only needed for MLRanker
# try:
#     import numpy as np
#     from sklearn.linear_model import LogisticRegression
#     from sklearn.preprocessing import StandardScaler
#     from sklearn.pipeline import Pipeline
#     _SKLEARN_AVAILABLE = True
# except ImportError:
#     _SKLEARN_AVAILABLE = False
#
#
# PRICE_LEVEL_MAP = {"$": 0, "$$": 1, "$$$": 2, "$$$$": 3, "": 1}
# BUDGET_MAP      = {"budget": 0, "mid-range": 1, "luxury": 2}
# VIBE_KEYWORDS   = {
#     "adventure":  ["outdoor", "hiking", "extreme", "sport", "kayak"],
#     "culture":    ["museum", "gallery", "temple", "heritage", "historic"],
#     "food":       ["restaurant", "cuisine", "market", "food", "chef"],
#     "relaxation": ["spa", "beach", "park", "garden", "resort"],
#     "nightlife":  ["bar", "club", "pub", "cocktail", "rooftop"],
# }
#
#
# class MLRanker:
#     """
#     Lightweight scikit-learn ranker.
#
#     Feature vector per attraction (7 dimensions):
#       [0] normalized rating        (rating / 5)
#       [1] log popularity           (log1p(num_reviews) / log1p(100_000))
#       [2] price fit                (1 - |price_encoded - budget_encoded| / 3)
#       [3] vibe tag overlap         (# matching vibe keywords / total subcats)
#       [4] dietary conflict         (1 = conflict found, 0 = safe)
#       [5] is_attraction category   (1/0)
#       [6] is_restaurant category   (1/0)
#     """
#
#     MODEL_PATH = Path("wayfinder_ml_model.pkl")
#
#     def __init__(self):
#         if not _SKLEARN_AVAILABLE:
#             raise ImportError(
#                 "scikit-learn and numpy are required for MLRanker.\n"
#                 "Install with: pip install scikit-learn numpy"
#             )
#         self._model: Pipeline | None = None
#         if self.MODEL_PATH.exists():
#             self.load(str(self.MODEL_PATH))
#
#     # ── public ─────────────────────────────────────────────────────────────
#     def rank(self, attractions: list[Attraction],
#              prefs: UserPreferences,
#              batch_size: int = 10) -> list[Attraction]:
#         """
#         Score attractions and return sorted high → low.
#         Falls back to heuristic scoring if no model is trained yet.
#         """
#         if self._model is None:
#             print("  [ML] No trained model found – using heuristic scoring.")
#             return self._heuristic_rank(attractions, prefs)
#
#         X = np.array([self._featurize(a, prefs) for a in attractions])
#         # predict_proba[:,1] = probability of "user would enjoy this"
#         scores = self._model.predict_proba(X)[:, 1]
#         for a, s in zip(attractions, scores):
#             a.score        = round(float(s) * 10, 2)  # scale to 0–10
#             a.score_reason = "ML model prediction"
#             a.ranker_used  = "ml"
#
#         return sorted(attractions, key=lambda a: a.score, reverse=True)
#
#     def fit(self, attractions: list[Attraction],
#             labels: list[int],
#             prefs: UserPreferences) -> None:
#         """
#         Train the model.
#         labels[i] = 1 if the user enjoyed attractions[i], 0 otherwise.
#         """
#         X = np.array([self._featurize(a, prefs) for a in attractions])
#         y = np.array(labels)
#         self._model = Pipeline([
#             ("scaler", StandardScaler()),
#             ("clf",    LogisticRegression(max_iter=500)),
#         ])
#         self._model.fit(X, y)
#         self.save(str(self.MODEL_PATH))
#         print(f"  [ML] Model trained on {len(labels)} examples and saved.")
#
#     def save(self, path: str) -> None:
#         with open(path, "wb") as f:
#             pickle.dump(self._model, f)
#
#     def load(self, path: str) -> None:
#         with open(path, "rb") as f:
#             self._model = pickle.load(f)
#         print(f"  [ML] Loaded trained model from {path}")
#
#     # ── feature engineering ────────────────────────────────────────────────
#     def _featurize(self, a: Attraction, prefs: UserPreferences) -> list[float]:
#         # [0] normalized rating
#         rating_norm = a.rating / 5.0
#
#         # [1] log-scaled popularity (caps at ~100k reviews → 1.0)
#         pop_norm = math.log1p(a.num_reviews) / math.log1p(100_000)
#
#         # [2] price fit (closer to user's budget tier = higher score)
#         price_enc  = PRICE_LEVEL_MAP.get(a.price_level, 1)
#         budget_enc = BUDGET_MAP.get(prefs.budget, 1)
#         price_fit  = 1.0 - abs(price_enc - budget_enc) / 3.0
#
#         # [3] vibe keyword overlap
#         vibe_score = 0.0
#         all_tags   = " ".join(a.subcategories + a.cuisine_types).lower()
#         for keyword_group in prefs.vibe.lower().split(","):
#             kw = keyword_group.strip()
#             matching = VIBE_KEYWORDS.get(kw, [kw])
#             hits = sum(1 for m in matching if m in all_tags)
#             vibe_score += hits / max(len(matching), 1)
#         vibe_score = min(vibe_score, 1.0)   # cap at 1
#
#         # [4] dietary conflict flag  (1 = bad, 0 = ok)
#         from .filters import AttractionFilter
#         filt    = AttractionFilter(prefs)
#         conflict = 0.0 if filt.passes(a) else 1.0
#
#         # [5-6] category flags
#         cat = a.category.lower()
#         is_attraction  = 1.0 if "attraction" in cat else 0.0
#         is_restaurant  = 1.0 if "restaurant" in cat else 0.0
#
#         return [rating_norm, pop_norm, price_fit,
#                 vibe_score, conflict, is_attraction, is_restaurant]
#
#     # ── heuristic fallback (no trained model needed) ───────────────────────
#     def _heuristic_rank(self, attractions: list[Attraction],
#                         prefs: UserPreferences) -> list[Attraction]:
#         """
#         Simple weighted formula used when no model.pkl exists yet.
#         Good enough for demos; replace with a trained model for production.
#         """
#         for a in attractions:
#             feats  = self._featurize(a, prefs)
#             # weights: rating, popularity, price_fit, vibe, -conflict, +attraction, +restaurant
#             weights = [0.35, 0.20, 0.15, 0.20, -0.30, 0.05, 0.05]
#             raw     = sum(f * w for f, w in zip(feats, weights))
#             a.score        = round(max(0.0, min(10.0, raw * 10)), 2)
#             a.score_reason = "heuristic score (no trained model)"
#             a.ranker_used  = "heuristic"
#         return sorted(attractions, key=lambda a: a.score, reverse=True)