"""experiment_config.py

Experiment structure:
  The participant always goes through Days -> Weeks -> Months.
  Within Days, Weeks and Months they each see two different graphs.
  The ORDER within each pair is independently counterbalanced (alternating on even/odd slots).

  Section order is always:
    Days Graph 1 -> Days Graph 2 -> Weeks Graph 1 -> Weeks Graph 2
    -> Months Graph 1 -> Months Graph 2 -> Months Graph 3

  Conditions:
    daily_line    = Line / dot plot          (screen-blood-daily)
    daily_bar     = Bar chart daily view     (screen-blood-daily-bar) <- injected
    weekly_bar    = Weekly bar plot          (screen-blood-weekly)
    weekly_line   = Weekly dot plot          (screen-blood-weekly-line) <- injected
    monthly       = Calendar heatmap         (screen-blood-data)
    monthly_bar   = Monthly bar chart        (screen-blood-monthly-bar) <- injected
    monthly_line  = Monthly dot/line plot    (screen-blood-monthly-line) <- injected

  Each condition has exactly 3 timed tasks.

criteria types used in TASKS_BY_CONDITION:
  "single_point" — last click matches dayKey + time (±tolerance_min minutes)
  "specific_date"— last click has the given dayKey
  "period"       — last click has the given period string
  "date_range"   — last click dayKey falls in [from, to]
  "low_in_month" — dayKey in month AND obs < threshold, or dayKey in valid_dates list
  "two_dates"    — all required dates appear somewhere in clicked_points
  "two_times"    — two specific times (± tolerance) appear in clicked_points on dayKey
"""
from __future__ import annotations

# ── Conditions ────────────────────────────────────────────────────────────────
CONDITIONS: list[str] = [
    "daily_line",
    "daily_bar",
    "weekly_bar",
    "weekly_line",
    "monthly",
    "monthly_line",
    "monthly_bar",
]

CONDITION_LABELS: dict[str, str] = {
    "daily_line":   "Days - Graph A (Line)",
    "daily_bar":    "Days - Graph B (Bar)",
    "weekly_bar":   "Weeks - Graph A (Bar)",
    "weekly_line":  "Weeks - Graph B (Dot)",
    "monthly":      "Months - Graph A (Calendar)",
    "monthly_line": "Months - Graph B (Line/Dot)",
    "monthly_bar":  "Months - Graph C (Bar)",
}

SCREEN_IDS: dict[str, str] = {
    "daily_line":   "screen-blood-daily",
    "daily_bar":    "screen-blood-daily-bar",
    "weekly_bar":   "screen-blood-weekly",
    "weekly_line":  "screen-blood-weekly-line",
    "monthly":      "screen-blood-data",
    "monthly_line": "screen-blood-monthly-line",
    "monthly_bar":  "screen-blood-monthly-bar",
}

# ── Tasks ──────────────────────────────────────────────────────────────────────
# July 2024 dates that have at least one reading below 4.4 mmol/L (computed from data)
_JULY_LOW_DATES: list[str] = [
    "2024-07-02", "2024-07-06", "2024-07-09", "2024-07-10",
    "2024-07-12", "2024-07-14", "2024-07-15", "2024-07-16",
    "2024-07-18", "2024-07-20", "2024-07-21", "2024-07-26",
]

_DAILY_TASKS: list[dict] = [
    {
        "question": "29. juli: Click the point that represents the start of a downward trend.",
        "answer":   "11:59, Glucose 13.7 (Afternoon, July 29)",
        "criteria": {
            "type":          "single_point",
            "dayKey":        "2024-07-29",
            "minute_of_day": 11 * 60 + 59,  # 719
            "tolerance_min": 5,
        },
    },
    {
        "question": "24. aug: Click on the observation that requires the most immediate attention.",
        "answer":   "21:32, Glucose 10.8 (Evening, Aug 24)",
        "criteria": {
            "type":          "single_point",
            "dayKey":        "2024-08-24",
            "minute_of_day": 21 * 60 + 32,  # 1292
            "tolerance_min": 5,
        },
    },
    {
        "question": "19. july: Click on the interval where the glucose level changes the least.",
        "answer":   "Both 12:21 and 18:20 on July 19 (9.8 → 9.9 mmol/L)",
        "criteria": {
            "type":          "two_times",
            "dayKey":        "2024-07-19",
            "times":         [12 * 60 + 21, 18 * 60 + 20],  # minutes of day
            "tolerance_min": 10,
        },
    },
]

