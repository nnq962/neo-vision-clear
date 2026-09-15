"use server"

import type {
  BaselineConfig,
  CalibrationPoint,
  CalibrationRunStatus,
} from "@/lib/types/calibration"

export type SaveBaselineState = {
  status: "idle" | "success" | "error"
  message: string
  baseline?: BaselineConfig
}

export type CalibrationRunResult = {
  status: "success" | "error"
  message: string
  run?: CalibrationRunStatus
}

export type SaveAndStartBaselineResult = {
  status: "success" | "error"
  message: string
  baseline?: BaselineConfig
  run?: CalibrationRunStatus
}

function readErrorMessage(payload: unknown): string {
  if (typeof payload !== "object" || payload === null || !("detail" in payload)) {
    return "Không thể lưu cấu hình baseline."
  }

  const detail = payload.detail
  if (typeof detail === "string") return detail
  if (Array.isArray(detail)) {
    const fieldLabels: Record<string, string> = {
      name: "Tên baseline",
      roi_points: "Điểm ROI",
      world_points: "Tọa độ thực",
      encoder: "Depth encoder",
      frame_count: "Số frame",
      input_size: "Input size",
      process_width: "Process width",
    }
    const messages = detail.flatMap((item) => {
      if (
        typeof item !== "object" ||
        item === null ||
        !("msg" in item) ||
        typeof item.msg !== "string"
      ) {
        return []
      }
      const message = item.msg.replace(/^Value error,\s*/i, "")
      const location =
        "loc" in item && Array.isArray(item.loc)
          ? item.loc
              .filter((part: unknown): part is string => typeof part === "string")
              .at(-1)
          : undefined
      const label = location ? fieldLabels[location] : undefined
      return [label ? `${label}: ${message}` : message]
    })
    if (messages.length) return messages.join("; ")
  }
  return "Không thể lưu cấu hình baseline."
}

function readPoints(formData: FormData, name: string): CalibrationPoint[] | undefined {
  try {
    const value: unknown = JSON.parse(String(formData.get(name) ?? ""))
    if (
      Array.isArray(value) &&
      value.length === 4 &&
      value.every(
        (point) =>
          Array.isArray(point) &&
          point.length === 2 &&
          point.every((coordinate) => Number.isFinite(coordinate))
      )
    ) {
      return value as CalibrationPoint[]
    }
  } catch {
    return undefined
  }
  return undefined
}

