import {
  getBaselineArtifactAvailability,
  getBaselines,
} from "@/lib/server/calibrations"
import { getCurrentCamera } from "@/lib/server/cameras"
import {
  getRuntimeConfig,
  getRuntimeProcessStatus,
} from "@/lib/server/runtime"

import { OverviewDashboard } from "./overview-dashboard"

export const dynamic = "force-dynamic"

export default async function OverviewPage() {
  const [camera, baselines, runtime, processStatus] = await Promise.all([
    getCurrentCamera(),
    getBaselines(),
    getRuntimeConfig(),
    getRuntimeProcessStatus(),
  ])
  const activeBaseline = baselines.find(
    (baseline) => baseline.id === runtime.activeBaselineId
  )
  const availability = runtime.activeBaselineId
    ? await getBaselineArtifactAvailability([runtime.activeBaselineId])
    : {}

  return (
    <OverviewDashboard
      camera={camera ? { id: camera.id, name: camera.name } : undefined}
      activeBaseline={
        runtime.activeBaselineId
          ? {
              id: runtime.activeBaselineId,
              name: activeBaseline?.name ?? runtime.activeBaselineId,
              ready: availability[runtime.activeBaselineId] === true,
              roiPoints: activeBaseline?.roiPoints ?? [],
            }
          : undefined
      }
      initialProcessStatus={processStatus}
    />
  )
}
