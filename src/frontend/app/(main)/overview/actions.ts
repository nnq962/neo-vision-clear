import { mapRuntimeProcessStatus } from "@/lib/server/runtime"
import type { RuntimeProcessStatus } from "@/lib/types/runtime"

type RuntimeControlResult = {
  status: "success" | "error"
  message: string
  process?: RuntimeProcessStatus
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
  return "Backend không thể thay đổi trạng thái runtime."
}

async function controlRuntime(
  command: "start" | "stop"
): Promise<RuntimeControlResult> {
  try {
    const response = await fetch(`/api/runtime/${command}`, {
      method: "POST",
      cache: "no-store",
    })
    const payload: unknown = await response.json()
    if (!response.ok) {
      return { status: "error", message: readErrorMessage(payload) }
    }
    const runtimeProcess = mapRuntimeProcessStatus(payload)
    if (!runtimeProcess) {
      return { status: "error", message: "Backend trả trạng thái không hợp lệ." }
    }
    return {
      status: "success",
      message:
        command === "start"
          ? "Đã gửi lệnh bắt đầu theo dõi."
          : "Đã gửi lệnh dừng theo dõi.",
      process: runtimeProcess,
    }
  } catch {
    return { status: "error", message: "Không kết nối được backend runtime." }
  }
}

export async function startRuntime(): Promise<RuntimeControlResult> {
  return controlRuntime("start")
}

export async function stopRuntime(): Promise<RuntimeControlResult> {
  return controlRuntime("stop")
}
