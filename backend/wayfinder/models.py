from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Any


# ── Recommendation models (Attraction pipeline) ───────────────────────────────

@dataclass
class UserPreferences:
    """All user-supplied inputs for the recommendation pipeline."""
    destination: str
    travel_dates: tuple[str, str] = ("", "")
    budget: str = "mid-range"
    vibe: str = ""
    dietary_restrictions: list[str] = field(default_factory=list)
    required_attractions: list[str] = field(default_factory=list)
    num_travelers: int = 2


@dataclass
class Attraction:
    """One point of interest returned from TripAdvisor + enriched by the pipeline."""
    location_id: str
    name: str
    category: str
    subcategories: list[str]
    rating: float
    num_reviews: int
    address: str
    latitude: float
    longitude: float
    web_url: str
    photo_url: str = ""
    price_level: str = ""
    cuisine_types: list[str] = field(default_factory=list)
    hours: dict = field(default_factory=dict)
    booking_url: str = ""
    booking_links: dict = field(default_factory=dict)
    score: float = 0.0
    score_reason: str = ""
    ranker_used: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ── Spatial planning models (routing/scheduling pipeline) ─────────────────────

@dataclass(slots=True)
class StopInput:
    name: str
    id: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    visit_minutes: int | None = None
    visit_minutes_source: str | None = None
    required: bool = False
    category: str | None = None
    notes: str | None = None
    place_id: str | None = None
    enabled: bool = True
    fixed_day: int | None = None
    preferred_start_time: str | None = None
    time_window_start: str | None = None
    time_window_end: str | None = None
    anchor_kind: str | None = None
    priority: int = 0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StopInput":
        visit_minutes = _coerce_optional_int(payload.get("visit_minutes"))
        return cls(
            name=payload["name"],
            id=payload.get("id"),
            address=payload.get("address"),
            latitude=payload.get("latitude"),
            longitude=payload.get("longitude"),
            visit_minutes=visit_minutes,
            visit_minutes_source=payload.get("visit_minutes_source"),
            required=bool(payload.get("required", False)),
            category=payload.get("category"),
            notes=payload.get("notes"),
            place_id=payload.get("place_id"),
            enabled=bool(payload.get("enabled", True)),
            fixed_day=_coerce_optional_int(payload.get("fixed_day")),
            preferred_start_time=payload.get("preferred_start_time"),
            time_window_start=payload.get("time_window_start"),
            time_window_end=payload.get("time_window_end"),
            anchor_kind=payload.get("anchor_kind"),
            priority=int(payload.get("priority", 0)),
        )

    def query_text(self, destination_hint: str | None = None) -> str:
        if self.address:
            return self.address
        if destination_hint and destination_hint.lower() not in self.name.lower():
            return f"{self.name}, {destination_hint}"
        return self.name


@dataclass(slots=True)
class ResolvedStop:
    id: str
    name: str
    latitude: float
    longitude: float
    visit_minutes: int
    visit_minutes_source: str
    address: str | None = None
    required: bool = False
    category: str | None = None
    notes: str | None = None
    place_id: str | None = None
    formatted_address: str | None = None
    source_query: str | None = None
    fixed_day: int | None = None
    preferred_start_minute: int | None = None
    time_window_start_minute: int | None = None
    time_window_end_minute: int | None = None
    anchor_kind: str | None = None
    priority: int = 0
    selected_transport_mode: str | None = None

    @classmethod
    def from_stop_input(
        cls,
        stop: StopInput,
        *,
        latitude: float,
        longitude: float,
        visit_minutes: int,
        visit_minutes_source: str,
        formatted_address: str | None = None,
        place_id: str | None = None,
        source_query: str | None = None,
    ) -> "ResolvedStop":
        return cls(
            id=stop.id or stop.name,
            name=stop.name,
            latitude=latitude,
            longitude=longitude,
            visit_minutes=visit_minutes,
            visit_minutes_source=visit_minutes_source,
            address=stop.address,
            required=stop.required,
            category=stop.category,
            notes=stop.notes,
            place_id=place_id or stop.place_id,
            formatted_address=formatted_address,
            source_query=source_query,
            fixed_day=stop.fixed_day,
            preferred_start_minute=parse_clock_time(stop.preferred_start_time),
            time_window_start_minute=parse_clock_time(stop.time_window_start),
            time_window_end_minute=parse_clock_time(stop.time_window_end),
            anchor_kind=stop.anchor_kind,
            priority=stop.priority,
        )

    def has_time_anchor(self) -> bool:
        return (
            self.preferred_start_minute is not None
            or self.time_window_start_minute is not None
            or self.time_window_end_minute is not None
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "visit_minutes": self.visit_minutes,
            "visit_minutes_source": self.visit_minutes_source,
            "address": self.address,
            "required": self.required,
            "category": self.category,
            "notes": self.notes,
            "place_id": self.place_id,
            "formatted_address": self.formatted_address,
            "source_query": self.source_query,
            "fixed_day": self.fixed_day,
            "preferred_start_minute": self.preferred_start_minute,
            "preferred_start_time": format_clock_time(self.preferred_start_minute),
            "time_window_start_minute": self.time_window_start_minute,
            "time_window_start": format_clock_time(self.time_window_start_minute),
            "time_window_end_minute": self.time_window_end_minute,
            "time_window_end": format_clock_time(self.time_window_end_minute),
            "anchor_kind": self.anchor_kind,
            "priority": self.priority,
            "selected_transport_mode": self.selected_transport_mode,
        }


