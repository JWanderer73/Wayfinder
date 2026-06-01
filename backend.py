from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from wayfinder.pipeline import generate_recommendations

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TripRequest(BaseModel):
    city: str
    preferences: list[str] = []
    budget: str = "mid-range"
    vibe: str = ""
    dietary_restrictions: list[str] = []
    required_attractions: list[str] = []
    travel_dates: list[str] = ["", ""]
    num_travelers: int = 2
    trip_shape: str = "balanced"
    k: int = 10


@app.get("/")
def health():
    return {"status": "healthy"}


@app.post("/recommend")
def recommend(req: TripRequest):

    result = generate_recommendations(
        city=req.city,
        preferences=req.preferences,
        k=req.k,
        budget=req.budget,
        vibe=req.vibe,
        dietary_restrictions=req.dietary_restrictions,
        required_attractions=req.required_attractions,
        travel_dates=tuple(req.travel_dates),
        num_travelers=req.num_travelers,
        trip_shape=req.trip_shape,
    )

    return result
