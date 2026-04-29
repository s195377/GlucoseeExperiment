"""test_environment.py

Contains all screens (Info, Writing, Likert, Comparative) and the CSV data
layer for the glucose tracking test environment.

Entry point: run()
"""

import csv
import os
import tkinter as tk
from tkinter import messagebox
import uuid

# ── Paths ────────────────────────────────────────────────────────────────────

CSV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions.csv")

# ── Text constants ────────────────────────────────────────────────────────────

DUMMY_INSTRUCTIONS = (
    "Thank you for taking the time to help us with this evaluation!.\n\n"
    "First, we would like you to go through some tasks while you look at our prototype."
    "As you go through these tasks, we want you to think out loud. \n"
    "That means saying exactly what is going through your mind—what you are noticing,\n "
    "what is confusing you, and why you are making the choices you make.\n\n"

    "Secondly, we would like you to answer a short questionnaire related to the prototype you just went through.\n\n"
    
    "Please remember, this is not a test of your abilities; it is a test of the charts themselves. \n"
    "There are no right or wrong answers, and your honest feedback is the most helpful thing for us. \n"
    "If you go quiet for a while, we might gently remind you to keep talking. \n\n"
    
    "Do you have any questions before we start?"
)

WRITING_PROMPT = (
    "Task 1: Imagine you are reviewing this person's/your own glucose log for the day to help them/you understand their health patterns. As you look through the daily data, please talk out loud about what you see. I'd like you to identify which time of day looks the most difficult for them to manage—specifically look for the time when their levels are the most unstable, swinging both too high and too low—and describe what you think might be causing those fluctuations and how clear it is too see.\n"
    "\n\n"
    "Task 2: Look at the data for the week. Does there seem to be any specific patterns between the different time periods (morning, afternoon, evening)? What could be causing these differences?"
    "\n\n"
    "Task 3: Look at the data for the month. Are there any concerning trends to address? "
)

# ── Questionnaire content ─────────────────────────────────────────────────────

SHORT_TERM_QUESTIONS = [
    "When in ‘days’ visualization, the color scheme makes it easier to understand glucose levels.",
    "When in ‘days’ visualization, It is easy to see if the glucose measurement is within the normal level.",
    "The ‘weeks’ visualization is easier to navigate than the ‘days’ visualization.",
    "The time period buttons (morning, afternoon, evening, night) are a relevant feature.",
]

LONG_TERM_QUESTIONS = [
    "It is easier to navigate glucose levels when all days are available.",
    "It is clear how the ‘average’ button works.",
    "Long term tendencies of glucose levels are visible.",
    "I would like to be able to choose a different visualization (bar plot/dot plot) when viewing an entire month.",
]

SCALE_LABELS = ["Strongly\nDisagree", "Disagree", "Neutral", "Agree", "Strongly\nAgree"]

COMPARATIVE_OPTIONS = [
    "Short-Term Advice (Specific actions to take right now)",
    "Long-Term Insights (Patterns and trends over months/seasons)",
    "Both are equally valuable",
    "Neither is particularly valuable",
]

CSV_HEADERS = [
    "test_id", "thinking_aloud",
    "Q1", "Q2", "Q3", "Q4",
    "Q5", "Q6", "Q7", "Q8",
    "comparative_choice", "comparative_explanation",
]


# ── Data layer ────────────────────────────────────────────────────────────────

def save_full_session(
    test_id: str,
    thinking_aloud: str,
    short_responses: list,
    long_responses: list,
    comparative_choice: str,
    comparative_explanation: str,
) -> None:
    """Write one complete session row to the CSV file."""
    file_exists = os.path.isfile(CSV_FILE)
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(CSV_HEADERS)
        writer.writerow(
            [test_id, thinking_aloud]
            + short_responses
            + long_responses
            + [comparative_choice, comparative_explanation]
        )


# ── Comparative screen ────────────────────────────────────────────────────────

