"use client"

import Link from "next/link"
import { useEffect, useState, useTransition } from "react"
import {
  ActivityIcon,
  CameraIcon,
  CircleStopIcon,
  LoaderCircleIcon,
  PlayIcon,
  SettingsIcon,
  TriangleAlertIcon,
  WifiIcon,
} from "lucide-react"
import { toast } from "sonner"

import { LiveCameraPlayer } from "@/components/camera/live-camera-player"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import type { CameraIdentity } from "@/lib/types/camera"
import { mapRuntimeProcessStatus } from "@/lib/server/runtime"
import type { RuntimeProcessStatus } from "@/lib/types/runtime"

import { startRuntime, stopRuntime } from "./actions"
import { SystemMetricsPanel } from "./system-metrics-panel"

const OVERVIEW_REFRESH_INTERVAL_MS = 100

type ActiveBaseline = {
  id: string
  name: string
  ready: boolean
  roiPoints: [number, number][]
}

type OverviewSource = {
  camera: CameraIdentity
  baseline: ActiveBaseline
}

type DifferenceZone = {
  polygon: [number, number][]
  areaRatio: number
}

type CorridorData = {
  maximumPassableWidthMeters: number
  walkwayWidthMeters: number
  bottleneckYMeters: number
  freeXRangesMeters: [number, number][]
  frameIndex: number
  capturedAt: number
  differenceZones: DifferenceZone[]
}

type CorridorReading = {
  status: "ok" | "warming_up" | "stale" | "error"
  ageMs?: number
  data?: CorridorData
  error?: string
}

type ConnectionState = "closed" | "connecting" | "open" | "error"

function processStatusLabel(status: RuntimeProcessStatus["status"]): string {
  const labels: Record<RuntimeProcessStatus["status"], string> = {
    stopped: "Đã dừng",
    starting: "Đang khởi động",
    running: "Đang theo dõi",
    stopping: "Đang dừng",
    failed: "Có lỗi",
  }
  return labels[status]
}

function processBadgeVariant(
  status: RuntimeProcessStatus["status"]
): "default" | "secondary" | "destructive" | "outline" {
  if (status === "running") return "default"
  if (status === "failed") return "destructive"
  if (status === "stopped") return "outline"
  return "secondary"
}

function readingBadgeVariant(
  reading: CorridorReading
): "default" | "secondary" | "destructive" | "outline" {
  if (reading.status === "ok") return "default"
  if (reading.status === "error") return "destructive"
  if (reading.status === "stale") return "outline"
  return "secondary"
}

function readingStatusLabel(reading: CorridorReading): string {
  if (reading.status === "ok") return "Dữ liệu mới"
  if (reading.status === "warming_up") return "Đang chờ"
  if (reading.status === "stale") return "Dữ liệu cũ"
  return "Có lỗi"
}

function formatMeters(value: number | undefined): string {
  return value === undefined ? "—" : `${value.toFixed(2)} m`
}

function formatAge(ageMs: number | undefined): string {
  if (ageMs === undefined) return "Chưa có dữ liệu"
  if (ageMs < 1000) return `${ageMs} ms trước`
  return `${(ageMs / 1000).toFixed(1)} giây trước`
}

