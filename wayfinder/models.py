from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any


@dataclass(slots=True)
class StopInput:
    name: str
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    visit_minutes: int = 90
    required: bool = False
    category: str | None = None
    notes: str | None = None
    place_id: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StopInput":
        return cls(
            name=payload["name"],
            address=payload.get("address"),
            latitude=payload.get("latitude"),
            longitude=payload.get("longitude"),
            visit_minutes=int(payload.get("visit_minutes", 90)),
            required=bool(payload.get("required", False)),
            category=payload.get("category"),
            notes=payload.get("notes"),
            place_id=payload.get("place_id"),
        )

    def query_text(self, destination_hint: str | None = None) -> str:
        if self.address:
            return self.address
        if destination_hint and destination_hint.lower() not in self.name.lower():
            return f"{self.name}, {destination_hint}"
        return self.name


@dataclass(slots=True)
class ResolvedStop:
    name: str
    latitude: float
    longitude: float
    visit_minutes: int
    address: str | None = None
    required: bool = False
    category: str | None = None
    notes: str | None = None
    place_id: str | None = None
    formatted_address: str | None = None
    source_query: str | None = None

    @classmethod
    def from_stop_input(
        cls,
        stop: StopInput,
        *,
        latitude: float,
        longitude: float,
        formatted_address: str | None = None,
        place_id: str | None = None,
        source_query: str | None = None,
    ) -> "ResolvedStop":
        return cls(
            name=stop.name,
            latitude=latitude,
            longitude=longitude,
            visit_minutes=stop.visit_minutes,
            address=stop.address,
            required=stop.required,
            category=stop.category,
            notes=stop.notes,
            place_id=place_id or stop.place_id,
            formatted_address=formatted_address,
            source_query=source_query,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MatrixCell:
    origin_index: int
    destination_index: int
    duration_seconds: float
    distance_meters: float
    condition: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DayPlan:
    day_number: int
    stops: list[ResolvedStop]
    total_visit_minutes: int
    total_travel_minutes: int
    ordered_stop_indices: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["stops"] = [stop.to_dict() for stop in self.stops]
        return payload


@dataclass(slots=True)
class ItineraryPlan:
    destination: str
    num_days: int
    resolved_stops: list[ResolvedStop]
    days: list[DayPlan]
    matrix: list[list[MatrixCell]]
    daily_minutes_budget: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "destination": self.destination,
            "num_days": self.num_days,
            "daily_minutes_budget": self.daily_minutes_budget,
            "resolved_stops": [stop.to_dict() for stop in self.resolved_stops],
            "days": [day.to_dict() for day in self.days],
            "matrix": [
                [cell.to_dict() for cell in row]
                for row in self.matrix
            ],
        }


@dataclass(slots=True)
class TripRequest:
    destination: str
    stops: list[StopInput]
    start_date: date | None = None
    end_date: date | None = None
    num_days: int | None = None
    daily_minutes_budget: int = 480
    travel_mode: str = "DRIVE"
    region_code: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TripRequest":
        start_date = _parse_date(payload.get("start_date"))
        end_date = _parse_date(payload.get("end_date"))
        return cls(
            destination=payload["destination"],
            stops=[StopInput.from_dict(item) for item in payload.get("stops", [])],
            start_date=start_date,
            end_date=end_date,
            num_days=payload.get("num_days"),
            daily_minutes_budget=int(payload.get("daily_minutes_budget", 480)),
            travel_mode=payload.get("travel_mode", "DRIVE"),
            region_code=payload.get("region_code"),
        )

    def inferred_num_days(self) -> int:
        if self.num_days:
            return self.num_days
        if self.start_date and self.end_date:
            delta = (self.end_date - self.start_date).days + 1
            if delta > 0:
                return delta
        return 1


def _parse_date(raw_value: str | None) -> date | None:
    if not raw_value:
        return None
    return date.fromisoformat(raw_value)
