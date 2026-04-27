"""main.py

Application entry point and controller.
"""

import tkinter as tk
from app import landing_environment, experiment_environment, test_environment


def launch_picker() -> None:
    """Show a launcher window to choose what to open."""
    root = tk.Tk()
    root.title("Glucosee Launcher")
    root.geometry("400x260")
    root.resizable(False, False)

    tk.Label(
        root, text="What would you like to launch?",
        font=("Arial", 13, "bold")
    ).pack(pady=(24, 20))

    # ── Buttons ───────────────────────────────────────────────────────────
    btn_frame = tk.Frame(root, pady=4)
    btn_frame.pack(fill="x", padx=24)

    def on_landing_page():
        root.destroy()
        landing_environment.run()

    def on_experiment_session():
        root.destroy()
        experiment_environment.run()

    def on_test_session():
        root.destroy()
        test_environment.run()

    tk.Button(btn_frame, text="Landing Page",
              command=on_landing_page, width=20, height=2).pack(fill="x", pady=4)
    tk.Button(btn_frame, text="Run Experiment Session",
              command=on_experiment_session, width=20, height=2).pack(fill="x", pady=4)
    tk.Button(btn_frame, text="Run Test Session",
              command=on_test_session, width=20, height=2).pack(fill="x", pady=4)

    root.mainloop()


def main() -> None:
    launch_picker()


if __name__ == "__main__":
    main()
