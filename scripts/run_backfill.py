"""Run the one-time historical AQI + weather backfill."""
from __future__ import annotations

import argparse
import asyncio

from airqualitycast.backfill.historical_loader import backfill
from airqualitycast.config import configure_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="AirQualityCast historical backfill")
    parser.add_argument("--years", type=float, default=1.0, help="Years of history to load")
    parser.add_argument("--min-stations", type=int, default=50, help="Minimum stations to backfill")
    args = parser.parse_args()

    configure_logging()
    asyncio.run(backfill(years=args.years, min_stations=args.min_stations))


if __name__ == "__main__":
    main()
