"use client"

import { useActionState, useEffect, useRef } from "react"
import { LoaderCircleIcon, PlusIcon } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { SheetFooter } from "@/components/ui/sheet"
import type { Camera } from "@/lib/types/camera"

import { saveCamera, type SaveCameraState } from "./actions"

const initialSaveCameraState: SaveCameraState = {
  status: "idle",
  message: "",
}

export function CameraForm({
  onCameraAdded,
}: {
  onCameraAdded: (camera: Camera) => void
}) {
  const formRef = useRef<HTMLFormElement>(null)
  const [state, formAction, pending] = useActionState(
    saveCamera,
    initialSaveCameraState
  )

  useEffect(() => {
    if (state.status === "success" && state.camera) {
      toast.success(state.message)
      formRef.current?.reset()
      onCameraAdded(state.camera)
    }
    if (state.status === "error") {
      toast.error(state.message)
    }
  }, [onCameraAdded, state])

  return (
    <form ref={formRef} action={formAction} className="flex flex-1 flex-col">
      <div className="grid gap-5 overflow-y-auto px-6 pb-6">
        <div className="grid gap-2">
          <Label htmlFor="camera-name">Tên camera</Label>
          <Input
            id="camera-name"
            name="name"
            placeholder="Camera hành lang 01"
            autoComplete="off"
            required
          />
        </div>

        <div className="grid gap-2">
          <Label htmlFor="camera-source">Địa chỉ RTSP</Label>
          <Input
            id="camera-source"
            name="source"
            placeholder="rtsp://username:password@camera.local/stream"
            autoComplete="off"
            required
          />
          <p className="text-xs text-muted-foreground">
            Camera chỉ được thêm sau khi backend kiểm tra luồng thành công.
          </p>
        </div>

        <Separator />

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="grid gap-2">
            <Label htmlFor="open-timeout">Open timeout (ms)</Label>
            <Input
              id="open-timeout"
              name="open_timeout_ms"
              type="number"
              defaultValue={5000}
              min="0"
              max="120000"
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="read-timeout">Read timeout (ms)</Label>
            <Input
              id="read-timeout"
              name="read_timeout_ms"
              type="number"
              defaultValue={5000}
              min="0"
              max="120000"
            />
          </div>
        </div>
      </div>

      <SheetFooter className="border-t">
        <Button type="submit" disabled={pending}>
          {pending ? (
            <LoaderCircleIcon data-icon="inline-start" className="animate-spin" />
          ) : (
            <PlusIcon data-icon="inline-start" />
          )}
          {pending ? "Đang kiểm tra..." : "Kiểm tra và thêm"}
        </Button>
      </SheetFooter>
    </form>
  )
}
