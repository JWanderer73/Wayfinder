from __future__ import annotations

import math
from dataclasses import dataclass

from .google_maps import GoogleMapsClient
from .models import DayPlan, ItineraryPlan, MatrixCell, ResolvedStop, TripRequest


@dataclass(slots=True)
class SpatialPlanner:
    client: GoogleMapsClient

    def build_plan(self, trip: TripRequest) -> ItineraryPlan:
        if not trip.stops:
            return ItineraryPlan(
                destination=trip.destination,
                num_days=max(1, trip.inferred_num_days()),
                resolved_stops=[],
                days=[],
                matrix=[],
                daily_minutes_budget=trip.daily_minutes_budget,
            )

        resolved_stops = [
            self.client.resolve_stop(
                stop,
                destination_hint=trip.destination,
                region_code=trip.region_code,
            )
            for stop in trip.stops
        ]
        matrix = self.client.compute_route_matrix(resolved_stops, travel_mode=trip.travel_mode)
        num_days = max(1, min(len(resolved_stops), trip.inferred_num_days()))
        if num_days == 1 and len(resolved_stops) > 0:
            estimated_days = estimate_days_from_budget(
                resolved_stops,
                matrix,
                daily_minutes_budget=trip.daily_minutes_budget,
            )
            num_days = max(1, estimated_days)

        day_clusters = cluster_stops_by_day(
            resolved_stops,
            num_days=num_days,
            daily_minutes_budget=trip.daily_minutes_budget,
        )

        days: list[DayPlan] = []
        for day_number, cluster in enumerate(day_clusters, start=1):
            ordered_indices = order_cluster(cluster, matrix)
            ordered_stops = [resolved_stops[index] for index in ordered_indices]
            total_visit_minutes = sum(stop.visit_minutes for stop in ordered_stops)
            total_travel_minutes = total_path_minutes(ordered_indices, matrix)
            days.append(
                DayPlan(
                    day_number=day_number,
                    stops=ordered_stops,
                    total_visit_minutes=total_visit_minutes,
                    total_travel_minutes=total_travel_minutes,
                    ordered_stop_indices=ordered_indices,
                )
            )

        return ItineraryPlan(
            destination=trip.destination,
            num_days=len(days),
            resolved_stops=resolved_stops,
            days=days,
            matrix=matrix,
            daily_minutes_budget=trip.daily_minutes_budget,
        )


def estimate_days_from_budget(
    stops: list[ResolvedStop],
    matrix: list[list[MatrixCell]],
    *,
    daily_minutes_budget: int,
) -> int:
    if not stops:
        return 1
    visit_minutes = sum(stop.visit_minutes for stop in stops)
    travel_minutes = 0
    for i in range(len(stops)):
        nearest_minutes = min(
            (
                math.ceil(matrix[i][j].duration_seconds / 60)
                for j in range(len(stops))
                if i != j and math.isfinite(matrix[i][j].duration_seconds)
            ),
            default=0,
        )
        travel_minutes += nearest_minutes

    total_minutes = visit_minutes + travel_minutes
    return max(1, math.ceil(total_minutes / daily_minutes_budget))


def cluster_stops_by_day(
    stops: list[ResolvedStop],
    *,
    num_days: int,
    daily_minutes_budget: int,
) -> list[list[int]]:
    if not stops:
        return []

    num_days = max(1, min(num_days, len(stops)))
    if num_days == 1:
        return [list(range(len(stops)))]

    seeds = farthest_first_seeds(stops, num_days)
    clusters: list[list[int]] = [[seed] for seed in seeds]
    assigned = set(seeds)
    cluster_minutes = [stops[seed].visit_minutes for seed in seeds]

    remaining = [
        index for index in sorted(range(len(stops)), key=lambda idx: stops[idx].visit_minutes, reverse=True)
        if index not in assigned
    ]

    for index in remaining:
        best_cluster = None
        best_score = float("inf")
        for cluster_index, cluster in enumerate(clusters):
            centroid_lat, centroid_lng = cluster_centroid(cluster, stops)
            geo_distance = haversine_meters(
                stops[index].latitude,
                stops[index].longitude,
                centroid_lat,
                centroid_lng,
            )
            overflow = max(
                0,
                cluster_minutes[cluster_index] + stops[index].visit_minutes - daily_minutes_budget,
            )
            score = geo_distance + overflow * 200
            if score < best_score:
                best_score = score
                best_cluster = cluster_index

        assert best_cluster is not None
        clusters[best_cluster].append(index)
        cluster_minutes[best_cluster] += stops[index].visit_minutes

    return [sorted(cluster) for cluster in clusters if cluster]


