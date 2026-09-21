import type { Camera } from "@/lib/types/camera"

type CameraApiPayload = {
  id: string
  name: string
  source: string
  open_timeout_ms: number
  read_timeout_ms: number
}

function isCameraApiPayload(value: unknown): value is CameraApiPayload {
  return (
    typeof value === "object" &&
    value !== null &&
    "id" in value &&
    typeof value.id === "string" &&
    "name" in value &&
    typeof value.name === "string" &&
    "source" in value &&
    typeof value.source === "string" &&
    "open_timeout_ms" in value &&
    typeof value.open_timeout_ms === "number" &&
    "read_timeout_ms" in value &&
    typeof value.read_timeout_ms === "number"
  )
}

function mapCamera(payload: CameraApiPayload): Camera {
  return {
    id: payload.id,
    name: payload.name,
    source: payload.source,
    openTimeoutMs: payload.open_timeout_ms,
    readTimeoutMs: payload.read_timeout_ms,
  }
}

export async function getCameras(): Promise<Camera[]> {
  try {
    const response = await fetch("/api/cameras", { cache: "no-store" })
    if (!response.ok) return []

    const cameras: unknown = await response.json()
    if (!Array.isArray(cameras)) return []

    return cameras.filter(isCameraApiPayload).map(mapCamera)
  } catch {
    return []
  }
}

export type DeleteCameraResult =
  | { success: true }
  | { success: false; message: string }

export async function deleteCamera(cameraId: string): Promise<DeleteCameraResult> {
  try {
    const response = await fetch(`/api/cameras/${encodeURIComponent(cameraId)}`, {
      method: "DELETE",
      cache: "no-store",
    })

    if (response.ok) return { success: true }

    const payload: unknown = await response.json().catch(() => null)
    if (
      typeof payload === "object" &&
      payload !== null &&
      "detail" in payload &&
      typeof payload.detail === "string"
    ) {
      return { success: false, message: payload.detail }
    }

    return { success: false, message: "Không thể xoá camera." }
  } catch {
    return { success: false, message: "Không kết nối được backend camera." }
  }
}
