"""Kiểm thử telemetry CPU/GPU/RAM độc lập với phần cứng Jetson thật."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from server.app import create_app
from server.services.system_metrics import SystemMetricsService
from server.settings import ServerSettings


class SystemMetricsTestCase(unittest.TestCase):
    """Xác nhận tỷ lệ CPU, GPU và fallback khi sysfs thiếu cảm biến."""

    def setUp(self) -> None:
        """Tạo cây procfs/sysfs giả cho từng test."""
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        root = Path(self.temporary_directory.name)
        self.proc_stat = root / "proc" / "stat"
        self.proc_stat.parent.mkdir()
        self.meminfo = root / "proc" / "meminfo"
        self.gpu_root = root / "gpu.0"
        self.gpu_root.mkdir()
        self.thermal_root = root / "thermal"
        self.thermal_root.mkdir()
        self.service = SystemMetricsService(
            proc_stat_path=self.proc_stat,
            meminfo_path=self.meminfo,
            gpu_root=self.gpu_root,
            thermal_root=self.thermal_root,
        )

    # ─────────────────────────────────────────────────────────────────────────

    def _write_proc_stat(
        self,
        user: int,
        idle: int,
        core_0: tuple[int, int] | None = None,
        core_1: tuple[int, int] | None = None,
    ) -> None:
        """Ghi hai lõi giả cùng tổng jiffies phục vụ phép đo delta."""
        # Bước 1: mặc định chia đều jiffies tổng cho hai lõi kiểm thử.
        first = core_0 or (user // 2, idle // 2)
        second = core_1 or (user - first[0], idle - first[1])
        self.proc_stat.write_text(
            f"cpu  {user} 0 0 {idle} 0 0 0 0 0 0\n"
            f"cpu0 {first[0]} 0 0 {first[1]} 0 0 0 0 0 0\n"
            f"cpu1 {second[0]} 0 0 {second[1]} 0 0 0 0 0 0\n",
            encoding="utf-8",
        )

    # ─────────────────────────────────────────────────────────────────────────

    def _write_temperature(self, index: int, name: str, value: int) -> None:
        """Ghi một thermal zone với giá trị theo millidegree Celsius."""
        # Bước 1: tạo cặp type/temp giống cấu trúc sysfs trên Jetson.
        zone = self.thermal_root / f"thermal_zone{index}"
        zone.mkdir()
        (zone / "type").write_text(name, encoding="utf-8")
        (zone / "temp").write_text(str(value), encoding="utf-8")

    # ─────────────────────────────────────────────────────────────────────────

    def test_reads_cpu_gpu_and_ram_metrics(self) -> None:
        """CPU lấy delta, GPU lấy sysfs và RAM lấy MemAvailable."""
        self._write_proc_stat(user=100, idle=100)
        self.meminfo.write_text(
            "MemTotal:       16384000 kB\nMemAvailable:    4096000 kB\n",
            encoding="utf-8",
        )
        (self.gpu_root / "load").write_text("345", encoding="utf-8")
        devfreq = self.gpu_root / "devfreq" / "17000000.gv11b"
        devfreq.mkdir(parents=True)
        (devfreq / "cur_freq").write_text("1109250000", encoding="utf-8")
        self._write_temperature(0, "CPU-therm", 57500)
        self._write_temperature(1, "GPU-therm", 56250)

        first = self.service.read()
        self._write_proc_stat(
            user=150,
            idle=150,
            core_0=(100, 50),
            core_1=(50, 100),
        )
        second = self.service.read()

        self.assertIsNone(first.cpu.usage_percent)
        self.assertEqual(second.cpu.usage_percent, 50.0)
        self.assertEqual(second.cpu.core_count, 2)
        self.assertEqual([core.usage_percent for core in first.cpu.cores], [None, None])
        self.assertEqual([core.usage_percent for core in second.cpu.cores], [100.0, 0.0])
        self.assertEqual(second.cpu.temperature_c, 57.5)
        self.assertEqual(second.gpu.usage_percent, 34.5)
        self.assertEqual(second.gpu.frequency_mhz, 1109.2)
        self.assertEqual(second.gpu.temperature_c, 56.2)
        self.assertEqual(second.ram.total_bytes, 16384000 * 1024)
        self.assertEqual(second.ram.available_bytes, 4096000 * 1024)
        self.assertEqual(second.ram.used_bytes, 12288000 * 1024)
        self.assertEqual(second.ram.usage_percent, 75.0)

    # ─────────────────────────────────────────────────────────────────────────

    def test_missing_and_invalid_sensors_return_null(self) -> None:
        """Máy không có node Jetson vẫn trả schema ổn định với null."""
        (self.gpu_root / "load").write_text("nan", encoding="utf-8")

        response = self.service.read()

        self.assertIsNone(response.cpu.usage_percent)
        self.assertIsNone(response.cpu.core_count)
        self.assertEqual(response.cpu.cores, [])
        self.assertIsNone(response.cpu.temperature_c)
        self.assertIsNone(response.gpu.usage_percent)
        self.assertIsNone(response.gpu.frequency_mhz)
        self.assertIsNone(response.gpu.temperature_c)
        self.assertIsNone(response.ram.total_bytes)
        self.assertIsNone(response.ram.usage_percent)

    # ─────────────────────────────────────────────────────────────────────────

    def test_invalid_meminfo_returns_empty_ram_metrics(self) -> None:
        """RAM không hợp lệ không làm lỗi telemetry CPU và GPU."""
        self._write_proc_stat(user=100, idle=100)
        self.meminfo.write_text(
            "MemTotal: 2048 kB\nMemAvailable: 4096 kB\n",
            encoding="utf-8",
        )

        response = self.service.read()

        self.assertIsNone(response.ram.used_bytes)
        self.assertIsNone(response.ram.total_bytes)

    # ─────────────────────────────────────────────────────────────────────────

    def test_api_returns_metrics_without_running_camera_worker(self) -> None:
        """Endpoint hoạt động khi chưa cấu hình camera hoặc runtime."""
        self._write_proc_stat(user=100, idle=100)
        root = Path(self.temporary_directory.name)
        application = create_app(
            ServerSettings(camera_config_path=str(root / "config.json"))
        )
        application.state.system_metrics_service = self.service

        with TestClient(application) as client:
            response = client.get("/api/system/metrics")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cpu"]["core_count"], 2)
        self.assertEqual([core["id"] for core in response.json()["cpu"]["cores"]], [0, 1])
        self.assertIsNone(response.json()["cpu"]["usage_percent"])
        self.assertIn("ram", response.json())
        self.assertIn("sampled_at", response.json())
