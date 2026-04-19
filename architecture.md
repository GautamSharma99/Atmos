# Product Requirements Document: AirQualityCast Data Pipeline (Phase 1)

> **Document Purpose:** This PRD is written to be consumed by an AI coding agent (Claude Code). It specifies WHAT to build and the quality constraints; the agent has latitude on implementation details within those constraints. Every section is actionable.

---

## 1. Project Context

### 1.1 The Broader System
AirQualityCast is an end-to-end ML system for hyperlocal air quality forecasting in India. The full system (three phases) will:
1. **Phase 1 (this PRD):** Build a production-grade data pipeline ingesting AQI, weather, and satellite fire data across all of India.
2. **Phase 2 (future):** Train multi-horizon forecasting models (LightGBM/XGBoost) predicting AQI at t+1h, t+6h, t+24h, t+72h with spatiotemporal features.
3. **Phase 3 (future):** Serve predictions via FastAPI + integrate an LLM layer (Anthropic Claude API) for pollution source attribution, personalized health advisories, and policy-grade reports.

### 1.2 This PRD's Scope
**ONLY Phase 1: the data pipeline.** Nothing else. Specifically:
- Ingestion from external APIs (AQI, weather, satellite fires, historical data).
- Storage in TimescaleDB with a bronze/silver/gold medallion architecture.
- Orchestration via Apache Airflow with scheduled DAGs.
- Data quality monitoring and basic observability.
- An EDA notebook demonstrating the data is usable for modeling.

**Explicitly OUT of scope for this PRD:**
- Any ML model training or feature engineering beyond raw data cleaning.
- Any API/serving layer (no FastAPI).
- Any frontend or Streamlit dashboard beyond a minimal data quality page.
- Any LLM integration.

### 1.3 Success Definition for Phase 1
The pipeline is "done" when all of the following are true:
1. `docker compose up` on a fresh machine brings up the full stack (DB + Airflow) without manual intervention beyond filling a `.env` file.
2. Three Airflow DAGs run on schedule and populate the database with fresh data continuously for at least 72 hours without human intervention.
3. Historical backfill has loaded ≥ 1 year of AQI + weather data for ≥ 50 Indian stations.
4. A data quality report confirms < 15% missing values for PM2.5 across active stations in the last 7 days.
5. An EDA notebook runs end-to-end from the database and produces the required visualizations (see §9).
6. README allows a technical recruiter to understand the architecture in < 5 minutes.

---

## 2. User Personas

| Persona | Who | What they need from Phase 1 |
|---|---|---|
| **The Developer (me)** | Project owner, AI/ML job candidate | Clean foundation for Phase 2 modeling; code that showcases production ML engineering skill |
| **The Recruiter** | Reviewing the GitHub repo during candidate evaluation | Clear README, clean architecture, visible evidence of best practices (tests, CI, medallion layers, observability) |
| **The Interviewer** | Deep-diving the project in a technical interview | Ability to trace any data point from raw API response to cleaned table; defensible design decisions |

---

## 3. Technology Stack (Fixed Decisions)

These are non-negotiable. Do not substitute.

| Layer | Technology | Version | Rationale |
|---|---|---|---|
| Language | Python | 3.11+ | Modern typing, performance |
| Package manager | `uv` | latest | Fast, modern; avoid `pip`/`requirements.txt` |
| Database | TimescaleDB | `latest-pg16` | Purpose-built for time-series; industry-standard demo point |
| Spatial extension | PostGIS | Bundled with Timescale image | For station distance/proximity queries |
| Orchestration | Apache Airflow | 2.9+ | Industry standard; learnable pattern |
| Containerization | Docker + Docker Compose | latest | Reproducibility |
| HTTP client | `httpx` | latest | Async-capable, modern |
| Retries | `tenacity` | latest | Exponential backoff |
| Data validation | `pydantic` v2 | latest | Request/response schemas |
| DB client | `psycopg` v3 | latest | Modern Postgres driver |
| Dataframe | `pandas` + `pyarrow` | latest | Standard for EDA |
| Testing | `pytest` + `pytest-mock` + `pytest-cov` | latest | Standard |
| Logging | `structlog` | latest | JSON logs for observability |
| Linting/formatting | `ruff` | latest | All-in-one, fast |
| Type checking | `mypy` | latest | Strict mode enforced |
| Pre-commit | `pre-commit` | latest | Enforce standards |
| CI | GitHub Actions | N/A | Standard |
| EDA visualization | `matplotlib`, `seaborn`, `folium`, `plotly` | latest | Standard |