def farthest_first_seeds(stops: list[ResolvedStop], num_days: int) -> list[int]:
    average_lat = sum(stop.latitude for stop in stops) / len(stops)
    average_lng = sum(stop.longitude for stop in stops) / len(stops)
    first_seed = max(
        range(len(stops)),
        key=lambda idx: haversine_meters(
            stops[idx].latitude,
            stops[idx].longitude,
            average_lat,
            average_lng,
        ),
    )
    seeds = [first_seed]

    while len(seeds) < num_days:
        next_seed = max(
            (
                idx for idx in range(len(stops))
                if idx not in seeds
            ),
            key=lambda idx: min(
                haversine_meters(
                    stops[idx].latitude,
                    stops[idx].longitude,
                    stops[seed].latitude,
                    stops[seed].longitude,
                )
                for seed in seeds
            ),
        )
        seeds.append(next_seed)

    return seeds


def cluster_centroid(cluster: list[int], stops: list[ResolvedStop]) -> tuple[float, float]:
    latitude = sum(stops[index].latitude for index in cluster) / len(cluster)
    longitude = sum(stops[index].longitude for index in cluster) / len(cluster)
    return latitude, longitude


def order_cluster(cluster: list[int], matrix: list[list[MatrixCell]]) -> list[int]:
    if len(cluster) <= 2:
        return list(cluster)

    best_order: list[int] | None = None
    best_cost = float("inf")
    for start in cluster:
        order = nearest_neighbor_path(cluster, matrix, start_index=start)
        improved = two_opt_open_path(order, matrix)
        cost = path_cost(improved, matrix)
        if cost < best_cost:
            best_cost = cost
            best_order = improved

    return best_order or list(cluster)


def nearest_neighbor_path(
    cluster: list[int],
    matrix: list[list[MatrixCell]],
    *,
    start_index: int,
) -> list[int]:
    unvisited = set(cluster)
    unvisited.remove(start_index)
    path = [start_index]

    while unvisited:
        current = path[-1]
        next_stop = min(
            unvisited,
            key=lambda candidate: _edge_cost(current, candidate, matrix),
        )
        path.append(next_stop)
        unvisited.remove(next_stop)

    return path


def two_opt_open_path(order: list[int], matrix: list[list[MatrixCell]]) -> list[int]:
    best = list(order)
    improved = True
    while improved:
        improved = False
        for i in range(1, len(best) - 2):
            for j in range(i + 1, len(best) - 1):
                candidate = best[:i] + list(reversed(best[i : j + 1])) + best[j + 1 :]
                if path_cost(candidate, matrix) + 1e-9 < path_cost(best, matrix):
                    best = candidate
                    improved = True
        if len(best) < 4:
            break
    return best


def path_cost(order: list[int], matrix: list[list[MatrixCell]]) -> float:
    return sum(_edge_cost(order[i], order[i + 1], matrix) for i in range(len(order) - 1))


def total_path_minutes(order: list[int], matrix: list[list[MatrixCell]]) -> int:
    return math.ceil(path_cost(order, matrix) / 60) if len(order) > 1 else 0


def _edge_cost(origin: int, destination: int, matrix: list[list[MatrixCell]]) -> float:
    duration = matrix[origin][destination].duration_seconds
    return duration if math.isfinite(duration) else 10**9


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