function mapResponse(payload: Record<string, unknown>): BaselineConfig | undefined {
  const roiPoints = payload.roi_points
  const worldPoints = payload.world_points
  if (
    typeof payload.id !== "string" ||
    typeof payload.name !== "string" ||
    typeof payload.camera_id !== "string" ||
    !Array.isArray(roiPoints) ||
    !Array.isArray(worldPoints) ||
    payload.unit !== "m" ||
    typeof payload.origin !== "string" ||
    typeof payload.x_axis !== "string" ||
    typeof payload.y_axis !== "string" ||
    (payload.encoder !== "vits" && payload.encoder !== "vitb" && payload.encoder !== "vitl") ||
    typeof payload.frame_count !== "number" ||
    typeof payload.input_size !== "number" ||
    typeof payload.process_width !== "number" ||
    typeof payload.created_at !== "string" ||
    typeof payload.updated_at !== "string"
  ) {
    return undefined
  }
  return {
    id: payload.id,
    name: payload.name,
    cameraId: payload.camera_id,
    roiPoints: roiPoints as CalibrationPoint[],
    worldPoints: worldPoints as CalibrationPoint[],
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

function mapRunResponse(
  payload: Record<string, unknown>
): CalibrationRunStatus | undefined {
  const status = payload.status
  if (
    typeof payload.baseline_id !== "string" ||
    (status !== "idle" &&
      status !== "running" &&
      status !== "completed" &&
      status !== "failed") ||
    typeof payload.processed_frames !== "number" ||
    typeof payload.total_frames !== "number" ||
    typeof payload.artifact_available !== "boolean"
  ) {
    return undefined
  }
  return {
    baselineId: payload.baseline_id,
    status,
    processedFrames: payload.processed_frames,
    totalFrames: payload.total_frames,
    error: typeof payload.error === "string" ? payload.error : undefined,
    artifactAvailable: payload.artifact_available,
    noiseP99: typeof payload.noise_p99 === "number" ? payload.noise_p99 : undefined,
    alignmentMedianError:
      typeof payload.alignment_median_error === "number"
        ? payload.alignment_median_error
        : undefined,
  }
}

export async function saveBaseline(
  _previousState: SaveBaselineState,
  formData: FormData
): Promise<SaveBaselineState> {
  const baselineId = String(formData.get("baseline_id") ?? "").trim()
  const name = String(formData.get("name") ?? "").trim()
  const roiPoints = readPoints(formData, "roi_points")
  const worldPoints: CalibrationPoint[] = Array.from({ length: 4 }, (_, index) => [
    Number(formData.get(`world_${index}_x`)),
    Number(formData.get(`world_${index}_y`)),
  ])

  if (!name) {
    return { status: "error", message: "Vui lòng nhập tên baseline." }
  }
  if (!roiPoints) {
    return { status: "error", message: "Vui lòng chọn đủ 4 điểm ROI." }
  }
  if (worldPoints.some((point) => point.some((value) => !Number.isFinite(value)))) {
    return { status: "error", message: "Tọa độ thực không hợp lệ." }
  }

  const body = {
    name,
    roi_points: roiPoints,
    world_points: worldPoints,
    unit: "m",
    origin: "P1",
    x_axis: "P1 → P2",
    y_axis: "P1 → P4",
    encoder: String(formData.get("encoder") ?? "vits"),
    frame_count: Number(formData.get("frame_count") ?? 60),
    input_size: Number(formData.get("input_size") ?? 518),
    process_width: Number(formData.get("process_width") ?? 960),
  }

  try {
    const apiUrl = process.env.SERVER_API_URL ?? "http://127.0.0.1:8000"
    const response = await fetch(
      baselineId
        ? `${apiUrl}/api/calibration/${encodeURIComponent(baselineId)}`
        : `${apiUrl}/api/calibration`,
      {
        method: baselineId ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        cache: "no-store",
      }
    )
    const payload: unknown = await response.json()
    if (!response.ok) {
      return { status: "error", message: readErrorMessage(payload) }
    }
    if (typeof payload !== "object" || payload === null) {
      return { status: "error", message: "Backend trả dữ liệu baseline không hợp lệ." }
    }
    const baseline = mapResponse(payload as Record<string, unknown>)
    if (!baseline) {
      return { status: "error", message: "Backend trả dữ liệu baseline không hợp lệ." }
    }

    return {
      status: "success",
      message: baselineId ? "Đã cập nhật baseline." : "Đã lưu baseline mới.",
      baseline,
    }
  } catch {
    return { status: "error", message: "Không kết nối được backend calibration." }
  }
}

export async function startCalibration(
  baselineId: string
): Promise<CalibrationRunResult> {
  try {
    const apiUrl = process.env.SERVER_API_URL ?? "http://127.0.0.1:8000"
    const response = await fetch(
      `${apiUrl}/api/calibration/${encodeURIComponent(baselineId)}/run`,
      { method: "POST", cache: "no-store" }
    )
    const payload: unknown = await response.json()
    if (!response.ok) {
      return { status: "error", message: readErrorMessage(payload) }
    }
    if (typeof payload !== "object" || payload === null) {
      return { status: "error", message: "Backend trả trạng thái không hợp lệ." }
    }
    const run = mapRunResponse(payload as Record<string, unknown>)
    if (!run) {
      return { status: "error", message: "Backend trả trạng thái không hợp lệ." }
    }
    return { status: "success", message: "Đã bắt đầu calibration.", run }
  } catch {
    return { status: "error", message: "Không kết nối được backend calibration." }
  }
}

export async function saveAndStartBaseline(
  formData: FormData
): Promise<SaveAndStartBaselineResult> {
  const saved = await saveBaseline(
    { status: "idle", message: "" },
    formData
  )
  if (saved.status === "error" || !saved.baseline) {
    return { status: "error", message: saved.message }
  }

  const started = await startCalibration(saved.baseline.id)
  if (started.status === "error" || !started.run) {
    // Hoàn tác bản ghi vừa tạo nếu worker không nhận job, tránh baseline rỗng.
    const apiUrl = process.env.SERVER_API_URL ?? "http://127.0.0.1:8000"
    await fetch(
      `${apiUrl}/api/calibration/${encodeURIComponent(saved.baseline.id)}`,
      { method: "DELETE", cache: "no-store" }
    ).catch(() => undefined)
    return {
      status: "error",
      message: started.message,
    }
  }

  return {
    status: "success",
    message: "Đã lưu baseline và bắt đầu calibration.",
    baseline: saved.baseline,
    run: started.run,
  }
}