function parseCorridorReading(value: unknown): CorridorReading | undefined {
  if (typeof value !== "object" || value === null) return undefined
  const payload = value as Record<string, unknown>
  const status = payload.status
  if (
    status !== "ok" &&
    status !== "warming_up" &&
    status !== "stale" &&
    status !== "error"
  ) {
    return undefined
  }
  const ageMs = typeof payload.age_ms === "number" ? payload.age_ms : undefined
  const error = typeof payload.error === "string" ? payload.error : undefined
  if (typeof payload.data !== "object" || payload.data === null) {
    return { status, ageMs, error }
  }
  const data = payload.data as Record<string, unknown>
  const bottleneck = data.bottleneck
  if (typeof bottleneck !== "object" || bottleneck === null) {
    return { status, ageMs, error }
  }
  const bottleneckPayload = bottleneck as Record<string, unknown>
  const freeRanges = bottleneckPayload.free_x_ranges_meters
  const changedZones = data.changed_zones
  if (
    typeof data.maximum_passable_width_meters !== "number" ||
    typeof data.walkway_width_meters !== "number" ||
    typeof bottleneckPayload.y_meters !== "number" ||
    typeof data.frame_index !== "number" ||
    typeof data.captured_at !== "number" ||
    !Array.isArray(freeRanges) ||
    !freeRanges.every(
      (range) =>
        Array.isArray(range) &&
        range.length === 2 &&
        range.every((coordinate) => typeof coordinate === "number")
    ) ||
    !Array.isArray(changedZones)
  ) {
    return { status, ageMs, error }
  }
  const differenceZones: DifferenceZone[] = []
  for (const zone of changedZones) {
    if (typeof zone !== "object" || zone === null) return { status, ageMs, error }
    const zonePayload = zone as Record<string, unknown>
    const polygon = zonePayload.polygon
    if (
      typeof zonePayload.area_ratio !== "number" ||
      !Array.isArray(polygon) ||
      polygon.length < 3 ||
      !polygon.every(
        (point) =>
          Array.isArray(point) &&
          point.length === 2 &&
          point.every(
            (coordinate) =>
              typeof coordinate === "number" &&
              Number.isFinite(coordinate) &&
              coordinate >= 0 &&
              coordinate <= 1
          )
      )
    ) {
      return { status, ageMs, error }
    }
    differenceZones.push({
      polygon: polygon as [number, number][],
      areaRatio: zonePayload.area_ratio,
    })
  }
  return {
    status,
    ageMs,
    error,
    data: {
      maximumPassableWidthMeters: data.maximum_passable_width_meters,
      walkwayWidthMeters: data.walkway_width_meters,
      bottleneckYMeters: bottleneckPayload.y_meters,
      freeXRangesMeters: freeRanges as [number, number][],
      frameIndex: data.frame_index,
      capturedAt: data.captured_at,
      differenceZones,
    },
  }
}

function parseOverviewReadings(
  value: unknown
): Record<string, CorridorReading> | undefined {
  if (typeof value !== "object" || value === null) return undefined
  const payload = value as Record<string, unknown>
  if (payload.type !== "overview_info" || !Array.isArray(payload.items)) {
    return undefined
  }
  const readings: Record<string, CorridorReading> = {}
  for (const item of payload.items) {
    if (typeof item !== "object" || item === null) return undefined
    const baselineId = (item as Record<string, unknown>).baseline_id
    const reading = parseCorridorReading(item)
    if (typeof baselineId !== "string" || !reading) return undefined
    readings[baselineId] = reading
  }
  return readings
}

