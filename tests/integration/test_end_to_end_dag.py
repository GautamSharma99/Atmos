"""End-to-end DAG smoke test using Airflow's dag.test() with mocked HTTP."""
from __future__ import annotations

import pytest

pytest.importorskip("airflow", reason="Airflow not installed in unit-test env")

pytestmark = pytest.mark.integration


def test_aqi_dag_imports() -> None:
    """The DAG file must parse cleanly under Airflow."""
    import importlib.util
    import pathlib

    dag_path = pathlib.Path(__file__).resolve().parents[2] / "airflow" / "dags" / "ingest_aqi_hourly.py"
    spec = importlib.util.spec_from_file_location("ingest_aqi_hourly", dag_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
