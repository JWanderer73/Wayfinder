from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List

from wayfinder.pipeline import generate_recommendations

app = FastAPI(title="Wayfinder API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------
# Request schema
# -------------------------

class PlanRequest(BaseModel):
    destination: str

    start_date: str
    end_date: str

    budget: str = "mid-range"

    preferred_categories: List[str] = []
    dietary_restrictions: List[str] = []
    required_attractions: List[str] = []

    trip_shape: str = "balanced"
    travel_mode: str = "TRANSIT"


# -------------------------
# Health check
# -------------------------

@app.get("/")
def health():
    return {
        "status": "healthy",
        "service": "wayfinder"
    }


# -------------------------
# Main planner endpoint
# -------------------------

@app.post("/api/plan")
def plan_trip(req: PlanRequest):

    result = generate_recommendations(
        city=req.destination,
        preferences=req.preferred_categories,
        budget=req.budget,
        dietary_restrictions=req.dietary_restrictions,
        required_attractions=req.required_attractions,
        travel_dates=(
            req.start_date,
            req.end_date
        ),
        trip_shape=req.trip_shape,
    )

    return result