@dataclass(slots=True)
class MatrixCell:
    origin_index: int
    destination_index: int
    duration_seconds: float
    distance_meters: float
    condition: str
    transport_mode: str = "unknown"
    cost_estimate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "origin_index": self.origin_index,
            "destination_index": self.destination_index,
            "duration_seconds": self.duration_seconds,
            "distance_meters": self.distance_meters,
            "condition": self.condition,
            "transport_mode": self.transport_mode,
            "cost_estimate": self.cost_estimate,
        }


@dataclass(slots=True)
class ScheduledVisit:
    stop: ResolvedStop
    arrival_time: str
    start_time: str
    departure_time: str
    travel_minutes_from_previous: int
    travel_buffer_minutes: int = 0
    transport_mode_from_previous: str | None = None
    distance_meters_from_previous: float = 0.0
    wait_minutes: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stop": self.stop.to_dict(),
            "arrival_time": self.arrival_time,
            "start_time": self.start_time,
            "departure_time": self.departure_time,
            "travel_minutes_from_previous": self.travel_minutes_from_previous,
            "travel_buffer_minutes": self.travel_buffer_minutes,
            "transport_mode_from_previous": self.transport_mode_from_previous,
            "distance_meters_from_previous": self.distance_meters_from_previous,
            "wait_minutes": self.wait_minutes,
            "warnings": list(self.warnings),
        }


@dataclass(slots=True)
class DayPlan:
    day_number: int
    scheduled_visits: list[ScheduledVisit]
    total_visit_minutes: int
    total_travel_minutes: int
    total_travel_buffer_minutes: int
    total_wait_minutes: int
    lunch_minutes: int
    dinner_minutes: int
    redundancy_minutes: int
    total_minutes: int
    warnings: list[str] = field(default_factory=list)
    ordered_stop_ids: list[str] = field(default_factory=list)
    matrix_stop_order: list[str] = field(default_factory=list)
    route_matrix: list[list[MatrixCell]] = field(default_factory=list)
    start_anchor: ResolvedStop | None = None
    end_anchor: ResolvedStop | None = None
    return_to_anchor_minutes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "day_number": self.day_number,
            "scheduled_visits": [visit.to_dict() for visit in self.scheduled_visits],
            "total_visit_minutes": self.total_visit_minutes,
            "total_travel_minutes": self.total_travel_minutes,
            "total_travel_buffer_minutes": self.total_travel_buffer_minutes,
            "total_wait_minutes": self.total_wait_minutes,
            "lunch_minutes": self.lunch_minutes,
            "dinner_minutes": self.dinner_minutes,
            "redundancy_minutes": self.redundancy_minutes,
            "total_minutes": self.total_minutes,
            "warnings": list(self.warnings),
            "ordered_stop_ids": list(self.ordered_stop_ids),
            "matrix_stop_order": list(self.matrix_stop_order),
            "route_matrix": [
                [cell.to_dict() for cell in row]
                for row in self.route_matrix
            ],
            "start_anchor": self.start_anchor.to_dict() if self.start_anchor else None,
            "end_anchor": self.end_anchor.to_dict() if self.end_anchor else None,
            "return_to_anchor_minutes": self.return_to_anchor_minutes,
        }


@dataclass(slots=True)
class ItineraryPlan:
    destination: str
    num_days: int
    resolved_stops: list[ResolvedStop]
    days: list[DayPlan]
    daily_minutes_budget: int
    removed_stops: list[str] = field(default_factory=list)
    planning_notes: list[str] = field(default_factory=list)
    anchor_location: ResolvedStop | None = None
    matrix_scope: str = "per_day"

    def to_dict(self) -> dict[str, Any]:
        return {
            "destination": self.destination,
            "num_days": self.num_days,
            "daily_minutes_budget": self.daily_minutes_budget,
            "resolved_stops": [stop.to_dict() for stop in self.resolved_stops],
            "days": [day.to_dict() for day in self.days],
            "removed_stops": list(self.removed_stops),
            "planning_notes": list(self.planning_notes),
            "anchor_location": self.anchor_location.to_dict() if self.anchor_location else None,
            "matrix_scope": self.matrix_scope,
        }