---

## 4. Data Sources

### 4.1 AQICN (Primary AQI Source)
- **URL:** `https://aqicn.org/data-platform/token/`
- **Authentication:** Free token, stored in env var `AQICN_TOKEN`
- **Endpoints used:**
  - `GET https://api.waqi.info/feed/@{station_uid}/?token={token}` — current reading per station
  - `GET https://api.waqi.info/search/?token={token}&keyword={query}` — station discovery
- **Rate limit policy:** Max 1 request/second per station; use an Airflow pool with 5 slots to limit concurrency.
- **Data freshness:** Updated approximately hourly.
- **Known issues to handle:**
  - Some stations return `{"aqi": "-"}` when offline. Treat as null, do not fail pipeline.
  - Field `iaqi` contains pollutant-specific readings; not all stations report all pollutants.
  - Timestamps come in local time with TZ info; normalize to UTC.

### 4.2 OpenAQ (Historical Backfill)
- **URL:** `https://api.openaq.org/v3/`
- **Authentication:** API key required as of v3, stored in `OPENAQ_API_KEY`
- **Endpoints used:**
  - `GET /v3/locations?countries_id=9&limit=1000` — India's country_id is 9
  - `GET /v3/locations/{id}/measurements?date_from={iso}&date_to={iso}&limit=1000` — historical measurements
- **Rate limit:** 60 req/min on free tier. Respect with a 1.5s delay between requests.
- **Use case:** One-time backfill of 1-2 years of historical data per station on Phase 1 initialization.

### 4.3 Open-Meteo (Weather — Free, No Auth)
- **URL:** `https://api.open-meteo.com/v1/forecast` (current/forecast) and `https://archive-api.open-meteo.com/v1/archive` (historical)
- **Authentication:** None
- **Variables to pull (hourly):**
  - `temperature_2m`
  - `relative_humidity_2m`
  - `wind_speed_10m`
  - `wind_direction_10m`
  - `precipitation`
  - `surface_pressure`
  - `boundary_layer_height` *(critical for AQI modeling — captures inversion events)*
- **Rate limit:** 10,000 calls/day free tier; batch up to 100 locations per request where possible.
- **Known issues:** Occasional gaps in `boundary_layer_height`; do not drop rows, just leave null.

### 4.4 NASA FIRMS (Satellite Fire Data)
- **URL:** `https://firms.modaps.eosdis.nasa.gov/api/`
- **Authentication:** MAP_KEY in env var `FIRMS_MAP_KEY`
- **Endpoint:** `GET https://firms.modaps.eosdis.nasa.gov/api/country/csv/{MAP_KEY}/VIIRS_SNPP_NRT/IND/{days}`
- **Response format:** CSV (not JSON)
- **Data freshness:** 3-6 hour lag from detection to availability.
- **Use case:** Capture stubble burning (critical for N. India winter AQI).
- **Rate limit:** 5,000 requests per 10 min; effectively unlimited for our use.

### 4.5 Source Priority & Fallback
- AQICN is primary for live data.
- If AQICN is down for > 2 hours, log a warning but do not fail; the pipeline continues with whatever it can fetch.
- OpenAQ is for one-time historical backfill only. Not a live fallback.

---

## 5. Repository Structure (Required)

Create exactly this structure. Deviations must be justified.

