"""session_logger.py

Writes one row per experiment session to experiment_sessions.csv.
Never touches test_environment's sessions.csv.

CSV schema (auto-generated from experiment_config):
  base fields + per-condition task columns + feedback columns
  e.g. monthly_task1_seconds, monthly_task1_correct, monthly_task1_notes, ...
"""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime

try:
    from . import experiment_config
except ImportError:
    import experiment_config

EXPERIMENT_CSV = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "experiment_sessions.csv"
)


def _fieldnames() -> list[str]:
    base = [
        "participant_id",
        "timestamp_start",
        "timestamp_end",
        "duration_seconds",
        "slot",
        "condition_order",
        "screens_visited",
    ]
    task_fields: list[str] = []
    for cond in experiment_config.CONDITIONS:
        task_fields.append(f"{cond}_total_clicks")
        for i in range(experiment_config.TASKS_PER_CONDITION):
            task_fields += [
                f"{cond}_task{i + 1}_seconds",
                f"{cond}_task{i + 1}_correct",
                f"{cond}_task{i + 1}_notes",
            ]
    feedback_fields = [
        f"feedback_{i + 1}"
        for i in range(len(experiment_config.FEEDBACK_QUESTIONS))
    ]
    return base + task_fields + feedback_fields


def _ensure_header() -> None:
    if not os.path.isfile(EXPERIMENT_CSV) or os.path.getsize(EXPERIMENT_CSV) == 0:
        with open(EXPERIMENT_CSV, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=_fieldnames()).writeheader()


def completed_session_count() -> int:
    """Count completed rows — used to pick the Latin-square slot."""
    if not os.path.isfile(EXPERIMENT_CSV):
        return 0
    with open(EXPERIMENT_CSV, encoding="utf-8") as f:
        return max(0, sum(1 for _ in f) - 1)


def log_session(
    *,
    participant_id: str,
    slot: int,
    condition_order: list[str],
    timestamp_start: datetime,
    timestamp_end: datetime,
    screens_visited: list[str],
    # {condition: [(seconds|None, correct|None, notes_str), ...]}
    task_clicks: dict[str, int],
    task_results: dict[str, list[tuple]],
    feedback: list[str],
) -> None:
    """Append one complete session row to experiment_sessions.csv."""
    _ensure_header()
    duration = round((timestamp_end - timestamp_start).total_seconds())

    row: dict = {
        "participant_id":   participant_id,
        "timestamp_start":  timestamp_start.isoformat(),
        "timestamp_end":    timestamp_end.isoformat(),
        "duration_seconds": duration,
        "slot":             slot,
        "condition_order":  json.dumps(condition_order),
        "screens_visited":  json.dumps(screens_visited),
    }

    for cond in experiment_config.CONDITIONS:
        row[f"{cond}_total_clicks"] = task_clicks.get(cond, 0)
        results = task_results.get(cond, [])
        for i in range(experiment_config.TASKS_PER_CONDITION):
            secs, correct, notes = results[i] if i < len(results) else (None, None, "")
            row[f"{cond}_task{i + 1}_seconds"] = "" if secs is None else round(secs)
            row[f"{cond}_task{i + 1}_correct"] = (
                "" if correct is None else ("yes" if correct else "no")
            )
            row[f"{cond}_task{i + 1}_notes"] = notes or ""

    for i, ans in enumerate(feedback):
        row[f"feedback_{i + 1}"] = ans

    with open(EXPERIMENT_CSV, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=_fieldnames()).writerow(row)
