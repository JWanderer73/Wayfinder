from __future__ import annotations

import math
from dataclasses import dataclass

from .models import MatrixCell, ResolvedStop


WALK_THRESHOLD_METERS = 1_200
TRANSIT_THRESHOLD_METERS = 8_000


@dataclass(slots=True)
class TransportProfile:
    mode: str
    speed_kmh: float
    base_minutes: int
    cost_per_km: float


TRANSPORT_PROFILES = {
    "walk": TransportProfile("walk", speed_kmh=4.8, base_minutes=0, cost_per_km=0.0),
    "bike": TransportProfile("bike", speed_kmh=14.0, base_minutes=2, cost_per_km=0.0),
    "transit": TransportProfile("transit", speed_kmh=22.0, base_minutes=10, cost_per_km=0.35),
    "drive": TransportProfile("drive", speed_kmh=32.0, base_minutes=6, cost_per_km=0.75),
}

MODE_ALIASES = {
    "walking": "walk",
    "foot": "walk",
    "by_foot": "walk",
    "public": "transit",
    "public_transport": "transit",
    "bus": "transit",
    "subway": "transit",
    "train": "transit",
    "car": "drive",
    "driving": "drive",
    "auto": "auto",
    "automatic": "auto",
    "bicycle": "bike",
    "cycling": "bike",
}


def standardize_transport_mode(raw_mode: str | None) -> str:
    if not raw_mode:
        return "auto"
    normalized = raw_mode.strip().lower().replace("-", "_").replace(" ", "_")
    return MODE_ALIASES.get(normalized, normalized if normalized in TRANSPORT_PROFILES else "auto")


def choose_transport_mode(distance_meters: float, requested_mode: str | None = "auto") -> str:
    mode = standardize_transport_mode(requested_mode)
    if mode != "auto":
        return mode
    if distance_meters <= WALK_THRESHOLD_METERS:
        return "walk"
    if distance_meters <= TRANSIT_THRESHOLD_METERS:
        return "transit"
    return "drive"


def estimate_travel_minutes(distance_meters: float, requested_mode: str | None = "auto") -> int:
    mode = choose_transport_mode(distance_meters, requested_mode)
    profile = TRANSPORT_PROFILES[mode]
    distance_km = distance_meters / 1_000
    moving_minutes = (distance_km / profile.speed_kmh) * 60 if profile.speed_kmh > 0 else 0
    return max(1, math.ceil(profile.base_minutes + moving_minutes))


def estimate_travel_cost(distance_meters: float, mode: str) -> float:
    profile = TRANSPORT_PROFILES[choose_transport_mode(distance_meters, mode)]
    return round((distance_meters / 1_000) * profile.cost_per_km, 2)


def build_distance_matrix(
    stops: list[ResolvedStop],
    *,
    requested_mode: str | None = "auto",
) -> list[list[MatrixCell]]:
    matrix: list[list[MatrixCell]] = []
    for origin_index, origin in enumerate(stops):
        row: list[MatrixCell] = []
        for destination_index, destination in enumerate(stops):
            if origin_index == destination_index:
                row.append(
                    MatrixCell(
                        origin_index=origin_index,
                        destination_index=destination_index,
                        duration_seconds=0.0,
                        distance_meters=0.0,
                        condition="ROUTE_EXISTS",
                        transport_mode="none",
                        cost_estimate=0.0,
                    )
                )
                continue

            distance_meters = haversine_meters(
                origin.latitude,
                origin.longitude,
                destination.latitude,
                destination.longitude,
            )
            mode = choose_transport_mode(distance_meters, requested_mode)
            minutes = estimate_travel_minutes(distance_meters, mode)
            row.append(
                MatrixCell(
                    origin_index=origin_index,
                    destination_index=destination_index,
                    duration_seconds=minutes * 60,
                    distance_meters=distance_meters,
                    condition="ROUTE_EXISTS",
                    transport_mode=mode,
                    cost_estimate=estimate_travel_cost(distance_meters, mode),
                )
            )
        matrix.append(row)
    return matrix


def travel_buffer_minutes(
    travel_minutes: int,
    *,
    buffer_ratio: float,
    minimum_buffer_minutes: int,
) -> int:
    if travel_minutes <= 0:
        return 0
    return max(minimum_buffer_minutes, math.ceil(travel_minutes * buffer_ratio))


def haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6_371_000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius * c
