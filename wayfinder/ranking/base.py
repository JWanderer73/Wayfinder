"""
wayfinder/ranking/base.py
──────────────────────────
Abstract base class for all rankers.
 
Any ranker plugged into the pipeline must implement rank().
check_completeness() is optional — the pipeline uses hasattr().
"""
from __future__ import annotations
 
from abc import ABC, abstractmethod
 
from ..models import Attraction, UserPreferences
 
 
class Ranker(ABC):
    """All rankers (Gemini, ML, heuristic, future) conform to this."""
 
    name: str = "base"
 
    @abstractmethod
    def rank(self, attractions: list[Attraction],
             prefs: UserPreferences) -> list[Attraction]:
        """
        Score every attraction and return sorted high → low.
        Implementations MUST set: score, score_reason, ranker_used, confidence.
        Implementations MUST NOT modify is_mandatory or selection_source.
        """
        ...