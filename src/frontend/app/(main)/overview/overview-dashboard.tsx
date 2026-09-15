"use client"

import Link from "next/link"
import { useEffect, useMemo, useState, useTransition } from "react"
import {
  ActivityIcon,
  CameraIcon,
  CircleStopIcon,
  Clock3Icon,
  GaugeIcon,
  LoaderCircleIcon,
  MapPinIcon,
  PlayIcon,
  RulerIcon,
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
import { Separator } from "@/components/ui/separator"
import type { CameraIdentity } from "@/lib/types/camera"
import type { RuntimeProcessStatus } from "@/lib/types/runtime"

import { refreshRuntimeStatus, startRuntime, stopRuntime } from "./actions"

type ActiveBaseline = {
  id: string
  name: string
  ready: boolean
  roiPoints: [number, number][]
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

type DifferenceZone = {
  polygon: [number, number][]
  areaRatio: number
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

function readingStatusLabel(reading: CorridorReading): string {
  if (reading.status === "ok") return "Dữ liệu mới"
  if (reading.status === "warming_up") return "Đang chờ kết quả"
  if (reading.status === "stale") return "Dữ liệu đã cũ"
  return "Lỗi dữ liệu"
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
    if (typeof zone !== "object" || zone === null) {
      return { status, ageMs, error }
    }
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

function overviewWebSocketUrl(): string {
  const configuredUrl = process.env.NEXT_PUBLIC_SERVER_WS_URL?.replace(/\/$/, "")
  if (configuredUrl) {
    const baseUrl = configuredUrl.replace(/\/ws\/(corridor|overview)$/, "")
    return `${baseUrl}/ws/overview`
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
  return `${protocol}//${window.location.hostname}:8000/ws/overview`
}

export function OverviewDashboard({
  camera,
  activeBaseline,
  initialProcessStatus,
}: {
  camera?: CameraIdentity
  activeBaseline?: ActiveBaseline
  initialProcessStatus: RuntimeProcessStatus
}) {
  const [processStatus, setProcessStatus] = useState(initialProcessStatus)
  const [reading, setReading] = useState<CorridorReading>({
    status: "warming_up",
  })
  const [connection, setConnection] = useState<ConnectionState>("closed")
  const [pending, startTransition] = useTransition()
  const processActive =
    processStatus.status === "starting" ||
    processStatus.status === "running" ||
    processStatus.status === "stopping"
  const shouldStream = processActive
  const displayedConnection = shouldStream ? connection : "closed"
  const visibleZones =
    shouldStream && connection === "open" && reading.status === "ok"
      ? reading.data?.differenceZones ?? []
      : []
  const walkwayPolygon = activeBaseline?.roiPoints ?? []
  const canStart = Boolean(camera && activeBaseline?.ready)
  const controlDisabled = pending || processStatus.status === "stopping"
  const lastCapture = useMemo(() => {
    if (!reading.data) return "Chưa có"
    return new Date(reading.data.capturedAt * 1000).toLocaleTimeString("vi-VN")
  }, [reading.data])

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
    const timer = window.setInterval(() => {
      void refreshRuntimeStatus().then(setProcessStatus)
    }, 1000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    if (!shouldStream) {
      return
    }

    let cancelled = false
    let socket: WebSocket | undefined
    let requestTimer: number | undefined
    let reconnectTimer: number | undefined

    function connect() {
      if (cancelled) return
      setConnection("connecting")
      socket = new WebSocket(overviewWebSocketUrl())
      socket.onopen = () => {
        if (cancelled || !socket) return
        setConnection("open")
        setReading({ status: "warming_up" })
        const requestSnapshot = () => {
          if (socket?.readyState !== WebSocket.OPEN) return
          socket.send(
            JSON.stringify({
              type: "get_overview_info",
              request_id: `overview-${Date.now()}`,
            })
          )
        }
        requestSnapshot()
        requestTimer = window.setInterval(requestSnapshot, 1000)
      }
      socket.onmessage = (event) => {
        try {
          const parsed = parseCorridorReading(JSON.parse(String(event.data)))
          if (parsed) setReading(parsed)
        } catch {
          setReading({ status: "error", error: "WebSocket trả JSON không hợp lệ." })
        }
      }
      socket.onerror = () => setConnection("error")
      socket.onclose = () => {
        if (requestTimer !== undefined) window.clearInterval(requestTimer)
        if (cancelled) return
        setConnection("error")
        reconnectTimer = window.setTimeout(connect, 2000)
      }
    }

    connect()
    return () => {
      cancelled = true
      if (requestTimer !== undefined) window.clearInterval(requestTimer)
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [shouldStream])

  const metricCards = [
    {
      label: "Bề rộng đi qua tối đa",
      value: formatMeters(reading.data?.maximumPassableWidthMeters),
      description: "Khoảng trống hẹp nhất còn có thể đi xuyên suốt",
      icon: RulerIcon,
    },
    {
      label: "Bề rộng hành lang",
      value: formatMeters(reading.data?.walkwayWidthMeters),
      description: "Chiều rộng ROI theo tọa độ calibration",
      icon: GaugeIcon,
    },
    {
      label: "Vị trí nút thắt",
      value: formatMeters(reading.data?.bottleneckYMeters),
      description: "Khoảng cách Y từ gốc calibration đến nút thắt",
      icon: MapPinIcon,
    },
  ]

  return (
    <div className="flex flex-1 flex-col gap-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Tổng quan</h1>
          <p className="text-muted-foreground">
            Xem camera, điều khiển runtime và theo dõi kết quả mới nhất.
          </p>
        </div>
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

      {!camera ? (
        <Alert variant="destructive">
          <CameraIcon />
          <AlertTitle>Chưa có camera</AlertTitle>
          <AlertDescription>
            Hãy lưu camera trước khi bắt đầu theo dõi.
          </AlertDescription>
        </Alert>
      ) : !activeBaseline ? (
        <Alert>
          <SettingsIcon />
          <AlertTitle>Chưa chọn baseline runtime</AlertTitle>
          <AlertDescription>
            Chọn một baseline hoàn tất trong trang Cài đặt trước khi chạy.
          </AlertDescription>
        </Alert>
      ) : !activeBaseline.ready ? (
        <Alert variant="destructive">
          <TriangleAlertIcon />
          <AlertTitle>Baseline chưa sẵn sàng</AlertTitle>
          <AlertDescription>
            Baseline đang chọn chưa có artifact hoàn chỉnh.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.45fr)_minmax(20rem,0.55fr)]">
        <Card>
          <CardHeader>
            <CardTitle>{camera?.name ?? "Video theo dõi"}</CardTitle>
            <CardDescription>
              Luồng trực tiếp từ camera hiện tại qua MediaMTX.
            </CardDescription>
            <CardAction>
              <Badge variant="outline">
                <CameraIcon data-icon="inline-start" />
                WebRTC
              </Badge>
            </CardAction>
          </CardHeader>
          <CardContent>
            <div className="relative">
              <LiveCameraPlayer
                cameraId={camera?.id}
                cameraName={camera?.name}
                emptyMessage="Hãy cấu hình camera để xem video trực tiếp"
              />
              {walkwayPolygon.length >= 3 || visibleZones.length ? (
                <svg
                  viewBox="0 0 1 1"
                  preserveAspectRatio="none"
                  className="pointer-events-none absolute inset-0 z-20 size-full rounded-xl"
                  aria-label={`Polygon lối đi và ${visibleZones.length} vùng sai khác với baseline`}
                >
                  {walkwayPolygon.length >= 3 ? (
                    <polygon
                      points={walkwayPolygon
                        .map(([xValue, yValue]) => `${xValue},${yValue}`)
                        .join(" ")}
                      className="fill-emerald-500/10 stroke-emerald-400"
                      strokeDasharray="8 5"
                      strokeWidth={2}
                      vectorEffect="non-scaling-stroke"
                    />
                  ) : null}
                  {visibleZones.map((zone, index) => (
                    <polygon
                      key={`${reading.data?.frameIndex}-${index}`}
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
              {walkwayPolygon.length >= 3 ? (
                <div className="pointer-events-none absolute right-3 top-3 z-30 flex gap-2">
                  <Badge variant="secondary">Viền xanh · vùng lối đi</Badge>
                  {visibleZones.length ? (
                    <Badge variant="destructive">Màu đỏ · sai khác</Badge>
                  ) : null}
                </div>
              ) : null}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Điều khiển theo dõi</CardTitle>
            <CardDescription>
              Runtime chạy trong worker nền độc lập với FastAPI.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-5">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Trạng thái</p>
                <p className="font-medium">
                  {processStatusLabel(processStatus.status)}
                </p>
              </div>
              <Badge variant={processBadgeVariant(processStatus.status)}>
                {processStatus.status}
              </Badge>
            </div>
            <Separator />
            <div>
              <p className="text-sm text-muted-foreground">Baseline</p>
              <p className="font-medium">
                {activeBaseline?.name ?? "Chưa cấu hình"}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Phiên bắt đầu</p>
              <p className="font-medium">
                {processStatus.startedAt
                  ? new Date(processStatus.startedAt).toLocaleString("vi-VN")
                  : "Chưa chạy"}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Snapshot gần nhất</p>
              <p className="font-medium">
                {formatAge(reading.ageMs ?? processStatus.snapshotAgeMs)}
              </p>
            </div>
            {processStatus.error ? (
              <Alert variant="destructive">
                <TriangleAlertIcon />
                <AlertTitle>Runtime gặp lỗi</AlertTitle>
                <AlertDescription>{processStatus.error}</AlertDescription>
              </Alert>
            ) : null}
          </CardContent>
          <CardFooter className="mt-auto flex-col items-stretch gap-3 border-t">
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
              {pending
                ? "Đang gửi lệnh..."
                : processStatus.status === "stopping"
                  ? "Đang cleanup..."
                  : processActive
                    ? "Dừng theo dõi"
                    : "Bắt đầu theo dõi"}
            </Button>
            {!canStart && !processActive ? (
              <Button variant="outline" render={<Link href="/settings" />}>
                <SettingsIcon data-icon="inline-start" />
                Mở cài đặt runtime
              </Button>
            ) : null}
          </CardFooter>
        </Card>
      </div>

      <section className="grid gap-4" aria-labelledby="latest-results-title">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 id="latest-results-title" className="text-xl font-semibold tracking-tight">
              Kết quả mới nhất
            </h2>
            <p className="text-sm text-muted-foreground">
              Các phép đo được cập nhật mỗi giây từ worker runtime.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant={displayedConnection === "open" ? "default" : "outline"}>
              <WifiIcon data-icon="inline-start" />
              {displayedConnection === "open"
                ? "WebSocket đã kết nối"
                : displayedConnection === "connecting"
                  ? "Đang kết nối"
                  : "WebSocket chưa kết nối"}
            </Badge>
            <Badge variant={reading.status === "error" ? "destructive" : "secondary"}>
              <Clock3Icon data-icon="inline-start" />
              {readingStatusLabel(reading)}
            </Badge>
            <Badge variant="outline">{visibleZones.length} vùng sai khác</Badge>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          {metricCards.map((metric) => (
            <Card key={metric.label} size="sm">
              <CardHeader>
                <CardDescription>{metric.label}</CardDescription>
                <CardAction>
                  <metric.icon className="size-4 text-muted-foreground" />
                </CardAction>
                <CardTitle className="text-2xl">{metric.value}</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-xs text-muted-foreground">
                  {metric.description}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Chi tiết nút thắt</CardTitle>
            <CardDescription>
              Các khoảng X còn trống tại vị trí hẹp nhất của hành lang.
            </CardDescription>
            <CardAction>
              <Badge variant="outline">Frame {reading.data?.frameIndex ?? "—"}</Badge>
            </CardAction>
          </CardHeader>
          <CardContent>
            {reading.data?.freeXRangesMeters.length ? (
              <div className="flex flex-wrap gap-2">
                {reading.data.freeXRangesMeters.map(([start, end], index) => (
                  <Badge key={`${start}-${end}-${index}`} variant="secondary">
                    {start.toFixed(2)} m → {end.toFixed(2)} m
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                {processActive
                  ? "Đang chờ worker công bố kết quả đầu tiên."
                  : "Bắt đầu theo dõi để nhận kết quả phân tích."}
              </p>
            )}
          </CardContent>
          <CardFooter className="justify-between border-t text-sm text-muted-foreground">
            <span>Cập nhật lúc {lastCapture}</span>
            <span>{formatAge(reading.ageMs)}</span>
          </CardFooter>
        </Card>

        {reading.error ? (
          <Alert variant="destructive">
            <TriangleAlertIcon />
            <AlertTitle>Không đọc được kết quả</AlertTitle>
            <AlertDescription>{reading.error}</AlertDescription>
          </Alert>
        ) : null}
      </section>
    </div>
  )
}
