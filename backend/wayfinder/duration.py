from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any
from urllib import error, request

from .models import StopInput


CATEGORY_DEFAULTS = {
    "museum": 150,
    "landmark": 75,
    "food": 75,
    "restaurant": 75,
    "viewpoint": 60,
    "park": 75,
    "shopping": 90,
    "beach": 150,
    "tour": 120,
    "nightlife": 120,
    "hike": 180,
    "market": 90,
}

KEYWORD_DEFAULTS = [
    ("museum", 150),
    ("gallery", 120),
    ("market", 90),
    ("park", 75),
    ("garden", 75),
    ("zoo", 180),
    ("aquarium", 150),
    ("cathedral", 60),
    ("church", 45),
    ("pizza", 60),
    ("restaurant", 75),
    ("deli", 60),
    ("cafe", 45),
    ("beach", 150),
    ("hike", 180),
    ("trail", 180),
    ("observation", 60),
    ("view", 60),
    ("tower", 75),
    ("plaza", 45),
]


class DurationEstimationError(RuntimeError):
    """Raised when duration estimation fails."""


@dataclass(slots=True)
class OpenAIDurationClient:
    api_key: str
    model: str
    timeout_seconds: int = 30

    def estimate_batch(
        self,
        stops: list[StopInput],
        *,
        destination: str,
    ) -> dict[str, dict[str, Any]]:
        prompt_lines = [
            f"Destination: {destination}",
            "Estimate how many minutes a typical traveler would spend at each stop.",
            "Return JSON only with the shape {\"estimates\": [{\"id\": string, \"visit_minutes\": integer, \"rationale\": string}]}",
            "Be realistic and conservative. Use whole-minute integers between 30 and 300.",
            "",
            "Stops:",
        ]
        for stop in stops:
            prompt_lines.append(
                json.dumps(
                    {
                        "id": stop.id,
                        "name": stop.name,
                        "category": stop.category,
                        "notes": stop.notes,
                        "required": stop.required,
                        "anchor_kind": stop.anchor_kind,
                    }
                )
            )

        payload = {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "You estimate visit durations for travel planning. "
                                "Always respond with JSON only."
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "\n".join(prompt_lines)}],
                },
            ],
            "text": {"format": {"type": "json_object"}},
        }

        response = self._request_json(payload)
        text = _extract_output_text(response)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise DurationEstimationError(
                f"OpenAI returned non-JSON duration output: {text}"
            ) from exc

        estimates = data.get("estimates")
        if not isinstance(estimates, list):
            raise DurationEstimationError(
                f"OpenAI duration output missing estimates list: {data}"
            )

        normalized: dict[str, dict[str, Any]] = {}
        for item in estimates:
            if not isinstance(item, dict):
                continue
            stop_id = str(item.get("id", "")).strip()
            if not stop_id:
                continue
            minutes = int(item.get("visit_minutes", 90))
            normalized[stop_id] = {
                "visit_minutes": max(30, min(300, minutes)),
                "rationale": str(item.get("rationale", "")).strip(),
            }
        return normalized

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
            raise DurationEstimationError(
                f"OpenAI duration request failed ({exc.code} {exc.reason}): {body}"
            ) from exc
        except error.URLError as exc:
            raise DurationEstimationError(f"OpenAI duration request failed: {exc.reason}") from exc

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise DurationEstimationError(f"OpenAI returned invalid JSON: {body}") from exc


@dataclass(slots=True)
class DurationEstimator:
    use_llm: bool = False
    llm_client: OpenAIDurationClient | None = None

    def apply(
        self,
        stops: list[StopInput],
        *,
        destination: str,
    ) -> tuple[list[StopInput], list[str]]:
        notes: list[str] = []
        updated: list[StopInput] = []
        missing = [stop for stop in stops if not stop.visit_minutes or stop.visit_minutes <= 0]
        llm_estimates: dict[str, dict[str, Any]] = {}

        if missing and self.use_llm:
            if self.llm_client is None:
                notes.append(
                    "LLM duration estimation was requested, but no OpenAI client was configured. "
                    "Used heuristic duration defaults instead."
                )
            else:
                try:
                    llm_estimates = self.llm_client.estimate_batch(missing, destination=destination)
                    if llm_estimates:
                        notes.append(
                            f"Used OpenAI to estimate durations for {len(llm_estimates)} stop(s)."
                        )
                except DurationEstimationError as exc:
                    notes.append(
                        f"OpenAI duration estimation failed and heuristic defaults were used instead: {exc}"
                    )

        for stop in stops:
            if stop.visit_minutes and stop.visit_minutes > 0:
                updated.append(
                    replace(
                        stop,
                        visit_minutes=stop.visit_minutes,
                        visit_minutes_source=stop.visit_minutes_source or "user",
                    )
                )
                continue

            llm_estimate = llm_estimates.get(stop.id or "")
            if llm_estimate is not None:
                updated.append(
                    replace(
                        stop,
                        visit_minutes=int(llm_estimate["visit_minutes"]),
                        visit_minutes_source="llm",
                    )
                )
                continue

            heuristic_minutes = estimate_minutes_heuristic(stop)
            updated.append(
                replace(
                    stop,
                    visit_minutes=heuristic_minutes,
                    visit_minutes_source="heuristic",
                )
            )

        if missing and not llm_estimates:
            notes.append(
                "Applied category and keyword-based duration defaults for stops that were missing visit times."
            )

        return updated, notes


def estimate_minutes_heuristic(stop: StopInput) -> int:
    category = (stop.category or "").strip().lower()
    if category in CATEGORY_DEFAULTS:
        return CATEGORY_DEFAULTS[category]

    name = stop.name.lower()
    for keyword, minutes in KEYWORD_DEFAULTS:
        if keyword in name:
            return minutes

    return 90


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

    raise DurationEstimationError(f"OpenAI response did not contain output text: {response}")
