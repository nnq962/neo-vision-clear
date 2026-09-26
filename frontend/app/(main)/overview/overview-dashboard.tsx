"use client"

import Link from "next/link"
import { useEffect, useRef, useState, useTransition } from "react"
import {
  ActivityIcon,
  ArrowDownIcon,
  CameraIcon,
  CircleCheckIcon,
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
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import type { CameraIdentity } from "@/lib/types/camera"
import { mapRuntimeProcessStatus } from "@/lib/server/runtime"
import type { RuntimeProcessStatus } from "@/lib/types/runtime"

import { startRuntime, stopRuntime } from "./actions"
import { SystemMetricsPanel } from "./system-metrics-panel"

const OVERVIEW_REFRESH_INTERVAL_MS = 100
const FPS_SMOOTHING_ALPHA = 0.25

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

type ClearanceZone = {
  index: number
  name: string
  startRatio: number
  endRatio: number
  freeRatio: number
  occupancyRatio: number
  walkwayWidthMeters: number
  occupiedWidthMeters: number
  freeWidthMeters: number
  blocked: boolean
  cameraPolygon: [number, number][]
}

type CorridorData = {
  frameIndex: number
  capturedAt: number
  differenceZones: DifferenceZone[]
  zones: ClearanceZone[]
  maximumOccupancyRatio: number
  maximumAllowedOccupancyRatio: number
  blockedZoneIndices: number[]
  canPass: boolean
}

type CorridorReading = {
  status: "ok" | "warming_up" | "stale" | "error"
  ageMs?: number
  data?: CorridorData
  error?: string
}

type ConnectionState = "closed" | "connecting" | "open" | "error"

type CameraFpsSample = {
  frameIndex: number
  capturedAt: number
}

type CameraFpsTracker = {
  samples: Record<string, CameraFpsSample>
  values: Record<string, number>
}

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

function formatCentimeters(value: number | undefined): string {
  return value === undefined ? "—" : `${(value * 100).toFixed(1)} cm`
}

function formatAge(ageMs: number | undefined): string {
  if (ageMs === undefined) return "Chưa có dữ liệu"
  if (ageMs < 1000) return `${ageMs} ms trước`
  return `${(ageMs / 1000).toFixed(1)} giây trước`
}

function formatPercentage(value: number): string {
  return `${Math.round(value * 100)}%`
}

function formatFps(value: number | undefined): string {
  return value === undefined ? "—" : `${value.toFixed(1)} FPS`
}

function polygonCenter(polygon: [number, number][]): [number, number] {
  const total = polygon.reduce(
    ([xTotal, yTotal], [xValue, yValue]) => [
      xTotal + xValue,
      yTotal + yValue,
    ],
    [0, 0]
  )
  return [total[0] / polygon.length, total[1] / polygon.length]
}

function polygonHeight(polygon: [number, number][]): number {
  const yValues = polygon.map(([, yValue]) => yValue)
  return Math.max(...yValues) - Math.min(...yValues)
}

function trackCameraFps(
  readings: Record<string, CorridorReading>,
  tracker: CameraFpsTracker
): CameraFpsTracker {
  const samples = { ...tracker.samples }
  let values = tracker.values

  for (const [baselineId, reading] of Object.entries(readings)) {
    const data = reading.status === "ok" ? reading.data : undefined
    if (!data) continue

    const previousSample = tracker.samples[baselineId]
    if (previousSample?.frameIndex === data.frameIndex) continue

    samples[baselineId] = {
      frameIndex: data.frameIndex,
      capturedAt: data.capturedAt,
    }
    if (!previousSample) continue

    const elapsedSeconds = data.capturedAt - previousSample.capturedAt
    const processedFrames = data.frameIndex - previousSample.frameIndex
    if (elapsedSeconds <= 0 || processedFrames <= 0) continue

    const instantFps = processedFrames / elapsedSeconds
    if (!Number.isFinite(instantFps)) continue

    const previousFps = tracker.values[baselineId]
    const smoothedFps = previousFps === undefined
      ? instantFps
      : previousFps * (1 - FPS_SMOOTHING_ALPHA) +
        instantFps * FPS_SMOOTHING_ALPHA
    if (values === tracker.values) values = { ...values }
    values[baselineId] = smoothedFps
  }

  return { samples, values }
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
  const changedZones = data.changed_zones
  const clearanceZones = data.zones
  if (
    typeof data.frame_index !== "number" ||
    typeof data.captured_at !== "number" ||
    !Array.isArray(changedZones) ||
    !Array.isArray(clearanceZones) ||
    typeof data.maximum_occupancy_ratio !== "number" ||
    typeof data.maximum_allowed_occupancy_ratio !== "number" ||
    !Array.isArray(data.blocked_zone_indices) ||
    !data.blocked_zone_indices.every(
      (index) => typeof index === "number" && Number.isInteger(index)
    ) ||
    typeof data.can_pass !== "boolean"
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
  const zones: ClearanceZone[] = []
  for (const zone of clearanceZones) {
    if (typeof zone !== "object" || zone === null) return { status, ageMs, error }
    const zonePayload = zone as Record<string, unknown>
    const cameraPolygon = zonePayload.camera_polygon
    if (
      typeof zonePayload.index !== "number" ||
      !Number.isInteger(zonePayload.index) ||
      typeof zonePayload.name !== "string" ||
      typeof zonePayload.start_ratio !== "number" ||
      typeof zonePayload.end_ratio !== "number" ||
      typeof zonePayload.free_ratio !== "number" ||
      typeof zonePayload.occupancy_ratio !== "number" ||
      typeof zonePayload.walkway_width_meters !== "number" ||
      typeof zonePayload.occupied_width_meters !== "number" ||
      typeof zonePayload.free_width_meters !== "number" ||
      typeof zonePayload.blocked !== "boolean" ||
      (cameraPolygon !== undefined &&
        (!Array.isArray(cameraPolygon) ||
          cameraPolygon.length > 8 ||
          !cameraPolygon.every(
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
          )))
    ) {
      return { status, ageMs, error }
    }
    zones.push({
      index: zonePayload.index,
      name: zonePayload.name,
      startRatio: zonePayload.start_ratio,
      endRatio: zonePayload.end_ratio,
      freeRatio: zonePayload.free_ratio,
      occupancyRatio: zonePayload.occupancy_ratio,
      walkwayWidthMeters: zonePayload.walkway_width_meters,
      occupiedWidthMeters: zonePayload.occupied_width_meters,
      freeWidthMeters: zonePayload.free_width_meters,
      blocked: zonePayload.blocked,
      cameraPolygon: Array.isArray(cameraPolygon)
        ? cameraPolygon as [number, number][]
        : [],
    })
  }
  return {
    status,
    ageMs,
    error,
    data: {
      frameIndex: data.frame_index,
      capturedAt: data.captured_at,
      differenceZones,
      zones,
      maximumOccupancyRatio: data.maximum_occupancy_ratio,
      maximumAllowedOccupancyRatio:
        data.maximum_allowed_occupancy_ratio,
      blockedZoneIndices: data.blocked_zone_indices as number[],
      canPass: data.can_pass,
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

function ClearanceZonesPanel({ data }: { data: CorridorData }) {
  const maximumZone = data.zones.reduce<ClearanceZone | undefined>(
    (maximum, zone) =>
      maximum === undefined || zone.occupancyRatio > maximum.occupancyRatio
        ? zone
        : maximum,
    undefined
  )
  const orderedZones = [...data.zones].sort(
    (first, second) => first.startRatio - second.startRatio
  )
  const showZoneLabels = orderedZones.length <= 14
  const zoneRows = orderedZones
    .map((zone) => `${Math.max(zone.endRatio - zone.startRatio, 0.001)}fr`)
    .join(" ")

  return (
    <section className="grid gap-3 rounded-lg border p-3" aria-label="Phân đoạn BEV">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium">Phân đoạn BEV</p>
          <p className="text-xs text-muted-foreground">
            Mặt bằng nhìn từ trên xuống · ngưỡng chiếm dụng{" "}
            {formatPercentage(data.maximumAllowedOccupancyRatio)}
          </p>
        </div>
        <Badge variant={data.canPass ? "default" : "destructive"}>
          {data.canPass ? (
            <CircleCheckIcon data-icon="inline-start" />
          ) : (
            <TriangleAlertIcon data-icon="inline-start" />
          )}
          {data.canPass ? "Có thể đi qua" : "Bị chặn"}
        </Badge>
      </div>

      {orderedZones.length ? (
        <figure className="mx-auto grid w-full max-w-sm gap-2">
          <figcaption className="sr-only">
            Sơ đồ hành lang BEV gồm {orderedZones.length} đoạn từ lối vào đến lối ra.
          </figcaption>
          <div className="flex items-center justify-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <span>Lối vào</span>
            <ArrowDownIcon className="size-3.5" aria-hidden="true" />
          </div>

          <div className="relative px-4">
            <div
              className="absolute inset-y-0 left-1.5 w-1 rounded-full bg-muted-foreground/25"
              aria-hidden="true"
            />
            <div
              className="absolute inset-y-0 right-1.5 w-1 rounded-full bg-muted-foreground/25"
              aria-hidden="true"
            />
            <div
              className="grid h-96 overflow-hidden border-2 bg-muted/20"
              style={{ gridTemplateRows: zoneRows }}
              role="group"
              aria-label={`Hành lang có ${orderedZones.length} đoạn; ${data.blockedZoneIndices.length} đoạn bị chặn`}
            >
              {orderedZones.map((zone) => (
                <Tooltip key={zone.index}>
                  <TooltipTrigger
                    render={
                      <button
                        type="button"
                        aria-label={`Đoạn ${zone.index}: ${formatPercentage(zone.occupancyRatio)} chiếm dụng, tương đương ${formatCentimeters(zone.occupiedWidthMeters)}, ${zone.blocked ? "bị chặn" : "đạt ngưỡng"}`}
                        className={
                          zone.blocked
                            ? "flex min-h-0 w-full cursor-default items-center justify-between gap-2 border-b border-destructive/30 bg-destructive/15 px-3 text-left text-destructive outline-none last:border-b-0 hover:bg-destructive/20 focus-visible:z-10 focus-visible:ring-2 focus-visible:ring-ring"
                            : "flex min-h-0 w-full cursor-default items-center justify-between gap-2 border-b border-emerald-500/25 bg-emerald-500/10 px-3 text-left text-emerald-800 outline-none last:border-b-0 hover:bg-emerald-500/15 focus-visible:z-10 focus-visible:ring-2 focus-visible:ring-ring dark:text-emerald-300"
                        }
                      >
                        {showZoneLabels ? (
                          <>
                            <span className="truncate text-xs font-medium">
                              Đoạn {zone.index}
                            </span>
                            <span className="shrink-0 text-xs font-semibold tabular-nums">
                              {formatPercentage(zone.occupancyRatio)} chiếm
                            </span>
                          </>
                        ) : (
                          <span className="sr-only">
                            Đoạn {zone.index}, {formatPercentage(zone.occupancyRatio)} chiếm dụng
                          </span>
                        )}
                      </button>
                    }
                  />
                  <TooltipContent>
                    <span>
                      <span className="font-medium">Đoạn {zone.index}</span>
                      {" · "}
                      {formatPercentage(zone.startRatio)}–{formatPercentage(zone.endRatio)}
                      {" chiều dài · "}
                      {formatPercentage(zone.freeRatio)} trống
                      {" · "}
                      {formatPercentage(zone.occupancyRatio)} chiếm dụng
                      {" · "}
                      {formatCentimeters(zone.occupiedWidthMeters)} chiếm
                      {" · "}
                      {formatCentimeters(zone.freeWidthMeters)} trống
                    </span>
                  </TooltipContent>
                </Tooltip>
              ))}
            </div>
          </div>

          <div className="flex items-center justify-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <ArrowDownIcon className="size-3.5" aria-hidden="true" />
            <span>Lối ra</span>
          </div>
        </figure>
      ) : (
        <p className="text-sm text-muted-foreground">
          Chưa có dữ liệu phân đoạn từ backend.
        </p>
      )}

      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 text-xs text-muted-foreground">
        <div className="flex flex-wrap gap-3">
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-emerald-500" />
            Đạt ngưỡng
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-destructive" />
            Bị chặn
          </span>
        </div>
        <span className="tabular-nums">
          Cao nhất: {formatPercentage(data.maximumOccupancyRatio)}
          {maximumZone ? ` tại đoạn ${maximumZone.index}` : ""}
        </span>
      </div>
      <p className="text-xs text-muted-foreground">
        Mỗi màu là trạng thái của một lát cắt; sơ đồ không thể hiện vị trí vật cản
        theo chiều ngang.
      </p>
    </section>
  )
}

function CameraResultCard({
  source,
  reading,
  fps,
  processActive,
  connection,
}: {
  source: OverviewSource
  reading: CorridorReading
  fps?: number
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
  const differenceZones =
    showReading && reading.status === "ok"
      ? reading.data?.differenceZones ?? []
      : []
  const clearanceZoneOverlays = displayData?.zones.filter(
    (zone) => zone.cameraPolygon.length >= 3
  ) ?? []
  const mostOccupiedZone = displayData?.zones.reduce<ClearanceZone | undefined>(
    (maximum, zone) =>
      maximum === undefined || zone.occupancyRatio > maximum.occupancyRatio
        ? zone
        : maximum,
    undefined
  )
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
          {polygon.length >= 3 ||
          differenceZones.length ||
          clearanceZoneOverlays.length ? (
            <svg
              viewBox="0 0 1 1"
              preserveAspectRatio="none"
              className="pointer-events-none absolute inset-0 z-20 size-full rounded-xl"
              role="img"
              aria-label={`${clearanceZoneOverlays.length} đoạn hành lang và ${differenceZones.length} vùng sai khác với baseline`}
            >
              {clearanceZoneOverlays.map((zone) => (
                <polygon
                  key={`clearance-zone-${zone.index}`}
                  points={zone.cameraPolygon
                    .map(([xValue, yValue]) => `${xValue},${yValue}`)
                    .join(" ")}
                  className={
                    zone.blocked
                      ? "fill-destructive/20 stroke-destructive"
                      : "fill-emerald-500/5 stroke-emerald-400/70"
                  }
                  strokeWidth={1.25}
                  vectorEffect="non-scaling-stroke"
                />
              ))}
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
              {differenceZones.map((zone, index) => (
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
          {clearanceZoneOverlays.length <= 14
            ? clearanceZoneOverlays
                .filter((zone) => polygonHeight(zone.cameraPolygon) >= 0.025)
                .map((zone) => {
                  const [centerX, centerY] = polygonCenter(zone.cameraPolygon)
                  return (
                    <span
                      key={`clearance-label-${zone.index}`}
                      className={
                        zone.blocked
                          ? "pointer-events-none absolute z-30 -translate-x-1/2 -translate-y-1/2 rounded-sm bg-destructive/85 px-1 py-0.5 text-[10px] font-medium leading-none text-destructive-foreground"
                          : "pointer-events-none absolute z-30 -translate-x-1/2 -translate-y-1/2 rounded-sm bg-background/80 px-1 py-0.5 text-[10px] font-medium leading-none text-foreground"
                      }
                      style={{
                        left: `${centerX * 100}%`,
                        top: `${centerY * 100}%`,
                      }}
                      aria-hidden="true"
                    >
                      Đ{zone.index}
                    </span>
                  )
                })
            : null}
          {differenceZones.length ? (
            <Badge
              variant="destructive"
              className="pointer-events-none absolute right-3 top-3 z-30"
            >
              {differenceZones.length} vùng sai khác
            </Badge>
          ) : null}
        </div>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div className="rounded-lg border p-2.5">
            <p className="text-xs text-muted-foreground">Chiếm dụng cao nhất</p>
            <p className="font-medium tabular-nums">
              {displayData
                ? formatPercentage(displayData.maximumOccupancyRatio)
                : "—"}
            </p>
          </div>
          <div className="rounded-lg border p-2.5">
            <p className="text-xs text-muted-foreground">Rộng bị chiếm</p>
            <p className="font-medium tabular-nums">
              {formatCentimeters(mostOccupiedZone?.occupiedWidthMeters)}
            </p>
          </div>
          <div className="rounded-lg border p-2.5">
            <p className="text-xs text-muted-foreground">Rộng còn trống</p>
            <p className="font-medium tabular-nums">
              {formatCentimeters(mostOccupiedZone?.freeWidthMeters)}
            </p>
          </div>
          <div className="rounded-lg border p-2.5">
            <p className="text-xs text-muted-foreground">FPS xử lý</p>
            <p className="font-medium tabular-nums">
              {formatFps(displayData ? fps : undefined)}
            </p>
          </div>
        </div>

        {displayData ? <ClearanceZonesPanel data={displayData} /> : null}

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
  const [cameraFps, setCameraFps] = useState<Record<string, number>>({})
  const [connection, setConnection] = useState<ConnectionState>("closed")
  const [pending, startTransition] = useTransition()
  const fpsTrackerRef = useRef<CameraFpsTracker>({ samples: {}, values: {} })
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
        fpsTrackerRef.current = { samples: {}, values: {} }
        setCameraFps({})
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
          if (parsed) {
            const previousFps = fpsTrackerRef.current.values
            const nextTracker = trackCameraFps(parsed, fpsTrackerRef.current)
            fpsTrackerRef.current = nextTracker
            if (nextTracker.values !== previousFps) {
              setCameraFps(nextTracker.values)
            }
            setReadings(parsed)
          }
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
                Video trực tiếp, FPS xử lý và độ thông thoáng theo từng đoạn BEV.
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
                fps={cameraFps[source.baseline.id]}
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
