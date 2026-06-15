from pydantic import BaseModel
from datetime import datetime

class AQIRecord(BaseModel):
    station_id: str
    timestamp: datetime
    pm25: float
    pm10: float
    aqi: int