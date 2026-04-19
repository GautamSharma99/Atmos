"""Shared pytest fixtures."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _silence_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide harmless defaults for required env vars during unit tests."""
    monkeypatch.setenv("POSTGRES_PASSWORD", "test")
    monkeypatch.setenv("AQICN_TOKEN", "test-token")
    monkeypatch.setenv("OPENAQ_API_KEY", "test-key")
    monkeypatch.setenv("FIRMS_MAP_KEY", "test-map-key")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")


@pytest.fixture
def aqicn_payload() -> dict:
    return json.loads((FIXTURES / "aqicn_response.json").read_text())


@pytest.fixture
def openmeteo_payload() -> dict:
    return json.loads((FIXTURES / "openmeteo_response.json").read_text())


@pytest.fixture
def firms_csv_text() -> str:
    return (FIXTURES / "firms_response.csv").read_text()


@pytest.fixture(scope="session")
def db_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL")
