import os

from dotenv import load_dotenv
load_dotenv()   # reads .env automatically

# backend/app.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Branch 1 pipeline
from wayfinder.pipeline import generate_recommendations

# Branch 2 spatial planner
from wayfinder.spatial import SpatialPlanner
from wayfinder.models import TripRequest, StopInput
from wayfinder.google_maps import GoogleMapsClient

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PlanRequest(BaseModel):
    destination: str
    start_date: str
    end_date: str
    budget: str = "mid-range"
    vibe: str = ""
    dietary_restrictions: list[str] = []
    required_attractions: list[str] = []

@app.post("/api/plan")
def plan_trip(req: PlanRequest):
    # 1. Branch 1: fetch + rank attractions
    rec = generate_recommendations(
        city=req.destination,
        budget=req.budget,
        vibe=req.vibe,
        dietary_restrictions=req.dietary_restrictions,
        required_attractions=req.required_attractions,
        k=12,
    )

    # 2. Convert Branch 1 output → Branch 2 input format
    stops = []
    for a in rec["attractions"]:
        stops.append({
            "name": a["name"],
            "latitude": a["latitude"],
            "longitude": a["longitude"],
            "visit_minutes": None,   # Branch 2 fills with heuristics
            "category": a["category"].lower(),
            "required": a["name"] in req.required_attractions,
        })

    # 3. Branch 2: cluster + route
    trip_req = TripRequest.from_dict({
        "destination": req.destination,
        "start_date": req.start_date,
        "end_date": req.end_date,
        "daily_minutes_budget": 480,
        "transport_mode": "auto",
        "lunch_minutes": 60,
        "dinner_minutes": 120,
        "stops": stops,
    })
    planner = SpatialPlanner(GoogleMapsClient(api_key=os.getenv("GOOGLE_MAPS_API_KEY")))
    itinerary = planner.build_plan(trip_req)

    # 4. Merge booking links back in
    link_map = {a["name"]: a["booking_links"] for a in rec["attractions"]}
    for day in itinerary.to_dict()["days"]:
        for visit in day["scheduled_visits"]:
            name = visit["stop"]["name"]
            visit["stop"]["booking_links"] = link_map.get(name, {})

    return {
        "destination": req.destination,
        "hotels": rec["hotels"],
        "itinerary": itinerary.to_dict(),
    }