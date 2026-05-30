from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any


@dataclass
class UserPreferences:
    """User inputs for the attraction recommendation pipeline."""

    destination: str
    travel_dates: tuple[str, str] = ("", "")
    budget: str = "mid-range"
    vibe: str = ""
    dietary_restrictions: list[str] = field(default_factory=list)
    required_attractions: list[str] = field(default_factory=list)
    num_travelers: int = 2


@dataclass
class Attraction:
    """A TripAdvisor place enriched by filtering, ranking, and booking links."""

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
    web_url: str | None = None
    photo_url: str | None = None
    booking_url: str | None = None
    booking_links: dict[str, str] = field(default_factory=dict)
    rating: float | None = None
    score: float | None = None
    score_reason: str | None = None
    open_hours_text: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StopInput":
        visit_minutes = _coerce_optional_int(
            payload.get("visit_minutes", payload.get("duration_minutes"))
        )
        return cls(
            name=payload["name"],
            id=payload.get("id") or payload.get("location_id"),
            address=payload.get("address"),
            latitude=payload.get("latitude"),
            longitude=payload.get("longitude"),
            visit_minutes=visit_minutes,
            visit_minutes_source=payload.get("visit_minutes_source"),
            required=bool(payload.get("required", payload.get("is_mandatory", False))),
            category=payload.get("category"),
            notes=payload.get("notes"),
            place_id=payload.get("place_id") or payload.get("location_id"),
            enabled=bool(payload.get("enabled", True)),
            fixed_day=_coerce_optional_int(payload.get("fixed_day")),
            preferred_start_time=payload.get("preferred_start_time"),
            time_window_start=payload.get("time_window_start"),
            time_window_end=payload.get("time_window_end"),
            anchor_kind=payload.get("anchor_kind"),
            priority=int(payload.get("priority", 0)),
            web_url=payload.get("web_url"),
            photo_url=payload.get("photo_url"),
            booking_url=payload.get("booking_url"),
            booking_links=dict(payload.get("booking_links") or {}),
            rating=_coerce_optional_float(payload.get("rating")),
            score=_coerce_optional_float(payload.get("score")),
            score_reason=payload.get("score_reason"),
            open_hours_text=[str(item) for item in payload.get("open_hours_text", [])],
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
    web_url: str | None = None
    photo_url: str | None = None
    booking_url: str | None = None
    booking_links: dict[str, str] = field(default_factory=dict)
    rating: float | None = None
    score: float | None = None
    score_reason: str | None = None
    open_hours_text: list[str] = field(default_factory=list)

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
            web_url=stop.web_url,
            photo_url=stop.photo_url,
            booking_url=stop.booking_url,
            booking_links=dict(stop.booking_links),
            rating=stop.rating,
            score=stop.score,
            score_reason=stop.score_reason,
            open_hours_text=list(stop.open_hours_text),
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
            "web_url": self.web_url,
            "photo_url": self.photo_url,
            "booking_url": self.booking_url,
            "booking_links": dict(self.booking_links),
            "rating": self.rating,
            "score": self.score,
            "score_reason": self.score_reason,
            "open_hours_text": list(self.open_hours_text),
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
    preferred_categories: list[str] = field(default_factory=list)
    excluded_categories: list[str] = field(default_factory=list)
    clustering_method: str = "best_point"
    anchor_location: StopInput | None = None
    end_each_day_at_anchor: bool = False
    use_llm_duration_estimates: bool = False
    llm_duration_model: str | None = None
    use_llm_cluster_review: bool = False
    llm_review_model: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TripRequest":
        payload = normalize_trip_payload(payload)
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
            preferred_categories=normalize_string_list(payload.get("preferred_categories", [])),
            excluded_categories=normalize_string_list(payload.get("excluded_categories", [])),
            clustering_method=payload.get("clustering_method", "best_point"),
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


def normalize_trip_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept both planner-native JSON and generated recommendation JSON."""

    normalized = dict(payload)
    if normalized.get("stops") or not normalized.get("attractions"):
        return normalized

    raw_preferences = normalized.get("preferences")
    preferences = raw_preferences if isinstance(raw_preferences, dict) else {}
    shape = str(preferences.get("trip_shape") or "balanced").strip().lower()
    shape_settings = {
        "relaxed": {"daily_minutes_budget": 480, "max_stops_per_day": 2, "slack": 60},
        "balanced": {"daily_minutes_budget": 540, "max_stops_per_day": 3, "slack": 45},
        "packed": {"daily_minutes_budget": 660, "max_stops_per_day": 4, "slack": 30},
    }
    settings = shape_settings.get(shape, shape_settings["balanced"])

    required_names = {
        str(name).strip().casefold()
        for name in preferences.get("required_attractions", [])
        if str(name).strip()
    }
    stops = [
        recommendation_item_to_stop(item, required_names=required_names)
        for item in normalized.get("attractions", [])
        if isinstance(item, dict) and item.get("name")
    ]

    normalized["stops"] = stops
    normalized.setdefault("daily_minutes_budget", settings["daily_minutes_budget"])
    normalized.setdefault("max_stops_per_day", settings["max_stops_per_day"])
    normalized.setdefault("daily_redundancy_minutes", settings["slack"])
    normalized.setdefault("lunch_minutes", 60)
    normalized.setdefault("dinner_minutes", 120)
    normalized.setdefault("transport_mode", "auto")
    normalized.setdefault("travel_mode", "auto")
    normalized.setdefault("routing_strategy", "distance")
    normalized.setdefault("clustering_method", "best_point")
    normalized.setdefault("travel_buffer_ratio", 0.15)
    normalized.setdefault("minimum_travel_buffer_minutes", 5)

    travel_dates = preferences.get("travel_dates") or []
    if len(travel_dates) >= 1 and travel_dates[0]:
        normalized.setdefault("start_date", travel_dates[0])
    if len(travel_dates) >= 2 and travel_dates[1]:
        normalized.setdefault("end_date", travel_dates[1])

    normalized.setdefault(
        "num_days",
        infer_generated_trip_days(
            stop_count=len(stops),
            target_stops_per_day=int(settings["max_stops_per_day"]),
            start_date=normalized.get("start_date"),
            end_date=normalized.get("end_date"),
        ),
    )

    anchor_location = recommendation_anchor_from_hotels(normalized.get("hotels", []))
    if anchor_location is not None:
        normalized.setdefault("anchor_location", anchor_location)
        normalized.setdefault("end_each_day_at_anchor", True)

    return normalized


def recommendation_item_to_stop(
    item: dict[str, Any],
    *,
    required_names: set[str],
) -> dict[str, Any]:
    name = str(item["name"])
    score = _coerce_optional_float(item.get("score")) or 0.0
    required = bool(item.get("is_mandatory")) or name.casefold() in required_names
    priority = int(round(score)) + (20 if required else 0)

    return {
        "id": item.get("id") or item.get("location_id") or item.get("place_id") or name,
        "name": name,
        "address": item.get("address"),
        "latitude": item.get("latitude"),
        "longitude": item.get("longitude"),
        "visit_minutes": item.get("visit_minutes", item.get("duration_minutes")),
        "visit_minutes_source": item.get("visit_minutes_source", "recommendation"),
        "required": required,
        "category": normalize_recommendation_category(item),
        "notes": item.get("notes") or item.get("score_reason"),
        "place_id": item.get("place_id") or item.get("location_id"),
        "priority": priority,
        "web_url": item.get("web_url"),
        "photo_url": item.get("photo_url"),
        "booking_url": item.get("booking_url"),
        "booking_links": item.get("booking_links") or {},
        "rating": item.get("rating"),
        "score": item.get("score"),
        "score_reason": item.get("score_reason"),
        "open_hours_text": item.get("open_hours_text") or [],
    }


def recommendation_anchor_from_hotels(hotels: Any) -> dict[str, Any] | None:
    if not isinstance(hotels, list):
        return None
    for hotel in hotels:
        if not isinstance(hotel, dict):
            continue
        if hotel.get("latitude") is None or hotel.get("longitude") is None:
            continue
        name = hotel.get("name")
        if not name:
            continue
        return {
            "id": hotel.get("id") or hotel.get("location_id") or "anchor-location",
            "name": name,
            "address": hotel.get("address"),
            "latitude": hotel.get("latitude"),
            "longitude": hotel.get("longitude"),
            "visit_minutes": 0,
            "visit_minutes_source": "anchor",
            "category": "hotel",
            "anchor_kind": "hotel",
            "web_url": hotel.get("web_url"),
            "photo_url": hotel.get("photo_url"),
            "booking_url": hotel.get("booking_url"),
            "booking_links": hotel.get("booking_links") or {},
            "rating": hotel.get("rating"),
            "score": hotel.get("score"),
            "score_reason": hotel.get("score_reason"),
        }
    return None


def infer_generated_trip_days(
    *,
    stop_count: int,
    target_stops_per_day: int,
    start_date: str | None,
    end_date: str | None,
) -> int:
    if stop_count <= 0:
        return 1

    target_days = max(1, math_ceil_div(stop_count, max(1, target_stops_per_day)))
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if start and end:
        date_days = (end - start).days + 1
        if date_days > 0:
            return max(1, min(date_days, target_days))
    return target_days


def normalize_recommendation_category(item: dict[str, Any]) -> str | None:
    category = str(item.get("category") or "").strip().lower()
    subcategories = " ".join(str(value) for value in item.get("subcategories", [])).lower()
    text = f"{category} {subcategories} {item.get('name', '')}".lower()

    if "restaurant" in text:
        return "restaurant"
    if "food" in text or "drink" in text:
        return "food"
    if "museum" in text or "gallery" in text or "art" in text:
        return "museum"
    if "disney" in text or "amusement" in text or "theme park" in text:
        return "amusement_park"
    if "shopping" in text or "department store" in text:
        return "shopping"
    if "spa" in text or "wellness" in text:
        return "wellness"
    if "transportation" in text or "railway" in text or "station" in text or "metro" in text:
        return "transportation"
    if "landmark" in text or "sight" in text or "tower" in text or "temple" in text:
        return "landmark"
    if "park" in text or "nature" in text or "garden" in text:
        return "park"
    if "tour" in text or "activity" in text:
        return "tour"
    if category and category != "attraction":
        return category
    return "attraction"


def math_ceil_div(left: int, right: int) -> int:
    return -(-left // right)


def parse_clock_time(raw_value: str | None) -> int | None:
    if not raw_value:
        return None
    hours_str, minutes_str = raw_value.split(":", maxsplit=1)
    hours = int(hours_str)
    minutes = int(minutes_str)
    return hours * 60 + minutes


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
    return int(float(value))


def _coerce_optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def normalize_string_list(raw_values: Any) -> list[str]:
    if raw_values is None:
        return []
    if isinstance(raw_values, str):
        raw_values = [raw_values]
    return [str(value).strip().lower() for value in raw_values if str(value).strip()]
