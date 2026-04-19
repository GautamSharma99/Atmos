# Operations Runbook

## First-time setup
```bash
cp .env.example .env       # fill in API keys + a real fernet key
make setup                 # uv sync + pre-commit
make up                    # docker compose up -d
make bootstrap             # populate silver.stations from AQICN
make backfill              # ≥ 1 year of OpenAQ history for ≥ 50 stations
```
Airflow UI: http://localhost:8080  (creds from `.env`).

## Generate a fernet key
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Re-run a failed DAG
1. Open Airflow UI → DAG runs.
2. Locate the failed run → "Clear" → confirm. Airflow re-schedules with retries.
3. Inspect logs: `docker compose logs -f airflow-scheduler` or click into the task in the UI.

## Add a new station
- AQICN: append the city keyword to the list in `src/airqualitycast/backfill/historical_loader.py::bootstrap_aqicn_stations`, then `make bootstrap`.
- Manual one-off: insert directly into `silver.stations` (the geom trigger handles the rest).

## Backfill a single station
```bash
uv run python -c "
import asyncio
from datetime import datetime, timedelta, timezone
from airqualitycast.ingestion.openaq_client import OpenAQClient
from airqualitycast.config import get_settings
async def main():
    s = get_settings()
    async with OpenAQClient(s.openaq_api_key.get_secret_value()) as c:
        end = datetime.now(tz=timezone.utc); start = end - timedelta(days=365)
        ms = await c.get_measurements(LOCATION_ID, start, end)
        print(len(ms))
asyncio.run(main())
"
```

## Inspect data quality
```bash
make quality                      # writes docs/data_quality_report.json
docker compose exec timescaledb psql -U aq_user -d airquality -c \
  "SELECT * FROM silver.ingestion_runs ORDER BY started_at DESC LIMIT 20;"
```

## Reset everything (destructive — confirms first)
```bash
make down
docker volume rm atmos_timescale_data    # local dev only!
make up
```
