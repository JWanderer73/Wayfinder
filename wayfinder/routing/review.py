from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from .models import DayPlan


class PlanningReviewError(RuntimeError):
    """Raised when the optional LLM planning review fails."""


@dataclass(slots=True)
class OpenAIPlanningReviewer:
    api_key: str
    model: str
    timeout_seconds: int = 30

    def review(self, *, destination: str, days: list[DayPlan]) -> list[str]:
        payload = {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "You review travel itinerary clusters. Return JSON only with "
                                "{\"notes\": [string]}. Focus on rushed days, awkward grouping, "
                                "and meal/travel slack. Keep notes concise."
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                {
                                    "destination": destination,
                                    "days": [compact_day(day) for day in days],
                                }
                            ),
                        }
                    ],
                },
            ],
            "text": {"format": {"type": "json_object"}},
        }

        response = self._request_json(payload)
        text = _extract_output_text(response)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PlanningReviewError(f"OpenAI returned non-JSON review output: {text}") from exc

        notes = data.get("notes", [])
        if not isinstance(notes, list):
            raise PlanningReviewError(f"OpenAI review output missing notes list: {data}")
        return [str(note) for note in notes if str(note).strip()]

    def _request_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url="https://api.openai.com/v1/responses",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            data=raw_data,
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise PlanningReviewError(
                f"OpenAI review request failed ({exc.code} {exc.reason}): {body}"
            ) from exc
        except error.URLError as exc:
            raise PlanningReviewError(f"OpenAI review request failed: {exc.reason}") from exc

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise PlanningReviewError(f"OpenAI returned invalid JSON: {body}") from exc


def compact_day(day: DayPlan) -> dict[str, Any]:
    return {
        "day_number": day.day_number,
        "total_minutes": day.total_minutes,
        "total_visit_minutes": day.total_visit_minutes,
        "total_travel_minutes": day.total_travel_minutes,
        "total_travel_buffer_minutes": day.total_travel_buffer_minutes,
        "lunch_minutes": day.lunch_minutes,
        "dinner_minutes": day.dinner_minutes,
        "redundancy_minutes": day.redundancy_minutes,
        "stops": [
            {
                "name": visit.stop.name,
                "visit_minutes": visit.stop.visit_minutes,
                "arrival_time": visit.arrival_time,
                "departure_time": visit.departure_time,
                "travel_minutes_from_previous": visit.travel_minutes_from_previous,
                "travel_buffer_minutes": visit.travel_buffer_minutes,
                "transport_mode_from_previous": visit.transport_mode_from_previous,
                "warnings": visit.warnings,
            }
            for visit in day.scheduled_visits
        ],
        "warnings": day.warnings,
    }


def _extract_output_text(response: dict[str, Any]) -> str:
    output_text = response.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    chunks: list[str] = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                chunks.append(content["text"])
    if chunks:
        return "".join(chunks)

    raise PlanningReviewError(f"OpenAI response did not contain output text: {response}")
