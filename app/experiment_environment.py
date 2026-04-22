"""experiment_environment.py

Experiment session runner.

Flow:
  1. Pre-session form   — researcher enters participant ID, sees Latin-square slot & order
  2. Webview            — index.html served with all experiment features injected in-memory;
                          JS auto-advances through all conditions without researcher action;
                          task timings recorded automatically and POSTed on close
  3. Correctness form   — researcher marks correct/incorrect + optional notes per task
                          (times are already filled from JS; no stopwatch needed)
  4. Participant feedback form — 3 open-ended questions (verbal responses)
  5. CSV log            — one row appended to experiment_sessions.csv automatically
"""
from __future__ import annotations

import json
import os
import re
import socket
import socketserver
import shutil
import tempfile
import threading
import tkinter as tk
import uuid
from datetime import datetime, timezone
from tkinter import messagebox, scrolledtext

try:
    from . import _html_runner, experiment_config, session_logger
except ImportError:
    import _html_runner, experiment_config, session_logger


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _mmss_to_seconds(raw: str) -> float | None:
    raw = raw.strip()
    if not raw:
        return None
    if ":" in raw:
        parts = raw.split(":")
        try:
            return int(parts[0]) * 60 + float(parts[1])
        except (ValueError, IndexError):
            return None
    try:
        return float(raw)
    except ValueError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 1. Pre-session form
# ─────────────────────────────────────────────────────────────────────────────

def _pre_session_form(slot: int, order: list[str]) -> dict | None:
    """Show researcher setup form. Returns {'participant_id': str} or None if cancelled."""
    result: dict | None = None

    root = tk.Tk()
    root.title("Glucosee — New Experiment Session")
    root.geometry("500x300")
    root.resizable(False, False)

    tk.Label(root, text="Glucosee — Experiment Setup",
             font=("Arial", 14, "bold")).grid(
        row=0, column=0, columnspan=2, pady=(18, 14), padx=20, sticky="w")

    tk.Label(root, text="Participant ID", font=("Arial", 11)).grid(
        row=1, column=0, sticky="w", padx=20, pady=6)
    pid_var = tk.StringVar(value=str(uuid.uuid4())[:8].upper())
    tk.Entry(root, textvariable=pid_var, width=30).grid(
        row=1, column=1, padx=10, sticky="w")

    tk.Label(root, text="Latin-square slot", font=("Arial", 11)).grid(
        row=2, column=0, sticky="w", padx=20, pady=6)
    tk.Label(root, text=str(slot), font=("Arial", 11, "bold")).grid(
        row=2, column=1, sticky="w", padx=10)

    tk.Label(root, text="Condition order", font=("Arial", 11)).grid(
        row=3, column=0, sticky="w", padx=20, pady=6)
    order_str = "  →  ".join(experiment_config.CONDITION_LABELS[c] for c in order)
    tk.Label(root, text=order_str, font=("Arial", 10), fg="#1d4ed8",
             wraplength=320, justify="left").grid(row=3, column=1, sticky="w", padx=10)

    tk.Label(root, text="First visualisation", font=("Arial", 11)).grid(
        row=4, column=0, sticky="w", padx=20, pady=6)
    tk.Label(root, text=experiment_config.CONDITION_LABELS[order[0]],
             font=("Arial", 11, "bold"), fg="#059669").grid(
        row=4, column=1, sticky="w", padx=10)

    btn_frame = tk.Frame(root)
    btn_frame.grid(row=5, column=0, columnspan=2, pady=20)

    def on_start() -> None:
        nonlocal result
        pid = pid_var.get().strip()
        if not pid:
            messagebox.showwarning("Missing", "Please enter a participant ID.")
            return
        result = {"participant_id": pid}
        root.destroy()

    tk.Button(btn_frame, text="▶  Start session", command=on_start,
              width=18, height=2, bg="#1d4ed8", fg="black").pack(side="left", padx=8)
    tk.Button(btn_frame, text="Cancel", command=root.destroy,
              width=10, height=2).pack(side="left")

    root.mainloop()
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 2. HTML injection + logging HTTP endpoint
# ─────────────────────────────────────────────────────────────────────────────

