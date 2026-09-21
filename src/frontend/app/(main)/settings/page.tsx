"use client"

import { useEffect, useState } from "react"

import {
  getBaselineArtifactAvailability,
  getBaselines,
} from "@/lib/server/calibrations"
import { getCameras } from "@/lib/server/cameras"
import { getRuntimeConfig } from "@/lib/server/runtime"
import type { BaselineConfig } from "@/lib/types/calibration"
import type { CameraIdentity } from "@/lib/types/camera"
import type { RuntimeConfig } from "@/lib/types/runtime"

import { RuntimeSettingsForm } from "./runtime-settings-form"

type SettingsPageData = {
  cameras: CameraIdentity[]
  baselines: BaselineConfig[]
  artifactAvailability: Record<string, boolean>
  runtime: RuntimeConfig
}

export default function SettingsPage() {
  const [data, setData] = useState<SettingsPageData>()

  useEffect(() => {
    void Promise.all([
      getCameras(),
      getBaselines(),
      getRuntimeConfig(),
    ]).then(async ([cameras, baselines, runtime]) => {
      const artifactAvailability = await getBaselineArtifactAvailability(
        baselines.map((baseline) => baseline.id)
      )
      setData({
        cameras: cameras.map(({ id, name }) => ({ id, name })),
        baselines,
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
      cameras={data.cameras}
      baselines={data.baselines}
      artifactAvailability={data.artifactAvailability}
      initialRuntime={data.runtime}
    />
  )
}