def open_comparative_screen(
    parent: tk.Tk,
    test_id: str,
    thinking_aloud: str,
    short_responses: list,
    long_responses: list,
) -> None:
    """Open the comparative value screen."""
    win = tk.Toplevel(parent)
    win.title("Comparative Value")
    win.geometry("900x480")
    win.minsize(720, 400)
    win.grab_set()

    tk.Label(
        win,
        text="Comparative Value",
        font=("Arial", 13, "bold"),
    ).pack(pady=(18, 14))

    content = tk.Frame(win, padx=24)
    content.pack(fill="both", expand=True)
    content.columnconfigure(0, weight=1, uniform="col")
    content.columnconfigure(1, weight=1, uniform="col")
    content.rowconfigure(0, weight=1)

    # Left column: radio buttons
    left = tk.LabelFrame(
        content, text="Your preference", font=("Arial", 11, "bold"), padx=16, pady=12
    )
    left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

    tk.Label(
        left,
        text="Which type of insight do you find more valuable for your daily life?",
        wraplength=320,
        justify="left",
        font=("Arial", 10),
    ).pack(anchor="w", pady=(0, 12))

    choice_var = tk.StringVar(value="")
    for option in COMPARATIVE_OPTIONS:
        tk.Radiobutton(
            left,
            text=option,
            variable=choice_var,
            value=option,
            wraplength=320,
            justify="left",
            anchor="w",
            font=("Arial", 10),
        ).pack(anchor="w", pady=4)

    # Right column: text explanation
    right = tk.LabelFrame(
        content, text="Your explanation", font=("Arial", 11, "bold"), padx=16, pady=12
    )
    right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
    right.rowconfigure(1, weight=1)
    right.columnconfigure(0, weight=1)

    tk.Label(
        right,
        text="Please explain your choice above",
        justify="left",
        font=("Arial", 10),
    ).grid(row=0, column=0, sticky="w", pady=(0, 8))

    explanation_text = tk.Text(
        right,
        font=("Arial", 10),
        wrap="word",
        relief="solid",
        bd=1,
    )
    explanation_text.grid(row=1, column=0, sticky="nsew")
    explanation_text.focus_set()

    # Bottom bar
    bottom = tk.Frame(win, padx=24, pady=16)
    bottom.pack(fill="x", side="bottom")

    def on_submit() -> None:
        if not choice_var.get():
            messagebox.showwarning("Incomplete", "Please select an option before submitting.")
            return
        save_full_session(
            test_id,
            thinking_aloud,
            short_responses,
            long_responses,
            choice_var.get(),
            explanation_text.get("1.0", tk.END).strip(),
        )
        win.destroy()

    tk.Button(bottom, text="Submit", command=on_submit, width=14, height=2).pack(side="right")


# ── Likert screen ─────────────────────────────────────────────────────────────

def _build_likert_section(frame: tk.LabelFrame, questions: list, var_list: list) -> None:
    """Populate a frame with scale-label header row and one radio-button row per question."""
    for col, label in enumerate(SCALE_LABELS, start=1):
        tk.Label(
            frame, text=label, font=("Arial", 9), justify="center", width=9
        ).grid(row=0, column=col, padx=4, pady=(0, 10))

    for row, q_text in enumerate(questions, start=1):
        var = tk.IntVar(value=0)
        var_list.append(var)

        lbl = tk.Label(
            frame,
            text=q_text,
            justify="left",
            anchor="nw",
            font=("Arial", 10),
        )
        lbl.grid(row=row, column=0, sticky="ew", padx=(0, 18), pady=8)
        lbl.bind("<Configure>", lambda e, l=lbl: l.config(wraplength=max(1, e.width - 6)))

        for col, val in enumerate([1, 2, 3, 4, 5], start=1):
            tk.Radiobutton(frame, variable=var, value=val).grid(
                row=row, column=col, padx=4, pady=8
            )

    frame.columnconfigure(0, weight=1)


