import unittest

from src.extractor import _build_empty_result_payload
from src.models import FinancialEntities


class PipelineConsistencyTests(unittest.TestCase):
    def test_empty_payload_contains_schema_aliases_once(self):
        payload = _build_empty_result_payload()

        self.assertEqual(len(payload), len(FinancialEntities.model_fields))
        self.assertEqual(payload["Company Name"], None)
        self.assertEqual(payload["Total Assets"], None)
        self.assertEqual(len(set(payload.keys())), len(payload))


if __name__ == "__main__":
    unittest.main()
