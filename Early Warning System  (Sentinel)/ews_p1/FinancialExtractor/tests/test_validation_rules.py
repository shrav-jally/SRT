import json
import tempfile
import unittest
from pathlib import Path

from src.validator import validate_entities


class ValidationRulesTests(unittest.TestCase):
    def test_warns_when_balance_sheet_relationships_do_not_hold(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "entities.json"
            output_path = Path(tmpdir) / "validated.json"
            input_path.write_text(json.dumps({
                "Total Assets": "100",
                "Total Equity": "40",
                "Total Liabilities": "30",
            }), encoding="utf-8")

            result = validate_entities(input_path, output_path)
            self.assertIn("validation_warnings", result)
            self.assertTrue(any("Assets = Equity + Liabilities" in warning for warning in result["validation_warnings"]))


if __name__ == "__main__":
    unittest.main()
