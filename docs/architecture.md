# Architecture

## High-level data flow

```mermaid
flowchart LR
    AQICN[AQICN<br/>live AQI] --> A1[ingest_aqi_hourly]
    OM[Open-Meteo<br/>weather] --> A2[ingest_weather_hourly]
    FIRMS[NASA FIRMS<br/>VIIRS fires] --> A3[ingest_fires_6hourly]
    OAQ[OpenAQ<br/>historical] --> BF[run_backfill]

    A1 --> BR[(bronze.aqi_readings_raw<br/>JSONB, 30-day TTL)]
    BR --> SV1[(silver.aqi_readings)]
    A2 --> SV2[(silver.weather)]
    A3 --> SV3[(silver.fires)]
    BF --> SV1
    BF --> SV2

    SV1 --> CA[(gold.aqi_hourly_by_city<br/>continuous aggregate)]

    DQ[data_quality_daily] --> RPT[(docs/data_quality_report.json)]
    SV1 --> DQ
    SV2 --> DQ

    SV1 --> EDA[notebooks/01_eda.ipynb]
    SV2 --> EDA
    SV3 --> EDA
```

## Components

| Component        | Responsibility                                                                |
| ---------------- | ----------------------------------------------------------------------------- |
| **TimescaleDB**  | Hypertable storage with retention + native compression on chunks > 14 days.   |
| **PostGIS**      | `geom` columns for spatial joins (stations × fires within radius).            |
| **Airflow**      | Scheduler + LocalExecutor. Idempotent DAGs, retries with exponential backoff. |
| **Ingestion**    | Async `httpx` clients with `tenacity` retries → Pydantic v2 models.           |
| **Bronze→Silver**| Re-parse the last hour of bronze JSONB to recover from parser bugs.           |
| **Quality DAG**  | Daily PM2.5 freshness/missing-rate; writes JSON snapshot for the README.      |

## Storage estimate (1 year)

- 250 stations × 24 readings/day × 365 days × ~120 B/row ≈ **0.26 GB** raw silver AQI
- 250 stations × 48 hourly weather × 365 × ~150 B/row ≈ **0.66 GB** silver weather
- ~50k fires/year × ~200 B/row ≈ **10 MB** silver fires
- Bronze raw payloads (TTL 30 d) ≈ 0.5 GB rolling

After Timescale compression on chunks > 14 d: **< 1.5 GB** total. Well under the 5 GB target.