_WEEKLY_TASKS: list[dict] = [
    {
        "question": "Week 29: Click a random observation on the day of the week that shows the worst glucose control.",
        "answer":   "Any observation on Sunday July 21",
        "criteria": {
            "type": "specific_date",
            "date": "2024-07-21",
        },
    },
    {
        "question": "Week 30: Click on the time period (Morning, Afternoon, Evening, Night) that appears most inconsistent across the week.",
        "answer":   "Any Night observation",
        "criteria": {
            "type":   "period",
            "period": "Night",
        },
    },
    {
        "question": "Week 26: Click on the two consecutive days where the glucose levels changed the most.",
        "answer":   "Friday July 26 and Saturday July 27",
        "criteria": {
            "type":  "two_dates",
            "dates": ["2024-07-26", "2024-07-27"],
        },
    },
]

_MONTHLY_TASKS: list[dict] = [
    {
        "question": "August: Click on the week that has the most missing data.",
        "answer":   "Any day between Aug 4 – Aug 17 (inclusive)",
        "criteria": {
            "type": "date_range",
            "from": "2024-08-04",
            "to":   "2024-08-17",
        },
    },
    {
        "question": "July: Click on a day where the glucose level dropped below the normal range.",
        "answer":   "Any July date with a reading below 4.4 mmol/L",
        "criteria": {
            "type":         "low_in_month",
            "month_prefix": "2024-07",
            "threshold":    4.4,
            "valid_dates":  _JULY_LOW_DATES,
        },
    },
    {
        "question": "September: Click on the week that shows the highest overall glucose levels.",
        "answer":   "Any day between Sep 1 – Sep 7 (inclusive)",
        "criteria": {
            "type": "date_range",
            "from": "2024-09-01",
            "to":   "2024-09-07",
        },
    },
]

TASKS_BY_CONDITION: dict[str, list[dict]] = {
    "daily_line":   _DAILY_TASKS,
    "daily_bar":    _DAILY_TASKS,
    "weekly_bar":   _WEEKLY_TASKS,
    "weekly_line":  _WEEKLY_TASKS,
    "monthly":      _MONTHLY_TASKS,
    "monthly_line": _MONTHLY_TASKS,
    "monthly_bar":  _MONTHLY_TASKS,
}

TASKS_PER_CONDITION: int = 3

FEEDBACK_QUESTIONS: list[str] = [
    "How clear and easy to read did you find each visualisation?",
    "Which visualisation did you find easiest to use for locating information?",
    "Any other comments or suggestions?",
]

# ── Randomisation ──────────────────────────────────────────────────────────────
_DAILY_ORDERS: list[list[str]] = [
    ["daily_line", "daily_bar"],
    ["daily_bar",  "daily_line"],
]

_WEEKLY_ORDERS: list[list[str]] = [
    ["weekly_bar",  "weekly_line"],
    ["weekly_line", "weekly_bar"],
]

_MONTHLY_ORDERS: list[list[str]] = [
    ["monthly",      "monthly_line", "monthly_bar"],   # slot 0
    ["monthly",      "monthly_bar",  "monthly_line"],  # slot 1
    ["monthly_line", "monthly",      "monthly_bar"],   # slot 2
    ["monthly_line", "monthly_bar",  "monthly"],       # slot 3
    ["monthly_bar",  "monthly",      "monthly_line"],  # slot 4
    ["monthly_bar",  "monthly_line", "monthly"],       # slot 5
]


def full_order_for_slot(slot: int, conditions: list[str] | None = None) -> list[str]:
    """Return the full 7-condition order for a given participant slot."""
    daily_pair   = _DAILY_ORDERS[slot % len(_DAILY_ORDERS)]
    weekly_pair  = _WEEKLY_ORDERS[slot % len(_WEEKLY_ORDERS)]
    monthly_trio = _MONTHLY_ORDERS[slot % len(_MONTHLY_ORDERS)]
    return daily_pair + weekly_pair + monthly_trio