from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

from src.config import Config


class ExcelWriter:
    def __init__(self, config: Config) -> None:
        self.config = config

    def write(self, data: dict) -> None:
        if not self.config.template_excel.exists():
            raise FileNotFoundError('Excel template missing.')

        workbook = load_workbook(self.config.template_excel)
        sheet = workbook.active

        mapping = {
            'Company Name': 'B2',
            'Financial Year': 'B3',
            'Revenue': 'B4',
            'Gross Profit': 'B5',
            'Operating Income': 'B6',
            'EBITDA': 'B7',
            'Net Income': 'B8',
            'EPS': 'B9',
            'Total Assets': 'B10',
            'Total Liabilities': 'B11',
            'Cash': 'B12',
            'Cash Flow': 'B13',
            'Operating Cash Flow': 'B14',
            'Investing Cash Flow': 'B15',
            'Financing Cash Flow': 'B16',
            'Capital Expenditure': 'B17',
            'Currency': 'B18',
            'Country': 'B19',
            'CEO': 'B20',
            'Employees': 'B21',
            'Auditor': 'B22',
            'Business Segments': 'B23',
            'Risk Factors': 'B24',
            'Dividend': 'B25',
            'Shares Outstanding': 'B26',
            'Market Capitalization': 'B27',
            'Notes': 'B28',
        }

        for field, cell in mapping.items():
            value = data.get(field)
            if value is not None:
                sheet[cell] = value

        workbook.save(self.config.output_excel)
