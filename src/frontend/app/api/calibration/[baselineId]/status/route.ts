import { getCalibrationRunStatuses } from "@/lib/server/calibrations"

export const dynamic = "force-dynamic"

export async function GET(
  _request: Request,
  context: RouteContext<"/api/calibration/[baselineId]/status">
): Promise<Response> {
  const { baselineId } = await context.params
  const statuses = await getCalibrationRunStatuses([baselineId])
  const status = statuses[baselineId]
  if (!status) {
    return Response.json(
      { detail: "Không tải được trạng thái calibration." },
      { status: 502 }
    )
  }
  return Response.json(status, {
    headers: { "Cache-Control": "no-store" },
  })
}
