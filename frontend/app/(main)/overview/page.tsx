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
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
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
    return (
      <div className="flex w-full flex-1 flex-col gap-6" aria-busy="true">
        <p className="sr-only" role="status">Đang tải tổng quan...</p>
        <div className="grid gap-2 border-b pb-5">
          <Skeleton className="h-7 w-36" />
          <Skeleton className="h-4 w-80 max-w-full" />
        </div>
        <Card size="sm">
          <CardHeader className="border-b">
            <Skeleton className="h-5 w-36" />
            <Skeleton className="h-4 w-72 max-w-full" />
          </CardHeader>
          <CardContent className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
            {[0, 1, 2, 3].map((item) => (
              <div key={item} className="grid gap-2">
                <Skeleton className="h-3 w-24" />
                <Skeleton className="h-5 w-32" />
              </div>
            ))}
          </CardContent>
        </Card>
        <div className="grid gap-4 xl:grid-cols-2">
          {[0, 1].map((item) => (
            <Card key={item} size="sm">
              <CardHeader className="border-b">
                <Skeleton className="h-5 w-32" />
                <Skeleton className="h-4 w-24" />
              </CardHeader>
              <CardContent>
                <Skeleton className="aspect-video w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    )
  }

  return (
    <OverviewDashboard
      sources={data.sources}
      initialProcessStatus={data.processStatus ?? DEFAULT_RUNTIME_PROCESS_STATUS}
    />
  )
}
