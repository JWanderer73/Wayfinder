"""
app.py — FastAPI server bridging the two pipeline stages.

Flow:
  POST /api/plan
    1. generate_recommendations()  → TripAdvisor + Gemini ranked attractions
    2. bridge.convert()            → converts to routing-stage TripRequest format
    3. SpatialPlanner.build_plan() → clusters + schedules day-by-day itinerary
    4. bridge.inject_restaurants_into_days() → adds nearby restaurants per day
    5. Return combined JSON to frontend

Run with:
  cd backend
  uvicorn app:app --reload --port 8000
"""
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

from wayfinder.pipeline import generate_recommendations
from wayfinder.bridge import convert, inject_restaurants_into_days
from wayfinder.models import TripRequest
from wayfinder.spatial import SpatialPlanner
from wayfinder.google_maps import GoogleMapsClient
from wayfinder.duration import DurationEstimator

app = FastAPI(title="Wayfinder API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class PlanRequest(BaseModel):
    destination: str
    start_date: str = "2026-06-10"
    end_date: str = "2026-06-12"
    budget: str = "mid-range"
    vibe: str = ""
    dietary_restrictions: list[str] = []
    required_attractions: list[str] = []
    num_travelers: int = 2
    trip_shape: str = "balanced"
    travel_mode: str = "TRANSIT"
    k: int = 10


@app.post("/api/plan")
def plan_trip(req: PlanRequest):
    # ── env checks ────────────────────────────────────────────────────────────
    if not os.getenv("TRIPADVISOR_API_KEY"):
        raise HTTPException(500, "TRIPADVISOR_API_KEY not set")
    if not os.getenv("GEMINI_API_KEY"):
        raise HTTPException(500, "GEMINI_API_KEY not set")

    # ── Stage 1: TripAdvisor + Gemini pipeline ────────────────────────────────
    ta_output = generate_recommendations(
        city=req.destination,
        k=req.k,
        budget=req.budget,
        vibe=req.vibe,
        dietary_restrictions=req.dietary_restrictions,
        required_attractions=req.required_attractions,
        travel_dates=(req.start_date, req.end_date),
        num_travelers=req.num_travelers,
        trip_shape=req.trip_shape,
        travel_mode=req.travel_mode,
        check_completeness=True,
        include_hotels=True,
        persist=False,  # don't write to disk on every API call
    )

    # ── Stage 2: bridge → routing format ─────────────────────────────────────
    trip_request_dict = convert(
        ta_output,
        start_date=req.start_date,
        end_date=req.end_date,
        travel_mode=req.travel_mode,
        end_each_day_at_anchor=True,
    )

    # ── Stage 3: spatial planner → day-by-day schedule ───────────────────────
    trip_request = TripRequest.from_dict(trip_request_dict)
    planner = SpatialPlanner(
        client=GoogleMapsClient(api_key=os.getenv("GOOGLE_MAPS_API_KEY")),
        duration_estimator=DurationEstimator(use_llm=False),
    )
    itinerary = planner.build_plan(trip_request)
    itinerary_dict = itinerary.to_dict()

    # ── Stage 4: inject restaurants into days ─────────────────────────────────
    days_with_restaurants = inject_restaurants_into_days(
        days=itinerary_dict["days"],
        restaurants=ta_output.get("restaurants", []),
        meals_per_day=1,
    )
    itinerary_dict["days"] = days_with_restaurants

    # ── Return combined response ──────────────────────────────────────────────
    return {
        "destination":      req.destination,
        "trip_id":          ta_output.get("trip_id", ""),
        "weather_summary":  ta_output.get("weather_summary", ""),
        "preferences":      ta_output.get("preferences", {}),
        "hotels":           ta_output.get("hotels", []),
        "attractions":      ta_output.get("attractions", []),
        "restaurants":      ta_output.get("restaurants", []),
        "gaps":             ta_output.get("gaps", ""),
        "gaps_structured":  ta_output.get("gaps_structured", []),
        "api_calls":        ta_output.get("api_calls", 0),
        "itinerary":        itinerary_dict,
    }


@app.get("/health")
def health():
    return {"status": "ok"}
