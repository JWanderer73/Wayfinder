from __future__ import annotations

import math
from dataclasses import dataclass

from .duration import DurationEstimator
from .google_maps import GoogleMapsClient
from .models import (
    DayPlan,
    ItineraryPlan,
    MatrixCell,
    ResolvedStop,
    ScheduledVisit,
    StopInput,
    TripRequest,
    format_clock_time,
)


@dataclass(slots=True)
class SpatialPlanner:
    client: GoogleMapsClient
    duration_estimator: DurationEstimator | None = None

    def build_plan(self, trip: TripRequest) -> ItineraryPlan:
        if not trip.stops:
            return ItineraryPlan(
                destination=trip.destination,
                num_days=max(1, trip.inferred_num_days()),
                resolved_stops=[],
                days=[],
                daily_minutes_budget=trip.daily_minutes_budget,
            )

        active_stop_inputs, removed_stops = filter_active_stops(
            trip.stops,
            excluded_stop_names=trip.excluded_stop_names,
        )
        if not active_stop_inputs:
            return ItineraryPlan(
                destination=trip.destination,
                num_days=max(1, trip.inferred_num_days()),
                resolved_stops=[],
                days=[],
                daily_minutes_budget=trip.daily_minutes_budget,
                removed_stops=removed_stops,
                planning_notes=["All candidate activities were excluded or disabled."],
            )

        duration_estimator = self.duration_estimator or DurationEstimator()
        active_stop_inputs, duration_notes = duration_estimator.apply(
            active_stop_inputs,
            destination=trip.destination,
        )

        resolved_stops = [
            self.client.resolve_stop(
                stop,
                destination_hint=trip.destination,
                region_code=trip.region_code,
            )
            for stop in active_stop_inputs
        ]
        anchor_location = (
            self.client.resolve_stop(
                trip.anchor_location,
                destination_hint=trip.destination,
                region_code=trip.region_code,
            )
            if trip.anchor_location
            else None
        )

        num_days = max(1, min(len(resolved_stops), trip.inferred_num_days()))
        if num_days == 1 and resolved_stops:
            estimated_days = estimate_days_from_budget(
                resolved_stops,
                daily_minutes_budget=trip.daily_minutes_budget,
            )
            num_days = max(1, estimated_days)

        day_clusters = cluster_stops_by_day(
            resolved_stops,
            num_days=num_days,
            daily_minutes_budget=trip.daily_minutes_budget,
            max_stops_per_day=trip.max_stops_per_day,
        )

        day_start_minute = trip.day_start_minute()
        days: list[DayPlan] = []
        total_route_matrix_elements = 0
        for day_number, cluster in enumerate(day_clusters, start=1):
            day_stops = [resolved_stops[index] for index in cluster]
            matrix_nodes = list(day_stops)
            anchor_index: int | None = None
            if anchor_location is not None:
                anchor_index = len(matrix_nodes)
                matrix_nodes.append(anchor_location)

            day_matrix = self.client.compute_route_matrix(
                matrix_nodes,
                travel_mode=trip.travel_mode,
            )
            total_route_matrix_elements += len(matrix_nodes) * len(matrix_nodes)

            ordered_indices = order_day_cluster(
                day_stops,
                day_matrix,
                day_start_minute=day_start_minute,
                start_anchor_index=anchor_index,
                end_anchor_index=anchor_index if trip.end_each_day_at_anchor else None,
            )
            day_plan = build_day_plan(
                day_number=day_number,
                day_stops=day_stops,
                order=ordered_indices,
                matrix=day_matrix,
                day_start_minute=day_start_minute,
                daily_minutes_budget=trip.daily_minutes_budget,
                start_anchor=anchor_location,
                start_anchor_index=anchor_index,
                end_anchor=anchor_location if trip.end_each_day_at_anchor else None,
                end_anchor_index=anchor_index if trip.end_each_day_at_anchor else None,
            )
            days.append(day_plan)

        planning_notes = list(duration_notes)
        planning_notes.append(
            "Route matrices are computed per day after filtering and clustering to reduce Google API cost."
        )
        planning_notes.append(
            f"Estimated route matrix usage for this plan: {total_route_matrix_elements} elements."
        )
        if trip.max_stops_per_day is not None:
            planning_notes.append(
                f"Soft max stops per day was set to {trip.max_stops_per_day}."
            )
        if anchor_location is not None:
            planning_notes.append(
                f"Using '{anchor_location.name}' as the daily anchor location."
            )

        return ItineraryPlan(
            destination=trip.destination,
            num_days=len(days),
            resolved_stops=resolved_stops,
            days=days,
            daily_minutes_budget=trip.daily_minutes_budget,
            removed_stops=removed_stops,
            planning_notes=planning_notes,
            anchor_location=anchor_location,
        )


