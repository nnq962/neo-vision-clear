"""Schema số liệu CPU, GPU và RAM của thiết bị chạy backend."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CpuCoreMetrics(BaseModel):
    """Mức sử dụng của một lõi CPU được đánh số theo procfs."""

    model_config = ConfigDict(extra="forbid")

    id: int = Field(ge=0)
    usage_percent: float | None = Field(default=None, ge=0, le=100)


class CpuMetrics(BaseModel):
    """Mức sử dụng tổng, từng lõi và nhiệt độ CPU hiện tại."""

    model_config = ConfigDict(extra="forbid")

    usage_percent: float | None = Field(default=None, ge=0, le=100)
    core_count: int | None = Field(default=None, ge=1)
    cores: list[CpuCoreMetrics] = Field(default_factory=list)
    temperature_c: float | None = None


class GpuMetrics(BaseModel):
    """Mức sử dụng, xung nhịp và nhiệt độ GPU Jetson."""

    model_config = ConfigDict(extra="forbid")

    usage_percent: float | None = Field(default=None, ge=0, le=100)
    frequency_mhz: float | None = Field(default=None, ge=0)
    temperature_c: float | None = None


class RamMetrics(BaseModel):
    """Dung lượng RAM dùng, khả dụng và tổng của hệ thống."""

    model_config = ConfigDict(extra="forbid")

    used_bytes: int | None = Field(default=None, ge=0)
    available_bytes: int | None = Field(default=None, ge=0)
    total_bytes: int | None = Field(default=None, gt=0)
    usage_percent: float | None = Field(default=None, ge=0, le=100)


class SystemMetricsResponse(BaseModel):
    """Một mẫu CPU/GPU/RAM trả cho trang Tổng quan."""

    model_config = ConfigDict(extra="forbid")

    sampled_at: datetime
    cpu: CpuMetrics
    gpu: GpuMetrics
    ram: RamMetrics
