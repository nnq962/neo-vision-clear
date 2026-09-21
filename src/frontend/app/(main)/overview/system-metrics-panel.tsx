"use client"

import { useEffect, useState } from "react"
import { CpuIcon, GaugeIcon, MemoryStickIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Separator } from "@/components/ui/separator"

type CpuCoreMetrics = {
  id: number
  usage_percent: number | null
}

type ProcessorMetrics = {
  usage_percent: number | null
  temperature_c: number | null
}

type SystemMetrics = {
  sampled_at: string
  cpu: ProcessorMetrics & {
    core_count: number | null
    cores: CpuCoreMetrics[]
  }
  gpu: ProcessorMetrics & { frequency_mhz: number | null }
  ram: {
    used_bytes: number | null
    available_bytes: number | null
    total_bytes: number | null
    usage_percent: number | null
  }
}

function isMetric(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isFinite(value))
}

function isByteCount(value: unknown): value is number | null {
  return value === null ||
    (typeof value === "number" && Number.isSafeInteger(value) && value >= 0)
}

function parseSystemMetrics(value: unknown): SystemMetrics | undefined {
  if (typeof value !== "object" || value === null) return undefined
  const payload = value as Record<string, unknown>
  if (
    typeof payload.sampled_at !== "string" ||
    typeof payload.cpu !== "object" ||
    payload.cpu === null ||
    typeof payload.gpu !== "object" ||
    payload.gpu === null ||
    typeof payload.ram !== "object" ||
    payload.ram === null
  ) {
    return undefined
  }
  const cpu = payload.cpu as Record<string, unknown>
  const gpu = payload.gpu as Record<string, unknown>
  const ram = payload.ram as Record<string, unknown>
  if (
    !isMetric(cpu.usage_percent) ||
    !isMetric(cpu.temperature_c) ||
    (cpu.core_count !== null &&
      (typeof cpu.core_count !== "number" || !Number.isInteger(cpu.core_count))) ||
    !Array.isArray(cpu.cores) ||
    !cpu.cores.every(
      (core) =>
        typeof core === "object" &&
        core !== null &&
        typeof core.id === "number" &&
        Number.isInteger(core.id) &&
        core.id >= 0 &&
        isMetric(core.usage_percent)
    ) ||
    !isMetric(gpu.usage_percent) ||
    !isMetric(gpu.temperature_c) ||
    !isMetric(gpu.frequency_mhz) ||
    !isByteCount(ram.used_bytes) ||
    !isByteCount(ram.available_bytes) ||
    !isByteCount(ram.total_bytes) ||
    !isMetric(ram.usage_percent)
  ) {
    return undefined
  }
  return payload as SystemMetrics
}

function formatPercent(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${value.toFixed(1)}%`
}

function formatTemperature(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${value.toFixed(1)} °C`
}