function overviewWebSocketUrl(): string {
  const configuredUrl = process.env.NEXT_PUBLIC_SERVER_WS_URL?.replace(/\/$/, "")
  if (configuredUrl) {
    const baseUrl = configuredUrl.replace(/\/ws\/(corridor|overview)$/, "")
    return `${baseUrl}/ws/overview`
  }
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.replace(/\/$/, "")
  if (backendUrl) {
    const baseUrl = backendUrl.replace(/^http:/, "ws:").replace(/^https:/, "wss:")
    return `${baseUrl}/ws/overview`
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
  return `${protocol}//${window.location.host}/ws/overview`
}

function CameraResultCard({
  source,
  reading,
  processActive,
  connection,
}: {
  source: OverviewSource
  reading: CorridorReading
  processActive: boolean
  connection: ConnectionState
}) {
  const streamConnected = processActive && connection === "open"
  const showReading = source.baseline.ready && streamConnected
  const isConnecting =
    processActive && (connection === "connecting" || connection === "closed")
  const showLoadingIcon =
    source.baseline.ready &&
    (isConnecting || (showReading && reading.status === "warming_up"))
  const displayData = showReading && reading.status !== "error"
    ? reading.data
    : undefined
  const statusLabel = !source.baseline.ready
    ? "Chưa sẵn sàng"
    : !processActive
      ? "Chưa chạy"
      : isConnecting
        ? "Đang kết nối"
        : !streamConnected
          ? "Mất kết nối"
          : readingStatusLabel(reading)
  const statusVariant =
    !source.baseline.ready || (processActive && connection === "error")
      ? "destructive"
      : !processActive
        ? "outline"
        : !streamConnected
          ? "secondary"
          : readingBadgeVariant(reading)
  const zones =
    showReading && reading.status === "ok"
      ? reading.data?.differenceZones ?? []
      : []
  const polygon = source.baseline.roiPoints

  return (
    <Card size="sm" className="min-w-0">
      <CardHeader className="border-b">
        <CardTitle className="min-w-0 truncate">{source.camera.name}</CardTitle>
        <CardDescription className="min-w-0 truncate">
          {source.baseline.name}
        </CardDescription>
        <CardAction>
          <Badge variant={statusVariant}>
            {showLoadingIcon ? (
              <LoaderCircleIcon data-icon="inline-start" className="animate-spin" />
            ) : !source.baseline.ready ||
              (processActive && connection === "error") ||
              (streamConnected && reading.status === "error") ? (
              <TriangleAlertIcon data-icon="inline-start" />
            ) : !processActive ? (
              <CircleStopIcon data-icon="inline-start" />
            ) : (
              <ActivityIcon data-icon="inline-start" />
            )}
            {statusLabel}
          </Badge>
        </CardAction>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div className="relative">
          <LiveCameraPlayer
            cameraId={source.camera.id}
            cameraName={source.camera.name}
            className="min-h-0"
          />
          {polygon.length >= 3 || zones.length ? (
            <svg
              viewBox="0 0 1 1"
              preserveAspectRatio="none"
              className="pointer-events-none absolute inset-0 z-20 size-full rounded-xl"
              aria-label={`${zones.length} vùng sai khác với baseline`}
            >
              {polygon.length >= 3 ? (
                <polygon
                  points={polygon
                    .map(([xValue, yValue]) => `${xValue},${yValue}`)
                    .join(" ")}
                  className="fill-emerald-500/10 stroke-emerald-400"
                  strokeDasharray="8 5"
                  strokeWidth={2}
                  vectorEffect="non-scaling-stroke"
                />
              ) : null}
              {zones.map((zone, index) => (
                <polygon
                  key={index}
                  points={zone.polygon
                    .map(([xValue, yValue]) => `${xValue},${yValue}`)
                    .join(" ")}
                  className="fill-destructive/30 stroke-destructive"
                  strokeWidth={2}
                  vectorEffect="non-scaling-stroke"
                />
              ))}
            </svg>
          ) : null}
          {zones.length ? (
            <Badge
              variant="destructive"
              className="pointer-events-none absolute right-3 top-3 z-30"
            >
              {zones.length} vùng sai khác
            </Badge>
          ) : null}
        </div>

        <div className="grid gap-2 sm:grid-cols-3">
          <div className="rounded-lg border p-2.5">
            <p className="text-xs text-muted-foreground">Rộng đi qua</p>
            <p className="font-medium tabular-nums">
              {formatMeters(displayData?.maximumPassableWidthMeters)}
            </p>
          </div>
          <div className="rounded-lg border p-2.5">
            <p className="text-xs text-muted-foreground">Hành lang</p>
            <p className="font-medium tabular-nums">
              {formatMeters(displayData?.walkwayWidthMeters)}
            </p>
          </div>
          <div className="rounded-lg border p-2.5">
            <p className="text-xs text-muted-foreground">Nút thắt Y</p>
            <p className="font-medium tabular-nums">
              {formatMeters(displayData?.bottleneckYMeters)}
            </p>
          </div>
        </div>

        {displayData?.freeXRangesMeters.length ? (
          <div className="grid gap-1.5">
            <p className="text-xs text-muted-foreground">Khoảng trống theo chiều ngang</p>
            <div className="flex flex-wrap gap-1.5">
              {displayData.freeXRangesMeters.map(([start, end], index) => (
                <Badge key={`${start}-${end}-${index}`} variant="secondary">
                  X: {start.toFixed(2)} → {end.toFixed(2)} m
                </Badge>
              ))}
            </div>
          </div>
        ) : null}

        {showReading && reading.error ? (
          <Alert variant="destructive">
            <TriangleAlertIcon />
            <AlertTitle>Không đọc được kết quả</AlertTitle>
            <AlertDescription>{reading.error}</AlertDescription>
          </Alert>
        ) : null}
      </CardContent>
      <CardFooter className="mt-auto justify-between border-t text-xs text-muted-foreground">
        <span>Frame {displayData?.frameIndex ?? "—"}</span>
        <span>{formatAge(showReading ? reading.ageMs : undefined)}</span>
      </CardFooter>
    </Card>
  )
}

export function OverviewDashboard({
  sources,
  initialProcessStatus,
}: {
  sources: OverviewSource[]
  initialProcessStatus: RuntimeProcessStatus
}) {
  const [processStatus, setProcessStatus] = useState(initialProcessStatus)
  const [readings, setReadings] = useState<Record<string, CorridorReading>>({})
  const [connection, setConnection] = useState<ConnectionState>("closed")
  const [pending, startTransition] = useTransition()
  const processActive =
    processStatus.status === "starting" ||
    processStatus.status === "running" ||
    processStatus.status === "stopping"
  const shouldStream = processActive
  const visibleConnection = shouldStream ? connection : "closed"
  const readyCount = sources.filter((source) => source.baseline.ready).length
  const canStart = sources.length > 0 && readyCount === sources.length
  const controlDisabled = pending || processStatus.status === "stopping"
  const sourceKey = sources.map((source) => source.baseline.id).join("|")

  function handleRuntimeControl() {
    startTransition(async () => {
      const result = processActive ? await stopRuntime() : await startRuntime()
      if (result.status === "error" || !result.process) {
        toast.error(result.message)
        return
      }
      setProcessStatus(result.process)
      toast.success(result.message)
    })
  }

  useEffect(() => {
    let requestInFlight = false
    const refresh = async () => {
      if (document.hidden || requestInFlight) return
      requestInFlight = true
      try {
        const response = await fetch("/api/runtime/status", { cache: "no-store" })
        if (!response.ok) return
        const status: unknown = await response.json()
        const mappedStatus = mapRuntimeProcessStatus(status)
        if (mappedStatus) setProcessStatus(mappedStatus)
      } finally {
        requestInFlight = false
      }
    }
    const timer = window.setInterval(refresh, 2500)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    if (!shouldStream) return

    let cancelled = false
    let socket: WebSocket | undefined
    let requestTimer: number | undefined
    let reconnectTimer: number | undefined
    let requestInFlight = false

    function scheduleRequest(delay = OVERVIEW_REFRESH_INTERVAL_MS) {
      if (cancelled || document.hidden) return
      if (requestTimer !== undefined) window.clearTimeout(requestTimer)
      requestTimer = window.setTimeout(requestSnapshot, delay)
    }

    function requestSnapshot() {
      requestTimer = undefined
      if (cancelled || document.hidden) return
      if (
        socket?.readyState !== WebSocket.OPEN ||
        socket.bufferedAmount > 0 ||
        requestInFlight
      ) {
        scheduleRequest()
        return
      }
      requestInFlight = true
      socket.send(
        JSON.stringify({
          type: "get_overview_info",
          request_id: `overview-${Date.now()}`,
        })
      )
    }

    function connect() {
      if (cancelled) return
      setConnection("connecting")
      socket = new WebSocket(overviewWebSocketUrl())
      socket.onopen = () => {
        if (cancelled) return
        setConnection("open")
        setReadings(
          Object.fromEntries(
            (sourceKey ? sourceKey.split("|") : []).map((baselineId) => [
              baselineId,
              { status: "warming_up" } satisfies CorridorReading,
            ])
          )
        )
        requestSnapshot()
      }
      socket.onmessage = (event) => {
        requestInFlight = false
        try {
          const parsed = parseOverviewReadings(JSON.parse(String(event.data)))
          if (parsed) setReadings(parsed)
        } catch {
          toast.error("WebSocket Overview trả dữ liệu không hợp lệ.")
        }
        scheduleRequest()
      }
      socket.onerror = () => setConnection("error")
      socket.onclose = () => {
        if (requestTimer !== undefined) window.clearTimeout(requestTimer)
        requestInFlight = false
        if (cancelled) return
        setConnection("error")
        reconnectTimer = window.setTimeout(connect, 2000)
      }
    }

    const handleVisibilityChange = () => {
      if (document.hidden) {
        if (requestTimer !== undefined) window.clearTimeout(requestTimer)
        requestTimer = undefined
      } else if (!requestInFlight) {
        scheduleRequest(0)
      }
    }

    document.addEventListener("visibilitychange", handleVisibilityChange)
    connect()
    return () => {
      cancelled = true
      if (requestTimer !== undefined) window.clearTimeout(requestTimer)
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer)
      document.removeEventListener("visibilitychange", handleVisibilityChange)
      socket?.close()
    }
  }, [shouldStream, sourceKey])

  return (
    <div className="flex w-full flex-1 flex-col gap-6">
      <div className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Tổng quan</h1>
          <p className="text-muted-foreground">
            Theo dõi lối đi và trạng thái vận hành theo thời gian thực.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            nativeButton={false}
            render={<Link href="/settings" />}
          >
            <SettingsIcon data-icon="inline-start" />
            Cài đặt
          </Button>
          <Button
            onClick={handleRuntimeControl}
            disabled={controlDisabled || (!processActive && !canStart)}
            variant={processActive ? "destructive" : "default"}
          >
            {pending || processStatus.status === "stopping" ? (
              <LoaderCircleIcon data-icon="inline-start" className="animate-spin" />
            ) : processActive ? (
              <CircleStopIcon data-icon="inline-start" />
            ) : (
              <PlayIcon data-icon="inline-start" />
            )}
            {processActive ? "Dừng" : "Bắt đầu"}
          </Button>
        </div>
      </div>

      <Card size="sm">
        <CardHeader className="border-b">
          <CardTitle>Phiên theo dõi</CardTitle>
          <CardDescription>Trạng thái xử lý và các nguồn dữ liệu hiện tại.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
          <div className="grid content-start gap-2">
            <p className="text-xs text-muted-foreground">Runtime</p>
            <Badge variant={processBadgeVariant(processStatus.status)}>
              {processStatus.status === "starting" ||
              processStatus.status === "stopping" ? (
                <LoaderCircleIcon data-icon="inline-start" className="animate-spin" />
              ) : processStatus.status === "failed" ? (
                <TriangleAlertIcon data-icon="inline-start" />
              ) : (
                <ActivityIcon data-icon="inline-start" />
              )}
              {processStatusLabel(processStatus.status)}
            </Badge>
          </div>
          <div className="grid content-start gap-2">
            <p className="text-xs text-muted-foreground">Kết nối dữ liệu</p>
            <Badge
              variant={
                visibleConnection === "open"
                  ? "default"
                  : visibleConnection === "error"
                    ? "destructive"
                    : "outline"
              }
            >
              <WifiIcon data-icon="inline-start" />
              {visibleConnection === "open"
                ? "Đã kết nối"
                : visibleConnection === "connecting" ||
                    (processActive && visibleConnection === "closed")
                  ? "Đang kết nối"
                  : visibleConnection === "error"
                    ? "Mất kết nối"
                    : "Chưa kết nối"}
            </Badge>
          </div>
          <div className="grid content-start gap-2">
            <p className="text-xs text-muted-foreground">Baseline sẵn sàng</p>
            <p className="text-lg font-semibold tabular-nums">
              {sources.length ? (
                <>
                  {readyCount}{" "}
                  <span className="text-sm font-normal text-muted-foreground">
                    / {sources.length} camera
                  </span>
                </>
              ) : (
                <span className="text-sm font-medium">Chưa có camera</span>
              )}
            </p>
          </div>
          <div className="grid content-start gap-2">
            <p className="text-xs text-muted-foreground">Phiên bắt đầu</p>
            <p className="text-sm font-medium">
              {processStatus.startedAt
                ? new Date(processStatus.startedAt).toLocaleString("vi-VN")
                : "Chưa chạy"}
            </p>
          </div>
        </CardContent>
      </Card>

      {sources.length === 0 ? (
        <Alert>
          <SettingsIcon />
          <AlertTitle>Chưa có camera trong runtime</AlertTitle>
          <AlertDescription>
            Chọn camera và baseline tại trang Cài đặt trước khi bắt đầu.
          </AlertDescription>
          <Button
            variant="outline"
            nativeButton={false}
            render={<Link href="/settings" />}
            className="col-start-2 mt-2 justify-self-start"
          >
            <SettingsIcon data-icon="inline-start" />
            Mở cài đặt
          </Button>
        </Alert>
      ) : sources.some((source) => !source.baseline.ready) ? (
        <Alert variant="destructive">
          <TriangleAlertIcon />
          <AlertTitle>Có baseline chưa sẵn sàng</AlertTitle>
          <AlertDescription>
            Hoàn tất calibration cho mọi camera tại trang{" "}
            <Link href="/calibration">Calibration</Link> trước khi chạy runtime.
          </AlertDescription>
        </Alert>
      ) : null}

      {processStatus.error ? (
        <Alert variant="destructive">
          <TriangleAlertIcon />
          <AlertTitle>Runtime gặp lỗi</AlertTitle>
          <AlertDescription>{processStatus.error}</AlertDescription>
        </Alert>
      ) : null}

      {sources.length > 0 ? (
        <section className="grid gap-4" aria-labelledby="overview-cameras-title">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 id="overview-cameras-title" className="text-lg font-semibold tracking-tight">
                Kết quả camera
              </h2>
              <p className="text-sm text-muted-foreground">
                Video trực tiếp, vùng sai khác và độ rộng lối đi.
              </p>
            </div>
            <Badge variant="secondary">
              <CameraIcon data-icon="inline-start" />
              {sources.length} camera
            </Badge>
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            {sources.map((source) => (
              <CameraResultCard
                key={source.baseline.id}
                source={source}
                reading={readings[source.baseline.id] ?? { status: "warming_up" }}
                processActive={processActive}
                connection={visibleConnection}
              />
            ))}
          </div>
        </section>
      ) : null}

      <SystemMetricsPanel />
    </div>
  )
}
