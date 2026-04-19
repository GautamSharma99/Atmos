"""Lightweight alerting hook for DAG failures."""
from __future__ import annotations

from typing import Any

from airqualitycast.config import get_logger

log = get_logger(__name__)


def on_failure_callback(context: dict[str, Any]) -> None:
    ti = context.get("task_instance")
    log.error(
        "dag.task_failure",
        dag_id=context.get("dag", {}).dag_id if context.get("dag") else None,
        task_id=ti.task_id if ti else None,
        execution_date=str(context.get("execution_date")),
        exception=str(context.get("exception")),
    )
