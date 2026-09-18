"use client"

import { useEffect, useState } from "react"

import {
  getBaselines,
  getCalibrationRunStatuses,
} from "@/lib/server/calibrations"
import { getCurrentCamera } from "@/lib/server/cameras"
import type { CalibrationRunStatus, BaselineConfig } from "@/lib/types/calibration"
import type { CameraIdentity } from "@/lib/types/camera"

import { CalibrationPageContent } from "./calibration-page-content"

type CalibrationPageData = {
  camera?: CameraIdentity
  baselines: BaselineConfig[]
  runStatuses: Record<string, CalibrationRunStatus>
}

export default function CalibrationPage() {
  const [data, setData] = useState<CalibrationPageData>()

  useEffect(() => {
    void Promise.all([getCurrentCamera(), getBaselines()]).then(
      async ([camera, baselines]) => {
        const cameraBaselines = baselines.filter(
          (baseline) => baseline.cameraId === camera?.id
        )
        const runStatuses = await getCalibrationRunStatuses(
          cameraBaselines.map((baseline) => baseline.id)
        )
        setData({
          camera: camera ? { id: camera.id, name: camera.name } : undefined,
          baselines: cameraBaselines,
          runStatuses,
        })
      }
    )
  }, [])

  if (!data) {
    return <p className="text-sm text-muted-foreground">Đang tải calibration...</p>
  }

  return (
    <CalibrationPageContent
      key={data.baselines.map((baseline) => baseline.updatedAt).join("|")}
      camera={data.camera}
      initialBaselines={data.baselines}
      initialRunStatuses={data.runStatuses}
    />
  )
}
