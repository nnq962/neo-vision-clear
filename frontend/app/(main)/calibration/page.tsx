"use client"

import { useEffect, useState } from "react"

import {
  getBaselines,
  getCalibrationRunStatuses,
} from "@/lib/server/calibrations"
import { getCameras } from "@/lib/server/cameras"
import type { CalibrationRunStatus, BaselineConfig } from "@/lib/types/calibration"
import type { CameraIdentity } from "@/lib/types/camera"

import { CalibrationPageContent } from "./calibration-page-content"

type CalibrationPageData = {
  cameras: CameraIdentity[]
  baselines: BaselineConfig[]
  runStatuses: Record<string, CalibrationRunStatus>
}

export default function CalibrationPage() {
  const [data, setData] = useState<CalibrationPageData>()

  useEffect(() => {
    void Promise.all([getCameras(), getBaselines()]).then(
      async ([cameras, baselines]) => {
        const runStatuses = await getCalibrationRunStatuses(
          baselines.map((baseline) => baseline.id)
        )
        setData({
          cameras: cameras.map(({ id, name }) => ({ id, name })),
          baselines,
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
      cameras={data.cameras}
      initialBaselines={data.baselines}
      initialRunStatuses={data.runStatuses}
    />
  )
}