```
airqualitycast/
├── README.md
├── pyproject.toml
├── uv.lock
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml
├── docker-compose.yml
├── Makefile
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── lint.yml
├── airflow/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── dags/
│       ├── __init__.py
│       ├── ingest_aqi_hourly.py
│       ├── ingest_weather_hourly.py
│       ├── ingest_fires_6hourly.py
│       ├── data_quality_daily.py
│       └── utils/
│           ├── __init__.py
│           ├── db.py
│           └── alerting.py
├── src/
│   └── airqualitycast/
│       ├── __init__.py
│       ├── config.py
│       ├── ingestion/
│       │   ├── __init__.py
│       │   ├── aqicn_client.py
│       │   ├── openaq_client.py
│       │   ├── openmeteo_client.py
│       │   ├── firms_client.py
│       │   └── models.py
│       ├── db/
│       │   ├── __init__.py
│       │   ├── connection.py
│       │   ├── upsert.py
│       │   └── queries.py
│       ├── processing/
│       │   ├── __init__.py
│       │   ├── bronze_to_silver.py
│       │   └── validators.py
│       ├── quality/
│       │   ├── __init__.py
│       │   ├── checks.py
│       │   └── reporter.py
│       └── backfill/
│           ├── __init__.py
│           └── historical_loader.py
├── sql/
│   ├── 01_extensions.sql
│   ├── 02_schemas.sql
│   ├── 03_tables.sql
│   ├── 04_hypertables.sql
│   ├── 05_indexes.sql
│   └── 06_continuous_aggregates.sql
├── scripts/
│   ├── bootstrap_stations.py
│   ├── run_backfill.py
│   └── check_data_quality.py
├── notebooks/
│   └── 01_eda.ipynb
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_aqicn_client.py
│   │   ├── test_openmeteo_client.py
│   │   ├── test_firms_client.py
│   │   ├── test_bronze_to_silver.py
│   │   └── test_quality_checks.py
│   ├── integration/
│   │   ├── test_db_upserts.py
│   │   └── test_end_to_end_dag.py
│   └── fixtures/
│       ├── aqicn_response.json
│       ├── openmeteo_response.json
│       └── firms_response.csv
└── docs/
    ├── architecture.md
    ├── schema.md
    └── runbook.md
```

---

## 6. Database Design (Required)

### 6.1 Medallion Architecture
Three schemas, each with a clear purpose:

| Schema | Purpose | Characteristics |
|---|---|---|
| `bronze` | Raw API responses, append-only | JSONB payloads, minimal processing, 30-day retention |
| `silver` | Cleaned, typed, deduplicated | Primary keys enforce uniqueness; ML-ready raw observations |
| `gold` | Feature-engineered (Phase 2 uses this) | Empty in Phase 1, schema defined for forward compatibility |

### 6.2 Required Tables

Define these in `sql/03_tables.sql`:

**`silver.stations`** (metadata, not time-series)
- `station_id TEXT PRIMARY KEY` — canonical ID (use AQICN station UID format)
- `station_name TEXT NOT NULL`
- `city TEXT`
- `state TEXT`
- `country TEXT DEFAULT 'IN'`
- `latitude DOUBLE PRECISION NOT NULL`
- `longitude DOUBLE PRECISION NOT NULL`
- `source TEXT NOT NULL` — 'aqicn', 'openaq', 'cpcb'
- `source_station_id TEXT NOT NULL` — ID in source system
- `active BOOLEAN DEFAULT true`
- `geom GEOGRAPHY(POINT, 4326)` — auto-populated via trigger
- `first_seen_at TIMESTAMPTZ DEFAULT NOW()`
- `last_seen_at TIMESTAMPTZ`
- **Index:** GIST index on `geom`; B-tree on `(source, active)`.

