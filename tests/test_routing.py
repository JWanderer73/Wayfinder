from __future__ import annotations

import unittest

from wayfinder.google_maps import GoogleMapsClient
from wayfinder.models import ResolvedStop, TripRequest
from wayfinder.routing import (
    build_distance_matrix,
    choose_transport_mode,
    standardize_transport_mode,
    travel_buffer_minutes,
)
from wayfinder.spatial import SpatialPlanner, estimate_days_from_budget
from wayfinder.spatial import cluster_stops_by_day, filter_active_stops
from wayfinder.models import StopInput


def stop(
    name: str,
    latitude: float,
    longitude: float,
    *,
    visit_minutes: int = 60,
) -> ResolvedStop:
    return ResolvedStop(
        id=name.lower().replace(" ", "-"),
        name=name,
        latitude=latitude,
        longitude=longitude,
        visit_minutes=visit_minutes,
        visit_minutes_source="test",
    )


class RoutingTest(unittest.TestCase):
    def test_standardizes_common_transport_names(self) -> None:
        self.assertEqual(standardize_transport_mode("by foot"), "walk")
        self.assertEqual(standardize_transport_mode("public transport"), "transit")
        self.assertEqual(standardize_transport_mode("driving"), "drive")
        self.assertEqual(standardize_transport_mode("unknown"), "auto")

    def test_auto_mode_uses_walk_for_close_stops(self) -> None:
        self.assertEqual(choose_transport_mode(400, "auto"), "walk")
        self.assertEqual(choose_transport_mode(3_000, "auto"), "transit")
        self.assertEqual(choose_transport_mode(20_000, "auto"), "drive")

    def test_distance_matrix_is_local_and_symmetric_enough_for_planning(self) -> None:
        stops = [
            stop("A", 40.0, -74.0),
            stop("B", 40.005, -74.0),
        ]
        matrix = build_distance_matrix(stops, requested_mode="auto")

        self.assertEqual(len(matrix), 2)
        self.assertEqual(matrix[0][0].distance_meters, 0)
        self.assertGreater(matrix[0][1].distance_meters, 500)
        self.assertEqual(matrix[0][1].transport_mode, "walk")
        self.assertEqual(matrix[0][1].condition, "ROUTE_EXISTS")

    def test_travel_buffer_has_minimum_for_nonzero_travel(self) -> None:
        self.assertEqual(travel_buffer_minutes(0, buffer_ratio=0.15, minimum_buffer_minutes=5), 0)
        self.assertEqual(travel_buffer_minutes(10, buffer_ratio=0.15, minimum_buffer_minutes=5), 5)
        self.assertEqual(travel_buffer_minutes(100, buffer_ratio=0.15, minimum_buffer_minutes=5), 15)

    def test_meal_and_redundancy_buffers_increase_day_estimate(self) -> None:
        stops = [
            stop("A", 40.0, -74.0, visit_minutes=180),
            stop("B", 40.01, -74.0, visit_minutes=180),
        ]

        without_buffers = estimate_days_from_budget(stops, daily_minutes_budget=480)
        with_buffers = estimate_days_from_budget(
            stops,
            daily_minutes_budget=480,
            lunch_minutes=60,
            dinner_minutes=120,
            daily_redundancy_minutes=45,
        )

        self.assertEqual(without_buffers, 1)
        self.assertEqual(with_buffers, 2)

    def test_planner_with_coordinates_does_not_require_google_key(self) -> None:
        trip = TripRequest.from_dict(
            {
                "destination": "Test City",
                "num_days": 1,
                "daily_minutes_budget": 480,
                "transport_mode": "auto",
                "lunch_minutes": 60,
                "dinner_minutes": 120,
                "daily_redundancy_minutes": 45,
                "anchor_location": {
                    "name": "Hotel",
                    "latitude": 40.0,
                    "longitude": -74.0,
                    "anchor_kind": "hotel",
                },
                "stops": [
                    {
                        "name": "Nearby Cafe",
                        "latitude": 40.001,
                        "longitude": -74.0,
                        "visit_minutes": 45,
                        "category": "food",
                    },
                    {
                        "name": "Museum",
                        "latitude": 40.02,
                        "longitude": -74.0,
                        "visit_minutes": 120,
                        "category": "museum",
                    },
                ],
            }
        )

        plan = SpatialPlanner(GoogleMapsClient(api_key=None)).build_plan(trip)

        self.assertEqual(plan.matrix_scope, "local_distance_per_day")
        self.assertEqual(plan.days[0].lunch_minutes, 60)
        self.assertEqual(plan.days[0].dinner_minutes, 120)
        self.assertEqual(plan.days[0].redundancy_minutes, 45)
        self.assertGreater(plan.days[0].total_travel_buffer_minutes, 0)
        self.assertIn("latitude/longitude", " ".join(plan.planning_notes))

    def test_category_preferences_filter_optional_stops(self) -> None:
        active, removed = filter_active_stops(
            [
                StopInput(name="Museum", category="museum", required=True),
                StopInput(name="Mall", category="shopping"),
                StopInput(name="Park", category="park"),
            ],
            excluded_stop_names=[],
            preferred_categories=["museum", "park"],
            excluded_categories=[],
        )

        self.assertEqual([stop.name for stop in active], ["Museum", "Park"])
        self.assertEqual(removed, ["Mall (outside preferred categories)"])

    def test_best_point_clustering_keeps_nearby_stops_together(self) -> None:
        stops = [
            stop("North Museum", 40.0, -74.0, visit_minutes=60),
            stop("North Park", 40.001, -74.0, visit_minutes=60),
            stop("South Museum", 41.0, -74.0, visit_minutes=60),
            stop("South Park", 41.001, -74.0, visit_minutes=60),
        ]

        clusters = cluster_stops_by_day(
            stops,
            num_days=2,
            daily_minutes_budget=300,
            max_stops_per_day=2,
            method="best_point",
        )

        cluster_sets = {frozenset(cluster) for cluster in clusters}
        self.assertEqual(cluster_sets, {frozenset({0, 1}), frozenset({2, 3})})


if __name__ == "__main__":
    unittest.main()
