"""Tests fuer Worker-Hilfsfunktionen."""

from s7py.worker import detect_count_gap


class TestDetectCountGap:
    def test_no_gap_when_first_point(self):
        assert detect_count_gap(0, 1) is None

    def test_no_gap_when_increment_by_one(self):
        assert detect_count_gap(5, 6) is None

    def test_gap_when_skipped_values(self):
        assert detect_count_gap(5, 8) == 2

    def test_no_gap_after_reset_marker(self):
        assert detect_count_gap(-1, 3) is None

    def test_no_gap_when_count_decreases(self):
        assert detect_count_gap(10, 3) is None
