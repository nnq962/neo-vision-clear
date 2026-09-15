import {
  getBaselines,
  getCalibrationRunStatuses,
} from "@/lib/server/calibrations"
import { getCurrentCamera } from "@/lib/server/cameras"

import { CalibrationPageContent } from "./calibration-page-content"

export const dynamic = "force-dynamic"

export default async function CalibrationPage() {
  const [camera, baselines] = await Promise.all([
    getCurrentCamera(),
    getBaselines(),
  ])
  const cameraBaselines = baselines.filter(
    (baseline) => baseline.cameraId === camera?.id
  )
  const initialRunStatuses = await getCalibrationRunStatuses(
    cameraBaselines.map((baseline) => baseline.id)
  )

  return (
    <CalibrationPageContent
      key={cameraBaselines.map((baseline) => baseline.updatedAt).join("|")}
      camera={camera ? { id: camera.id, name: camera.name } : undefined}
      initialBaselines={cameraBaselines}
      initialRunStatuses={initialRunStatuses}
    />
  )
}
