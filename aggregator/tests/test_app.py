"""Kiểm thử schema ingest và quyết định tổng hợp qua API công khai."""

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from neo_vision_clear_aggregator.app import create_app
from neo_vision_clear_aggregator.config import AggregatorConfig
from neo_vision_clear_aggregator.settings import AggregatorSettings


class AggregatorAppTestCase(unittest.TestCase):
    """Kiểm tra join source-camera và ba trạng thái hành lang."""

    def setUp(self) -> None:
        """Tạo application hai camera, không kết nối WS server thật."""
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.config_path = Path(temporary_directory.name) / "config.json"
        config = AggregatorConfig.model_validate(
            {
                "schema_version": 1,
                "corridor": {
                    "corridor_id": "corridor-test",
                    "corridor_name": "Hành lang kiểm thử",
                    "required_width_cm": 50,
                },
                "cameras": [
                    {
                        "camera_id": "camera-01",
                        "source_id": "jetson-a",
                        "order": 1,
                        "location_name": "Đầu hành lang",
                    },
                    {
                        "camera_id": "camera-02",
                        "source_id": "jetson-a",
                        "order": 2,
                        "location_name": "Cuối hành lang",
                    },
                ],
                "outbound": {"enabled": False},
            }
        )
        self.app = create_app(
            AggregatorSettings(
                host="127.0.0.1",
                port=8100,
                source_stale_seconds=3.0,
                config_path=str(self.config_path),
            ),
            config=config,
        )

    # ─────────────────────────────────────────────────────────────────────────

    def _payload(
        self,
        camera_id: str,
        state: str = "pass",
        width_cm: float = 72,
    ) -> dict:
        """Tạo message camera hợp lệ với timestamp hiện tại."""
        blocked = state == "blocked"
        return {
            "schema_version": 1,
            "camera_id": camera_id,
            "camera_name": f"Camera {camera_id[-2:]}",
            "state": state,
            "zone_count": 10,
            "blocked_zones": [4, 5] if blocked else [],
            "minimum_free_ratio": 0.18 if blocked else 0.8,
            "max_passable_width_cm": width_cm,
            "reason": "insufficient_clearance" if blocked else None,
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }

    # ─────────────────────────────────────────────────────────────────────────

    def test_health_and_initial_decision_are_unknown(self) -> None:
        """Process mới healthy nhưng chưa được phép kết luận hành lang thông."""
        with TestClient(self.app) as client:
            health = client.get("/health").json()
            decision = client.get("/api/decision").json()

        self.assertEqual(health["configured_cameras"], 2)
        self.assertEqual(health["received_messages"], 0)
        self.assertEqual(decision["state"], "unknown")
        self.assertIsNone(decision["can_pass"])
        self.assertEqual(len(decision["unavailable_cameras"]), 2)

    # ─────────────────────────────────────────────────────────────────────────

    def test_dashboard_page_and_combined_status_are_available(self) -> None:
        """Frontend cùng endpoint tổng hợp phải được phục vụ bởi Aggregator."""
        with TestClient(self.app) as client:
            page = client.get("/")
            dashboard = client.get("/api/dashboard").json()

        self.assertEqual(page.status_code, 200)
        self.assertIn("Neo Vision Aggregator", page.text)
        self.assertEqual(dashboard["decision"]["state"], "unknown")
        self.assertEqual(len(dashboard["cameras"]), 2)
        self.assertFalse(dashboard["outbound"]["enabled"])

    # ─────────────────────────────────────────────────────────────────────────

    def test_config_update_is_persisted_and_applied_without_restart(self) -> None:
        """PUT config phải đổi dashboard và ghi JSON bền vững."""
        updated = {
            "schema_version": 1,
            "corridor": {
                "corridor_id": "corridor-new",
                "corridor_name": "Hành lang mới",
                "required_width_cm": 62,
            },
            "cameras": [
                {
                    "camera_id": "camera-new",
                    "source_id": "jetson-c",
                    "order": 1,
                    "location_name": "Khu vực mới",
                }
            ],
            "outbound": {
                "enabled": False,
                "websocket_url": None,
                "reconnect_seconds": 1,
            },
        }

        with TestClient(self.app) as client:
            response = client.put("/api/config", json=updated)
            dashboard = client.get("/api/dashboard").json()

        saved = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(saved["corridor"]["corridor_name"], "Hành lang mới")
        self.assertEqual(dashboard["decision"]["corridor_id"], "corridor-new")
        self.assertEqual(dashboard["cameras"][0]["camera_id"], "camera-new")

    # ─────────────────────────────────────────────────────────────────────────

    def test_all_fresh_cameras_produce_pass_decision(self) -> None:
        """Tất cả camera đủ rộng và mới phải kết luận hành lang đi được."""
        with TestClient(self.app) as client:
            with client.websocket_connect("/ws/ingest/jetson-a") as jetson_a:
                jetson_a.send_json(self._payload("camera-01"))
                jetson_a.send_json(self._payload("camera-02"))
                decision = client.get("/api/decision").json()
                cameras = client.get("/api/cameras").json()
                latest = client.get("/api/dashboard").json()["latest_received"]

        self.assertEqual(decision["state"], "pass")
        self.assertTrue(decision["can_pass"])
        self.assertEqual(decision["corridor_name"], "Hành lang kiểm thử")
        self.assertEqual([item["order"] for item in cameras], [1, 2])
        self.assertEqual(
            [item["payload"]["camera_id"] for item in latest],
            ["camera-01", "camera-02"],
        )

    # ─────────────────────────────────────────────────────────────────────────

    def test_camera_width_below_robot_threshold_produces_blocked(self) -> None:
        """Aggregator tự chặn khi bề rộng nhỏ hơn required_width_cm."""
        with TestClient(self.app) as client:
            with client.websocket_connect("/ws/ingest/jetson-a") as jetson_a:
                jetson_a.send_json(self._payload("camera-01", width_cm=72))
                jetson_a.send_json(self._payload("camera-02", width_cm=18))
                decision = client.get("/api/decision").json()

        self.assertEqual(decision["state"], "blocked")
        self.assertFalse(decision["can_pass"])
        self.assertEqual(decision["blocked_areas"][0]["camera_id"], "camera-02")
        self.assertEqual(
            decision["blocked_areas"][0]["location_name"],
            "Cuối hành lang",
        )
        self.assertEqual(
            decision["blocked_areas"][0]["reason"],
            "insufficient_clearance",
        )

    # ─────────────────────────────────────────────────────────────────────────

    def test_source_mismatch_is_rejected_without_storing_message(self) -> None:
        """Camera từ sai Jetson phải bị đóng socket và không ảnh hưởng quyết định."""
        with TestClient(self.app) as client:
            with client.websocket_connect("/ws/ingest/jetson-b") as socket:
                socket.send_json(self._payload("camera-01"))
                message = socket.receive()
            health = client.get("/health").json()

        self.assertEqual(message["type"], "websocket.close")
        self.assertEqual(message["code"], 1008)
        self.assertEqual(health["received_messages"], 0)

    # ─────────────────────────────────────────────────────────────────────────

    def test_latest_payload_is_validated_and_kept_per_source(self) -> None:
        """Endpoint debug trả payload có schema thay vì raw JSON tùy ý."""
        with TestClient(self.app) as client:
            with client.websocket_connect("/ws/ingest/jetson-a") as socket:
                socket.send_json(self._payload("camera-01"))
                latest = client.get("/api/sources/jetson-a/latest").json()

        self.assertEqual(latest["payload"]["schema_version"], 1)
        self.assertEqual(latest["payload"]["camera_id"], "camera-01")


if __name__ == "__main__":
    unittest.main()
