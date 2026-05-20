"""
wayfinder – AI-powered travel planning package.

Spatial planning (routing/scheduling):
  SpatialPlanner, TripRequest, ItineraryPlan — see wayfinder.spatial / wayfinder.models

Attraction recommendations (TripAdvisor + AI ranking):
  Attraction, UserPreferences, generate_recommendations — see wayfinder.pipeline
"""
from .models import Attraction, UserPreferences
from .pipeline import generate_recommendations

__all__ = ["Attraction", "UserPreferences", "generate_recommendations"]
