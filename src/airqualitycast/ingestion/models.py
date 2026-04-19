"""Pydantic v2 models for all external API responses."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AQIComponents(BaseModel):
    """Pollutant-specific readings nested in AQICN responses."""
    model_config = ConfigDict(extra="ignore")

    pm25: float | None = None
    pm10: float | None = None
    no2: float | None = None
    so2: float | None = None
    o3: float | None = None
    co: float | None = None


class StationFeed(BaseModel):
    """A single AQICN station feed reading."""
    model_config = ConfigDict(extra="ignore")

    station_uid: str
    station_name: str
    latitude: float
    longitude: float
    aqi: int | None = None
    dominant_pollutant: str | None = None
    measured_at: datetime
    components: AQIComponents = Field(default_factory=AQIComponents)
    raw_payload: dict = Field(default_factory=dict)


class StationSearchResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    uid: str
    station_name: str
    latitude: float
    longitude: float
    country: str | None = None


class WeatherReading(BaseModel):
    model_config = ConfigDict(extra="ignore")

    latitude: float
    longitude: float
    measured_at: datetime
    temperature_2m: float | None = None
    relative_humidity_2m: float | None = None
    wind_speed_10m: float | None = None
    wind_direction_10m: float | None = None
    precipitation: float | None = None
    surface_pressure: float | None = None
    boundary_layer_height: float | None = None
    is_forecast: bool = False


class FireDetection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    fire_id: str
    detected_at: datetime
    latitude: float
    longitude: float
    brightness: float | None = None
    frp: float | None = None
    confidence: str | None = None
    satellite: str | None = None
    daynight: str | None = None

    @field_validator("confidence", mode="before")
    @classmethod
    def _conf_to_str(cls, v: object) -> str | None:
        if v is None:
            return None
        return str(v)


class OpenAQLocation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    latitude: float
    longitude: float
    country: str | None = None
    city: str | None = None


class OpenAQMeasurement(BaseModel):
    model_config = ConfigDict(extra="ignore")

    location_id: int
    parameter: str
    value: float
    unit: str
    measured_at: datetime
