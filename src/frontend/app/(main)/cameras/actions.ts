import type { Camera } from "@/lib/types/camera"

export type SaveCameraState = {
  status: "idle" | "success" | "error"
  message: string
  camera?: Camera
}

function readErrorMessage(payload: unknown): string {
  if (
    typeof payload === "object" &&
    payload !== null &&
    "detail" in payload &&
    typeof payload.detail === "string"
  ) {
    return payload.detail
  }
  return "Không thể kiểm tra hoặc lưu camera."
}

export async function saveCamera(
  _previousState: SaveCameraState,
  formData: FormData
): Promise<SaveCameraState> {
  const name = String(formData.get("name") ?? "").trim()
  const source = String(formData.get("source") ?? "").trim()
  const openTimeoutMs = Number(formData.get("open_timeout_ms") ?? 5000)
  const readTimeoutMs = Number(formData.get("read_timeout_ms") ?? 5000)

  if (!name || !source) {
    return {
      status: "error",
      message: "Vui lòng nhập tên camera và URL RTSP.",
    }
  }

  try {
    const response = await fetch("/api/cameras", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        source,
        open_timeout_ms: openTimeoutMs,
        read_timeout_ms: readTimeoutMs,
      }),
      cache: "no-store",
    })
    const payload: unknown = await response.json()

    if (!response.ok) {
      return { status: "error", message: readErrorMessage(payload) }
    }
    if (
      typeof payload !== "object" ||
      payload === null ||
      !("id" in payload) ||
      typeof payload.id !== "string" ||
      !("name" in payload) ||
      typeof payload.name !== "string" ||
      !("source" in payload) ||
      typeof payload.source !== "string" ||
      !("open_timeout_ms" in payload) ||
      typeof payload.open_timeout_ms !== "number" ||
      !("read_timeout_ms" in payload) ||
      typeof payload.read_timeout_ms !== "number"
    ) {
      return { status: "error", message: "Backend trả dữ liệu camera không hợp lệ." }
    }
    return {
      status: "success",
      message: "Camera hợp lệ và đã được thêm.",
      camera: {
        id: payload.id,
        name: payload.name,
        source: payload.source,
        openTimeoutMs: payload.open_timeout_ms,
        readTimeoutMs: payload.read_timeout_ms,
      },
    }
  } catch {
    return {
      status: "error",
      message: "Không kết nối được backend camera.",
    }
  }
}