def open_likert_screen(parent: tk.Tk, test_id: str, thinking_aloud: str) -> None:
    """Open the Likert questionnaire screen."""
    win = tk.Toplevel(parent)
    win.title("Questionnaire")
    win.geometry("1100x590")
    win.minsize(920, 500)
    win.grab_set()

    tk.Label(
        win,
        text="Please rate the following statements",
        font=("Arial", 13, "bold"),
    ).pack(pady=(18, 14))

    content = tk.Frame(win, padx=24)
    content.pack(fill="both", expand=True)
    content.columnconfigure(0, weight=1, uniform="col")
    content.columnconfigure(1, weight=1, uniform="col")
    content.rowconfigure(0, weight=1)

    short_vars: list = []
    long_vars: list = []

    left_frame = tk.LabelFrame(
        content, text="Short-term Insight", font=("Arial", 11, "bold"), padx=16, pady=12
    )
    left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

    right_frame = tk.LabelFrame(
        content, text="Long-term Insight", font=("Arial", 11, "bold"), padx=16, pady=12
    )
    right_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

    _build_likert_section(left_frame, SHORT_TERM_QUESTIONS, short_vars)
    _build_likert_section(right_frame, LONG_TERM_QUESTIONS, long_vars)

    bottom = tk.Frame(win, padx=24, pady=16)
    bottom.pack(fill="x", side="bottom")

    def on_submit() -> None:
        all_vars = short_vars + long_vars
        if any(v.get() == 0 for v in all_vars):
            messagebox.showwarning("Incomplete", "Please answer all questions before submitting.")
            return
        win.destroy()
        open_comparative_screen(
            parent,
            test_id,
            thinking_aloud,
            [v.get() for v in short_vars],
            [v.get() for v in long_vars],
        )

    tk.Button(bottom, text="Submit", command=on_submit, width=14, height=2).pack(side="right")


# ── Writing screen ────────────────────────────────────────────────────────────

def open_writing_screen(parent: tk.Tk, test_id: str) -> None:
    """Open the free-text writing prompt screen."""
    win = tk.Toplevel(parent)
    win.title("Writing Prompt")
    win.geometry("700x520")
    win.minsize(520, 380)
    win.grab_set()

    tk.Label(
        win, text=f"Test ID: {test_id}", font=("Arial", 9), fg="gray", anchor="w"
    ).pack(fill="x", padx=24, pady=(16, 0))

    tk.Label(
        win,
        text=WRITING_PROMPT,
        justify="left",
        anchor="nw",
        wraplength=640,
        font=("Arial", 12),
    ).pack(fill="x", padx=24, pady=(12, 8))

    text_frame = tk.Frame(win, padx=24)
    text_frame.pack(fill="both", expand=True)

    scrollbar = tk.Scrollbar(text_frame)
    scrollbar.pack(side="right", fill="y")

    text_area = tk.Text(
        text_frame,
        font=("Arial", 12),
        wrap="word",
        yscrollcommand=scrollbar.set,
        relief="solid",
        bd=1,
    )
    text_area.pack(fill="both", expand=True)
    scrollbar.config(command=text_area.yview)
    text_area.focus_set()

    bottom = tk.Frame(win, padx=24, pady=16)
    bottom.pack(fill="x", side="bottom")

    def on_save() -> None:
        talking_aloud = text_area.get("1.0", tk.END).strip()
        win.destroy()
        open_likert_screen(parent, test_id, talking_aloud)

    tk.Button(bottom, text="Save", command=on_save, width=14, height=2).pack(side="right")


# ── Info screen ───────────────────────────────────────────────────────────────

def build_info_screen() -> tk.Tk:
    """Create and return the initial information / landing screen."""
    root = tk.Tk()
    root.title("Test Environment")
    root.geometry("700x420")
    root.minsize(520, 320)

    main_container = tk.Frame(root, padx=24, pady=24)
    main_container.pack(fill="both", expand=True)

    tk.Label(
        main_container,
        text=DUMMY_INSTRUCTIONS,
        justify="left",
        anchor="nw",
        wraplength=640,
        font=("Arial", 12),
    ).pack(fill="both", expand=True)

    bottom_container = tk.Frame(root, padx=24, pady=20)
    bottom_container.pack(fill="x", side="bottom")

    def on_start_clicked() -> None:
        test_id = str(uuid.uuid4())
        open_writing_screen(root, test_id)

    tk.Button(
        bottom_container, text="Start", command=on_start_clicked, width=14, height=2
    ).pack(side="right")

    return root


# ── Stand-alone launcher (optional) ──────────────────────────────────────────

def run() -> None:
    """Build the info screen and start the Tk event loop."""
    app = build_info_screen()
    app.mainloop()


if __name__ == "__main__":
    run()

