"""Sanity bounds for ingested numeric values."""
from __future__ import annotations

# Plausible upper bounds — values above these are clipped to None.
_BOUNDS = {
    "pm25": (0.0, 1500.0),
    "pm10": (0.0, 3000.0),
    "no2":  (0.0, 1000.0),
    "so2":  (0.0, 1000.0),
    "o3":   (0.0, 1000.0),
    "co":   (0.0, 100.0),
    "aqi":  (0.0, 1000.0),
    "temperature_2m":       (-60.0, 60.0),
    "relative_humidity_2m": (0.0, 100.0),
    "wind_speed_10m":       (0.0, 100.0),
    "wind_direction_10m":   (0.0, 360.0),
    "precipitation":        (0.0, 500.0),
    "surface_pressure":     (800.0, 1100.0),
    "boundary_layer_height": (0.0, 5000.0),
}


def clip(field: str, value: float | None) -> float | None:
    if value is None:
        return None
    bounds = _BOUNDS.get(field)
    if bounds is None:
        return value
    lo, hi = bounds
    if value < lo or value > hi:
        return None
    return value
