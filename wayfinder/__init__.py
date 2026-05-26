"""
wayfinder — AI-powered travel pipeline (TripAdvisor + Gemini + routing handoff).
"""
from .models import (
    Attraction,
    PipelineResult,
    SOURCE_COMPLETENESS,
    SOURCE_RANKED,
    SOURCE_RESTAURANT_INJECT,
    SOURCE_SWAP,
    SOURCE_USER_REQUIRED,
    TRIP_SHAPE_PRESETS,
    UserPreferences,
)
from .pipeline import generate_recommendations
from .trip_store import TripStore, make_trip_id

__all__ = [
    "generate_recommendations",
    "Attraction",
    "UserPreferences",
    "PipelineResult",
    "TRIP_SHAPE_PRESETS",
    "TripStore",
    "make_trip_id",
    "SOURCE_USER_REQUIRED",
    "SOURCE_RANKED",
    "SOURCE_COMPLETENESS",
    "SOURCE_SWAP",
    "SOURCE_RESTAURANT_INJECT",
]