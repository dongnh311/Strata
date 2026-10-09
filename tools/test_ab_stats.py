"""Tests for tools/ab_stats.py (no GPU): the bootstrap verdict calls a clear gain, a clear loss and noise correctly."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ab_stats import ratio_ci, verdict  # noqa: E402


class Verdict(unittest.TestCase):
    def test_clear_gain(self):
        v = verdict([50.1, 50.4, 49.8, 50.2, 50.0, 50.3], [55.2, 54.9, 55.4, 55.0, 55.1, 54.8])
        self.assertEqual(v["verdict"], "B better")
        self.assertGreater(v["ci95"][0], 1.0)

    def test_clear_loss(self):
        self.assertEqual(verdict([50, 51, 50, 52, 51], [45, 46, 44, 45, 46])["verdict"], "B worse")

    def test_overlap_is_no_difference(self):
        # the v0.1.41 decode samples on the RTX 3060: +2% median, but the runs overlap
        a = [49.8, 51.6, 49.6, 51.7, 50.5, 51.7, 52.5, 51.7]
        b = [50.9, 52.6, 53.0, 53.5, 50.6, 52.6, 53.0, 53.6]
        self.assertEqual(verdict(a, b)["verdict"], "no measured difference")

    def test_times_lower_is_better(self):
        a, b = [1771, 2083, 1755, 1666, 1703, 1801], [1462, 1585, 1430, 1486, 1543, 1436]
        self.assertEqual(verdict(a, b, lower_is_better=True)["verdict"], "B better")
        self.assertEqual(verdict(a, b)["verdict"], "B worse")      # read as speeds, the same numbers are a loss

    def test_few_samples_warn(self):
        self.assertIn("warning", verdict([1.0, 1.1], [1.2, 1.3]))
        self.assertNotIn("warning", verdict([1.0] * 5, [1.2] * 5))

    def test_deterministic_and_ordered(self):
        r1, lo1, hi1 = ratio_ci([1, 2, 3, 4, 5], [2, 3, 4, 5, 6])
        r2, lo2, hi2 = ratio_ci([1, 2, 3, 4, 5], [2, 3, 4, 5, 6])
        self.assertEqual((r1, lo1, hi1), (r2, lo2, hi2))
        self.assertLessEqual(lo1, hi1)

    def test_empty_side_raises(self):
        with self.assertRaises(ValueError):
            ratio_ci([], [1.0])


if __name__ == "__main__":
    unittest.main()
