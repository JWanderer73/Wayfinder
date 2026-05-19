"""
Google Route Optimization API - Python Client
Docs: https://developers.google.com/maps/documentation/route-optimization
"""

import json
import requests
from datetime import datetime, timezone


API_KEY = "AIzaSyAaDKEi5MvuhU7ZwyNtxcqeRxD0SwLl2vc"
ENDPOINT = "https://routeoptimization.googleapis.com/v1/projects/wayfindertrial:optimizeTours"

# ── Helpers ────────────────────────────────────────────────────────────────────

def make_timestamp(dt: datetime) -> str:
    """Convert a datetime to RFC3339 UTC string expected by the API."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_request_body() -> dict:
    """
    Build a sample OptimizeTours request.

    Scenario: 1 vehicle starting/ending at a depot, visiting 3 shipment stops.
    Customize shipments, vehicles, and time windows for your use case.
    """
    return {
        "model": {
            # ── Global time window ──────────────────────────────────────────
            "globalStartTime": make_timestamp(datetime(2025, 6, 1, 8, 0)),
            "globalEndTime":   make_timestamp(datetime(2025, 6, 1, 18, 0)),

            # ── Shipments (deliveries / pickups) ────────────────────────────
            "shipments": [
                {
                    "deliveries": [{
                        "arrivalLocation": {"latitude": 37.7749, "longitude": -122.4194},
                        "duration": "300s",   # 5 min service time
                        "timeWindows": [{
                            "startTime": make_timestamp(datetime(2025, 6, 1, 9, 0)),
                            "endTime":   make_timestamp(datetime(2025, 6, 1, 12, 0)),
                        }],
                    }],
                    "label": "Stop A - San Francisco",
                },
                {
                    "deliveries": [{
                        "arrivalLocation": {"latitude": 37.3382, "longitude": -121.8863},
                        "duration": "600s",   # 10 min service time
                        "timeWindows": [{
                            "startTime": make_timestamp(datetime(2025, 6, 1, 10, 0)),
                            "endTime":   make_timestamp(datetime(2025, 6, 1, 14, 0)),
                        }],
                    }],
                    "label": "Stop B - San Jose",
                },
                {
                    "deliveries": [{
                        "arrivalLocation": {"latitude": 37.5630, "longitude": -122.0530},
                        "duration": "450s",   # 7.5 min service time
                    }],
                    "label": "Stop C - Fremont (no time window)",
                },
            ],

            # ── Vehicles ────────────────────────────────────────────────────
            "vehicles": [
                {
                    "startLocation": {"latitude": 37.6879, "longitude": -122.4702},  # SFO depot
                    "endLocation":   {"latitude": 37.6879, "longitude": -122.4702},
                    "startTimeWindows": [{
                        "startTime": make_timestamp(datetime(2025, 6, 1, 8, 0)),
                        "endTime":   make_timestamp(datetime(2025, 6, 1, 9, 0)),
                    }],
                    "travelDurationMultiple": 1.0,   # 1.0 = normal speed
                    "label": "Vehicle 1",
                }
            ],
        },

        # Ask the API to populate route polylines in the response
        "populatePolylines": False,
        "considerRoadTraffic": False,
    }


# ── API call ───────────────────────────────────────────────────────────────────

def optimize_tours(project_id: str, api_key: str = API_KEY) -> dict:
    """
    Call the Route Optimization API and return the parsed JSON response.

    Args:
        project_id: Your Google Cloud project ID (e.g. "my-gcp-project").
        api_key:    API key with Route Optimization API enabled.

    Returns:
        Parsed response dict with optimized routes.
    """
    url = ENDPOINT.format(project_id=project_id)
    headers = {"Content-Type": "application/json", "X-Goog-Api-Key": api_key}
    payload = build_request_body()

    print(f"Sending request to: {url}\n")
    response = requests.post(url, headers=headers, json=payload, timeout=30)

    if not response.ok:
        print(f"Error {response.status_code}: {response.text}")
        response.raise_for_status()

    return response.json()


# ── Response parsing ───────────────────────────────────────────────────────────

def print_routes(result: dict) -> None:
    """Pretty-print the optimized routes from the API response."""
    routes = result.get("routes", [])
    if not routes:
        print("No routes returned. Check for skipped shipments below.")

    for i, route in enumerate(routes):
        vehicle_label = route.get("vehicleLabel", f"Vehicle {i}")
        print(f"\n{'='*50}")
        print(f"Route for: {vehicle_label}")
        print(f"{'='*50}")

        visits = route.get("visits", [])
        for j, visit in enumerate(visits):
            shipment_idx = visit.get("shipmentIndex", "?")
            start_time   = visit.get("startTime", "N/A")
            detour       = visit.get("detour", "N/A")
            print(f"  Stop {j+1}: Shipment #{shipment_idx}  |  Arrival: {start_time}  |  Detour: {detour}")

        metrics = route.get("metrics", {})
        print(f"\n  Total travel duration : {metrics.get('travelDuration', 'N/A')}")
        print(f"  Total visit duration  : {metrics.get('visitDuration', 'N/A')}")
        print(f"  Total route duration  : {metrics.get('totalDuration', 'N/A')}")

    # Skipped shipments
    skipped = result.get("skippedShipments", [])
    if skipped:
        print(f"\n⚠️  {len(skipped)} shipment(s) could not be scheduled:")
        for s in skipped:
            print(f"  - Index {s.get('index')}: {s.get('reasons', [])}")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # ✏️  Replace with your actual GCP project ID
    PROJECT_ID = "your-gcp-project-id"

    result = optimize_tours(project_id=PROJECT_ID, api_key=API_KEY)

    # Save full response to file
    with open("route_optimization_response.json", "w") as f:
        json.dump(result, f, indent=2)
    print("Full response saved to route_optimization_response.json\n")

    # Print summary
    print_routes(result)