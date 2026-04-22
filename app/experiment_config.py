"""experiment_config.py

Experiment structure:
  The participant always goes through Days -> Weeks -> Months.
  Within Days, Weeks and Months they each see two different graphs.
  The ORDER within each pair is independently counterbalanced (alternating on even/odd slots).

  Section order is always:
    Days Graph 1 -> Days Graph 2 -> Weeks Graph 1 -> Weeks Graph 2
    -> Months Graph 1 -> Months Graph 2

  Conditions:
    daily_line    = Line / dot plot          (screen-blood-daily)
    daily_bar     = Bar chart daily view     (screen-blood-daily-bar) <- injected
    weekly_bar    = Weekly bar plot          (screen-blood-weekly)
    weekly_line   = Weekly dot plot          (screen-blood-weekly-line) <- injected
    monthly       = Calendar heatmap         (screen-blood-data)
    monthly_bar   = Monthly bar chart        (screen-blood-monthly-bar) <- injected
    monthly_line  = Monthly dot/line plot    (screen-blood-monthly-line) <- injected

  Each condition has exactly 3 timed tasks.
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
_DAILY_TASKS: list[dict] = [
    {"question": "How many observations are outside of the normal area on July 20th?",
     "answer":   "2"},
    {"question": "Which time frame generally has the most observations: morning, afternoon, evening or night?",
     "answer":   "Evening"},
    {"question": "At what time does the lowest measured observation take place on September 14th?",
     "answer":   "19:48"},
]

_WEEKLY_TASKS: list[dict] = [
    {"question": "Which week has the most observations outside the normal area?",
     "answer":   "Week 29 & Week 31 (14 observations each)"},
    {"question": "Which time frame has the lowest observations over the week: morning, afternoon, evening or night?",
     "answer":   "Evening"},
    {"question": "What is the biggest leap in glucose level between 2 observations?",
     "answer":   "July 26th to July 27th: 2.9 mmol/L to 13.2 mmol/L (difference: 10.3)"},
]

_MONTHLY_TASKS: list[dict] = [
    {"question": "How big is the gap in data? Mark from where to where it goes.",
     "answer":   "8 days - from August 7th to August 14th"},
    {"question": "Which day has the very lowest measurement overall?",
     "answer":   "July 26th, 2.9 mmol/L"},
    {"question": "Which day has the very highest measurement overall?",
     "answer":   "July 14th & July 30th, 16.7 mmol/L"},
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
