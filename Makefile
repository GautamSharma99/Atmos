.PHONY: setup up down logs test lint format bootstrap backfill quality eda clean help

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup:  ## Install dev deps via uv, set up pre-commit
	uv sync --extra dev --extra eda
	uv run pre-commit install

up:  ## docker compose up -d
	docker compose up -d

down:  ## docker compose down
	docker compose down

logs:  ## Tail Airflow scheduler + webserver logs
	docker compose logs -f airflow-scheduler airflow-webserver

test:  ## Run pytest with coverage
	uv run pytest

lint:  ## Ruff check + mypy
	uv run ruff check .
	uv run mypy src/

format:  ## Ruff format
	uv run ruff format .
	uv run ruff check . --fix

bootstrap:  ## Run station bootstrap script
	uv run python scripts/bootstrap_stations.py

backfill:  ## Run historical backfill (≥1 year, ≥50 stations)
	uv run python scripts/run_backfill.py --years 1 --min-stations 50

quality:  ## Run one-off data quality check
	uv run python scripts/check_data_quality.py

eda:  ## Launch Jupyter for the EDA notebook
	uv run jupyter lab notebooks/01_eda.ipynb

clean:  ## Remove __pycache__, .pytest_cache, etc.
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov dist build