@dataclass(slots=True)
class TripRequest:
    destination: str
    stops: list[StopInput]
    start_date: date | None = None
    end_date: date | None = None
    num_days: int | None = None
    daily_minutes_budget: int = 480
    day_start_time: str = "09:00"
    travel_mode: str = "DRIVE"
    routing_strategy: str = "distance"
    transport_mode: str = "auto"
    lunch_minutes: int = 60
    dinner_minutes: int = 120
    include_lunch_buffer: bool = True
    include_dinner_buffer: bool = True
    travel_buffer_ratio: float = 0.15
    minimum_travel_buffer_minutes: int = 5
    daily_redundancy_minutes: int = 45
    region_code: str | None = None
    max_stops_per_day: int | None = None
    excluded_stop_names: list[str] = field(default_factory=list)
    anchor_location: StopInput | None = None
    end_each_day_at_anchor: bool = False
    use_llm_duration_estimates: bool = False
    llm_duration_model: str | None = None
    use_llm_cluster_review: bool = False
    llm_review_model: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TripRequest":
        start_date = _parse_date(payload.get("start_date"))
        end_date = _parse_date(payload.get("end_date"))
        stops = [StopInput.from_dict(item) for item in payload.get("stops", [])]
        for index, stop in enumerate(stops, start=1):
            if not stop.id:
                stop.id = f"stop-{index}"

        anchor_payload = payload.get("anchor_location")
        anchor_location = StopInput.from_dict(anchor_payload) if anchor_payload else None
        if anchor_location and not anchor_location.id:
            anchor_location.id = "anchor-location"

        return cls(
            destination=payload["destination"],
            stops=stops,
            start_date=start_date,
            end_date=end_date,
            num_days=_coerce_optional_int(payload.get("num_days")),
            daily_minutes_budget=int(payload.get("daily_minutes_budget", 480)),
            day_start_time=payload.get("day_start_time", "09:00"),
            travel_mode=payload.get("travel_mode", "DRIVE"),
            routing_strategy=payload.get("routing_strategy", "distance"),
            transport_mode=payload.get("transport_mode", payload.get("travel_mode", "auto")),
            lunch_minutes=int(payload.get("lunch_minutes", 60)),
            dinner_minutes=int(payload.get("dinner_minutes", 120)),
            include_lunch_buffer=bool(payload.get("include_lunch_buffer", True)),
            include_dinner_buffer=bool(payload.get("include_dinner_buffer", True)),
            travel_buffer_ratio=float(payload.get("travel_buffer_ratio", 0.15)),
            minimum_travel_buffer_minutes=int(payload.get("minimum_travel_buffer_minutes", 5)),
            daily_redundancy_minutes=int(payload.get("daily_redundancy_minutes", 45)),
            region_code=payload.get("region_code"),
            max_stops_per_day=_coerce_optional_int(payload.get("max_stops_per_day")),
            excluded_stop_names=[str(item) for item in payload.get("excluded_stop_names", [])],
            anchor_location=anchor_location,
            end_each_day_at_anchor=bool(payload.get("end_each_day_at_anchor", False)),
            use_llm_duration_estimates=bool(payload.get("use_llm_duration_estimates", False)),
            llm_duration_model=payload.get("llm_duration_model"),
            use_llm_cluster_review=bool(payload.get("use_llm_cluster_review", False)),
            llm_review_model=payload.get("llm_review_model"),
        )

    def inferred_num_days(self) -> int:
        if self.num_days:
            return self.num_days
        if self.start_date and self.end_date:
            delta = (self.end_date - self.start_date).days + 1
            if delta > 0:
                return delta
        return 1

    def day_start_minute(self) -> int:
        return parse_clock_time(self.day_start_time) or 9 * 60


# ── Shared helpers ────────────────────────────────────────────────────────────

def parse_clock_time(raw_value: str | None) -> int | None:
    if not raw_value:
        return None
    hours_str, minutes_str = raw_value.split(":", maxsplit=1)
    return int(hours_str) * 60 + int(minutes_str)


def format_clock_time(total_minutes: int | None) -> str | None:
    if total_minutes is None:
        return None
    minutes_in_day = total_minutes % (24 * 60)
    hours = minutes_in_day // 60
    minutes = minutes_in_day % 60
    return f"{hours:02d}:{minutes:02d}"


def _parse_date(raw_value: str | None) -> date | None:
    if not raw_value:
        return None
    return date.fromisoformat(raw_value)


def _coerce_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)
