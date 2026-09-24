"""Đọc telemetry CPU/GPU/RAM nhẹ từ procfs và sysfs của Jetson."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from pathlib import Path
from threading import Lock

from server.models.system_metrics import (
    CpuCoreMetrics,
    CpuMetrics,
    GpuMetrics,
    RamMetrics,
    SystemMetricsResponse,
)


class SystemMetricsService:
    """Lấy mẫu CPU theo khoảng thời gian giữa hai request và đọc GPU tức thời."""

    def __init__(
        self,
        proc_stat_path: str | Path = "/proc/stat",
        meminfo_path: str | Path = "/proc/meminfo",
        gpu_root: str | Path = "/sys/devices/gpu.0",
        thermal_root: str | Path = "/sys/class/thermal",
    ) -> None:
        """Lưu các nguồn telemetry và bộ đếm CPU của mẫu trước."""
        self._proc_stat_path = Path(proc_stat_path)
        self._meminfo_path = Path(meminfo_path)
        self._gpu_root = Path(gpu_root)
        self._thermal_root = Path(thermal_root)
        self._previous_cpu: dict[str, tuple[int, int]] = {}
        self._lock = Lock()

    # ─────────────────────────────────────────────────────────────────────────

    def read(self) -> SystemMetricsResponse:
        """Trả một mẫu CPU/GPU/RAM, dùng null khi cảm biến không khả dụng."""
        # Bước 1: lấy delta CPU tổng và từng lõi dưới lock để không tráo mẫu.
        with self._lock:
            counters = self._read_cpu_counters()
            previous = self._previous_cpu
            if counters is not None:
                self._previous_cpu = counters
        core_names = sorted(
            (name for name in counters or {} if name != "cpu"),
            key=lambda name: int(name[3:]),
        )
        cores = [
            CpuCoreMetrics(
                id=int(name[3:]),
                usage_percent=self._calculate_usage(
                    counters[name], previous.get(name)
                ),
            )
            for name in core_names
        ]
        usage_percent = (
            self._calculate_usage(counters["cpu"], previous.get("cpu"))
            if counters is not None
            else None
        )

        # Bước 2: RAM đọc procfs; GPU và nhiệt độ lấy từ sysfs.
        return SystemMetricsResponse(
            sampled_at=datetime.now(timezone.utc),
            cpu=CpuMetrics(
                usage_percent=usage_percent,
                core_count=len(cores) or None,
                cores=cores,
                temperature_c=self._read_temperature("cpu"),
            ),
            gpu=GpuMetrics(
                usage_percent=self._read_gpu_usage(),
                frequency_mhz=self._read_gpu_frequency(),
                temperature_c=self._read_temperature("gpu"),
            ),
            ram=self._read_ram_metrics(),
        )

    # ─────────────────────────────────────────────────────────────────────────

    def _read_cpu_counters(self) -> dict[str, tuple[int, int]] | None:
        """Đọc tổng và idle jiffies của CPU tổng cùng từng lõi."""
        try:
            lines = self._proc_stat_path.read_text(encoding="utf-8").splitlines()
            counters: dict[str, tuple[int, int]] = {}
            for line in lines:
                parts = line.split()
                if not parts:
                    continue
                name = parts[0]
                if name != "cpu" and not (name.startswith("cpu") and name[3:].isdigit()):
                    continue
                if len(parts) < 5:
                    return None
                values = [int(value) for value in parts[1:9]]
                idle = values[3] + (values[4] if len(values) > 4 else 0)
                counters[name] = (sum(values), idle)
            if "cpu" not in counters or len(counters) < 2:
                return None
            return counters
        except (OSError, IndexError, ValueError):
            return None

    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _calculate_usage(
        current: tuple[int, int],
        previous: tuple[int, int] | None,
    ) -> float | None:
        """Tính phần trăm bận từ chênh lệch tổng và idle jiffies."""
        # Bước 1: mẫu đầu tiên chưa có khoảng thời gian nên không tính được.
        if previous is None:
            return None
        total_delta = current[0] - previous[0]
        idle_delta = current[1] - previous[1]
        if total_delta <= 0 or not 0 <= idle_delta <= total_delta:
            return None
        return round(100 * (1 - idle_delta / total_delta), 1)

    # ─────────────────────────────────────────────────────────────────────────

    def _read_gpu_usage(self) -> float | None:
        """Đổi tải GPU Jetson từ thang 0–1000 thành phần trăm."""
        value = self._read_number(self._gpu_root / "load")
        if value is None or not 0 <= value <= 1000:
            return None
        return round(value / 10, 1)

    # ─────────────────────────────────────────────────────────────────────────

    def _read_ram_metrics(self) -> RamMetrics:
        """Tính RAM đang dùng từ MemTotal và MemAvailable trong /proc/meminfo."""
        try:
            # Bước 1: chỉ đọc hai trường cần thiết; giá trị meminfo dùng đơn vị kB.
            values: dict[str, int] = {}
            for line in self._meminfo_path.read_text(encoding="utf-8").splitlines():
                name, separator, raw_value = line.partition(":")
                if not separator or name not in {"MemTotal", "MemAvailable"}:
                    continue
                parts = raw_value.split()
                if len(parts) != 2 or parts[1] != "kB":
                    return RamMetrics()
                values[name] = int(parts[0]) * 1024
            total = values.get("MemTotal")
            available = values.get("MemAvailable")
            if total is None or available is None or total <= 0:
                return RamMetrics()
            if not 0 <= available <= total:
                return RamMetrics()

            # Bước 2: MemAvailable đã tính cả cache có thể thu hồi.
            used = total - available
            return RamMetrics(
                used_bytes=used,
                available_bytes=available,
                total_bytes=total,
                usage_percent=round(used * 100 / total, 1),
            )
        except (OSError, ValueError):
            return RamMetrics()

    # ─────────────────────────────────────────────────────────────────────────

    def _read_gpu_frequency(self) -> float | None:
        """Đọc xung GPU từ devfreq và đổi hertz sang megahertz."""
        try:
            paths = sorted((self._gpu_root / "devfreq").glob("*/cur_freq"))
        except OSError:
            return None
        for path in paths:
            value = self._read_number(path)
            if value is not None and value >= 0:
                return round(value / 1_000_000, 1)
        return None

    # ─────────────────────────────────────────────────────────────────────────

    def _read_temperature(self, device: str) -> float | None:
        """Tìm thermal zone CPU hoặc GPU và đổi millidegree sang độ C."""
        try:
            zones = sorted(self._thermal_root.glob("thermal_zone*"))
        except OSError:
            return None
        for zone in zones:
            try:
                zone_type = (
                    (zone / "type").read_text(encoding="utf-8").strip().lower()
                )
            except OSError:
                continue
            if not zone_type.startswith(device):
                continue
            value = self._read_number(zone / "temp")
            if value is not None:
                return round(value / 1000, 1)
        return None

    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _read_number(path: Path) -> float | None:
        """Đọc giá trị số từ sysfs mà không làm hỏng toàn bộ mẫu khi thiếu node."""
        try:
            value = float(path.read_text(encoding="utf-8").strip())
            return value if math.isfinite(value) else None
        except (OSError, ValueError):
            return None
