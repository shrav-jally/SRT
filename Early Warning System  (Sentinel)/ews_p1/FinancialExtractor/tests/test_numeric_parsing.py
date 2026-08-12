import unittest

from src.validator import parse_numeric_value


class NumericParsingTests(unittest.TestCase):
    def test_parses_common_financial_formats(self):
        cases = [
            ("1,234", "1,234", 1234.0, None, None),
            ("1,234.56", "1,234.56", 1234.56, None, None),
            ("(456)", "(456)", -456.0, None, None),
            ("₹1,234", "₹1,234", 1234.0, "₹", None),
            ("$5,600", "$5,600", 5600.0, "$", None),
            ("2 million", "2 million", 2000000.0, None, "million"),
            ("5 billion", "5 billion", 5000000000.0, None, "billion"),
            ("-250", "-250", -250.0, None, None),
        ]

        for raw, display, numeric, currency, unit in cases:
            parsed = parse_numeric_value(raw)
            self.assertEqual(parsed["raw_value"], raw)
            self.assertEqual(parsed["display_value"], display)
            self.assertEqual(parsed["numeric_value"], numeric)
            self.assertEqual(parsed["currency"], currency)
            self.assertEqual(parsed["unit"], unit)


if __name__ == "__main__":
    unittest.main()
