# Atmos

**Hyperlocal air quality forecasting platform for India.**

Atmos is an end-to-end machine learning and AI system built to close a critical gap in India's air quality monitoring — national AQI stations are too sparse to give people block-level visibility into pollution, which is the resolution that actually matters for personal health decisions.

Built as a college major project, targeting production-grade AI/ML engineering practices from data ingestion through to LLM-powered user-facing insights.

---

## Overview

Atmos ingests live data from **250+ AQI monitoring stations** across India, along with satellite fire detection feeds and weather data, into a structured data pipeline. It trains spatiotemporal machine learning models to forecast AQI up to **72 hours ahead** at a hyperlocal resolution, and uses the Claude API to translate raw forecasts into plain-English explanations and personalized health advisories.

The project is being built in three phases:

- ✅ **Phase 1 — Data Pipeline** (complete)
- 🔄 **Phase 2 — ML Modeling** (in progress)
- ⏳ **Phase 3 — Serving + LLM Layer** (planned)

---

## Architecture

```
Live Data Sources (AQI stations, satellite, weather)
              │
              ▼
     Apache Airflow (orchestration)
              │
              ▼
   TimescaleDB (bronze → silver → gold)
              │
              ▼
  Spatiotemporal ML Models (LightGBM, XGBoost)
              │
              ▼
       FastAPI Backend
              │
              ▼
   Claude API (explanations + health advisories)
              │
              ▼
          Frontend
```

### Data Pipeline

A multi-source ingestion pipeline built with **Apache Airflow** pulls in:
- Live readings from 250+ AQI monitoring stations
- Satellite-based fire detection data
- Meteorological / weather data

Data flows through a **bronze / silver / gold** architecture on **TimescaleDB**, designed to handle partial data gaps and inconsistent update frequencies across sources without breaking downstream model training.

### ML Modeling

Spatiotemporal models built with **LightGBM** and **XGBoost**, using engineered features that capture both time and spatial pollution dispersion patterns — standard time-series models don't account for how pollution physically moves across a region, so this required custom feature engineering beyond off-the-shelf approaches.

Target: AQI forecasts up to **72 hours ahead** at a resolution finer than what national monitoring stations provide.

### LLM Layer

The **Claude API** is integrated to:
- Generate plain-English explanations for *why* a pollution spike is happening
- Deliver personalized health advisories based on individual user health profiles

This turns a raw forecast number into something a non-technical user can actually act on.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Orchestration | Apache Airflow |
| Database | TimescaleDB |
| ML Modeling | LightGBM, XGBoost, Python |
| Backend | FastAPI |
| LLM | Claude API |
| Data Sources | AQI monitoring APIs, satellite fire detection, weather APIs |

---

## Status

This is an actively developed project. The data pipeline (Phase 1) is complete and stable. ML modeling (Phase 2) is in progress. Contributions, feedback, and issues are welcome.

---

## Author

**Gautam Sharma**
B.E. Information Science and Engineering, Bangalore Institute of Technology

- GitHub: [github.com/GautamSharma99](https://github.com/GautamSharma99)
- LinkedIn: [linkedin.com/in/gautam-sharma569](https://www.linkedin.com/in/gautam-sharma569/)
- Email: gautamsharma99067@gmail.com
