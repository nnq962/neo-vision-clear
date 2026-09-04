"""Kiểm thử state machine xác nhận trạng thái theo nhiều frame."""

import unittest

from walkway_monitor.detection.models import OccupancyState
from walkway_monitor.detection.temporal_filter import TemporalOccupancyFilter


class TemporalOccupancyFilterTestCase(unittest.TestCase):
    """Kiểm tra hysteresis và reset khi frame không hợp lệ."""

    def test_hysteresis_and_invalid_reset(self) -> None:
        """Bộ lọc chỉ đổi trạng thái khi đủ frame và reset về UNKNOWN khi invalid."""
        temporal_filter = TemporalOccupancyFilter(occupied_frames=2, clear_frames=3)
        self.assertEqual(temporal_filter.update(False), OccupancyState.UNKNOWN)
        self.assertEqual(temporal_filter.update(False), OccupancyState.UNKNOWN)
        self.assertEqual(temporal_filter.update(False), OccupancyState.CLEAR)
        self.assertEqual(temporal_filter.update(True), OccupancyState.CLEAR)
        self.assertEqual(temporal_filter.update(True), OccupancyState.OCCUPIED)
        self.assertEqual(
            temporal_filter.update(raw_occupied=False, valid=False),
            OccupancyState.UNKNOWN,
        )


if __name__ == "__main__":
    unittest.main()
