"use client"

import { CameraIcon } from "lucide-react"
import { useContext, useLayoutEffect, useRef } from "react"

import { PersistentLiveCameraContext } from "@/components/camera/persistent-live-camera-provider"
import { cn } from "@/lib/utils"

type LiveCameraPlayerProps = {
  cameraId?: string
  cameraName?: string
  className?: string
  emptyMessage?: string
}

export function LiveCameraPlayer({
  cameraId,
  cameraName = "Camera",
  className,
  emptyMessage = "Camera sẽ hiển thị sau khi kiểm tra và lưu thành công",
}: LiveCameraPlayerProps) {
  const cameraContext = useContext(PersistentLiveCameraContext)
  const hostRef = useRef<HTMLDivElement>(null)

  useLayoutEffect(() => {
    if (!cameraId || !hostRef.current || !cameraContext) return
    return cameraContext.registerHost({
      element: hostRef.current,
      cameraId,
      cameraName,
    })
  }, [cameraContext, cameraId, cameraName])

  if (cameraId) {
    return (
      <div
        ref={hostRef}
        className={cn(
          "aspect-video min-h-72 w-full rounded-xl border bg-black",
          className
        )}
        role="img"
        aria-label={`Video trực tiếp từ ${cameraName}`}
      />
    )
  }

  return (
    <div
      className={cn(
        "flex aspect-video min-h-72 items-center justify-center rounded-xl bg-zinc-950 text-zinc-400",
        className
      )}
    >
      <div className="flex flex-col items-center gap-3 text-center">
        <CameraIcon className="size-10" />
        <div>
          <p className="font-medium text-zinc-200">Camera preview</p>
          <p className="text-sm">{emptyMessage}</p>
        </div>
      </div>
    </div>
  )
}
