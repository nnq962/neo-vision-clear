"use client"

import { useEffect, useState } from "react"

import {
  getBaselineArtifactAvailability,
  getBaselines,
} from "@/lib/server/calibrations"
import { getCurrentCamera } from "@/lib/server/cameras"
import { getRuntimeConfig } from "@/lib/server/runtime"
import type { BaselineConfig } from "@/lib/types/calibration"
import type { CameraIdentity } from "@/lib/types/camera"
import type { RuntimeConfig } from "@/lib/types/runtime"

import { RuntimeSettingsForm } from "./runtime-settings-form"

type SettingsPageData = {
  camera?: CameraIdentity
  baselines: BaselineConfig[]
  artifactAvailability: Record<string, boolean>
  runtime: RuntimeConfig
}

export default function SettingsPage() {
  const [data, setData] = useState<SettingsPageData>()

  useEffect(() => {
    void Promise.all([
      getCurrentCamera(),
      getBaselines(),
      getRuntimeConfig(),
    ]).then(async ([camera, baselines, runtime]) => {
      const cameraBaselines = baselines.filter(
        (baseline) => baseline.cameraId === camera?.id
      )
      const artifactAvailability = await getBaselineArtifactAvailability(
        cameraBaselines.map((baseline) => baseline.id)
      )
      setData({
        camera: camera ? { id: camera.id, name: camera.name } : undefined,
        baselines: cameraBaselines,
        artifactAvailability,
        runtime,
      })
    })
  }, [])

  if (!data) {
    return <p className="text-sm text-muted-foreground">Đang tải cài đặt...</p>
  }

  return (
    <RuntimeSettingsForm
      camera={data.camera}
      baselines={data.baselines}
      artifactAvailability={data.artifactAvailability}
      initialRuntime={data.runtime}
    />
  )
}
