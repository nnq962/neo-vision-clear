"""Kiểm thử hợp đồng JSON thực tế gửi tới WebSocket server."""

import asyncio
from datetime import datetime, timezone
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import ValidationError

from neo_vision_clear_aggregator.config import CorridorConfig, OutboundConfig
from neo_vision_clear_aggregator.models import CorridorDecision
from neo_vision_clear_aggregator.outbound import OutboundPublisher


class OutboundTestCase(unittest.IsolatedAsyncioTestCase):
    """Xác nhận envelope và quy tắc chặn khi thiếu dữ liệu."""

    async def test_websocket_report_for_all_states(self):
        """Mọi trạng thái phải gửi đúng event, mã hành lang và cờ boolean."""
        for state, can_pass, is_blocked in (
            ("pass", True, False),
            ("blocked", False, True),
            ("unknown", None, True),
        ):
            with self.subTest(state=state):
                decision = CorridorDecision(
                    zone_code="ZONE_B",
                    corridor_id="corridor-test",
                    corridor_name="Hành lang kiểm thử",
                    state=state,
                    can_pass=can_pass,
                    occupancy_threshold_ratio=0.4,
                    decided_at=datetime.now(timezone.utc),
                )
                publisher = OutboundPublisher(OutboundConfig(
                    enabled=True, websocket_url="ws://example.test/report",
                ))
                sent = asyncio.Event()
                socket = MagicMock()

                async def capture(message):
                    """Đánh dấu message đã được truyền tới transport."""
                    sent.set()

                socket.send = AsyncMock(side_effect=capture)
                connection = MagicMock()
                connection.__aenter__ = AsyncMock(return_value=socket)
                connection.__aexit__ = AsyncMock(return_value=False)
                with patch(
                    "neo_vision_clear_aggregator.outbound.connect",
                    return_value=connection,
                ):
                    publisher.start()
                    try:
                        await publisher.publish(decision)
                        await asyncio.wait_for(sent.wait(), timeout=2)
                        wire = socket.send.call_args[0][0]
                        self.assertIsInstance(wire, str)
                        payload = json.loads(wire)
                        self.assertEqual(payload["event"], "camera_report_zone")
                        expected = decision.model_dump(mode="json", exclude_none=True)
                        expected["is_blocked"] = is_blocked
                        self.assertEqual(payload["data"], expected)
                        self.assertIs(payload["data"]["is_blocked"], is_blocked)
                        self.assertEqual(
                            publisher.status().last_payload.model_dump(
                                mode="json", exclude_none=True,
                            ),
                            payload,
                        )
                    finally:
                        await publisher.close()

    def test_empty_zone_code_is_rejected(self):
        """Không cho lưu mã khu vực rỗng hoặc chỉ chứa khoảng trắng."""
        for zone_code in ("", "   "):
            with self.subTest(zone_code=zone_code), self.assertRaises(ValidationError):
                CorridorConfig(
                    zone_code=zone_code,
                    corridor_id="corridor-test",
                    corridor_name="Hành lang kiểm thử",
                )
