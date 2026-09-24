import type { RuntimeConfig } from "@/lib/types/runtime"

export type SaveRuntimeState = {
  status: "success" | "error"
  message: string
  runtime?: RuntimeConfig
}

function readErrorMessage(payload: unknown): string {
  if (typeof payload !== "object" || payload === null || !("detail" in payload)) {
    return "Không thể lưu cấu hình runtime."
  }
  if (typeof payload.detail === "string") return payload.detail
  if (Array.isArray(payload.detail)) {
    const messages = payload.detail.flatMap((item) => {
      if (
        typeof item !== "object" ||
        item === null ||
        !("msg" in item) ||
        typeof item.msg !== "string"
      ) {
        return []
      }
      return [item.msg.replace(/^Value error,\s*/i, "")]
    })
    if (messages.length) return messages.join("; ")
  }
  return "Cấu hình runtime không hợp lệ."
}

function readNumber(formData: FormData, name: string): number {
  const value = formData.get(name)
  if (typeof value !== "string" || value.trim() === "") return Number.NaN
  return Number(value)
}

export async function saveRuntimeConfig(
  formData: FormData
): Promise<SaveRuntimeState> {
  let activeBaselineIds: string[] = []
  try {
    const parsed: unknown = JSON.parse(
      String(formData.get("active_baseline_ids") ?? "[]")
    )
    if (Array.isArray(parsed) && parsed.every((item) => typeof item === "string")) {
      activeBaselineIds = parsed
    }
  } catch {
    return { status: "error", message: "Danh sách camera đã chọn không hợp lệ." }
  }
  const runtime: RuntimeConfig = {
    enabled: formData.get("enabled") === "true",
    activeBaselineIds,
    snapshotMaxAgeSeconds: readNumber(formData, "snapshot_max_age_seconds"),
    logIntervalSeconds: readNumber(formData, "log_interval_seconds"),
    detection: {
      noiseMultiplier: readNumber(formData, "noise_multiplier"),
      minimumDifference: readNumber(formData, "minimum_difference"),
      bevPixelsPerMeter: readNumber(formData, "bev_pixels_per_meter"),
      morphologyDivisor: readNumber(formData, "morphology_divisor"),
      depthBlurKernel: readNumber(formData, "depth_blur_kernel"),
      checkAreaPadding: readNumber(formData, "check_area_padding"),
      depthAlignment: formData.get("depth_alignment") === "true",
      alignmentInlierRatio: readNumber(formData, "alignment_inlier_ratio"),
      displayMinimumAreaRatio: readNumber(
        formData,
        "display_minimum_area_ratio"
      ),
    },
  }
  const numericValues = [
    runtime.snapshotMaxAgeSeconds,
    runtime.logIntervalSeconds,
    ...Object.values(runtime.detection).filter(
      (value): value is number => typeof value === "number"
    ),
  ]
  if (numericValues.some((value) => !Number.isFinite(value))) {
    return { status: "error", message: "Các tham số số không hợp lệ." }
  }
  if (runtime.enabled && runtime.activeBaselineIds.length === 0) {
    return {
      status: "error",
      message: "Hãy chọn baseline trước khi bật runtime.",
    }
  }

  const body = {
    enabled: runtime.enabled,
    active_baseline_ids: runtime.activeBaselineIds,
    snapshot_max_age_seconds: runtime.snapshotMaxAgeSeconds,
    log_interval_seconds: runtime.logIntervalSeconds,
    detection: {
      noise_multiplier: runtime.detection.noiseMultiplier,
      minimum_difference: runtime.detection.minimumDifference,
      bev_pixels_per_meter: runtime.detection.bevPixelsPerMeter,
      morphology_divisor: runtime.detection.morphologyDivisor,
      depth_blur_kernel: runtime.detection.depthBlurKernel,
      check_area_padding: runtime.detection.checkAreaPadding,
      depth_alignment: runtime.detection.depthAlignment,
      alignment_inlier_ratio: runtime.detection.alignmentInlierRatio,
      display_minimum_area_ratio:
        runtime.detection.displayMinimumAreaRatio,
    },
  }

  try {
    const response = await fetch("/api/runtime", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    })
    const payload: unknown = await response.json()
    if (!response.ok) {
      return { status: "error", message: readErrorMessage(payload) }
    }
    return {
      status: "success",
      message: "Đã lưu cấu hình runtime.",
      runtime,
    }
  } catch {
    return { status: "error", message: "Không kết nối được backend runtime." }
  }
}
