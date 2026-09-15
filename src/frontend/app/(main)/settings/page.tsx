import {
  getBaselineArtifactAvailability,
  getBaselines,
} from "@/lib/server/calibrations"
import { getCurrentCamera } from "@/lib/server/cameras"
import { getRuntimeConfig } from "@/lib/server/runtime"

import { RuntimeSettingsForm } from "./runtime-settings-form"

export const dynamic = "force-dynamic"

export default async function SettingsPage() {
  const [camera, baselines, runtime] = await Promise.all([
    getCurrentCamera(),
    getBaselines(),
    getRuntimeConfig(),
  ])
  const cameraBaselines = baselines.filter(
    (baseline) => baseline.cameraId === camera?.id
  )
  const artifactAvailability = await getBaselineArtifactAvailability(
    cameraBaselines.map((baseline) => baseline.id)
  )

  return (
    <RuntimeSettingsForm
      camera={camera ? { id: camera.id, name: camera.name } : undefined}
      baselines={cameraBaselines}
      artifactAvailability={artifactAvailability}
      initialRuntime={runtime}
    />
  )
}
