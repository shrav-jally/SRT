import unittest

from src.parser import preprocess_pdf_text


class PreprocessingTests(unittest.TestCase):
    def test_removes_headers_footers_and_blank_lines(self):
        raw_text = """
        Annual Report 2024
        Company Name
        Revenue from operations 100

        Other income 20
        Page 1 of 5
        """
        cleaned = preprocess_pdf_text(raw_text)

        self.assertNotIn("Annual Report 2024", cleaned)
        self.assertNotIn("Page 1 of 5", cleaned)
        self.assertNotIn("Company Name", cleaned)
        self.assertNotIn("\n\n", cleaned)


if __name__ == "__main__":
    unittest.main()
