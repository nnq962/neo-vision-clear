import "server-only"

import type { RuntimeConfig, RuntimeProcessStatus } from "@/lib/types/runtime"

type RuntimeApiPayload = {
  enabled: boolean
  active_baseline_id: string | null
  snapshot_max_age_seconds: number
  log_interval_seconds: number
  detection: {
    noise_multiplier: number
    minimum_difference: number
    bev_pixels_per_meter: number
    morphology_divisor: number
    depth_blur_kernel: number
    check_area_padding: number
    depth_alignment: boolean
    alignment_inlier_ratio: number
    display_minimum_area_ratio: number
  }
}

type RuntimeProcessApiPayload = {
  status: "stopped" | "starting" | "running" | "stopping" | "failed"
  active_baseline_id: string | null
  snapshot_age_ms: number | null
  error: string | null
  started_at: string | null
}

export const DEFAULT_RUNTIME_PROCESS_STATUS: RuntimeProcessStatus = {
  status: "stopped",
}

export const DEFAULT_RUNTIME_CONFIG: RuntimeConfig = {
  enabled: false,
  snapshotMaxAgeSeconds: 2,
  logIntervalSeconds: 2,
  detection: {
    noiseMultiplier: 6,
    minimumDifference: 0.03,
    bevPixelsPerMeter: 100,
    morphologyDivisor: 180,
    depthBlurKernel: 5,
    checkAreaPadding: 12,
    depthAlignment: true,
    alignmentInlierRatio: 0.55,
    displayMinimumAreaRatio: 0.001,
  },
}

function isRuntimeApiPayload(value: unknown): value is RuntimeApiPayload {
  if (typeof value !== "object" || value === null || !("detection" in value)) {
    return false
  }
  const payload = value as Record<string, unknown>
  const detection = payload.detection
  if (typeof detection !== "object" || detection === null) return false
  const detector = detection as Record<string, unknown>
  return (
    typeof payload.enabled === "boolean" &&
    (payload.active_baseline_id === null ||
      typeof payload.active_baseline_id === "string") &&
    typeof payload.snapshot_max_age_seconds === "number" &&
    typeof payload.log_interval_seconds === "number" &&
    typeof detector.noise_multiplier === "number" &&
    typeof detector.minimum_difference === "number" &&
    typeof detector.bev_pixels_per_meter === "number" &&
    typeof detector.morphology_divisor === "number" &&
    typeof detector.depth_blur_kernel === "number" &&
    typeof detector.check_area_padding === "number" &&
    typeof detector.depth_alignment === "boolean" &&
    typeof detector.alignment_inlier_ratio === "number" &&
    typeof detector.display_minimum_area_ratio === "number"
  )
}

export function mapRuntimeProcessStatus(
  value: unknown
): RuntimeProcessStatus | undefined {
  if (typeof value !== "object" || value === null) return undefined
  const payload = value as Record<string, unknown>
  const status = payload.status
  if (
    status !== "stopped" &&
    status !== "starting" &&
    status !== "running" &&
    status !== "stopping" &&
    status !== "failed"
  ) {
    return undefined
  }
  if (
    payload.active_baseline_id !== null &&
    typeof payload.active_baseline_id !== "string"
  ) {
    return undefined
  }
  if (
    payload.snapshot_age_ms !== null &&
    typeof payload.snapshot_age_ms !== "number"
  ) {
    return undefined
  }
  if (payload.error !== null && typeof payload.error !== "string") {
    return undefined
  }
  if (payload.started_at !== null && typeof payload.started_at !== "string") {
    return undefined
  }
  const typedPayload = payload as RuntimeProcessApiPayload
  return {
    status: typedPayload.status,
    activeBaselineId: typedPayload.active_baseline_id ?? undefined,
    snapshotAgeMs: typedPayload.snapshot_age_ms ?? undefined,
    error: typedPayload.error ?? undefined,
    startedAt: typedPayload.started_at ?? undefined,
  }
}

export function mapRuntimeConfig(payload: RuntimeApiPayload): RuntimeConfig {
  return {
    enabled: payload.enabled,
    activeBaselineId: payload.active_baseline_id ?? undefined,
    snapshotMaxAgeSeconds: payload.snapshot_max_age_seconds,
    logIntervalSeconds: payload.log_interval_seconds,
    detection: {
      noiseMultiplier: payload.detection.noise_multiplier,
      minimumDifference: payload.detection.minimum_difference,
      bevPixelsPerMeter: payload.detection.bev_pixels_per_meter,
      morphologyDivisor: payload.detection.morphology_divisor,
      depthBlurKernel: payload.detection.depth_blur_kernel,
      checkAreaPadding: payload.detection.check_area_padding,
      depthAlignment: payload.detection.depth_alignment,
      alignmentInlierRatio: payload.detection.alignment_inlier_ratio,
      displayMinimumAreaRatio:
        payload.detection.display_minimum_area_ratio,
    },
  }
}

export async function getRuntimeConfig(): Promise<RuntimeConfig> {
  try {
    const apiUrl = process.env.SERVER_API_URL ?? "http://127.0.0.1:8000"
    const response = await fetch(`${apiUrl}/api/runtime`, { cache: "no-store" })
    if (!response.ok) return DEFAULT_RUNTIME_CONFIG

    const payload: unknown = await response.json()
    return isRuntimeApiPayload(payload)
      ? mapRuntimeConfig(payload)
      : DEFAULT_RUNTIME_CONFIG
  } catch {
    return DEFAULT_RUNTIME_CONFIG
  }
}

export async function getRuntimeProcessStatus(): Promise<RuntimeProcessStatus> {
  try {
    const apiUrl = process.env.SERVER_API_URL ?? "http://127.0.0.1:8000"
    const response = await fetch(`${apiUrl}/api/runtime/status`, {
      cache: "no-store",
    })
    if (!response.ok) return DEFAULT_RUNTIME_PROCESS_STATUS

    const payload: unknown = await response.json()
    return mapRuntimeProcessStatus(payload) ?? DEFAULT_RUNTIME_PROCESS_STATUS
  } catch {
    return DEFAULT_RUNTIME_PROCESS_STATUS
  }
}
