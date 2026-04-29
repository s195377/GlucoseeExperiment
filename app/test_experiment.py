import unittest
import sys
import os

# Add the current folder to the system path so Python can see experiment_environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from experiment_environment import evaluate_answer

class TestExperimentLogic(unittest.TestCase):

    def test_single_point_correct(self):
        # 29. juli Task: 11:59 (719 mins). Click at 12:02 (722 mins) should PASS (tol=5)
        mock_click = [{
            "dayKey": "2024-07-29",
            "minuteOfDay": 722,
            "observation": 13.7
        }]
        result = evaluate_answer("daily_line", 0, mock_click)
        self.assertTrue(result, "Should pass: within 5-minute tolerance.")

    def test_single_point_wrong_day(self):
        # Correct time, but clicked on July 30 instead of July 29
        mock_click = [{
            "dayKey": "2024-07-30",
            "minuteOfDay": 719
        }]
        result = evaluate_answer("daily_line", 0, mock_click)
        self.assertFalse(result, "Should fail: incorrect date.")

    def test_date_range_boundary(self):
        # August task: Range is Aug 4 to Aug 17.
        # Test the exact boundary (Aug 17)
        mock_click = [{"dayKey": "2024-08-17"}]
        result = evaluate_answer("monthly", 0, mock_click)
        self.assertTrue(result, "Should pass: boundary date is inclusive.")

    def test_low_in_month_threshold(self):
        # July task: Threshold 4.4. Click 4.3 should pass.
        mock_click = [{
            "dayKey": "2024-07-15",
            "observation": 4.3,
            "month_prefix": "2024-07"
        }]
        result = evaluate_answer("monthly", 1, mock_click)
        self.assertTrue(result, "Should pass: observation is below 4.4.")

    def test_two_times_logic(self):
        # July 19 task: Needs 12:21 AND 18:20
        mock_clicks = [
            {"dayKey": "2024-07-19", "minuteOfDay": 741}, # 12:21
            {"dayKey": "2024-07-19", "minuteOfDay": 1100} # 18:20
        ]
        result = evaluate_answer("daily_line", 2, mock_clicks)
        self.assertTrue(result, "Should pass: both required times clicked.")

if __name__ == "__main__":
    unittest.main()