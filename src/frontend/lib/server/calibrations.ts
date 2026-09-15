import "server-only"

import type {
  BaselineConfig,
  CalibrationPoint,
} from "@/lib/types/calibration"

type BaselineApiPayload = {
  id: string
  name: string
  camera_id: string
  roi_points: CalibrationPoint[]
  world_points: CalibrationPoint[]
  unit: "m"
  origin: string
  x_axis: string
  y_axis: string
  encoder: "vits" | "vitb" | "vitl"
  frame_count: number
  input_size: number
  process_width: number
  created_at: string
  updated_at: string
}

function isPointList(value: unknown): value is CalibrationPoint[] {
  return (
    Array.isArray(value) &&
    value.length === 4 &&
    value.every(
      (point) =>
        Array.isArray(point) &&
        point.length === 2 &&
        point.every((coordinate) => typeof coordinate === "number")
    )
  )
}

function isBaselineApiPayload(value: unknown): value is BaselineApiPayload {
  return (
    typeof value === "object" &&
    value !== null &&
    "id" in value &&
    typeof value.id === "string" &&
    "name" in value &&
    typeof value.name === "string" &&
    "camera_id" in value &&
    typeof value.camera_id === "string" &&
    "roi_points" in value &&
    isPointList(value.roi_points) &&
    "world_points" in value &&
    isPointList(value.world_points) &&
    "unit" in value &&
    value.unit === "m" &&
    "origin" in value &&
    typeof value.origin === "string" &&
    "x_axis" in value &&
    typeof value.x_axis === "string" &&
    "y_axis" in value &&
    typeof value.y_axis === "string" &&
    "encoder" in value &&
    (value.encoder === "vits" || value.encoder === "vitb" || value.encoder === "vitl") &&
    "frame_count" in value &&
    typeof value.frame_count === "number" &&
    "input_size" in value &&
    typeof value.input_size === "number" &&
    "process_width" in value &&
    typeof value.process_width === "number" &&
    "created_at" in value &&
    typeof value.created_at === "string" &&
    "updated_at" in value &&
    typeof value.updated_at === "string"
  )
}

function mapBaseline(payload: BaselineApiPayload): BaselineConfig {
  return {
    id: payload.id,
    name: payload.name,
    cameraId: payload.camera_id,
    roiPoints: payload.roi_points,
    worldPoints: payload.world_points,
    unit: payload.unit,
    origin: payload.origin,
    xAxis: payload.x_axis,
    yAxis: payload.y_axis,
    encoder: payload.encoder,
    frameCount: payload.frame_count,
    inputSize: payload.input_size,
    processWidth: payload.process_width,
    createdAt: payload.created_at,
    updatedAt: payload.updated_at,
  }
}

export async function getBaselines(): Promise<BaselineConfig[]> {
  try {
    const apiUrl = process.env.SERVER_API_URL ?? "http://127.0.0.1:8000"
    const response = await fetch(`${apiUrl}/api/calibration`, { cache: "no-store" })
    if (!response.ok) return []

    const payload: unknown = await response.json()
    if (!Array.isArray(payload)) return []
    return payload.filter(isBaselineApiPayload).map(mapBaseline)
  } catch {
    return []
  }
}

export async function getBaselineArtifactAvailability(
  baselineIds: string[]
): Promise<Record<string, boolean>> {
  const apiUrl = process.env.SERVER_API_URL ?? "http://127.0.0.1:8000"
  const entries = await Promise.all(
    baselineIds.map(async (baselineId) => {
      try {
        const response = await fetch(
          `${apiUrl}/api/calibration/${encodeURIComponent(baselineId)}/status`,
          { cache: "no-store" }
        )
        if (!response.ok) return [baselineId, false] as const
        const payload: unknown = await response.json()
        const available =
          typeof payload === "object" &&
          payload !== null &&
          "artifact_available" in payload &&
          payload.artifact_available === true
        return [baselineId, available] as const
      } catch {
        return [baselineId, false] as const
      }
    })
  )
  return Object.fromEntries(entries)
}
