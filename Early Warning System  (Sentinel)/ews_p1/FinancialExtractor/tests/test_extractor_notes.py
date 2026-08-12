import unittest

from src.extractor import _extract_missing_fields_from_notes


class DummyClient:
    def __init__(self):
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        if "Contingent Liabilities" in prompt:
            return '{"Contingent Liabilities": "10,000"}'
        return '{"Current maturities of borrowings": "5,000"}'


class ExtractorNotesFallbackTests(unittest.TestCase):
    def test_extracts_one_missing_field_per_note_prompt(self):
        client = DummyClient()
        section_result = {
            "Contingent Liabilities": None,
            "Current maturities of borrowings": None,
        }

        result = _extract_missing_fields_from_notes(
            "Balance Sheet",
            section_result,
            ["Notes about contingent liabilities"],
            client,
            max_retries=1,
        )

        self.assertEqual(result, {"Contingent Liabilities": "10,000", "Current maturities of borrowings": "5,000"})
        self.assertEqual(len(client.prompts), 2)
        self.assertIn("Contingent Liabilities", client.prompts[0])
        self.assertIn("Current maturities of borrowings", client.prompts[1])


if __name__ == "__main__":
    unittest.main()
