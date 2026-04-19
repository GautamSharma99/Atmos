"""Discover and register AQICN stations across major Indian cities."""
from __future__ import annotations

import asyncio

from airqualitycast.backfill.historical_loader import bootstrap_aqicn_stations
from airqualitycast.config import configure_logging, get_logger


def main() -> None:
    configure_logging()
    log = get_logger(__name__)
    n = asyncio.run(bootstrap_aqicn_stations())
    log.info("bootstrap.done", stations_registered=n)


if __name__ == "__main__":
    main()