def _inject_experiment(html: str, first_condition: str,
                       task_questions: dict,
                       condition_order: list[str]) -> str:
    """
    Takes the clean index.html string and injects:
      1. CSS for task banner + answer button
      2. HTML for task banner, answer button, task-intro screen
      3. JS for task management (openTaskIntro, startTask, etc.)
      4. Experiment boot script (sets __experimentMode, navigates to first intro)
    index.html is NEVER written to — all changes live only in this in-memory string.
    """
    # ── 1. CSS injection ─────────────────────────────────────────────────
    experiment_css = """
  /* ═══ EXPERIMENT OVERLAY STYLES ═══ */
  #task-banner {
    display: none; position: absolute; top: 0; left: 0; right: 0;
    z-index: 90; background: rgba(20,20,20,0.93);
    padding: 10px 14px 12px; border-radius: 0 0 14px 14px;
    backdrop-filter: blur(4px);
  }
  #task-banner-meta {
    font-size: 10px; color: #94a3b8; text-transform: uppercase;
    letter-spacing: 0.1em; margin-bottom: 4px;
  }
  #task-banner-text {
    font-size: 13px; color: #fff; font-weight: 600; line-height: 1.4;
  }
  #task-banner-progress { display: flex; gap: 5px; margin-top: 8px; }
  .task-dot {
    height: 4px; flex: 1; border-radius: 2px; background: #475569;
    transition: background 0.3s;
  }
  .task-dot.done   { background: #22c55e; }
  .task-dot.active { background: #fff; }
  #answer-wrap {
    display: none; position: absolute; bottom: 70px; left: 0; right: 0;
    z-index: 91; padding: 0 18px;
  }
  #answer-btn {
    width: 100%; padding: 15px; background: #22c55e;
    color: #1a1a1a; font-size: 15px; font-weight: 700;
    border: none; border-radius: 13px; cursor: pointer;
    box-shadow: 0 4px 16px rgba(34,197,94,0.35);
  }
"""
    html = re.sub(r'(</style>)', experiment_css + r'\1', html, count=1,
                  flags=re.IGNORECASE)

    # ── 2a. Absolutely-positioned overlays: task banner + answer button ───
    #        Injected before the status bar (position:absolute, no flow impact)
    experiment_overlays = """
  <!-- ═══ EXPERIMENT OVERLAYS ═══ -->
  <div id="task-banner">
    <div id="task-banner-meta">
      Task <span id="task-num">1</span> of <span id="task-total">3</span>
    </div>
    <div id="task-banner-text"></div>
    <div id="task-banner-progress"></div>
  </div>
  <div id="answer-wrap">
    <button id="answer-btn" onclick="submitTaskAnswer()">&#10003; &nbsp;This is my answer</button>
  </div>
"""
    html = re.sub(r'(<!-- Status bar -->)', experiment_overlays + r'\1', html,
                  count=1, flags=re.IGNORECASE)

    # ── 2b. Task-intro screen — injected as a flex sibling after the status
    #        bar, so it sits in the correct position within the phone layout ─
    experiment_intro_screen = """
  <!-- Thank-you screen shown after the very last task -->
  <div id="screen-thank-you" class="screen">
    <div class="content" style="justify-content:center;align-items:center;text-align:center;
                                padding:32px 28px;gap:0;">
      <div style="font-size:22px;font-weight:700;color:#1a1a1a;margin-bottom:18px;
                  line-height:1.3;">
        Thank you for your participation!
      </div>
      <div style="font-size:15px;color:#334155;line-height:1.6;
                  background:rgba(255,255,255,0.6);border-radius:14px;
                  padding:16px 18px;margin-bottom:32px;">
        We will now ask you to answer a few questions about this experiment.
      </div>
      <button onclick="finishExperiment()"
              style="width:100%;padding:18px;border-radius:14px;border:none;
                     background:#1a1a1a;color:#fff;font-size:17px;font-weight:700;
                     cursor:pointer;letter-spacing:0.02em;">
        Continue &#8250;
      </button>
    </div>
  </div>

  <!-- Task introduction screen (one per condition) -->
  <div id="screen-task-intro" class="screen">
    <div class="topbar">
      <button class="btn-back" onclick="goBack()">&#8592;</button>
      <span class="topbar-brand">Glucosee</span>
      <button class="btn-menu" onclick="openDrawer()">&#9776;</button>
    </div>
    <div class="content" style="overflow-y:auto;padding-bottom:24px;">
      <div style="background:rgba(255,255,255,0.7);border-radius:16px;
                  padding:18px 16px;margin-bottom:16px;">
        <div id="intro-label"
             style="font-size:13px;font-weight:700;color:#64748b;
                    text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;"></div>
        <div style="font-size:15px;font-weight:700;color:#1a1a1a;margin-bottom:10px;">
          Your task:
        </div>
        <div id="intro-task-text"
             style="font-size:15px;color:#1a1a1a;line-height:1.5;padding:10px 12px;
                    background:rgba(255,255,255,0.6);border-radius:10px;
                    border-left:4px solid #1a1a1a;"></div>
      </div>
      <div style="background:rgba(255,255,255,0.5);border-radius:14px;padding:14px 16px;
                  font-size:13px;color:#334155;line-height:1.55;">
        Find the answer in the visualisation as quickly as possible.<br>
        Tap on a measurement, then press <strong>"This is my answer"</strong>.<br>
        Further tasks will appear after each answer.
      </div>
      <div style="flex:1;min-height:20px;"></div>
      <button onclick="startTask()"
              style="width:100%;padding:16px;margin-top:20px;border-radius:14px;border:none;
                     background:#1a1a1a;color:#fff;font-size:17px;font-weight:700;
                     cursor:pointer;letter-spacing:0.02em;">
        Start &#8250;
      </button>
    </div>
  </div>

  <!-- Monthly bar screen (injected — never written to index.html) -->
  <div id="screen-blood-monthly-bar" class="screen">
    <div class="topbar">
      <button class="btn-back" onclick="goBack()">&#8592;</button>
      <span class="topbar-brand">Glucosee</span>
      <button class="btn-menu" onclick="openDrawer()">&#9776;</button>
    </div>
    <div class="chart-screen">
      <div class="chart-header">
        <div class="chart-header-title">Blood Sugar Levels</div>
        <div class="chart-header-sub">Monthly &#8212; Bar</div>
      </div>
      <div class="chart-scroll">
        <div id="monthly-bar-label" style="text-align:center;font-size:13px;font-weight:600;
             color:#334155;flex-shrink:0;padding:2px 0;"></div>
        <div style="display:flex;align-items:center;gap:4px;flex-shrink:0;">
          <button onclick="prevMonthBar()"
                  style="background:none;border:2px solid #1a1a1a;border-radius:50%;
                         width:30px;height:30px;font-size:16px;cursor:pointer;flex-shrink:0;">&#8249;</button>
          <div id="monthly-bar-chart"
               style="background:white;border-radius:10px;border:1px solid #e2e8f0;
                      padding:4px;flex:1;min-width:0;overflow:hidden;"></div>
          <button onclick="nextMonthBar()"
                  style="background:none;border:2px solid #1a1a1a;border-radius:50%;
                         width:30px;height:30px;font-size:16px;cursor:pointer;flex-shrink:0;">&#8250;</button>
        </div>
        <div class="tabs" style="gap:5px;flex-shrink:0;">
          <button class="tab active" onclick="setMonthBarPeriod(this,'All')"       style="font-size:11px;padding:8px 0;">All</button>
          <button class="tab"        onclick="setMonthBarPeriod(this,'Morning')"   style="font-size:11px;padding:8px 0;">Morning</button>
          <button class="tab"        onclick="setMonthBarPeriod(this,'Afternoon')" style="font-size:11px;padding:8px 0;">Afternoon</button>
          <button class="tab"        onclick="setMonthBarPeriod(this,'Evening')"   style="font-size:11px;padding:8px 0;">Evening</button>
          <button class="tab"        onclick="setMonthBarPeriod(this,'Night')"     style="font-size:11px;padding:8px 0;">Night</button>
        </div>
        <div id="monthly-bar-list" style="background:white;border-radius:10px;
             border:1px solid #e2e8f0;overflow:hidden;flex-shrink:0;font-size:13px;
             max-height:220px;overflow-y:auto;">
          <div class="chart-loading">Loading\u2026</div>
        </div>
      </div>
    </div>
  </div>

  <!-- Monthly line/dot screen (injected — never written to index.html) -->
  <div id="screen-blood-monthly-line" class="screen">
    <div class="topbar">
      <button class="btn-back" onclick="goBack()">&#8592;</button>
      <span class="topbar-brand">Glucosee</span>
      <button class="btn-menu" onclick="openDrawer()">&#9776;</button>
    </div>
    <div class="chart-screen">
      <div class="chart-header">
        <div class="chart-header-title">Blood Sugar Levels</div>
        <div class="chart-header-sub">Monthly &#8212; Line</div>
      </div>
      <div class="chart-scroll">
        <div id="monthly-line-label" style="text-align:center;font-size:13px;font-weight:600;
             color:#334155;flex-shrink:0;padding:2px 0;"></div>
        <div style="display:flex;align-items:center;gap:4px;flex-shrink:0;">
          <button onclick="prevMonthLine()"
                  style="background:none;border:2px solid #1a1a1a;border-radius:50%;
                         width:30px;height:30px;font-size:16px;cursor:pointer;flex-shrink:0;">&#8249;</button>
          <div id="monthly-line-chart"
               style="background:white;border-radius:10px;border:1px solid #e2e8f0;
                      padding:4px;flex:1;min-width:0;overflow:hidden;"></div>
          <button onclick="nextMonthLine()"
                  style="background:none;border:2px solid #1a1a1a;border-radius:50%;
                         width:30px;height:30px;font-size:16px;cursor:pointer;flex-shrink:0;">&#8250;</button>
        </div>
        <div class="tabs" style="gap:5px;flex-shrink:0;">
          <button class="tab active" onclick="setMonthLinePeriod(this,'All')"       style="font-size:11px;padding:8px 0;">All</button>
          <button class="tab"        onclick="setMonthLinePeriod(this,'Morning')"   style="font-size:11px;padding:8px 0;">Morning</button>
          <button class="tab"        onclick="setMonthLinePeriod(this,'Afternoon')" style="font-size:11px;padding:8px 0;">Afternoon</button>
          <button class="tab"        onclick="setMonthLinePeriod(this,'Evening')"   style="font-size:11px;padding:8px 0;">Evening</button>
          <button class="tab"        onclick="setMonthLinePeriod(this,'Night')"     style="font-size:11px;padding:8px 0;">Night</button>
        </div>
        <div id="monthly-line-list" style="background:white;border-radius:10px;
             border:1px solid #e2e8f0;overflow:hidden;flex-shrink:0;font-size:13px;
             max-height:220px;overflow-y:auto;">
          <div class="chart-loading">Loading\u2026</div>
        </div>
      </div>
    </div>
  </div>

  <!-- Weekly line-chart screen (injected — never written to index.html) -->
  <div id="screen-blood-weekly-line" class="screen">
    <div class="topbar">
      <button class="btn-back" onclick="goBack()">&#8592;</button>
      <span class="topbar-brand">Glucosee</span>
      <button class="btn-menu" onclick="openDrawer()">&#9776;</button>
    </div>
    <div class="chart-screen">
      <div class="chart-header">
        <div class="chart-header-title">Blood Sugar Levels</div>
        <div class="chart-header-sub">Weekly &#8212; Dot</div>
      </div>
      <div class="chart-scroll">
        <div id="weekly-line-label" style="text-align:center;font-size:13px;font-weight:600;
             color:#334155;flex-shrink:0;padding:2px 0;"></div>
        <div style="display:flex;align-items:center;gap:4px;flex-shrink:0;">
          <button onclick="prevWeekLine()"
                  style="background:none;border:2px solid #1a1a1a;border-radius:50%;
                         width:30px;height:30px;font-size:16px;cursor:pointer;flex-shrink:0;">&#8249;</button>
          <div id="weekly-line-chart"
               style="background:white;border-radius:10px;border:1px solid #e2e8f0;
                      padding:4px;flex:1;min-width:0;overflow:hidden;"></div>
          <button onclick="nextWeekLine()"
                  style="background:none;border:2px solid #1a1a1a;border-radius:50%;
                         width:30px;height:30px;font-size:16px;cursor:pointer;flex-shrink:0;">&#8250;</button>
        </div>
        <div class="tabs" style="gap:5px;flex-shrink:0;">
          <button class="tab active" onclick="setWeekLinePeriod(this,'All')"       style="font-size:11px;padding:8px 0;">All</button>
          <button class="tab"        onclick="setWeekLinePeriod(this,'Morning')"   style="font-size:11px;padding:8px 0;">Morning</button>
          <button class="tab"        onclick="setWeekLinePeriod(this,'Afternoon')" style="font-size:11px;padding:8px 0;">Afternoon</button>
          <button class="tab"        onclick="setWeekLinePeriod(this,'Evening')"   style="font-size:11px;padding:8px 0;">Evening</button>
          <button class="tab"        onclick="setWeekLinePeriod(this,'Night')"     style="font-size:11px;padding:8px 0;">Night</button>
        </div>
        <div id="weekly-line-list" style="background:white;border-radius:10px;
             border:1px solid #e2e8f0;overflow:hidden;flex-shrink:0;font-size:13px;
             max-height:220px;overflow-y:auto;">
          <div class="chart-loading">Loading\u2026</div>
        </div>
      </div>
    </div>
  </div>

  <!-- Daily bar-chart screen (injected — never written to index.html) -->
  <div id="screen-blood-daily-bar" class="screen">
    <div class="topbar">
      <button class="btn-back" onclick="goBack()">&#8592;</button>
      <span class="topbar-brand">Glucosee</span>
      <button class="btn-menu" onclick="openDrawer()">&#9776;</button>
    </div>
    <div class="chart-screen">
      <div class="chart-header">
        <div class="chart-header-title">Blood Sugar Levels</div>
        <div class="chart-header-sub">Daily — Bar</div>
      </div>
      <div class="chart-scroll">
        <div id="daily-bar-label" style="text-align:center;font-size:13px;font-weight:600;
             color:#334155;flex-shrink:0;padding:2px 0;"></div>
        <div style="display:flex;align-items:center;gap:4px;flex-shrink:0;">
          <button onclick="prevDayBar()"
                  style="background:none;border:2px solid #1a1a1a;border-radius:50%;
                         width:30px;height:30px;font-size:16px;cursor:pointer;flex-shrink:0;">&#8249;</button>
          <div id="daily-bar-chart"
               style="background:white;border-radius:10px;border:1px solid #e2e8f0;
                      padding:4px;flex:1;min-width:0;overflow:visible;"></div>
          <button onclick="nextDayBar()"
                  style="background:none;border:2px solid #1a1a1a;border-radius:50%;
                         width:30px;height:30px;font-size:16px;cursor:pointer;flex-shrink:0;">&#8250;</button>
        </div>
        <div class="tabs" style="gap:5px;flex-shrink:0;">
          <button class="tab active" onclick="setDayBarPeriod(this,'All')"       style="font-size:11px;padding:8px 0;">All</button>
          <button class="tab"        onclick="setDayBarPeriod(this,'Morning')"   style="font-size:11px;padding:8px 0;">Morning</button>
          <button class="tab"        onclick="setDayBarPeriod(this,'Afternoon')" style="font-size:11px;padding:8px 0;">Afternoon</button>
          <button class="tab"        onclick="setDayBarPeriod(this,'Evening')"   style="font-size:11px;padding:8px 0;">Evening</button>
          <button class="tab"        onclick="setDayBarPeriod(this,'Night')"     style="font-size:11px;padding:8px 0;">Night</button>
        </div>
        <div id="daily-bar-list" style="background:white;border-radius:10px;
             border:1px solid #e2e8f0;overflow:hidden;flex-shrink:0;font-size:13px;
             max-height:220px;overflow-y:auto;">
          <div class="chart-loading">Loading\u2026</div>
        </div>
      </div>
    </div>
  </div>
"""
    # Inject all experiment screens as flex siblings after the status bar
    html = re.sub(r'(<!-- SCREEN 1 — Home)', experiment_intro_screen + r'\1', html,
                  count=1, flags=re.IGNORECASE)

    # ── 3. Home screen tabs — left as plain navigate() since auto-advance
    #        means the participant never reaches the home screen during a session.

    # ── 4. Add onMeasurementClicked to Vega charts ────────────────────────
    html = html.replace(
        "if (item && item.datum && item.datum.dayKey) {\n            showReadings(item.datum.dayKey);\n          }",
        "if (item && item.datum && item.datum.dayKey) {\n            showReadings(item.datum.dayKey);\n            onMeasurementClicked();\n          }"
    )
    html = html.replace(
        "buildDailySpec(dayData, dayStr, currentDayFilter), { actions: false });",
        "buildDailySpec(dayData, dayStr, currentDayFilter), { actions: false })\n"
        "      .then(function(result) {\n"
        "        result.view.addEventListener('click', function(event, item) {\n"
        "          if (item && item.datum) onMeasurementClicked();\n"
        "        });\n"
        "      });"
    )
    html = html.replace(
        "buildWeeklySpec(weekData, currentWeekFilter), { actions: false });",
        "buildWeeklySpec(weekData, currentWeekFilter), { actions: false })\n"
        "      .then(function(result) {\n"
        "        result.view.addEventListener('click', function(event, item) {\n"
        "          if (item && item.datum) onMeasurementClicked();\n"
        "        });\n"
        "      });"
    )
    # Daily reading list rows
    html = html.replace(
        "return '<div style=\"display:flex;align-items:center;background:'+th.bg",
        "return '<div onclick=\"onMeasurementClicked()\" "
        "style=\"display:flex;align-items:center;cursor:pointer;background:'+th.bg"
    )

    # ── 5. Task management JS + experiment boot script ────────────────────
    experiment_js = f"""
  <!-- ═══ EXPERIMENT JS ═══ -->
  <script>
    window.__experimentMode  = true;
    window.__taskQuestions   = {json.dumps(task_questions)};
    window.__conditionOrder  = {json.dumps(condition_order)};
    window.__taskTimings     = {{}};

    var TASK_LABELS  = {{
      daily_line:   'Days \u2014 Graph A',
      daily_bar:    'Days \u2014 Graph B',
      weekly_bar:   'Weeks \u2014 Graph A',
      weekly_line:  'Weeks \u2014 Graph B',
      monthly:      'Months \u2014 Graph A',
      monthly_line: 'Months \u2014 Graph B',
      monthly_bar:  'Months \u2014 Graph C'
    }};
    var TASK_SCREENS = {{
      daily_line:   'screen-blood-daily',
      daily_bar:    'screen-blood-daily-bar',
      weekly_bar:   'screen-blood-weekly',
      weekly_line:  'screen-blood-weekly-line',
      monthly:      'screen-blood-data',
      monthly_line: 'screen-blood-monthly-line',
      monthly_bar:  'screen-blood-monthly-bar'
    }};

    var _activeCondition   = null;
    var _taskIdx           = 0;
    var _taskStartTime     = null;
    var _taskTimings       = {{}};
    var _pendingScreen     = null;
    var _conditionOrderIdx = 0;

    function openTaskIntro(condition) {{
      _activeCondition   = condition;
      _conditionOrderIdx = window.__conditionOrder.indexOf(condition);
      _taskIdx           = 0;
      _pendingScreen     = TASK_SCREENS[condition];
      var questions    = window.__taskQuestions[condition] || [];

      document.getElementById('intro-label').textContent =
        (TASK_LABELS[condition] || condition) + '  \u2014  Task 1 of ' + questions.length;
      document.getElementById('intro-task-text').textContent = questions[0] || '';
      navigate('screen-task-intro');
    }}

    function startTask() {{
      if (!_pendingScreen) return;
      _taskStartTime = Date.now();
      _updateTaskBanner();
      navigate(_pendingScreen);
    }}

    function onMeasurementClicked() {{
      if (!_activeCondition) return;
      document.getElementById('answer-wrap').style.display = 'block';
    }}

    function submitTaskAnswer() {{
      document.getElementById('answer-wrap').style.display = 'none';
      var elapsed = _taskStartTime ? (Date.now() - _taskStartTime) / 1000 : null;
      if (!_taskTimings[_activeCondition]) _taskTimings[_activeCondition] = [];
      _taskTimings[_activeCondition].push(elapsed);
      window.__taskTimings = _taskTimings;

      _taskIdx++;
      var questions = window.__taskQuestions[_activeCondition] || [];
      if (_taskIdx < questions.length) {{
        _taskStartTime = Date.now();
        _updateTaskBanner();
      }} else {{
        document.getElementById('task-banner').style.display = 'none';
        _activeCondition = null;
        _conditionOrderIdx++;
        var nextCond = window.__conditionOrder[_conditionOrderIdx];
        if (nextCond) {{
          openTaskIntro(nextCond);
        }} else {{
          navigate('screen-thank-you');
        }}
      }}
    }}

    function _updateTaskBanner() {{
      var questions = window.__taskQuestions[_activeCondition] || [];
      var total     = questions.length;
      document.getElementById('task-banner').style.display  = 'block';
      document.getElementById('task-num').textContent        = _taskIdx + 1;
      document.getElementById('task-total').textContent      = total;
      document.getElementById('task-banner-text').textContent = questions[_taskIdx] || '';
      var prog = document.getElementById('task-banner-progress');
      prog.innerHTML = '';
      for (var i = 0; i < total; i++) {{
        var dot = document.createElement('div');
        dot.className = 'task-dot ' +
          (i < _taskIdx ? 'done' : i === _taskIdx ? 'active' : '');
        prog.appendChild(dot);
      }}
    }}

    // ── Daily bar-chart helpers ───────────────────────────────────────────
    var currentDayBarFilter = 'All';

    function updateDailyBarLabel() {{
      var key = dailyStartDays[currentDayIdx];
      if (!key) return;
      var el = document.getElementById('daily-bar-label');
      if (el) el.textContent = new Date(key + 'T12:00:00').toLocaleDateString('en-GB',
        {{ weekday:'short', day:'numeric', month:'long', year:'numeric' }});
    }}

    function prevDayBar() {{
      if (currentDayIdx > 0) {{ currentDayIdx--; renderDailyBar(); }}
    }}
    function nextDayBar() {{
      if (currentDayIdx < dailyStartDays.length - 1) {{ currentDayIdx++; renderDailyBar(); }}
    }}

    function setDayBarPeriod(btn, period) {{
      var tabs = btn.closest('.tabs').querySelectorAll('.tab');
      for (var i = 0; i < tabs.length; i++) tabs[i].classList.remove('active');
      btn.classList.add('active');
      currentDayBarFilter = period;
      renderDailyBar();
    }}

    function buildDailyBarSpec(dayData, dayStr, filter) {{
      var enriched = dayData.map(function(d) {{
        return Object.assign({{}}, d, {{ isoTime: d.displayTime.toISOString() }});
      }});
      var startISO = dayStr + 'T00:00:00';
      var endISO   = dayStr + 'T23:59:59';
      var opacityBar = {{
        condition: [
          {{ test: "'" + filter + "' === 'All'",       value: 0.8 }},
          {{ test: "datum.period === '" + filter + "'", value: 1.0 }}
        ],
        value: 0.1
      }};
      return {{
        $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
        data: {{ values: enriched }},
        transform: [{{ calculate: "datum.observation > 10 ? 'High' : (datum.observation < 4.4 ? 'Low' : 'Normal')", as: 'status' }}],
        width: 220, height: 180,
        autosize: {{ type: 'fit', contains: 'padding' }},
        layer: [
          {{
            mark: {{ type: 'bar', width: 8, stroke: 'white', strokeWidth: 1,
                     tooltip: true, cursor: 'pointer' }},
            encoding: {{
              x: {{ field: 'isoTime', type: 'temporal',
                   scale: {{ domain: [startISO, endISO] }},
                   axis: {{ format: '%H:%M', labelFontSize: 10, labelColor: '#64748b',
                            ticks: false, domain: false, gridColor: '#f1f5f9', title: null }} }},
              y: {{ field: 'observation', type: 'quantitative',
                   scale: {{ domain: [0, 20] }},
                   axis: {{ labelFontSize: 10, labelColor: '#64748b',
                            ticks: false, domain: false, gridColor: '#f1f5f9' }},
                   title: 'mmol/l' }},
              color: {{ field: 'period', type: 'nominal',
                       scale: {{ domain: ['Morning','Afternoon','Evening','Night'],
                                range: ['#f59e0b','#10b981','#6366f1','#64748b'] }},
                       legend: null }},
              opacity: opacityBar,
              tooltip: [
                {{ field: 'isoTime',     type: 'temporal',    title: 'Time',    format: '%H:%M' }},
                {{ field: 'observation', type: 'quantitative', title: 'Glucose', format: '.1f'  }},
                {{ field: 'period',      type: 'nominal',      title: 'Period'                  }}
              ]
            }}
          }},
          {{
            mark: {{ type: 'circle', size: 50, stroke: 'white', strokeWidth: 1 }},
            transform: [{{ filter: 'datum.observation > 10 || datum.observation < 4.4' }}],
            encoding: {{
              x: {{ field: 'isoTime', type: 'temporal' }},
              y: {{ field: 'observation', type: 'quantitative' }},
              color: {{ condition: {{ test: 'datum.observation > 10', value: '#ef4444' }}, value: '#3b82f6' }},
              opacity: opacityBar
            }}
          }}
        ],
        config: {{ view: {{ stroke: null }} }}
      }};
    }}

    function renderDailyBar() {{
      if (!chartData || !dailyStartDays || !dailyStartDays.length) return;
      updateDailyBarLabel();
      var dayStr  = dailyStartDays[currentDayIdx];
      var dayData = chartData.filter(function(d){{ return d.dayKey === dayStr; }})
                             .sort(function(a,b){{ return a.displayTime - b.displayTime; }});

      vegaEmbed(document.getElementById('daily-bar-chart'),
                buildDailyBarSpec(dayData, dayStr, currentDayBarFilter), {{ actions: false }})
        .then(function(result) {{
          result.view.addEventListener('click', function(event, item) {{
            if (item && item.datum) onMeasurementClicked();
          }});
        }});

      var listDiv = document.getElementById('daily-bar-list');
      var rows = dayData.map(function(r) {{
        var hi  = currentDayBarFilter === 'All' || r.period === currentDayBarFilter;
        var th  = statusTheme(r.observation);
        var col = PERIOD_COLORS[r.period] || '#94a3b8';
        var ts2 = r.displayTime.toLocaleTimeString([],{{hour:'2-digit',minute:'2-digit',hour12:false}});
        var bl  = (hi && currentDayBarFilter !== 'All') ? col : 'transparent';
        var shortL = {{ Morning:'M', Afternoon:'A', Evening:'E', Night:'N' }}[r.period] || '?';
        return '<div onclick="onMeasurementClicked()" '
          + 'style="display:flex;align-items:center;cursor:pointer;background:'+th.bg
          +';border-bottom:1px solid #f1f5f9;border-left:4px solid '+bl
          +';opacity:'+(hi?'1':'0.2')+'">'
          +'<div style="flex:2;padding:6px 10px;color:'+th.text+';font-weight:600;white-space:nowrap;">'+ts2+'</div>'
          +'<div style="flex:1;padding:6px 4px;text-align:center;">'
          +'<span style="background:'+col+';color:#fff;padding:2px 8px;border-radius:6px;font-size:0.76em;">'+shortL+'</span></div>'
          +'<div style="flex:1.5;padding:6px 10px 6px 0;text-align:right;font-weight:700;color:'+th.text+';white-space:nowrap;font-size:0.85em;">'
          +r.observation.toFixed(1)+'<small style="font-weight:400;font-size:0.78em;"> mmol/l</small></div>'
          +'</div>';
      }}).join('');

      listDiv.innerHTML = dayData.length
        ? '<div style="padding:8px 13px;font-weight:700;border-bottom:1px solid #f1f5f9;'
          +'display:flex;justify-content:space-between;align-items:center;">'
          +'<span style="color:#334155;font-size:13px;">Daily log</span>'
          +'<span style="background:#f1f5f9;color:#64748b;padding:2px 8px;border-radius:20px;font-size:0.75em;">'
          +dayData.length+' readings</span></div>'
          +'<div style="display:flex;background:#f8fafc;border-bottom:2px solid #e2e8f0;'
          +'font-size:0.68em;color:#64748b;font-weight:600;text-transform:uppercase;">'
          +'<div style="flex:2;padding:5px 10px;">Time</div>'
          +'<div style="flex:1;padding:5px 4px;text-align:center;">Period</div>'
          +'<div style="flex:1.5;padding:5px 10px 5px 0;text-align:right;">Glucose</div></div>'
          + rows
        : '<div class="chart-loading">No readings for this day</div>';
    }}

    // ── Monthly bar helpers ───────────────────────────────────────────────
    var currentMonthBarIdx    = 0;
    var currentMonthBarFilter = 'All';
    var _monthBarInitialized  = false;

    function updateMonthlyBarLabel() {{
      var key = availableMonths[currentMonthBarIdx];
      if (!key) return;
      var d  = new Date(key + '-15T12:00:00');
      var el = document.getElementById('monthly-bar-label');
      if (el) el.textContent = d.toLocaleDateString('en-GB', {{ month: 'long', year: 'numeric' }});
    }}

    function prevMonthBar() {{
      if (currentMonthBarIdx > 0) {{ currentMonthBarIdx--; renderMonthlyBar(); }}
    }}
    function nextMonthBar() {{
      if (currentMonthBarIdx < availableMonths.length - 1) {{ currentMonthBarIdx++; renderMonthlyBar(); }}
    }}

    function setMonthBarPeriod(btn, period) {{
      var tabs = btn.closest('.tabs').querySelectorAll('.tab');
      for (var i = 0; i < tabs.length; i++) tabs[i].classList.remove('active');
      btn.classList.add('active');
      currentMonthBarFilter = period;
      renderMonthlyBar();
    }}

    function buildMonthlyBarSpec(monthData, filter, startIso, endIso) {{
      var enriched = monthData.map(function(d) {{
        return Object.assign({{}}, d, {{
          isoTime: d.displayTime.toISOString(),
          status:  d.observation > 10 ? 'High' : (d.observation < 4.4 ? 'Low' : 'Normal')
        }});
      }});
      var periodColors = ['#f59e0b', '#10b981', '#6366f1', '#64748b'];
      var periodDomain = ['Morning', 'Afternoon', 'Evening', 'Night'];

      var opacityBar = filter === 'All'
        ? {{ value: 0.8 }}
        : {{ condition: {{ test: "datum.period === '" + filter + "'", value: 1.0 }}, value: 0.07 }};
      var opacityDot = filter === 'All'
        ? {{ value: 1.0 }}
        : {{ condition: {{ test: "datum.period === '" + filter + "'", value: 1.0 }}, value: 0.05 }};

      return {{
        $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
        data: {{ values: enriched }},
        width: 'container', height: 180,
        autosize: {{ type: 'fit', contains: 'padding' }},
        layer: [
          {{
            mark: {{ type: 'bar', width: 5, stroke: 'white', strokeWidth: 0.5, tooltip: true }},
            encoding: {{
              x: {{ field: 'isoTime', type: 'temporal', title: null,
                   scale: {{ domain: [startIso, endIso] }},
                   axis: {{ format: '%d %b', labelAngle: -45, labelFontSize: 9,
                            labelColor: '#64748b', ticks: false, domain: false,
                            grid: true, gridColor: '#f1f5f9' }} }},
              y: {{ field: 'observation', type: 'quantitative', title: 'mmol/l',
                   scale: {{ domain: [0, 20] }},
                   axis: {{ labelFontSize: 10, labelColor: '#64748b',
                            ticks: false, domain: false, gridColor: '#f1f5f9' }} }},
              color: {{ field: 'period', type: 'nominal',
                       scale: {{ domain: periodDomain, range: periodColors }}, legend: null }},
              opacity: opacityBar,
              tooltip: [
                {{ field: 'isoTime',      type: 'temporal',    title: 'Time',    format: '%A, %b %e \u00b7 %H:%M' }},
                {{ field: 'observation',  type: 'quantitative', title: 'Glucose', format: '.1f' }},
                {{ field: 'period',       type: 'nominal',      title: 'Period' }},
                {{ field: 'status',       type: 'nominal',      title: 'Status' }}
              ]
            }}
          }},
          {{
            mark: {{ type: 'circle', size: 35, stroke: 'white', strokeWidth: 1 }},
            transform: [{{ filter: 'datum.observation > 10 || datum.observation < 4.4' }}],
            encoding: {{
              x: {{ field: 'isoTime', type: 'temporal' }},
              y: {{ field: 'observation', type: 'quantitative' }},
              color: {{ condition: {{ test: 'datum.observation > 10', value: '#ef4444' }}, value: '#3b82f6' }},
              opacity: opacityDot
            }}
          }}
        ],
        config: {{ view: {{ stroke: null }} }}
      }};
    }}

    function renderMonthlyBar() {{
      if (!chartData || !availableMonths || !availableMonths.length) return;
      if (!_monthBarInitialized) {{
        currentMonthBarIdx   = availableMonths.length - 1;
        _monthBarInitialized = true;
      }}
      updateMonthlyBarLabel();
      var key    = availableMonths[currentMonthBarIdx];
      var parts  = key.split('-');
      var yr     = parseInt(parts[0]), mo = parseInt(parts[1]) - 1;
      var startTs  = new Date(yr, mo, 1).getTime();
      var endTs    = new Date(yr, mo + 1, 1).getTime();
      var startIso = new Date(startTs).toISOString();
      var endIso   = new Date(endTs).toISOString();
      var monthData = chartData.filter(function(d) {{
        var t = d.displayTime.getTime(); return t >= startTs && t < endTs;
      }});

      vegaEmbed(document.getElementById('monthly-bar-chart'),
                buildMonthlyBarSpec(monthData, currentMonthBarFilter, startIso, endIso),
                {{ actions: false }})
        .then(function(result) {{
          result.view.addEventListener('click', function(event, item) {{
            if (item && item.datum) onMeasurementClicked();
          }});
        }});

      var listDiv = document.getElementById('monthly-bar-list');
      var sorted  = monthData.slice().sort(function(a,b){{ return a.displayTime - b.displayTime; }});
      var rows = sorted.map(function(r) {{
        var hi  = currentMonthBarFilter === 'All' || r.period === currentMonthBarFilter;
        var th  = statusTheme(r.observation);
        var col = PERIOD_COLORS[r.period] || '#94a3b8';
        var ds  = r.displayTime.toLocaleDateString('en-GB',{{weekday:'short',day:'numeric',month:'short'}});
        var ts2 = r.displayTime.toLocaleTimeString([],{{hour:'2-digit',minute:'2-digit',hour12:false}});
        var bl  = (hi && currentMonthBarFilter !== 'All') ? col : 'transparent';
        var shortL = {{ Morning:'M', Afternoon:'A', Evening:'E', Night:'N' }}[r.period] || '?';
        return '<div onclick="onMeasurementClicked()" '
          + 'style="display:flex;align-items:center;cursor:pointer;background:'+th.bg
          +';border-bottom:1px solid #f1f5f9;border-left:4px solid '+bl
          +';opacity:'+(hi?'1':'0.18')+'">'
          +'<div style="flex:2.5;padding:6px 8px;">'
          +'<span style="color:'+th.text+';font-weight:600;display:block;font-size:0.78em;">'+ds+'</span>'
          +'<span style="color:#94a3b8;font-size:0.72em;">'+ts2+'</span></div>'
          +'<div style="flex:1;padding:6px 4px;text-align:center;">'
          +'<span style="background:'+col+';color:#fff;padding:2px 6px;border-radius:6px;font-size:0.72em;">'+shortL+'</span></div>'
          +'<div style="flex:1.5;padding:6px 10px 6px 0;text-align:right;font-weight:700;color:'+th.text+';white-space:nowrap;font-size:0.85em;">'
          +r.observation.toFixed(1)+'<small style="font-weight:400;font-size:0.78em;"> mmol/l</small></div>'
          +'</div>';
      }}).join('');

      listDiv.innerHTML = sorted.length
        ? '<div style="padding:8px 13px;font-weight:700;border-bottom:1px solid #f1f5f9;'
          +'display:flex;justify-content:space-between;align-items:center;">'
          +'<span style="color:#334155;font-size:13px;">Monthly log</span>'
          +'<span style="background:#f1f5f9;color:#64748b;padding:2px 8px;border-radius:20px;font-size:0.75em;">'
          +sorted.length+' readings</span></div>'
          +'<div style="display:flex;background:#f8fafc;border-bottom:2px solid #e2e8f0;'
          +'font-size:0.68em;color:#64748b;font-weight:600;text-transform:uppercase;">'
          +'<div style="flex:2.5;padding:5px 8px;">Date &amp; Time</div>'
          +'<div style="flex:1;padding:5px 4px;text-align:center;">Period</div>'
          +'<div style="flex:1.5;padding:5px 10px 5px 0;text-align:right;">Glucose</div></div>'
          + rows
        : '<div class="chart-loading">No data for this month</div>';
    }}

    // ── Monthly line/dot helpers ──────────────────────────────────────────
    var currentMonthLineIdx    = 0;
    var currentMonthLineFilter = 'All';
    var _monthLineInitialized  = false;

    function updateMonthlyLineLabel() {{
      var key = availableMonths[currentMonthLineIdx]; // 'YYYY-MM'
      if (!key) return;
      var d  = new Date(key + '-15T12:00:00');
      var el = document.getElementById('monthly-line-label');
      if (el) el.textContent = d.toLocaleDateString('en-GB', {{ month: 'long', year: 'numeric' }});
    }}

    function prevMonthLine() {{
      if (currentMonthLineIdx > 0) {{ currentMonthLineIdx--; renderMonthlyLine(); }}
    }}
    function nextMonthLine() {{
      if (currentMonthLineIdx < availableMonths.length - 1) {{ currentMonthLineIdx++; renderMonthlyLine(); }}
    }}

    function setMonthLinePeriod(btn, period) {{
      var tabs = btn.closest('.tabs').querySelectorAll('.tab');
      for (var i = 0; i < tabs.length; i++) tabs[i].classList.remove('active');
      btn.classList.add('active');
      currentMonthLineFilter = period;
      renderMonthlyLine();
    }}

    function buildMonthlyLineSpec(monthData, filter, startTs, endTs) {{
      var enriched = monthData.map(function(d) {{
        return Object.assign({{}}, d, {{ isoTime: d.displayTime.toISOString() }});
      }});
      var startIso     = new Date(startTs).toISOString();
      var endIso       = new Date(endTs).toISOString();
      var periodColors = ['#f59e0b', '#10b981', '#6366f1', '#64748b'];
      var periodDomain = ['Morning', 'Afternoon', 'Evening', 'Night'];
      var periodColor  = filter !== 'All'
        ? periodColors[periodDomain.indexOf(filter)] : null;

      var xEnc = {{ field: 'isoTime', type: 'temporal', title: null,
                    scale: {{ domain: [startIso, endIso] }},
                    axis: {{ format: '%d %b', labelAngle: -45, labelFontSize: 10,
                             labelColor: '#64748b', ticks: false, domain: false,
                             grid: true, gridColor: '#f1f5f9' }} }};
      var yEnc = {{ field: 'observation', type: 'quantitative', title: 'mmol/l',
                    scale: {{ domain: [0, 20] }},
                    axis: {{ labelFontSize: 10, labelColor: '#64748b',
                             ticks: false, domain: false, gridColor: '#f1f5f9' }} }};

      var opacityDot = filter === 'All'
        ? {{ value: 1.0 }}
        : {{ condition: {{ test: "datum.period === '" + filter + "'", value: 1.0 }}, value: 0.07 }};

      var layers = [
        {{ mark: {{ type: 'rect', color: '#dcfce7', opacity: 0.45 }},
           encoding: {{ y: {{ datum: 4.4, type: 'quantitative' }}, y2: {{ datum: 10 }} }} }},
        {{ mark: {{ type: 'rule', color: '#3b82f6', strokeDash: [4,2], size: 1 }},
           encoding: {{ y: {{ datum: 4.4, type: 'quantitative' }} }} }},
        {{ mark: {{ type: 'rule', color: '#ef4444', strokeDash: [4,2], size: 1 }},
           encoding: {{ y: {{ datum: 10, type: 'quantitative' }} }} }}
      ];

      if (filter !== 'All' && periodColor) {{
        // Thin faint lines for all periods in the background
        layers.push({{
          mark: {{ type: 'line', interpolate: 'monotone', size: 1.2,
                   strokeJoin: 'round', opacity: 0.18 }},
          encoding: {{
            x: xEnc, y: yEnc,
            color: {{ field: 'period', type: 'nominal',
                      scale: {{ domain: periodDomain, range: periodColors }}, legend: null }},
            detail: {{ field: 'period' }}
          }}
        }});
        // Area shading for selected period
        layers.push({{
          mark: {{ type: 'area', interpolate: 'monotone', color: periodColor,
                   opacity: 0.15, line: false }},
          transform: [{{ filter: "datum.period === '" + filter + "'" }}],
          encoding: {{ x: xEnc, y: yEnc }}
        }});
        // Bold line for selected period
        layers.push({{
          mark: {{ type: 'line', interpolate: 'monotone', size: 3,
                   strokeJoin: 'round', color: periodColor }},
          transform: [{{ filter: "datum.period === '" + filter + "'" }}],
          encoding: {{ x: xEnc, y: yEnc }}
        }});
      }}

      // Dots — always on top
      layers.push({{
        mark: {{ type: 'circle', size: 50, stroke: 'white', strokeWidth: 1.5, tooltip: true }},
        encoding: {{
          x: xEnc, y: yEnc,
          color: {{
            condition: {{ test: 'datum.observation > 10 || datum.observation < 4.4',
                          value: '#ef4444' }},
            field: 'period', type: 'nominal',
            scale: {{ domain: periodDomain, range: periodColors }}, legend: null
          }},
          opacity: opacityDot,
          tooltip: [
            {{ field: 'isoTime',     type: 'temporal',    title: 'Time',    format: '%e %b \u00b7 %H:%M' }},
            {{ field: 'observation', type: 'quantitative', title: 'Glucose', format: '.1f' }},
            {{ field: 'period',      type: 'nominal',      title: 'Period' }}
          ]
        }}
      }});

      return {{
        $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
        data: {{ values: enriched }},
        width: 'container', height: 180,
        autosize: {{ type: 'fit', contains: 'padding' }},
        layer: layers,
        config: {{ view: {{ stroke: null }} }}
      }};
    }}

    function renderMonthlyLine() {{
      if (!chartData || !availableMonths || !availableMonths.length) return;
      if (!_monthLineInitialized) {{
        currentMonthLineIdx   = availableMonths.length - 1;
        _monthLineInitialized = true;
      }}
      updateMonthlyLineLabel();
      var key    = availableMonths[currentMonthLineIdx]; // 'YYYY-MM'
      var parts  = key.split('-');
      var yr     = parseInt(parts[0]), mo = parseInt(parts[1]) - 1;
      var startTs = new Date(yr, mo, 1).getTime();
      var endTs   = new Date(yr, mo + 1, 1).getTime();
      var monthData = chartData.filter(function(d) {{
        var t = d.displayTime.getTime(); return t >= startTs && t < endTs;
      }});

      vegaEmbed(document.getElementById('monthly-line-chart'),
                buildMonthlyLineSpec(monthData, currentMonthLineFilter, startTs, endTs),
                {{ actions: false }})
        .then(function(result) {{
          result.view.addEventListener('click', function(event, item) {{
            if (item && item.datum) onMeasurementClicked();
          }});
        }});

      var listDiv = document.getElementById('monthly-line-list');
      var sorted  = monthData.slice().sort(function(a,b){{ return a.displayTime - b.displayTime; }});
      var rows = sorted.map(function(r) {{
        var hi  = currentMonthLineFilter === 'All' || r.period === currentMonthLineFilter;
        var th  = statusTheme(r.observation);
        var col = PERIOD_COLORS[r.period] || '#94a3b8';
        var ds  = r.displayTime.toLocaleDateString('en-GB',{{day:'numeric',month:'short'}});
        var ts2 = r.displayTime.toLocaleTimeString([],{{hour:'2-digit',minute:'2-digit',hour12:false}});
        var bl  = (hi && currentMonthLineFilter !== 'All') ? col : 'transparent';
        var shortL = {{ Morning:'M', Afternoon:'A', Evening:'E', Night:'N' }}[r.period] || '?';
        return '<div onclick="onMeasurementClicked()" '
          + 'style="display:flex;align-items:center;cursor:pointer;background:'+th.bg
          +';border-bottom:1px solid #f1f5f9;border-left:4px solid '+bl
          +';opacity:'+(hi?'1':'0.18')+'">'
          +'<div style="flex:2.5;padding:6px 8px;">'
          +'<span style="color:'+th.text+';font-weight:600;display:block;font-size:0.78em;">'+ds+'</span>'
          +'<span style="color:#94a3b8;font-size:0.72em;">'+ts2+'</span></div>'
          +'<div style="flex:1;padding:6px 4px;text-align:center;">'
          +'<span style="background:'+col+';color:#fff;padding:2px 6px;border-radius:6px;font-size:0.72em;">'+shortL+'</span></div>'
          +'<div style="flex:1.5;padding:6px 10px 6px 0;text-align:right;font-weight:700;color:'+th.text+';white-space:nowrap;font-size:0.85em;">'
          +r.observation.toFixed(1)+'<small style="font-weight:400;font-size:0.78em;"> mmol/l</small></div>'
          +'</div>';
      }}).join('');

      listDiv.innerHTML = sorted.length
        ? '<div style="padding:8px 13px;font-weight:700;border-bottom:1px solid #f1f5f9;'
          +'display:flex;justify-content:space-between;align-items:center;">'
          +'<span style="color:#334155;font-size:13px;">Monthly log</span>'
          +'<span style="background:#f1f5f9;color:#64748b;padding:2px 8px;border-radius:20px;font-size:0.75em;">'
          +sorted.length+' readings</span></div>'
          +'<div style="display:flex;background:#f8fafc;border-bottom:2px solid #e2e8f0;'
          +'font-size:0.68em;color:#64748b;font-weight:600;text-transform:uppercase;">'
          +'<div style="flex:2.5;padding:5px 8px;">Date &amp; Time</div>'
          +'<div style="flex:1;padding:5px 4px;text-align:center;">Period</div>'
          +'<div style="flex:1.5;padding:5px 10px 5px 0;text-align:right;">Glucose</div></div>'
          + rows
        : '<div class="chart-loading">No data for this month</div>';
    }}

    // ── Weekly line-chart helpers ─────────────────────────────────────────
    var currentWeekLineIdx    = 0;
    var currentWeekLineFilter = 'All';
    var _weekLineInitialized  = false;

    function updateWeeklyLineLabel() {{
      var ts  = weeklyStartDays[currentWeekLineIdx];
      var s   = new Date(ts);
      var e   = new Date(ts + 6*24*60*60*1000);
      var fmt = function(d){{ return d.toLocaleDateString('en-GB',{{day:'numeric',month:'short'}}); }};
      var iso = isoWeekNumber(s);
      var el  = document.getElementById('weekly-line-label');
      if (el) el.textContent =
        iso.year + '  \u00b7  Week ' + iso.week + '  (' + fmt(s) + ' \u2013 ' + fmt(e) + ')';
    }}

    function prevWeekLine() {{
      if (currentWeekLineIdx > 0) {{ currentWeekLineIdx--; renderWeeklyLine(); }}
    }}
    function nextWeekLine() {{
      if (currentWeekLineIdx < weeklyStartDays.length - 1) {{ currentWeekLineIdx++; renderWeeklyLine(); }}
    }}

    function setWeekLinePeriod(btn, period) {{
      var tabs = btn.closest('.tabs').querySelectorAll('.tab');
      for (var i = 0; i < tabs.length; i++) tabs[i].classList.remove('active');
      btn.classList.add('active');
      currentWeekLineFilter = period;
      renderWeeklyLine();
    }}

    function buildWeeklyLineSpec(weekData, filter, startTs, endTs) {{
      var enriched = weekData.map(function(d) {{
        return Object.assign({{}}, d, {{ isoTime: d.displayTime.toISOString() }});
      }});
      var startIso     = new Date(startTs).toISOString();
      var endIso       = new Date(endTs).toISOString();
      var periodColors = ['#f59e0b', '#10b981', '#6366f1', '#64748b'];
      var periodDomain = ['Morning', 'Afternoon', 'Evening', 'Night'];
      var periodColor  = filter !== 'All'
        ? periodColors[periodDomain.indexOf(filter)] : null;

      // x / y shared encoding shortcuts
      var xEnc = {{ field: 'isoTime', type: 'temporal', title: null,
                    scale: {{ domain: [startIso, endIso] }},
                    axis: {{ format: '%a %d', labelAngle: 0, labelFontSize: 10,
                             labelColor: '#64748b', ticks: false, domain: false,
                             grid: true, gridColor: '#f1f5f9' }} }};
      var yEnc = {{ field: 'observation', type: 'quantitative', title: 'mmol/l',
                    scale: {{ domain: [0, 20] }},
                    axis: {{ labelFontSize: 10, labelColor: '#64748b',
                             ticks: false, domain: false, gridColor: '#f1f5f9' }} }};

      // Dot opacity: All → full for all; period → full for match, faint for others
      var opacityDot = filter === 'All'
        ? {{ value: 1.0 }}
        : {{ condition: {{ test: "datum.period === '" + filter + "'", value: 1.0 }}, value: 0.07 }};

      // Base layers always present
      var layers = [
        // Normal-range band
        {{ mark: {{ type: 'rect', color: '#dcfce7', opacity: 0.45 }},
           encoding: {{ y: {{ datum: 4.4, type: 'quantitative' }}, y2: {{ datum: 10 }} }} }},
        // Threshold rules
        {{ mark: {{ type: 'rule', color: '#3b82f6', strokeDash: [4,2], size: 1 }},
           encoding: {{ y: {{ datum: 4.4, type: 'quantitative' }} }} }},
        {{ mark: {{ type: 'rule', color: '#ef4444', strokeDash: [4,2], size: 1 }},
           encoding: {{ y: {{ datum: 10, type: 'quantitative' }} }} }}
      ];

      // Period selected → add background thin lines + area shading + bold line for that period
      if (filter !== 'All' && periodColor) {{
        // Thin faint lines for ALL periods in the background
        layers.push({{
          mark: {{ type: 'line', interpolate: 'monotone', size: 1.2,
                   strokeJoin: 'round', opacity: 0.18 }},
          encoding: {{
            x: xEnc, y: yEnc,
            color: {{ field: 'period', type: 'nominal',
                      scale: {{ domain: periodDomain, range: periodColors }}, legend: null }},
            detail: {{ field: 'period' }}
          }}
        }});
        // Area shading for selected period
        layers.push({{
          mark: {{ type: 'area', interpolate: 'monotone', color: periodColor, opacity: 0.15,
                   line: false }},
          transform: [{{ filter: "datum.period === '" + filter + "'" }}],
          encoding: {{ x: xEnc, y: yEnc }}
        }});
        // Bold line for selected period
        layers.push({{
          mark: {{ type: 'line', interpolate: 'monotone', size: 3,
                   strokeJoin: 'round', color: periodColor }},
          transform: [{{ filter: "datum.period === '" + filter + "'" }}],
          encoding: {{ x: xEnc, y: yEnc }}
        }});
      }}

      // Dots — always on top
      layers.push({{
        mark: {{ type: 'circle', size: 60, stroke: 'white', strokeWidth: 1.5, tooltip: true }},
        encoding: {{
          x: xEnc,
          y: yEnc,
          color: {{
            condition: {{ test: 'datum.observation > 10 || datum.observation < 4.4',
                          value: '#ef4444' }},
            field: 'period', type: 'nominal',
            scale: {{ domain: periodDomain, range: periodColors }}, legend: null
          }},
          opacity: opacityDot,
          tooltip: [
            {{ field: 'isoTime',     type: 'temporal',    title: 'Time',    format: '%a %e %b \u00b7 %H:%M' }},
            {{ field: 'observation', type: 'quantitative', title: 'Glucose', format: '.1f' }},
            {{ field: 'period',      type: 'nominal',      title: 'Period' }}
          ]
        }}
      }});

      return {{
        $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
        data: {{ values: enriched }},
        width: 'container', height: 180,
        autosize: {{ type: 'fit', contains: 'padding' }},
        layer: layers,
        config: {{ view: {{ stroke: null }} }}
      }};
    }}

    function renderWeeklyLine() {{
      if (!chartData || !weeklyStartDays || !weeklyStartDays.length) return;
      if (!_weekLineInitialized) {{
        currentWeekLineIdx   = weeklyStartDays.length - 1;
        _weekLineInitialized = true;
      }}
      updateWeeklyLineLabel();
      var startTs  = weeklyStartDays[currentWeekLineIdx];
      var endTs    = startTs + 7*24*60*60*1000;
      var weekData = chartData.filter(function(d) {{
        var t = d.displayTime.getTime(); return t >= startTs && t < endTs;
      }});

      vegaEmbed(document.getElementById('weekly-line-chart'),
                buildWeeklyLineSpec(weekData, currentWeekLineFilter, startTs, endTs),
                {{ actions: false }})
        .then(function(result) {{
          result.view.addEventListener('click', function(event, item) {{
            if (item && item.datum) onMeasurementClicked();
          }});
        }});

      var listDiv = document.getElementById('weekly-line-list');
      var sorted  = weekData.slice().sort(function(a,b){{ return a.displayTime - b.displayTime; }});
      var rows = sorted.map(function(r) {{
        var hi  = currentWeekLineFilter === 'All' || r.period === currentWeekLineFilter;
        var th  = statusTheme(r.observation);
        var col = PERIOD_COLORS[r.period] || '#94a3b8';
        var ds  = r.displayTime.toLocaleDateString('en-GB',{{weekday:'short',day:'numeric',month:'short'}});
        var ts2 = r.displayTime.toLocaleTimeString([],{{hour:'2-digit',minute:'2-digit',hour12:false}});
        var bl  = (hi && currentWeekLineFilter !== 'All') ? col : 'transparent';
        var shortL = {{ Morning:'M', Afternoon:'A', Evening:'E', Night:'N' }}[r.period] || '?';
        return '<div onclick="onMeasurementClicked()" '
          + 'style="display:flex;align-items:center;cursor:pointer;background:'+th.bg
          +';border-bottom:1px solid #f1f5f9;border-left:4px solid '+bl
          +';opacity:'+(hi?'1':'0.18')+'">'
          +'<div style="flex:2.5;padding:6px 8px;">'
          +'<span style="color:'+th.text+';font-weight:600;display:block;font-size:0.78em;">'+ds+'</span>'
          +'<span style="color:#94a3b8;font-size:0.72em;">'+ts2+'</span></div>'
          +'<div style="flex:1;padding:6px 4px;text-align:center;">'
          +'<span style="background:'+col+';color:#fff;padding:2px 6px;border-radius:6px;font-size:0.72em;">'+shortL+'</span></div>'
          +'<div style="flex:1.5;padding:6px 10px 6px 0;text-align:right;font-weight:700;color:'+th.text+';white-space:nowrap;font-size:0.85em;">'
          +r.observation.toFixed(1)+'<small style="font-weight:400;font-size:0.78em;"> mmol/l</small></div>'
          +'</div>';
      }}).join('');

      listDiv.innerHTML = sorted.length
        ? '<div style="padding:8px 13px;font-weight:700;border-bottom:1px solid #f1f5f9;'
          +'display:flex;justify-content:space-between;align-items:center;">'
          +'<span style="color:#334155;font-size:13px;">Weekly log</span>'
          +'<span style="background:#f1f5f9;color:#64748b;padding:2px 8px;border-radius:20px;font-size:0.75em;">'
          +sorted.length+' readings</span></div>'
          +'<div style="display:flex;background:#f8fafc;border-bottom:2px solid #e2e8f0;'
          +'font-size:0.68em;color:#64748b;font-weight:600;text-transform:uppercase;">'
          +'<div style="flex:2.5;padding:5px 8px;">Date &amp; Time</div>'
          +'<div style="flex:1;padding:5px 4px;text-align:center;">Period</div>'
          +'<div style="flex:1.5;padding:5px 10px 5px 0;text-align:right;">Glucose</div></div>'
          + rows
        : '<div class="chart-loading">No data for this week</div>';
    }}

    // Navigate to the first task intro on load
    document.addEventListener('DOMContentLoaded', function () {{
      var _origNav = window.navigate;
      window.navigate = function(id) {{
        window.__visitLog = window.__visitLog || [];
        window.__visitLog.push({{ screen: id, t: new Date().toISOString() }});
        _origNav(id);
        if (id === 'screen-blood-daily-bar')    renderDailyBar();
        if (id === 'screen-blood-weekly-line')  renderWeeklyLine();
        if (id === 'screen-blood-monthly-line') renderMonthlyLine();
        if (id === 'screen-blood-monthly-bar')  renderMonthlyBar();
      }};
      openTaskIntro({json.dumps(first_condition)});
    }});

    function finishExperiment() {{
      var payload = JSON.stringify({{
        visited:     window.__visitLog    || [],
        taskTimings: window.__taskTimings || {{}}
      }});
      var xhr = new XMLHttpRequest();
      xhr.open('POST', '/experiment_log', false);
      xhr.setRequestHeader('Content-Type', 'application/json');
      try {{ xhr.send(payload); }} catch(e) {{}}
      try {{ pywebview.api.close_window(); }} catch(e) {{ window.close(); }}
    }}

    // Fallback: also send on beforeunload in case the window is closed manually
    window.addEventListener('beforeunload', function () {{
      var payload = JSON.stringify({{
        visited:     window.__visitLog    || [],
        taskTimings: window.__taskTimings || {{}}
      }});
      var xhr = new XMLHttpRequest();
      xhr.open('POST', '/experiment_log', false);
      xhr.setRequestHeader('Content-Type', 'application/json');
      try {{ xhr.send(payload); }} catch(e) {{}}
    }});
  </script>
"""
    return re.sub(r'(</body>)', experiment_js + r'\1', html, count=1,
                  flags=re.IGNORECASE)


