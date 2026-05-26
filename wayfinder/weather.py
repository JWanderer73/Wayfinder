"""
wayfinder/weather.py
─────────────────────
Lightweight weather summary for the destination + trip dates.

PURPOSE
  The Gemini ranker uses this string to down-weight outdoor activities in
  bad weather. We don't need pinpoint forecasts, just a sentence the LLM
  can reason over.

PROVIDER
  Open-Meteo — free, no API key. Falls back to a month-based climatology
  hint when dates are beyond the 16-day forecast horizon.
"""
from __future__ import annotations

import datetime as _dt
from typing import Optional

import requests

_GEO_URL      = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


_MONTH_HINTS: dict[int, str] = {
    1:  "winter — cold, short days",
    2:  "late winter — cold, occasional snow in many regions",
    3:  "early spring — mild and unpredictable",
    4:  "spring — mild, occasional rain",
    5:  "late spring — pleasant, warming",
    6:  "early summer — warm",
    7:  "summer — hot, humid in many regions",
    8:  "late summer — hot, peak rainfall in monsoon regions",
    9:  "early autumn — warm days, cool evenings",
    10: "autumn — mild, possible early storms",
    11: "late autumn — cool, shorter days",
    12: "winter — cold, possible snow",
}


def _geocode(city: str) -> tuple[float, float] | None:
    try:
        resp = requests.get(_GEO_URL, params={"name": city, "count": 1}, timeout=8)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return None
        return float(results[0]["latitude"]), float(results[0]["longitude"])
    except Exception:
        return None


def _parse_date(s: str) -> Optional[_dt.date]:
    try:
        return _dt.date.fromisoformat(s)
    except Exception:
        return None


def get_weather_summary(destination: str,
                        start_date: str = "",
                        end_date: str = "") -> str:
    """Build a short weather summary string for the trip. Returns '' on failure."""
    start = _parse_date(start_date) if start_date else None
    end   = _parse_date(end_date)   if end_date   else None

    if not start:
        return ""

    today = _dt.date.today()
    days_until = (start - today).days

    # beyond forecast horizon → climatology fallback
    if days_until > 14:
        hint = _MONTH_HINTS.get(start.month, "")
        if not hint:
            return ""
        return f"{destination}, {start.strftime('%B')}: {hint}."

    coords = _geocode(destination)
    if not coords:
        return (f"{destination}, {start.strftime('%B')}: "
                f"{_MONTH_HINTS.get(start.month, 'mixed conditions')}.")

    lat, lon = coords
    fcst_end = end or start

    try:
        resp = requests.get(_FORECAST_URL, params={
            "latitude":   lat,
            "longitude":  lon,
            "start_date": start.isoformat(),
            "end_date":   fcst_end.isoformat(),
            "daily":      "temperature_2m_max,temperature_2m_min,"
                          "precipitation_sum,precipitation_probability_max",
            "timezone":   "auto",
        }, timeout=10)
        resp.raise_for_status()
        daily = resp.json().get("daily", {})

        highs = daily.get("temperature_2m_max", [])
        lows  = daily.get("temperature_2m_min", [])
        precip_prob = daily.get("precipitation_probability_max", []) or \
                      daily.get("precipitation_sum", [])

        if not highs:
            raise ValueError("no daily data")

        avg_high = sum(highs) / len(highs)
        avg_low  = sum(lows)  / len(lows) if lows else avg_high
        rainy_days = sum(1 for p in precip_prob if p and p > 50)
        total_days = len(highs)

        bits = [
            f"{destination}, {start.strftime('%B %d').lstrip('0')}–"
            f"{fcst_end.strftime('%B %d').lstrip('0')}:",
            f"highs near {round(avg_high)}°C / {round(avg_high * 9/5 + 32)}°F,",
            f"lows near {round(avg_low)}°C.",
        ]
        if rainy_days:
            bits.append(f"Rain likely on {rainy_days} of {total_days} days.")
        return " ".join(bits)
    except Exception:
        return (f"{destination}, {start.strftime('%B')}: "
                f"{_MONTH_HINTS.get(start.month, 'mixed conditions')}.")