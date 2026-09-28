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
                    "maximum_occupancy_ratio": 0.4,
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
        occupancy_ratio: float = 0.2,
    ) -> dict:
        """Tạo message camera hợp lệ với timestamp hiện tại."""
        blocked = occupancy_ratio >= 0.4
        return {
            "schema_version": 2,
            "camera_id": camera_id,
            "camera_name": f"Camera {camera_id[-2:]}",
            "state": state,
            "zone_count": 10,
            "zones": [
                {
                    "index": index,
                    "occupancy_ratio": occupancy_ratio if index in (4, 5) else 0.1,
                    "walkway_width_cm": 100.0,
                    "occupied_width_cm": (
                        occupancy_ratio * 100 if index in (4, 5) else 10.0
                    ),
                    "free_width_cm": (
                        (1 - occupancy_ratio) * 100 if index in (4, 5) else 90.0
                    ),
                    "blocked": blocked and index in (4, 5),
                }
                for index in range(1, 11)
            ],
            "blocked_zones": [4, 5] if blocked else [],
            "maximum_occupancy_ratio": occupancy_ratio,
            "occupancy_threshold_ratio": 0.4,
            "reason": "occupancy_threshold_exceeded" if blocked else None,
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
                "zone_code": "ZONE_B",
                "corridor_id": "corridor-new",
                "corridor_name": "Hành lang mới",
                "maximum_occupancy_ratio": 0.55,
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
        self.assertEqual(saved["corridor"]["zone_code"], "ZONE_B")
        self.assertEqual(dashboard["decision"]["zone_code"], "ZONE_B")
        self.assertEqual(dashboard["cameras"][0]["camera_id"], "camera-new")

    # ─────────────────────────────────────────────────────────────────────────

    def test_legacy_width_config_migrates_to_default_occupancy(self) -> None:
        """Config cũ phải khởi động được với ngưỡng chiếm dụng mặc định 40%."""
        config = AggregatorConfig.model_validate(
            {
                "schema_version": 1,
                "corridor": {
                    "corridor_id": "legacy",
                    "corridor_name": "Hành lang cũ",
                    "required_width_cm": 50,
                },
                "cameras": [
                    {
                        "camera_id": "camera-old",
                        "source_id": "jetson-old",
                        "order": 1,
                        "location_name": "Đầu hành lang",
                    }
                ],
            }
        )

        self.assertEqual(config.corridor.zone_code, "ZONE_A")
        self.assertEqual(config.corridor.maximum_occupancy_ratio, 0.4)
        self.assertNotIn("required_width_cm", config.model_dump()["corridor"])

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

    def test_camera_occupancy_above_threshold_produces_blocked(self) -> None:
        """Aggregator tự chặn khi một zone đạt ngưỡng chiếm dụng."""
        with TestClient(self.app) as client:
            with client.websocket_connect("/ws/ingest/jetson-a") as jetson_a:
                jetson_a.send_json(self._payload("camera-01", occupancy_ratio=0.2))
                jetson_a.send_json(self._payload("camera-02", occupancy_ratio=0.65))
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
            "occupancy_threshold_exceeded",
        )

    # ─────────────────────────────────────────────────────────────────────────

    def test_camera_occupancy_equal_threshold_is_blocked(self) -> None:
        """Tỷ lệ đúng bằng ngưỡng 40 phần trăm phải được xem là bị chặn."""
        with TestClient(self.app) as client:
            with client.websocket_connect("/ws/ingest/jetson-a") as jetson_a:
                jetson_a.send_json(self._payload("camera-01", occupancy_ratio=0.4))
                jetson_a.send_json(self._payload("camera-02", occupancy_ratio=0.2))
                decision = client.get("/api/decision").json()

        self.assertEqual(decision["state"], "blocked")
        self.assertEqual(decision["blocked_areas"][0]["blocked_zones"], [4, 5])

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

        self.assertEqual(latest["payload"]["schema_version"], 2)
        self.assertEqual(latest["payload"]["camera_id"], "camera-01")


if __name__ == "__main__":
    unittest.main()