**`bronze.aqi_readings_raw`**
- `id BIGSERIAL`
- `ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `source TEXT NOT NULL`
- `station_id TEXT`
- `http_status INTEGER`
- `payload JSONB NOT NULL`
- `PRIMARY KEY (id, ingested_at)`
- **Hypertable** on `ingested_at`, chunk interval 1 day.
- **Retention policy:** 30 days.

**`silver.aqi_readings`**
- `station_id TEXT NOT NULL REFERENCES silver.stations(station_id)`
- `measured_at TIMESTAMPTZ NOT NULL`
- `pm25 DOUBLE PRECISION`
- `pm10 DOUBLE PRECISION`
- `no2 DOUBLE PRECISION`
- `so2 DOUBLE PRECISION`
- `o3 DOUBLE PRECISION`
- `co DOUBLE PRECISION`
- `aqi INTEGER`
- `dominant_pollutant TEXT`
- `source TEXT NOT NULL`
- `ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `PRIMARY KEY (station_id, measured_at)`
- **Hypertable** on `measured_at`, chunk interval 7 days.
- **Index:** `(station_id, measured_at DESC)`.

**`silver.weather`**
- `station_id TEXT NOT NULL REFERENCES silver.stations(station_id)`
- `measured_at TIMESTAMPTZ NOT NULL`
- `temperature_2m DOUBLE PRECISION`
- `relative_humidity_2m DOUBLE PRECISION`
- `wind_speed_10m DOUBLE PRECISION`
- `wind_direction_10m DOUBLE PRECISION`
- `precipitation DOUBLE PRECISION`
- `surface_pressure DOUBLE PRECISION`
- `boundary_layer_height DOUBLE PRECISION`
- `is_forecast BOOLEAN NOT NULL DEFAULT false`
- `ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `PRIMARY KEY (station_id, measured_at, is_forecast)`
- **Hypertable** on `measured_at`, chunk interval 7 days.

**`silver.fires`**
- `fire_id TEXT PRIMARY KEY` — constructed as `{satellite}_{acq_date}_{acq_time}_{lat}_{lon}`
- `detected_at TIMESTAMPTZ NOT NULL`
- `latitude DOUBLE PRECISION NOT NULL`
- `longitude DOUBLE PRECISION NOT NULL`
- `brightness DOUBLE PRECISION`
- `frp DOUBLE PRECISION` — fire radiative power
- `confidence TEXT`
- `satellite TEXT`
- `daynight TEXT`
- `geom GEOGRAPHY(POINT, 4326)`
- `ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- **Index:** GIST on `geom`; B-tree on `detected_at`.

**`silver.ingestion_runs`** (observability)
- `run_id BIGSERIAL PRIMARY KEY`
- `dag_id TEXT NOT NULL`
- `task_id TEXT NOT NULL`
- `source TEXT NOT NULL`
- `started_at TIMESTAMPTZ NOT NULL`
- `ended_at TIMESTAMPTZ`
- `status TEXT NOT NULL` — 'success', 'failure', 'partial'
- `records_fetched INTEGER`
- `records_inserted INTEGER`
- `error_message TEXT`
- **Index:** `(dag_id, started_at DESC)`.

### 6.3 Continuous Aggregates (Phase 1 bonus)

Create one TimescaleDB continuous aggregate to demonstrate the feature — `gold.aqi_hourly_by_city`:
```sql
CREATE MATERIALIZED VIEW gold.aqi_hourly_by_city
WITH (timescaledb.continuous) AS
SELECT
    s.city,
    time_bucket('1 hour', ar.measured_at) AS hour,
    AVG(ar.pm25) AS avg_pm25,
    MAX(ar.aqi) AS max_aqi,
    COUNT(*) AS n_readings
FROM silver.aqi_readings ar
JOIN silver.stations s ON ar.station_id = s.station_id
GROUP BY s.city, hour;
```
This is a portfolio flex — mention it in the README.

### 6.4 Retention & Compression
- Enable TimescaleDB native compression on `silver.aqi_readings` and `silver.weather` for chunks > 14 days old.
- Retention policy on `bronze.aqi_readings_raw`: drop chunks > 30 days.

