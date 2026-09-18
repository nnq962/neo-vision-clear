"use client"

import { useEffect, useState } from "react"

import {
  getBaselineArtifactAvailability,
  getBaselines,
} from "@/lib/server/calibrations"
import { getCurrentCamera } from "@/lib/server/cameras"
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
  camera?: CameraIdentity
  activeBaseline?: {
    id: string
    name: string
    ready: boolean
    roiPoints: CalibrationPoint[]
  }
  processStatus: RuntimeProcessStatus
}

export default function OverviewPage() {
  const [data, setData] = useState<OverviewPageData>()

  useEffect(() => {
    void Promise.all([
      getCurrentCamera(),
      getBaselines(),
      getRuntimeConfig(),
      getRuntimeProcessStatus(),
    ]).then(async ([camera, baselines, runtime, processStatus]) => {
      const baseline = baselines.find(
        (item) => item.id === runtime.activeBaselineId
      )
      const availability = runtime.activeBaselineId
        ? await getBaselineArtifactAvailability([runtime.activeBaselineId])
        : {}
      setData({
        camera: camera ? { id: camera.id, name: camera.name } : undefined,
        activeBaseline: runtime.activeBaselineId
          ? {
              id: runtime.activeBaselineId,
              name: baseline?.name ?? runtime.activeBaselineId,
              ready: availability[runtime.activeBaselineId] === true,
              roiPoints: baseline?.roiPoints ?? [],
            }
          : undefined,
        processStatus,
      })
    })
  }, [])

  if (!data) {
    return <p className="text-sm text-muted-foreground">Đang tải tổng quan...</p>
  }

  return (
    <OverviewDashboard
      camera={data.camera}
      activeBaseline={data.activeBaseline}
      initialProcessStatus={data.processStatus ?? DEFAULT_RUNTIME_PROCESS_STATUS}
    />
  )
}
