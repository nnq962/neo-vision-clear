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

export async function getCurrentCamera(): Promise<Camera | undefined> {
  try {
    const response = await fetch("/api/cameras", { cache: "no-store" })
    if (!response.ok) return undefined

    const cameras: unknown = await response.json()
    if (!Array.isArray(cameras) || !isCameraApiPayload(cameras[0])) {
      return undefined
    }

    const camera = cameras[0]
    return {
      id: camera.id,
      name: camera.name,
      source: camera.source,
      openTimeoutMs: camera.open_timeout_ms,
      readTimeoutMs: camera.read_timeout_ms,
    }
  } catch {
    return undefined
  }
}