---

## 7. Ingestion Specifications

### 7.1 AQICN Client (`src/airqualitycast/ingestion/aqicn_client.py`)

**Required public API:**
```python
class AQICNClient:
    def __init__(self, token: str, timeout_s: float = 10.0) -> None: ...
    async def get_station_feed(self, station_uid: str) -> StationFeed | None: ...
    async def search_stations_by_keyword(self, keyword: str) -> list[StationSearchResult]: ...
    async def batch_get_station_feeds(self, station_uids: list[str], concurrency: int = 5) -> list[StationFeed]: ...
```

**Requirements:**
- Use `httpx.AsyncClient` with connection pooling.
- Wrap all calls in `tenacity.retry` with exponential backoff: max 3 retries, start 1s, max 30s.
- Return Pydantic models (defined in `ingestion/models.py`), never raw dicts.
- On HTTP 429 or 5xx: retry. On 4xx (other than 429): log + return None, do not raise.
- All timestamps returned must be timezone-aware in UTC.

### 7.2 Open-Meteo Client

**Required public API:**
```python
class OpenMeteoClient:
    async def get_current_weather(self, lat: float, lon: float) -> WeatherReading: ...
    async def get_historical_weather(
        self, lat: float, lon: float, start: date, end: date
    ) -> list[WeatherReading]: ...
    async def batch_get_current(self, coords: list[tuple[float, float]]) -> list[WeatherReading]: ...
```

**Requirements:**
- Batch up to 100 coordinates per request when possible (Open-Meteo supports this via comma-separated lat/lon).
- No auth; keep calls under 10,000/day.

### 7.3 FIRMS Client

**Required public API:**
```python
class FIRMSClient:
    def __init__(self, map_key: str) -> None: ...
    def fetch_fires_for_india(self, days: int = 1) -> pd.DataFrame: ...
```

**Requirements:**
- Returns a DataFrame with normalized column names (snake_case).
- Constructs the `fire_id` deterministically for idempotent upserts.
- `detected_at` combined from `acq_date` + `acq_time` in UTC.

### 7.4 OpenAQ Client (Historical Only)

**Required public API:**
```python
class OpenAQClient:
    def __init__(self, api_key: str) -> None: ...
    async def list_locations_in_india(self, limit: int = 1000) -> list[Location]: ...
    async def get_measurements(
        self, location_id: int, date_from: datetime, date_to: datetime
    ) -> list[Measurement]: ...
```

**Requirements:**
- Pagination handled transparently.
- Rate limited to 40 req/min (with 25% safety margin below the 60/min cap).

### 7.5 Pydantic Models Required

Define in `ingestion/models.py`:
- `StationSearchResult`
- `StationFeed` (with nested `AQIComponents`)
- `WeatherReading`
- `FireDetection`
- `OpenAQLocation`
- `OpenAQMeasurement`

All should use Pydantic v2 patterns (`model_config`, `field_validator`).

---

## 8. Airflow DAGs (Required)

All DAGs must be in `airflow/dags/` and follow these principles:
- Idempotent (safe to re-run any day).
- `catchup=False` unless explicitly needed.
- Retries: 3 attempts, `retry_delay=timedelta(minutes=5)`, exponential backoff.
- Use Airflow Variables for API keys (loaded at DAG parse from env).
- Use an Airflow Connection named `timescale_default` for the database.
- All tasks write a row to `silver.ingestion_runs` on completion (success or failure).
- Use the `@dag` / `@task` decorator syntax (TaskFlow API), not classic operators unless necessary.

### 8.1 `ingest_aqi_hourly`
- **Schedule:** `0 * * * *` (top of every hour)
- **Max active runs:** 1
- **Pool:** `aqicn_pool` (5 slots)
- **Tasks:**
  1. `get_active_stations` — query `silver.stations WHERE active = true`
  2. `fetch_feed` (dynamic task mapping, `.expand(station_id=...)`) — fetch each station, write raw to `bronze.aqi_readings_raw`
  3. `parse_bronze_to_silver` — read last hour's bronze rows, parse to silver rows, upsert
  4. `record_run` — write to `silver.ingestion_runs`
