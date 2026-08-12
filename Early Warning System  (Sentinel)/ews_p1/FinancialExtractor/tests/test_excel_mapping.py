import unittest

from openpyxl import Workbook

from src.excel_writer import resolve_excel_target_cell


class ExcelMappingTests(unittest.TestCase):
    def test_resolves_alias_labels_to_the_same_template_row(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet["A1"] = "Property, Plant & Equipment"
        sheet["B1"] = None

        cell = resolve_excel_target_cell(
            sheet,
            "Property Plant and Equipment",
            {"Property Plant and Equipment": ["PPE", "Property, Plant & Equipment", "Fixed Assets"]},
        )

        self.assertEqual(cell.coordinate, "B1")


if __name__ == "__main__":
    unittest.main()