def filter_active_stops(
    stops: list[StopInput],
    *,
    excluded_stop_names: list[str],
) -> tuple[list[StopInput], list[str]]:
    excluded = {name.casefold() for name in excluded_stop_names}
    active: list[StopInput] = []
    removed: list[str] = []
    for stop in stops:
        if not stop.enabled:
            removed.append(f"{stop.name} (disabled)")
            continue
        if stop.name.casefold() in excluded:
            removed.append(f"{stop.name} (excluded)")
            continue
        active.append(stop)
    return active, removed


def estimate_days_from_budget(
    stops: list[ResolvedStop],
    *,
    daily_minutes_budget: int,
) -> int:
    if not stops:
        return 1

    visit_minutes = sum(stop.visit_minutes for stop in stops)
    travel_minutes = 0
    for index, stop in enumerate(stops):
        nearest_minutes = min(
            (
                approx_travel_minutes(stop, stops[other_index])
                for other_index in range(len(stops))
                if other_index != index
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
    max_stops_per_day: int | None,
) -> list[list[int]]:
    if not stops:
        return []

    num_days = max(1, min(num_days, len(stops)))
    target_items_per_day = max_stops_per_day or math.ceil(len(stops) / num_days)
    clusters: list[list[int]] = [[] for _ in range(num_days)]
    cluster_minutes = [0 for _ in range(num_days)]
    cluster_items = [0 for _ in range(num_days)]
    assigned: set[int] = set()

    for index, stop in enumerate(stops):
        if stop.fixed_day is None:
            continue
        day_index = min(num_days, max(1, stop.fixed_day)) - 1
        clusters[day_index].append(index)
        cluster_minutes[day_index] += stop.visit_minutes
        cluster_items[day_index] += 1
        assigned.add(index)

    empty_days = [day_index for day_index, cluster in enumerate(clusters) if not cluster]
    if empty_days:
        seeds = farthest_first_seeds(
            stops,
            count=min(len(empty_days), len(stops) - len(assigned)),
            disallowed=assigned,
        )
        for day_index, seed_index in zip(empty_days, seeds):
            clusters[day_index].append(seed_index)
            cluster_minutes[day_index] += stops[seed_index].visit_minutes
            cluster_items[day_index] += 1
            assigned.add(seed_index)

    remaining = [
        index
        for index in sorted(
            range(len(stops)),
            key=lambda idx: (
                not stops[idx].required,
                -stops[idx].priority,
                -stops[idx].visit_minutes,
            ),
        )
        if index not in assigned
    ]

    for index in remaining:
        best_cluster = None
        best_score = float("inf")
        for cluster_index, cluster in enumerate(clusters):
            if not cluster:
                centroid_lat = stops[index].latitude
                centroid_lng = stops[index].longitude
            else:
                centroid_lat, centroid_lng = cluster_centroid(cluster, stops)

            geo_distance = haversine_meters(
                stops[index].latitude,
                stops[index].longitude,
                centroid_lat,
                centroid_lng,
            )
            minute_overflow = max(
                0,
                cluster_minutes[cluster_index] + stops[index].visit_minutes - daily_minutes_budget,
            )
            item_overflow = max(0, cluster_items[cluster_index] + 1 - target_items_per_day)
            score = geo_distance + minute_overflow * 250 + item_overflow * 4_000
            if score < best_score:
                best_score = score
                best_cluster = cluster_index

        assert best_cluster is not None
        clusters[best_cluster].append(index)
        cluster_minutes[best_cluster] += stops[index].visit_minutes
        cluster_items[best_cluster] += 1

    return [sorted(cluster) for cluster in clusters if cluster]


def farthest_first_seeds(
    stops: list[ResolvedStop],
    count: int,
    *,
    disallowed: set[int] | None = None,
) -> list[int]:
    disallowed = disallowed or set()
    candidates = [index for index in range(len(stops)) if index not in disallowed]
    if not candidates or count <= 0:
        return []

    average_lat = sum(stops[index].latitude for index in candidates) / len(candidates)
    average_lng = sum(stops[index].longitude for index in candidates) / len(candidates)
    first_seed = max(
        candidates,
        key=lambda idx: haversine_meters(
            stops[idx].latitude,
            stops[idx].longitude,
            average_lat,
            average_lng,
        ),
    )
    seeds = [first_seed]

    while len(seeds) < count and len(seeds) < len(candidates):
        next_seed = max(
            (idx for idx in candidates if idx not in seeds),
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


def order_day_cluster(
    day_stops: list[ResolvedStop],
    matrix: list[list[MatrixCell]],
    *,
    day_start_minute: int,
    start_anchor_index: int | None,
    end_anchor_index: int | None,
) -> list[int]:
    cluster = list(range(len(day_stops)))
    anchored = sorted(
        [index for index, stop in enumerate(day_stops) if stop.has_time_anchor()],
        key=lambda idx: (
            day_stops[idx].preferred_start_minute
            if day_stops[idx].preferred_start_minute is not None
            else day_stops[idx].time_window_start_minute
            if day_stops[idx].time_window_start_minute is not None
            else 24 * 60
        ),
    )
    if not anchored:
        return order_cluster(
            cluster,
            matrix,
            start_node=start_anchor_index,
            end_node=end_anchor_index,
        )

    remaining = {index for index in cluster if index not in anchored}
    ordered: list[int] = []
    current_node = start_anchor_index
    current_time = day_start_minute

    for anchor_index in anchored:
        anchor_stop = day_stops[anchor_index]
        target_time = (
            anchor_stop.preferred_start_minute
            if anchor_stop.preferred_start_minute is not None
            else anchor_stop.time_window_start_minute
        )
        if target_time is not None:
            segment = build_segment_before_anchor(
                remaining=remaining,
                current_node=current_node,
                current_time=current_time,
                anchor_index=anchor_index,
                deadline=target_time,
                day_stops=day_stops,
                matrix=matrix,
            )
            for stop_index in segment:
                ordered.append(stop_index)
                remaining.remove(stop_index)
                current_time = projected_departure_time(
                    current_node=current_node,
                    next_index=stop_index,
                    current_time=current_time,
                    day_stops=day_stops,
                    matrix=matrix,
                )
                current_node = stop_index

        ordered.append(anchor_index)
        current_time = projected_departure_time(
            current_node=current_node,
            next_index=anchor_index,
            current_time=current_time,
            day_stops=day_stops,
            matrix=matrix,
        )
        current_node = anchor_index

    if remaining:
        tail_order = order_cluster(
            list(remaining),
            matrix,
            start_node=current_node,
            end_node=end_anchor_index,
        )
        ordered.extend(tail_order)

    return ordered


def build_segment_before_anchor(
    *,
    remaining: set[int],
    current_node: int | None,
    current_time: int,
    anchor_index: int,
    deadline: int,
    day_stops: list[ResolvedStop],
    matrix: list[list[MatrixCell]],
) -> list[int]:
    segment: list[int] = []
    simulated_remaining = set(remaining)
    simulated_node = current_node
    simulated_time = current_time

    while simulated_remaining:
        feasible_candidates: list[tuple[float, int, int]] = []
        for candidate in simulated_remaining:
            departure_after_candidate = projected_departure_time(
                current_node=simulated_node,
                next_index=candidate,
                current_time=simulated_time,
                day_stops=day_stops,
                matrix=matrix,
            )
            arrival_at_anchor = departure_after_candidate + edge_minutes(
                candidate,
                anchor_index,
                matrix,
            )
            if arrival_at_anchor <= deadline:
                detour_cost = edge_seconds(simulated_node, candidate, matrix)
                feasible_candidates.append((detour_cost, candidate, departure_after_candidate))

        if not feasible_candidates:
            break

        feasible_candidates.sort(key=lambda item: item[0])
        _, chosen, departure_after_chosen = feasible_candidates[0]
        segment.append(chosen)
        simulated_remaining.remove(chosen)
        simulated_node = chosen
        simulated_time = departure_after_chosen

    return segment


def projected_departure_time(
    *,
    current_node: int | None,
    next_index: int,
    current_time: int,
    day_stops: list[ResolvedStop],
    matrix: list[list[MatrixCell]],
) -> int:
    stop = day_stops[next_index]
    travel_minutes = edge_minutes(current_node, next_index, matrix)
    arrival_time = current_time + travel_minutes
    wait_minutes = 0
    if stop.preferred_start_minute is not None and arrival_time < stop.preferred_start_minute:
        wait_minutes = stop.preferred_start_minute - arrival_time
    elif stop.time_window_start_minute is not None and arrival_time < stop.time_window_start_minute:
        wait_minutes = stop.time_window_start_minute - arrival_time
    start_time = arrival_time + wait_minutes
    return start_time + stop.visit_minutes


def order_cluster(
    cluster: list[int],
    matrix: list[list[MatrixCell]],
    *,
    start_node: int | None = None,
    end_node: int | None = None,
) -> list[int]:
    if len(cluster) <= 1:
        return list(cluster)

    best_order: list[int] | None = None
    best_cost = float("inf")
    for start in cluster:
        order = nearest_neighbor_path(cluster, matrix, start_index=start)
        improved = two_opt_open_path(order, matrix, start_node=start_node, end_node=end_node)
        cost = route_objective(improved, matrix, start_node=start_node, end_node=end_node)
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
        next_stop = min(unvisited, key=lambda candidate: edge_seconds(current, candidate, matrix))
        path.append(next_stop)
        unvisited.remove(next_stop)

    return path


def two_opt_open_path(
    order: list[int],
    matrix: list[list[MatrixCell]],
    *,
    start_node: int | None,
    end_node: int | None,
) -> list[int]:
    best = list(order)
    improved = True
    while improved:
        improved = False
        for i in range(1, len(best) - 2):
            for j in range(i + 1, len(best) - 1):
                candidate = best[:i] + list(reversed(best[i : j + 1])) + best[j + 1 :]
                if route_objective(
                    candidate,
                    matrix,
                    start_node=start_node,
                    end_node=end_node,
                ) + 1e-9 < route_objective(
                    best,
                    matrix,
                    start_node=start_node,
                    end_node=end_node,
                ):
                    best = candidate
                    improved = True
        if len(best) < 4:
            break
    return best


def route_objective(
    order: list[int],
    matrix: list[list[MatrixCell]],
    *,
    start_node: int | None,
    end_node: int | None,
) -> float:
    total = path_cost(order, matrix)
    if order and start_node is not None:
        total += edge_seconds(start_node, order[0], matrix)
    if order and end_node is not None:
        total += edge_seconds(order[-1], end_node, matrix)
    return total


def build_day_plan(
    *,
    day_number: int,
    day_stops: list[ResolvedStop],
    order: list[int],
    matrix: list[list[MatrixCell]],
    day_start_minute: int,
    daily_minutes_budget: int,
    start_anchor: ResolvedStop | None,
    start_anchor_index: int | None,
    end_anchor: ResolvedStop | None,
    end_anchor_index: int | None,
) -> DayPlan:
    scheduled_visits: list[ScheduledVisit] = []
    current_time = day_start_minute
    current_node = start_anchor_index
    total_travel_minutes = 0
    total_wait_minutes = 0
    total_visit_minutes = 0

    for local_index in order:
        stop = day_stops[local_index]
        travel_minutes = edge_minutes(current_node, local_index, matrix)
        arrival_time = current_time + travel_minutes
        wait_minutes = 0
        if stop.preferred_start_minute is not None and arrival_time < stop.preferred_start_minute:
            wait_minutes = stop.preferred_start_minute - arrival_time
        elif stop.time_window_start_minute is not None and arrival_time < stop.time_window_start_minute:
            wait_minutes = stop.time_window_start_minute - arrival_time

        start_time = arrival_time + wait_minutes
        departure_time = start_time + stop.visit_minutes

        warnings: list[str] = []
        if (
            stop.preferred_start_minute is not None
            and start_time > stop.preferred_start_minute + 15
        ):
            warnings.append(
                f"Misses the preferred start time by {start_time - stop.preferred_start_minute} minutes."
            )
        if wait_minutes >= 45:
            warnings.append(
                f"Long wait before this stop: {wait_minutes} minutes. Consider adding another nearby activity first."
            )
        if stop.time_window_end_minute is not None and departure_time > stop.time_window_end_minute:
            warnings.append(
                f"Runs past the requested end window by {departure_time - stop.time_window_end_minute} minutes."
            )
        if stop.visit_minutes >= 180:
            warnings.append("Time-intensive activity. Consider giving it a dedicated day segment.")

        scheduled_visits.append(
            ScheduledVisit(
                stop=stop,
                arrival_time=format_clock_time(arrival_time) or "00:00",
                start_time=format_clock_time(start_time) or "00:00",
                departure_time=format_clock_time(departure_time) or "00:00",
                travel_minutes_from_previous=travel_minutes,
                wait_minutes=wait_minutes,
                warnings=warnings,
            )
        )

        total_travel_minutes += travel_minutes
        total_wait_minutes += wait_minutes
        total_visit_minutes += stop.visit_minutes
        current_time = departure_time
        current_node = local_index

    return_to_anchor_minutes = 0
    if order and end_anchor_index is not None:
        return_to_anchor_minutes = edge_minutes(order[-1], end_anchor_index, matrix)
        total_travel_minutes += return_to_anchor_minutes
        current_time += return_to_anchor_minutes

    apply_detour_warnings(
        scheduled_visits,
        order=order,
        matrix=matrix,
        start_anchor_index=start_anchor_index,
        end_anchor_index=end_anchor_index,
    )

    warnings: list[str] = []
    total_minutes = total_visit_minutes + total_travel_minutes + total_wait_minutes
    if total_minutes > daily_minutes_budget:
        warnings.append(
            f"Day is overloaded by {total_minutes - daily_minutes_budget} minutes."
        )
    if return_to_anchor_minutes >= 45:
        warnings.append(
            f"Returning to the anchor adds {return_to_anchor_minutes} minutes."
        )

    ordered_stop_ids = [day_stops[index].id for index in order]
    matrix_stop_order = [stop.name for stop in day_stops]
    if start_anchor is not None:
        matrix_stop_order.append(start_anchor.name)

    return DayPlan(
        day_number=day_number,
        scheduled_visits=scheduled_visits,
        total_visit_minutes=total_visit_minutes,
        total_travel_minutes=total_travel_minutes,
        total_wait_minutes=total_wait_minutes,
        total_minutes=total_minutes,
        warnings=warnings,
        ordered_stop_ids=ordered_stop_ids,
        matrix_stop_order=matrix_stop_order,
        route_matrix=matrix,
        start_anchor=start_anchor,
        end_anchor=end_anchor,
        return_to_anchor_minutes=return_to_anchor_minutes,
    )


def apply_detour_warnings(
    scheduled_visits: list[ScheduledVisit],
    *,
    order: list[int],
    matrix: list[list[MatrixCell]],
    start_anchor_index: int | None,
    end_anchor_index: int | None,
) -> None:
    for position, visit in enumerate(scheduled_visits):
        current = order[position]
        previous_node = start_anchor_index if position == 0 else order[position - 1]
        next_node = (
            end_anchor_index
            if position == len(order) - 1
            else order[position + 1]
        )

        if previous_node is not None and next_node is not None:
            detour_seconds = (
                edge_seconds(previous_node, current, matrix)
                + edge_seconds(current, next_node, matrix)
                - edge_seconds(previous_node, next_node, matrix)
            )
        elif previous_node is not None:
            detour_seconds = edge_seconds(previous_node, current, matrix)
        elif next_node is not None:
            detour_seconds = edge_seconds(current, next_node, matrix)
        else:
            detour_seconds = 0

        detour_minutes = math.ceil(detour_seconds / 60) if detour_seconds > 0 else 0
        if detour_minutes >= 45:
            visit.warnings.append(
                f"Out-of-the-way stop: adds about {detour_minutes} minutes of detour."
            )


def path_cost(order: list[int], matrix: list[list[MatrixCell]]) -> float:
    return sum(edge_seconds(order[i], order[i + 1], matrix) for i in range(len(order) - 1))


def edge_seconds(origin: int | None, destination: int | None, matrix: list[list[MatrixCell]]) -> float:
    if origin is None or destination is None:
        return 0.0
    duration = matrix[origin][destination].duration_seconds
    return duration if math.isfinite(duration) else 10**9


def edge_minutes(origin: int | None, destination: int | None, matrix: list[list[MatrixCell]]) -> int:
    return math.ceil(edge_seconds(origin, destination, matrix) / 60)


def approx_travel_minutes(origin: ResolvedStop, destination: ResolvedStop) -> int:
    distance_km = haversine_meters(
        origin.latitude,
        origin.longitude,
        destination.latitude,
        destination.longitude,
    ) / 1_000
    # A simple city-scale heuristic that avoids API calls before clustering.
    return max(5, math.ceil((distance_km / 25) * 60))


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
