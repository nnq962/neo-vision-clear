"use client"

import { useEffect, useState } from "react"

import { CameraForm } from "./camera-form"
import { getCurrentCamera } from "@/lib/server/cameras"
import type { Camera } from "@/lib/types/camera"

export default function CamerasPage() {
  const [camera, setCamera] = useState<Camera>()
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    void getCurrentCamera().then((value) => {
      setCamera(value)
      setLoaded(true)
    })
  }, [])

  return (
    <div className="flex flex-1 flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Camera</h1>
        <p className="text-muted-foreground">
          Thêm một nguồn RTSP để sử dụng trong hệ thống.
        </p>
      </div>
      {loaded ? (
        <CameraForm initialCamera={camera} />
      ) : (
        <p className="text-sm text-muted-foreground">Đang tải cấu hình camera...</p>
      )}
    </div>
  )
}
