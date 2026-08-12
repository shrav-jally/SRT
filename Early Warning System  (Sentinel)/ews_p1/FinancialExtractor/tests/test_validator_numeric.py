import json
import tempfile
import unittest
from pathlib import Path

from src.validator import _extract_multi_year_value


class MultiYearValueTests(unittest.TestCase):
    def test_extracts_latest_value_and_keeps_history(self):
        latest, history = _extract_multi_year_value(
            "Current Year: ₹12,000; Previous Year: ₹10,000",
            "Revenue from operations",
        )

        self.assertEqual(latest, "₹12,000")
        self.assertEqual(history, {"current_year": "₹12,000", "previous_year": "₹10,000"})

    def test_returns_original_value_when_no_multi_year_structure(self):
        latest, history = _extract_multi_year_value("₹8,500", "Profit before tax")

        self.assertEqual(latest, "₹8,500")
        self.assertIsNone(history)


if __name__ == "__main__":
    unittest.main()
