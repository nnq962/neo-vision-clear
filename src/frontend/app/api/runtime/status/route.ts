import { getRuntimeProcessStatus } from "@/lib/server/runtime"

export const dynamic = "force-dynamic"

export async function GET(): Promise<Response> {
  const status = await getRuntimeProcessStatus()
  return Response.json(status, {
    headers: { "Cache-Control": "no-store" },
  })
}