def _patch_html_runner_with_log(log_store: list) -> None:
    """Replace _html_runner's server factory with one that also handles POST /experiment_log,
    and patch _html_runner.run to expose a js_api so JS can close the window cleanly."""
    import http.server
    import webview

    # ── Python API exposed to JS via pywebview ────────────────────────────
    # Using a threading.Event so destroy() is never called from within the
    # JS API callback thread (which conflicts with the Cocoa GUI thread on macOS).
    _done_event = threading.Event()

    class _ExperimentApi:
        def close_window(self):           # called by JS: pywebview.api.close_window()
            _done_event.set()             # signal — actual destroy happens in monitor thread

    def _monitor_and_close():
        """Runs in a background thread via webview.start(func=…).
        Waits for the done signal, then destroys the window on a safe callsite."""
        _done_event.wait()
        import time as _t; _t.sleep(0.05)   # let the JS API callback return cleanly
        if webview.windows:
            webview.windows[0].destroy()

    def patched_start(html: str) -> int:
        tmpdir = tempfile.mkdtemp()
        with open(os.path.join(tmpdir, "index.html"), "w", encoding="utf-8") as fh:
            fh.write(html)
        data_src = os.path.join(_html_runner.BASE_DIR, "data")
        if os.path.isdir(data_src):
            shutil.copytree(data_src, os.path.join(tmpdir, "data"))

        class LoggingHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **kw):
                super().__init__(*a, directory=tmpdir, **kw)

            def do_POST(self):
                if self.path == "/experiment_log":
                    length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(length)
                    try:
                        payload = json.loads(body)
                        log_store.clear()
                        log_store.append(payload)
                    except Exception:
                        pass
                    self.send_response(204)
                    self.end_headers()
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, *_):
                pass

        with socket.socket() as s:
            s.bind(("", 0))
            port = s.getsockname()[1]
        server = socketserver.TCPServer(("127.0.0.1", port), LoggingHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return port

    _html_runner._start_html_server = patched_start

    # ── Patch run() to pass js_api to the webview window ─────────────────
    def patched_run(title: str, html: str) -> None:
        port = _html_runner._start_html_server(html)
        import time
        time.sleep(0.2)
        webview.create_window(
            title,
            url=f"http://127.0.0.1:{port}/index.html",
            width=1280, height=860, resizable=True,
            js_api=_ExperimentApi(),
        )
        webview.start(func=_monitor_and_close)

    _html_runner.run = patched_run


# ─────────────────────────────────────────────────────────────────────────────
# 3. Per-condition timing form
# ─────────────────────────────────────────────────────────────────────────────

def _condition_timing_form(
    condition: str, condition_number: int, total: int,
    auto_times: list | None = None
) -> list[tuple]:
    """
    Researcher timing form for one condition (3 tasks).
    Returns list of (seconds|None, correct|None, notes_str) per task.
    """
    tasks = experiment_config.TASKS_BY_CONDITION[condition]
    results: list[tuple] = [(None, None, "")] * len(tasks)

    label = experiment_config.CONDITION_LABELS[condition]
    root = tk.Tk()
    root.title(f"Timing — {label}  ({condition_number}/{total})")
    root.geometry(f"720x{160 + len(tasks) * 115}")
    root.resizable(False, True)

    tk.Label(root, text=f"Condition {condition_number}/{total}:  {label}",
             font=("Arial", 13, "bold")).pack(pady=(14, 2), padx=20, anchor="w")
    tk.Label(root,
             text="Enter time as MM:SS or plain seconds.  "
                  "Tick 'Correct' if the participant answered right.  "
                  "Leave time blank if the task was skipped.",
             font=("Arial", 9), fg="#64748b", wraplength=680).pack(padx=20, anchor="w")

    frame = tk.Frame(root, padx=20, pady=8)
    frame.pack(fill="both", expand=True)

    time_vars:     list[tk.StringVar]  = []
    corr_vars:     list[tk.BooleanVar] = []
    notes_widgets: list[tk.Text]       = []

    for i, task in enumerate(tasks):
        tk.Frame(frame, height=1, bg="#e2e8f0").pack(fill="x", pady=(10, 4))

        # Question row
        q_row = tk.Frame(frame)
        q_row.pack(fill="x")
        tk.Label(q_row, text=f"Task {i + 1}", font=("Arial", 10, "bold"),
                 width=7, anchor="w").pack(side="left")
        tk.Label(q_row, text=task["question"], font=("Arial", 10),
                 wraplength=390, justify="left", anchor="w").pack(
            side="left", padx=6, fill="x", expand=True)

        # Correct answer (researcher reference only)
        tk.Label(frame, text=f"   ✓  Correct answer: {task['answer']}",
                 font=("Arial", 9, "italic"), fg="#059669", anchor="w").pack(
            fill="x", padx=4)

        # Input row
        inp = tk.Frame(frame)
        inp.pack(fill="x", pady=3)

        tk.Label(inp, text="Time:", font=("Arial", 10), width=5,
                 anchor="w").pack(side="left")
        tvar = tk.StringVar()
        # Pre-fill with auto-recorded time from the app if available
        auto_t = (auto_times or [])[i] if auto_times and i < len(auto_times) else None
        if auto_t is not None:
            mins, secs = divmod(round(auto_t), 60)
            tvar.set(f"{mins}:{secs:02d}")
        time_vars.append(tvar)
        tk.Entry(inp, textvariable=tvar, width=8,
                 font=("Arial", 11)).pack(side="left", padx=(0, 4))
        tk.Label(inp, text="MM:SS", font=("Arial", 8),
                 fg="#94a3b8").pack(side="left", padx=(0, 20))

        cvar = tk.BooleanVar(value=False)
        corr_vars.append(cvar)
        tk.Checkbutton(inp, text="Participant answered correctly",
                       variable=cvar, font=("Arial", 10)).pack(side="left", padx=(0, 16))

        tk.Label(inp, text="Notes:", font=("Arial", 10)).pack(side="left")
        nt = tk.Text(inp, height=1, width=26, font=("Arial", 10),
                     relief="solid", bd=1)
        nt.pack(side="left", padx=4)
        notes_widgets.append(nt)

    def on_save() -> None:
        for i, (tv, cv, nw) in enumerate(zip(time_vars, corr_vars, notes_widgets)):
            results[i] = (
                _mmss_to_seconds(tv.get()),
                cv.get(),
                nw.get("1.0", tk.END).strip(),
            )
        root.destroy()

    btn_bar = tk.Frame(root, padx=20, pady=12)
    btn_bar.pack(fill="x", side="bottom")
    next_lbl = "Save & finish →" if condition_number == total else "Save & next condition →"
    tk.Button(btn_bar, text=next_lbl, command=on_save,
              width=24, height=2, bg="#059669", fg="black").pack(side="right", padx=6)
    tk.Button(btn_bar, text="Skip condition", command=root.destroy,
              width=14, height=2).pack(side="right")

    root.mainloop()
    return results


# ─────────────────────────────────────────────────────────────────────────────
# 4. Post-session feedback form
# ─────────────────────────────────────────────────────────────────────────────

def _feedback_form() -> list[str]:
    """Collect participant verbal feedback (recorded by researcher) after all conditions."""
    answers = [""] * len(experiment_config.FEEDBACK_QUESTIONS)

    root = tk.Tk()
    root.title("Post-session — Participant Feedback")
    root.geometry(f"620x{140 + len(experiment_config.FEEDBACK_QUESTIONS) * 110}")
    root.resizable(False, True)

    tk.Label(root, text="Participant Feedback",
             font=("Arial", 13, "bold")).pack(pady=(14, 2), padx=20, anchor="w")
    tk.Label(root,
             text="Record the participant's verbal responses to each question below.",
             font=("Arial", 9), fg="#64748b").pack(padx=20, anchor="w")

    frame = tk.Frame(root, padx=20, pady=8)
    frame.pack(fill="both", expand=True)
    text_widgets: list[scrolledtext.ScrolledText] = []

    for i, q in enumerate(experiment_config.FEEDBACK_QUESTIONS):
        tk.Label(frame, text=f"Q{i + 1}:  {q}", font=("Arial", 10, "bold"),
                 wraplength=560, justify="left", anchor="w").pack(
            fill="x", pady=(10, 2))
        tw = scrolledtext.ScrolledText(frame, height=3, font=("Arial", 10),
                                       wrap="word", relief="solid", bd=1)
        tw.pack(fill="x")
        text_widgets.append(tw)

    def on_save() -> None:
        for i, tw in enumerate(text_widgets):
            answers[i] = tw.get("1.0", tk.END).strip()
        root.destroy()

    btn_bar = tk.Frame(root, padx=20, pady=12)
    btn_bar.pack(fill="x", side="bottom")
    tk.Button(btn_bar, text="Save & finish session", command=on_save,
              width=22, height=2, bg="#059669", fg="black").pack(side="right", padx=6)
    tk.Button(btn_bar, text="Skip feedback", command=root.destroy,
              width=14, height=2).pack(side="right")

    root.mainloop()
    return answers


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def run(_legacy_arg: str = "") -> None:
    """Full experiment session: setup → webview → timing × 3 → feedback → CSV."""

    slot  = session_logger.completed_session_count()
    order = experiment_config.full_order_for_slot(slot)

    # ── 1. Pre-session form ───────────────────────────────────────────────
    meta = _pre_session_form(slot, order)
    if meta is None:
        return  # researcher cancelled

    participant_id  = meta["participant_id"]
    condition_first = order[0]
    first_screen_id = experiment_config.SCREEN_IDS[condition_first]
    ts_start        = datetime.now(timezone.utc)

    # ── 2. Load, patch and serve index.html ──────────────────────────────
    html_path = os.path.join(_html_runner.BASE_DIR, "index.html")
    with open(html_path, encoding="utf-8") as fh:
        html = fh.read()

    task_questions = {
        cond: [t["question"] for t in tasks]
        for cond, tasks in experiment_config.TASKS_BY_CONDITION.items()
    }

    log_store: list = []
    _patch_html_runner_with_log(log_store)
    html = _inject_experiment(html, condition_first, task_questions, order)

    _html_runner.run(f"Glucosee — Experiment [{participant_id}]", html)

    ts_end          = datetime.now(timezone.utc)
    payload         = log_store[0] if log_store else {}
    screens_visited = [e["screen"] for e in payload.get("visited", []) if "screen" in e]
    app_task_timings = payload.get("taskTimings", {})  # {condition: [sec, sec, sec]}

    # ── 3. Build task results directly from JS-recorded timings ─────────
    task_results: dict[str, list[tuple]] = {}
    for cond in order:
        auto_times = app_task_timings.get(cond, [])
        task_results[cond] = [(t, None, "") for t in auto_times]

    # ── 4. Participant feedback ───────────────────────────────────────────
    feedback = _feedback_form()

    # ── 5. Write to experiment_sessions.csv ──────────────────────────────
    session_logger.log_session(
        participant_id  = participant_id,
        slot            = slot,
        condition_order = order,
        timestamp_start = ts_start,
        timestamp_end   = ts_end,
        screens_visited = screens_visited,
        task_results    = task_results,
        feedback        = feedback,
    )


if __name__ == "__main__":
    run()
