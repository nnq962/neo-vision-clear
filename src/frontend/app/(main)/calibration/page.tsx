import { getBaselines } from "@/lib/server/calibrations"
import { getCurrentCamera } from "@/lib/server/cameras"

import { CalibrationPageContent } from "./calibration-page-content"

export const dynamic = "force-dynamic"

export default async function CalibrationPage() {
  const [camera, baselines] = await Promise.all([
    getCurrentCamera(),
    getBaselines(),
  ])

  return (
    <CalibrationPageContent
      key={baselines.map((baseline) => baseline.updatedAt).join("|")}
      camera={camera ? { id: camera.id, name: camera.name } : undefined}
      initialBaselines={baselines}
    />
  )
}
