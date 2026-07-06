"""Tests fuer Worker-Hilfsfunktionen."""

from s7py.constants import RECORDING_MODE_COUNT, RECORDING_MODE_EVERY_CYCLE
from s7py.worker import detect_count_gap, should_store_sample


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


class TestShouldStoreSample:
    def test_count_mode_only_on_increase(self):
        assert should_store_sample(
            recording_mode=RECORDING_MODE_COUNT,
            count_value=6,
            old_count=5,
        )
        assert not should_store_sample(
            recording_mode=RECORDING_MODE_COUNT,
            count_value=5,
            old_count=5,
        )

    def test_every_cycle_mode_always(self):
        assert should_store_sample(
            recording_mode=RECORDING_MODE_EVERY_CYCLE,
            count_value=5,
            old_count=5,
        )
        assert should_store_sample(
            recording_mode=RECORDING_MODE_EVERY_CYCLE,
            count_value=3,
            old_count=10,
        )
