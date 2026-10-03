"""Failure classifications; synthetic data does not qualify a real source."""
import unittest
from types import SimpleNamespace
from baostock_probe import sample_state


class CaptureStateTests(unittest.TestCase):
    def check(self, expected, rows, error="0", fields=None):
        result = SimpleNamespace(error_code=error, fields=fields or ["price", "volume"], data=rows)
        self.assertEqual(sample_state(result, ["price", "volume"], 3), expected)

    def test_precision_strings_remain_strings(self):
        self.check("captured_sample_not_qualified", [["0.100000000000000001", "9007199254740993"]])

    def test_error_with_partial_data_is_not_success(self):
        self.check("sdk_query_error", [["10", "100"]], error="10002007")

    def test_empty_is_unknown(self):
        self.check("empty_result", [])

    def test_field_change(self):
        self.check("field_mismatch", [["10", "100"]], fields=["volume", "price"])

    def test_page_boundary_is_unverified(self):
        self.check("pagination_unverified", [["10", "100"]] * 3)

    def test_non_string_and_short_rows_are_not_accepted(self):
        for row in [[10.0, "100"], ["10", 100], ["10"], None]:
            with self.subTest(row=row):
                self.check("non_string_or_invalid_cells", [row])

    def test_invalid_rows(self):
        self.check("invalid_rows", None)


if __name__ == "__main__":
    unittest.main()