- **Failure policy:** If < 50% of stations return data, mark run as `partial` but do not fail DAG.

### 8.2 `ingest_weather_hourly`
- **Schedule:** `15 * * * *` (offset by 15 min from AQI DAG)
- **Tasks:**
  1. `get_active_stations`
  2. `fetch_current_weather_batched` — batch 100 stations per request
  3. `upsert_weather_readings`
  4. `record_run`

### 8.3 `ingest_fires_6hourly`
- **Schedule:** `0 */6 * * *`
- **Tasks:**
  1. `fetch_fires` — last 24h of VIIRS data for India
  2. `upsert_fires` — `ON CONFLICT (fire_id) DO NOTHING`
  3. `record_run`

### 8.4 `data_quality_daily`
- **Schedule:** `30 2 * * *` (2:30 AM IST equivalent; adjust based on UTC)
- **Tasks:**
  1. `check_aqi_freshness` — any station with no data > 24h gets `active = false`
  2. `check_missing_rates` — compute PM2.5 null rate per station, last 7 days
  3. `check_duplicate_rows` — should be zero given PKs, but verify
  4. `generate_quality_report` — write summary JSON to `docs/data_quality_report.json`
  5. Fail DAG with clear error if global PM2.5 null rate > 30%.

---

## 9. EDA Notebook (`notebooks/01_eda.ipynb`)

The notebook must run end-to-end from a fresh `docker compose up` + backfill, and produce the following (in order):

1. **Station coverage map** — Folium map of India with all active stations colored by data freshness.
2. **Time-series overview** — Daily avg PM2.5 for a selected city (default: Delhi) over the past year.
3. **Diwali spike analysis** — Zoom into Oct-Nov for any year in data; annotate the Diwali date; show the spike.
4. **Stubble burning correlation** — Count of fires in Punjab/Haryana vs. Delhi PM2.5, with 0-3 day lag cross-correlation.
5. **Hourly pattern heatmap** — Hour-of-day × day-of-week heatmap of average AQI for 3 cities.
6. **Wind-PM2.5 wind rose** — Delhi wind rose colored by PM2.5 concentration; clearly shows NW winds bring the worst air.
7. **Monsoon washout** — Monthly average PM2.5 for a full year, highlighting July-Sept drop.
8. **Data completeness heatmap** — Station × date matrix for last 30 days.

Each section has: (a) a markdown cell describing what's being shown, (b) the plot, (c) 1-2 sentences on the insight. These go straight into the README.

---

## 10. Testing Requirements

| Category | Minimum coverage |
|---|---|
| Unit tests on ingestion clients | ≥ 85% line coverage |
| Integration tests on DB upserts | Happy path + conflict path |
| End-to-end DAG test | At least one DAG tested via Airflow's `dag.test()` with mocked HTTP |
| Overall project | ≥ 75% line coverage |

**Fixtures must exist for:** AQICN response, OpenAQ response, Open-Meteo response, FIRMS CSV. Store these in `tests/fixtures/` as real captured responses (sanitized).

**CI requirement:** `pytest` must run on every PR via GitHub Actions, with a Postgres service container (Timescale image) for integration tests.

---

## 11. Code Quality Standards

### 11.1 Enforcement
Configure in `pyproject.toml` and `.pre-commit-config.yaml`:
- `ruff` with rule sets: `E`, `F`, `I`, `UP`, `B`, `SIM`, `N`, `D` (with `D` limited to public APIs)
- `mypy` in strict mode on `src/`
- `ruff format` as the formatter (not Black)

### 11.2 Typing
- Every function in `src/` has full type annotations.
- Use Pydantic models for all external data.
- Use `typing.Protocol` where interfaces matter.

