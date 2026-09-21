"use client"

import { useEffect, useState } from "react"

import {
  getBaselineArtifactAvailability,
  getBaselines,
} from "@/lib/server/calibrations"
import { getCameras } from "@/lib/server/cameras"
import {
  DEFAULT_RUNTIME_PROCESS_STATUS,
  getRuntimeConfig,
  getRuntimeProcessStatus,
} from "@/lib/server/runtime"
import type { CameraIdentity } from "@/lib/types/camera"
import type { CalibrationPoint } from "@/lib/types/calibration"
import type { RuntimeProcessStatus } from "@/lib/types/runtime"

import { OverviewDashboard } from "./overview-dashboard"

type OverviewPageData = {
  sources: Array<{
    camera: CameraIdentity
    baseline: {
      id: string
      name: string
      ready: boolean
      roiPoints: CalibrationPoint[]
    }
  }>
  processStatus: RuntimeProcessStatus
}

export default function OverviewPage() {
  const [data, setData] = useState<OverviewPageData>()

  useEffect(() => {
    void Promise.all([
      getCameras(),
      getBaselines(),
      getRuntimeConfig(),
      getRuntimeProcessStatus(),
    ]).then(async ([cameras, baselines, runtime, processStatus]) => {
      const availability = await getBaselineArtifactAvailability(
        runtime.activeBaselineIds
      )
      const sources = runtime.activeBaselineIds.flatMap((baselineId) => {
        const baseline = baselines.find((item) => item.id === baselineId)
        const camera = cameras.find((item) => item.id === baseline?.cameraId)
        if (!baseline || !camera) return []
        return [{
          camera: { id: camera.id, name: camera.name },
          baseline: {
            id: baseline.id,
            name: baseline.name,
            ready: availability[baseline.id] === true,
            roiPoints: baseline.roiPoints,
          },
        }]
      })
      setData({
        sources,
        processStatus,
      })
    })
  }, [])

  if (!data) {
    return <p className="text-sm text-muted-foreground">Đang tải tổng quan...</p>
  }

  return (
    <OverviewDashboard
      sources={data.sources}
      initialProcessStatus={data.processStatus ?? DEFAULT_RUNTIME_PROCESS_STATUS}
    />
  )
}
