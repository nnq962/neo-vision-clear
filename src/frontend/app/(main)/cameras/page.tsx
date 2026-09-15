import { CameraForm } from "./camera-form"
import { getCurrentCamera } from "@/lib/server/cameras"

export const dynamic = "force-dynamic"

export default async function CamerasPage() {
  const initialCamera = await getCurrentCamera()

  return (
    <div className="flex flex-1 flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Camera</h1>
        <p className="text-muted-foreground">
          Thêm một nguồn RTSP để sử dụng trong hệ thống.
        </p>
      </div>
      <CameraForm initialCamera={initialCamera} />
    </div>
  )
}