### 11.3 Logging
- Use `structlog` configured for JSON output.
- Every ingestion call logs at INFO: source, records fetched, duration.
- Every failure logs at ERROR with exception traceback.
- Never print; always log.

### 11.4 Config Management
- All config via env vars, loaded through a `pydantic_settings.BaseSettings` class in `src/airqualitycast/config.py`.
- `.env.example` lists every variable with a comment explaining its purpose.
- Secrets never committed. `.env` in `.gitignore`.

### 11.5 Forbidden
- No `requirements.txt` — use `pyproject.toml` + `uv.lock`.
- No Jupyter notebooks outside `notebooks/`.
- No hardcoded paths, station IDs, or API keys.
- No `print()` statements in `src/`.
- No silent `except Exception: pass`.
- No global mutable state.

---

## 12. Deliverables Checklist

At the end of Phase 1, the repo must have:

- [ ] `docker compose up` brings up TimescaleDB + Airflow fresh, with schema auto-created.
- [ ] `.env.example` with all required variables documented.
- [ ] `README.md` covering: project overview, architecture diagram, quickstart, data sources, schema overview, how to run EDA notebook, tech stack, future work (Phase 2/3).
- [ ] `docs/architecture.md` with a Mermaid or rendered diagram of the data flow.
- [ ] `docs/schema.md` with full DB schema documentation (can be auto-generated).
- [ ] `docs/runbook.md` with operational playbook (how to re-run a failed DAG, how to backfill, how to add a new station).
- [ ] All 4 Airflow DAGs working and scheduled.
- [ ] Historical backfill script populating ≥ 1 year of data for ≥ 50 stations.
- [ ] Station bootstrap script populating `silver.stations` with all Indian AQICN stations.
- [ ] EDA notebook producing all 8 required visualizations.
- [ ] Test suite passing with ≥ 75% coverage.
- [ ] GitHub Actions CI workflow running on every PR.
- [ ] Pre-commit hooks configured and passing on a clean checkout.
- [ ] `Makefile` with targets: `setup`, `up`, `down`, `test`, `lint`, `format`, `backfill`, `eda`.

---

## 13. Non-Functional Requirements

- **Reproducibility:** A new developer should go from `git clone` to a running pipeline in < 20 minutes (assuming Docker is installed and API keys are obtained).
- **Performance:** AQI ingestion for 250 stations must complete in < 10 minutes per hourly run.
- **Storage:** Estimate < 5 GB for 1 year of data across all stations; verify this in the architecture doc.
- **Cost:** All data sources must be on free tiers. No paid APIs in Phase 1.
- **Timezone discipline:** Every timestamp in the database is `TIMESTAMPTZ` in UTC. Display layer (notebooks, reports) may convert to IST.
- **Failure isolation:** Failure of one station's ingestion must never fail the entire DAG run.

---

## 14. Known Risks & Mitigations

| Risk | Mitigation |
|---|---|
| AQICN API changes or goes down | Bronze layer preserves raw payloads; re-parsing is always possible. OpenAQ available for historical. |
| Airflow complexity on first setup | Use the official Airflow docker-compose as the base, add Timescale as an additional service. |
| Rate limiting from any API | All clients use `tenacity` + Airflow pools; limits documented per source. |
| Timezone bugs | Enforce UTC at the DB layer; all parsing code has tests specifically for TZ conversion. |
| OpenAQ v3 API quirks | Historical backfill script is idempotent; can be re-run to fill gaps. |
| Apple Silicon users | `docker-compose.yml` sets `platform: linux/amd64` for Airflow images where needed. |
| Station ID mismatches across sources | Phase 1 uses AQICN IDs as canonical; mapping to other sources deferred to Phase 2. |

---

## 15. Execution Guidance for the Coding Agent

When implementing this PRD:

