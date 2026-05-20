from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request

from .models import MatrixCell, ResolvedStop, StopInput


class GoogleMapsError(RuntimeError):
    """Raised when Google Maps APIs return an error."""


@dataclass(slots=True)
class GoogleMapsClient:
    api_key: str | None
    timeout_seconds: int = 20

    def resolve_stop(
        self,
        stop: StopInput,
        *,
        destination_hint: str | None = None,
        region_code: str | None = None,
    ) -> ResolvedStop:
        if stop.visit_minutes is None and stop.anchor_kind is not None:
            visit_minutes = 0
            visit_minutes_source = stop.visit_minutes_source or "anchor"
        else:
            visit_minutes = stop.visit_minutes if stop.visit_minutes is not None else 90
            visit_minutes_source = stop.visit_minutes_source or "heuristic"
        if stop.latitude is not None and stop.longitude is not None:
            return ResolvedStop.from_stop_input(
                stop,
                latitude=stop.latitude,
                longitude=stop.longitude,
                visit_minutes=visit_minutes,
                visit_minutes_source=visit_minutes_source,
                formatted_address=stop.address,
                source_query=stop.query_text(destination_hint),
            )

        geocode = self.geocode(stop.query_text(destination_hint), region_code=region_code)
        return ResolvedStop.from_stop_input(
            stop,
            latitude=geocode["latitude"],
            longitude=geocode["longitude"],
            visit_minutes=visit_minutes,
            visit_minutes_source=visit_minutes_source,
            formatted_address=geocode["formatted_address"],
            place_id=geocode.get("place_id"),
            source_query=geocode["query"],
        )

    def geocode(self, query: str, *, region_code: str | None = None) -> dict[str, Any]:
        if not self.api_key:
            raise GoogleMapsError(
                f"Cannot geocode '{query}' because GOOGLE_MAPS_API_KEY is not configured."
            )

        params = {"address": query, "key": self.api_key}
        if region_code:
            params["region"] = region_code

        response = self._request_json(
            method="GET",
            url=f"https://maps.googleapis.com/maps/api/geocode/json?{parse.urlencode(params)}",
        )
        status = response.get("status")
        if status != "OK":
            raise GoogleMapsError(
                f"Geocoding failed for '{query}' with status={status}: "
                f"{response.get('error_message', 'unknown error')}"
            )

        result = response["results"][0]
        location = result["geometry"]["location"]
        return {
            "query": query,
            "latitude": float(location["lat"]),
            "longitude": float(location["lng"]),
            "formatted_address": result.get("formatted_address"),
            "place_id": result.get("place_id"),
        }

    def compute_route_matrix(
        self,
        stops: list[ResolvedStop],
        *,
        travel_mode: str = "DRIVE",
    ) -> list[list[MatrixCell]]:
        if not stops:
            return []

        if len(stops) > 25:
            raise GoogleMapsError(
                "This starter uses a single square route matrix, so it supports up to 25 stops "
                "(25 x 25 = 625 route elements)."
            )

        payload = {
            "origins": [self._matrix_origin(stop) for stop in stops],
            "destinations": [self._matrix_destination(stop) for stop in stops],
            "travelMode": travel_mode,
        }
        response = self._request_json(
            method="POST",
            url="https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix",
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": (
                    "originIndex,destinationIndex,status,condition,distanceMeters,duration"
                ),
            },
            payload=payload,
        )

        size = len(stops)
        matrix = [
            [
                MatrixCell(
                    origin_index=i,
                    destination_index=j,
                    duration_seconds=0.0 if i == j else float("inf"),
                    distance_meters=0.0 if i == j else float("inf"),
                    condition="ROUTE_EXISTS" if i == j else "UNKNOWN",
                )
                for j in range(size)
            ]
            for i in range(size)
        ]

        for element in response:
            origin_index = element["originIndex"]
            destination_index = element["destinationIndex"]
            if origin_index == destination_index:
                matrix[origin_index][destination_index] = MatrixCell(
                    origin_index=origin_index,
                    destination_index=destination_index,
                    duration_seconds=0.0,
                    distance_meters=0.0,
                    condition="ROUTE_EXISTS",
                )
                continue

            condition = element.get("condition", "UNKNOWN")
            status = element.get("status", {})
            status_code = int(status.get("code", 0)) if status else 0
            if status_code != 0 or condition != "ROUTE_EXISTS":
                matrix[origin_index][destination_index] = MatrixCell(
                    origin_index=origin_index,
                    destination_index=destination_index,
                    duration_seconds=float("inf"),
                    distance_meters=float("inf"),
                    condition=condition,
                )
                continue

            matrix[origin_index][destination_index] = MatrixCell(
                origin_index=origin_index,
                destination_index=destination_index,
                duration_seconds=_parse_duration_seconds(element.get("duration", "0s")),
                distance_meters=float(element.get("distanceMeters", 0.0)),
                condition=condition,
            )

        return matrix

    def compute_route_summary(
        self,
        ordered_stops: list[ResolvedStop],
        *,
        travel_mode: str = "DRIVE",
    ) -> dict[str, Any]:
        if len(ordered_stops) < 2:
            return {"distance_meters": 0, "duration_seconds": 0}

        intermediates = [
            self._waypoint(stop)
            for stop in ordered_stops[1:-1]
        ]
        payload = {
            "origin": self._waypoint(ordered_stops[0]),
            "destination": self._waypoint(ordered_stops[-1]),
            "intermediates": intermediates,
            "travelMode": travel_mode,
        }
        response = self._request_json(
            method="POST",
            url="https://routes.googleapis.com/directions/v2:computeRoutes",
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": "routes.distanceMeters,routes.duration",
            },
            payload=payload,
        )
        routes = response.get("routes", [])
        if not routes:
            raise GoogleMapsError("Routes API returned no routes for the ordered day plan.")
        route = routes[0]
        return {
            "distance_meters": int(route.get("distanceMeters", 0)),
            "duration_seconds": int(_parse_duration_seconds(route.get("duration", "0s"))),
        }

    def _request_json(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        raw_data = None
        request_headers = headers or {}
        if payload is not None:
            raw_data = json.dumps(payload).encode("utf-8")

        req = request.Request(url=url, method=method, headers=request_headers, data=raw_data)
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise GoogleMapsError(
                f"Google Maps request failed ({exc.code} {exc.reason}): {body}"
            ) from exc
        except error.URLError as exc:
            raise GoogleMapsError(f"Google Maps request failed: {exc.reason}") from exc

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise GoogleMapsError(f"Google Maps returned invalid JSON: {body}") from exc

    @staticmethod
    def _matrix_origin(stop: ResolvedStop) -> dict[str, Any]:
        return {"waypoint": GoogleMapsClient._waypoint(stop)}

    @staticmethod
    def _matrix_destination(stop: ResolvedStop) -> dict[str, Any]:
        return {"waypoint": GoogleMapsClient._waypoint(stop)}

    @staticmethod
    def _waypoint(stop: ResolvedStop) -> dict[str, Any]:
        return {
            "location": {
                "latLng": {
                    "latitude": stop.latitude,
                    "longitude": stop.longitude,
                }
            }
        }


def _parse_duration_seconds(raw_duration: str) -> float:
    return float(raw_duration.removesuffix("s") or "0")
