import unittest

from src.chunker import reconstruct_table_like_text


class TableReconstructionTests(unittest.TestCase):
    def test_reconstructs_rows_for_consecutive_table_lines(self):
        text = "Revenue from operations 100\nOther income 20\nTotal income 120"
        reconstructed = reconstruct_table_like_text(text)

        self.assertIn("Revenue from operations | 100", reconstructed)
        self.assertIn("Other income | 20", reconstructed)
        self.assertIn("Total income | 120", reconstructed)

    def test_preserves_page_reference_when_present(self):
        text = "Page 1\nRevenue from operations 100"
        reconstructed = reconstruct_table_like_text(text)

        self.assertIn("Page 1", reconstructed)


if __name__ == "__main__":
    unittest.main()