1. **Work in this order** and commit at each stage:
   1. Repo scaffolding (`pyproject.toml`, structure, pre-commit, CI skeleton)
   2. SQL schema files
   3. `docker-compose.yml` with TimescaleDB (get DB working first, before Airflow)
   4. Pydantic models + one ingestion client (AQICN) with tests
   5. Station bootstrap script (proves end-to-end path)
   6. Other ingestion clients with tests
   7. Airflow setup in docker-compose
   8. DAGs one at a time (AQI first)
   9. Backfill script
   10. Data quality DAG
   11. EDA notebook
   12. README + docs

2. **Ask for clarification before** making decisions about:
   - Any change to the fixed tech stack (§3)
   - Any change to the database schema (§6)
   - Any change to source priority (§4.5)

3. **Do not** commit:
   - API keys or `.env` files
   - Large data files (> 10 MB); put in `.gitignore`
   - Generated files from the notebook (clear outputs before commit)

4. **Validation before claiming completion:**
   - Run `make setup && make up && make test` on a clean checkout.
   - Let the pipeline run for at least 2 hourly cycles.
   - Open the EDA notebook and confirm all cells execute.
   - Run `ruff check . && mypy src/` with zero errors.

---

## 16. Out of Scope (Do Not Build in Phase 1)

- Model training, feature stores, MLflow (Phase 2).
- FastAPI, endpoints, serving infrastructure (Phase 3).
- LLM integration (Phase 3).
- Frontend beyond the Airflow UI and the EDA notebook.
- Authentication/authorization (not needed for internal pipeline).
- Kubernetes, Helm, or cloud deployment (Docker Compose is the target).
- Fancy observability stacks (Grafana, Loki, Prometheus) — basic logging + the daily quality report is sufficient.
- CPCB direct scraping — it's encrypted; use AQICN which already aggregates CPCB data.

---

## Appendix A: Environment Variables

```dotenv
# Database
POSTGRES_DB=airquality
POSTGRES_USER=aq_user
POSTGRES_PASSWORD=CHANGE_ME

# Airflow
AIRFLOW_UID=50000
AIRFLOW_FERNET_KEY=CHANGE_ME_32_BYTES_BASE64
AIRFLOW_ADMIN_USER=admin
AIRFLOW_ADMIN_PASSWORD=CHANGE_ME

# Data source API keys
AQICN_TOKEN=                  # Register at aqicn.org/data-platform/token
OPENAQ_API_KEY=               # Register at openaq.org
FIRMS_MAP_KEY=                # Register at firms.modaps.eosdis.nasa.gov/api/

# Operational
LOG_LEVEL=INFO
ENVIRONMENT=dev
```

## Appendix B: Makefile Targets (Required)

```makefile
setup:        ## Install dev deps via uv, set up pre-commit
up:           ## docker compose up -d
down:         ## docker compose down
logs:         ## Tail Airflow scheduler + webserver logs
test:         ## Run pytest with coverage
lint:         ## Ruff check + mypy
format:       ## Ruff format
bootstrap:    ## Run station bootstrap script
backfill:     ## Run historical backfill
quality:      ## Run one-off data quality check
eda:          ## Launch Jupyter for the EDA notebook
clean:        ## Remove __pycache__, .pytest_cache, etc.
```

## Appendix C: README Structure (Required Outline)

```
# AirQualityCast

> One-line tagline

## Overview
(2-3 sentences + architecture diagram)

## Features
(Phase 1 scope as bullets)

## Tech Stack
(Tool table)

## Quickstart
(Exact copy-pasteable commands)

## Data Sources
(Table with freshness/limitations)

## Architecture
(Diagram + brief walk-through)

## Database Schema
(Schema diagram + link to docs/schema.md)

## Data Quality
(How the daily DAG works + latest quality snapshot)

## EDA Highlights
(3-4 inlined charts from the notebook)

## Project Structure
(File tree with brief notes)

## Roadmap
(Phase 2 modeling, Phase 3 serving + LLM)

## Contributing & License
```

---

**End of PRD.**