function formatFrequency(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${Math.round(value)} MHz`
}

function formatGiB(value: number | null | undefined): string {
  return value === null || value === undefined
    ? "—"
    : `${(value / 1024 ** 3).toFixed(1)} GiB`
}

function MeterRow({
  label,
  value,
}: {
  label: string
  value: number | null | undefined
}) {
  return (
    <div className="grid grid-cols-[3.5rem_minmax(0,1fr)_3.5rem] items-center gap-3 text-xs">
      <span className="font-mono font-medium">{label}</span>
      <Progress value={value ?? 0} aria-label={`Mức sử dụng ${label}`} />
      <span className="text-right font-mono tabular-nums text-muted-foreground">
        {formatPercent(value)}
      </span>
    </div>
  )
}

export function SystemMetricsPanel() {
  const [metrics, setMetrics] = useState<SystemMetrics>()
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    let requestInFlight = false
    const controller = new AbortController()

    async function refresh() {
      if (document.hidden || requestInFlight) return
      requestInFlight = true
      try {
        const response = await fetch("/api/system/metrics", {
          cache: "no-store",
          signal: controller.signal,
        })
        if (!response.ok) throw new Error("Không đọc được telemetry Jetson.")
        const payload: unknown = await response.json()
        const parsed = parseSystemMetrics(payload)
        if (!parsed) throw new Error("Telemetry Jetson không hợp lệ.")
        if (!cancelled) {
          setMetrics(parsed)
          setError(false)
        }
      } catch {
        if (!cancelled) {
          setMetrics(undefined)
          setError(true)
        }
      } finally {
        requestInFlight = false
      }
    }

    void refresh()
    const timer = window.setInterval(() => void refresh(), 1000)
    const handleVisibilityChange = () => {
      if (!document.hidden) void refresh()
    }
    document.addEventListener("visibilitychange", handleVisibilityChange)
    return () => {
      cancelled = true
      controller.abort()
      window.clearInterval(timer)
      document.removeEventListener("visibilitychange", handleVisibilityChange)
    }
  }, [])

  return (
    <section className="grid gap-3" aria-label="Tài nguyên Jetson">
      <Card size="sm">
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <CardTitle>Tài nguyên Jetson</CardTitle>
              <CardDescription>CPU, GPU và RAM đang chạy trên thiết bị.</CardDescription>
            </div>
            <Badge variant={error ? "destructive" : "secondary"}>
              {error
                ? "Không đọc được"
                : metrics
                  ? `Cập nhật ${new Date(metrics.sampled_at).toLocaleTimeString("vi-VN")}`
                  : "Đang lấy mẫu"}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="grid gap-5 lg:grid-cols-[minmax(0,1.6fr)_1px_minmax(0,1fr)] lg:gap-6">
          <div className="grid content-start gap-4">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <CpuIcon className="size-4" aria-hidden="true" />
                <h3 className="font-medium">CPU</h3>
                <span className="text-xs text-muted-foreground">
                  {metrics?.cpu.core_count ?? "—"} lõi
                </span>
              </div>
              <span className="text-xl font-semibold tabular-nums">
                {formatPercent(metrics?.cpu.usage_percent)}
              </span>
            </div>
            <MeterRow label="Tổng" value={metrics?.cpu.usage_percent} />
            <Separator />
            <div className="grid gap-x-5 gap-y-3 sm:grid-cols-2">
              {metrics?.cpu.cores.length ? (
                metrics.cpu.cores.map((core) => (
                  <MeterRow
                    key={core.id}
                    label={`CPU ${core.id}`}
                    value={core.usage_percent}
                  />
                ))
              ) : (
                <p className="text-sm text-muted-foreground">
                  Đang chờ số liệu từng lõi.
                </p>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              Nhiệt độ CPU: {formatTemperature(metrics?.cpu.temperature_c)}
            </p>
          </div>

          <Separator className="lg:hidden" />
          <Separator orientation="vertical" className="hidden lg:block" />

          <div className="grid content-start gap-5">
            <div className="grid gap-4">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <GaugeIcon className="size-4" aria-hidden="true" />
                  <h3 className="font-medium">GPU</h3>
                </div>
                <span className="text-xl font-semibold tabular-nums">
                  {formatPercent(metrics?.gpu.usage_percent)}
                </span>
              </div>
              <MeterRow label="GR3D" value={metrics?.gpu.usage_percent} />
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-xs text-muted-foreground">Xung nhịp</p>
                  <p className="font-medium tabular-nums">
                    {formatFrequency(metrics?.gpu.frequency_mhz)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Nhiệt độ</p>
                  <p className="font-medium tabular-nums">
                    {formatTemperature(metrics?.gpu.temperature_c)}
                  </p>
                </div>
              </div>
            </div>

            <Separator />

            <div className="grid gap-4">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <MemoryStickIcon className="size-4" aria-hidden="true" />
                  <h3 className="font-medium">RAM</h3>
                </div>
                <span className="text-xl font-semibold tabular-nums">
                  {formatPercent(metrics?.ram.usage_percent)}
                </span>
              </div>
              <MeterRow label="RAM" value={metrics?.ram.usage_percent} />
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-xs text-muted-foreground">Đang dùng</p>
                  <p className="font-medium tabular-nums">
                    {formatGiB(metrics?.ram.used_bytes)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Tổng</p>
                  <p className="font-medium tabular-nums">
                    {formatGiB(metrics?.ram.total_bytes)}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </section>
  )
}
