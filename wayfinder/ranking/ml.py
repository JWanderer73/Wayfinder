"""
wayfinder/ranking/ml.py
────────────────────────
Scikit-learn-based ranker. Optional — only imported when used.

Falls back to HeuristicRanker when no trained model exists.

MANDATORY HANDLING
  Mandatory items skip ML scoring entirely and get the fixed high score
  from the heuristic. This means a not-yet-trained model can never push a
  user-requested attraction off the list.
"""
from __future__ import annotations

import math
import pickle
from pathlib import Path

from ..models import Attraction, UserPreferences
from .base import Ranker
from .heuristic import MANDATORY_FLOOR_SCORE, HeuristicRanker

try:
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False


PRICE_LEVEL_MAP = {"$": 0, "$$": 1, "$$$": 2, "$$$$": 3, "": 1}
BUDGET_MAP      = {"budget": 0, "mid-range": 1, "luxury": 2}
VIBE_KEYWORDS   = {
    "adventure":  ["outdoor", "hiking", "extreme", "sport", "kayak"],
    "culture":    ["museum", "gallery", "temple", "heritage", "historic"],
    "food":       ["restaurant", "cuisine", "market", "food", "chef"],
    "relaxation": ["spa", "beach", "park", "garden", "resort"],
    "nightlife":  ["bar", "club", "pub", "cocktail", "rooftop"],
}


class MLRanker(Ranker):
    """Logistic-regression ranker. Mandatory items bypass ML entirely."""

    name       = "ml"
    MODEL_PATH = Path("wayfinder_ml_model.pkl")

    def __init__(self):
        if not _SKLEARN_AVAILABLE:
            raise ImportError(
                "scikit-learn + numpy required.\npip install scikit-learn numpy"
            )
        self._model: Pipeline | None = None
        if self.MODEL_PATH.exists():
            self.load(str(self.MODEL_PATH))

    def rank(self, attractions: list[Attraction],
             prefs: UserPreferences) -> list[Attraction]:
        if self._model is None:
            print("  [ML] No trained model — falling back to heuristic.")
            return HeuristicRanker().rank(attractions, prefs)

        for a in attractions:
            if a.is_mandatory:
                a.score        = round(MANDATORY_FLOOR_SCORE + 0.01 * a.rating, 2)
                a.score_reason = "Mandatory — user-requested"
                a.confidence   = 1.0
                a.ranker_used  = self.name

        suggested = [a for a in attractions if not a.is_mandatory]
        if suggested:
            X = np.array([self._featurize(a, prefs) for a in suggested])
            scores = self._model.predict_proba(X)[:, 1]
            for a, s in zip(suggested, scores):
                a.score        = round(float(s) * 10, 2)
                a.score_reason = "ML model prediction"
                a.ranker_used  = self.name
                a.confidence   = round(abs(float(s) - 0.5) * 2.0, 3)

        return sorted(attractions, key=lambda a: a.score, reverse=True)

    def fit(self, attractions: list[Attraction],
            labels: list[int], prefs: UserPreferences) -> None:
        """Train on (attraction, liked?) pairs and persist the model."""
        X = np.array([self._featurize(a, prefs) for a in attractions])
        y = np.array(labels)
        self._model = Pipeline([
            ("scaler", StandardScaler()),
            ("clf",    LogisticRegression(max_iter=500)),
        ])
        self._model.fit(X, y)
        self.save(str(self.MODEL_PATH))
        print(f"  [ML] Trained on {len(labels)} examples.")

    def save(self, path: str) -> None:
        with open(path, "wb") as f:
            pickle.dump(self._model, f)

    def load(self, path: str) -> None:
        with open(path, "rb") as f:
            self._model = pickle.load(f)
        print(f"  [ML] Loaded model from {path}")

    def _featurize(self, a: Attraction, prefs: UserPreferences) -> list[float]:
        rating_norm = a.rating / 5.0
        pop_norm    = math.log1p(a.num_reviews) / math.log1p(100_000)
        price_enc   = PRICE_LEVEL_MAP.get(a.price_level, 1)
        budget_enc  = BUDGET_MAP.get(prefs.budget, 1)
        price_fit   = 1.0 - abs(price_enc - budget_enc) / 3.0

        vibe_score = 0.0
        all_tags   = " ".join(a.subcategories + a.cuisine_types).lower()
        for keyword_group in prefs.vibe.lower().split(","):
            kw = keyword_group.strip()
            matching = VIBE_KEYWORDS.get(kw, [kw])
            hits = sum(1 for m in matching if m in all_tags)
            vibe_score += hits / max(len(matching), 1)
        vibe_score = min(vibe_score, 1.0)

        conflict = 0.0
        for diet in prefs.dietary_restrictions:
            for blocked in _DIETARY_BLOCKLIST.get(diet.lower(), []):
                if blocked in all_tags:
                    conflict = 1.0
                    break

        cat = a.category.lower()
        return [rating_norm, pop_norm, price_fit, vibe_score, conflict,
                1.0 if "attraction" in cat else 0.0,
                1.0 if "restaurant" in cat else 0.0]


_DIETARY_BLOCKLIST: dict[str, list[str]] = {
    "vegan":       ["steakhouse", "seafood", "sushi", "bbq", "barbecue"],
    "vegetarian":  ["steakhouse", "bbq", "barbecue"],
    "gluten-free": [],
    "halal":       ["bar", "pub", "brewery"],
    "kosher":      ["seafood", "shellfish", "pork"],
}