"use client"

import { useActionState, useEffect } from "react"
import {
  CircleIcon,
  Clock3Icon,
  GaugeIcon,
  LoaderCircleIcon,
  SaveIcon,
  VideoIcon,
} from "lucide-react"
import { toast } from "sonner"

import { LiveCameraPlayer } from "@/components/camera/live-camera-player"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import type { Camera } from "@/lib/types/camera"

import { saveCamera, type SaveCameraState } from "./actions"

const initialSaveCameraState: SaveCameraState = {
  status: "idle",
  message: "",
}

export function CameraForm({ initialCamera }: { initialCamera?: Camera }) {
  const [state, formAction, pending] = useActionState(saveCamera, {
    ...initialSaveCameraState,
    cameraId: initialCamera?.id,
    cameraName: initialCamera?.name,
  })
  const cameraId = state.cameraId
  const cameraName = state.cameraName ?? "Camera hành lang chính"
  const cameraStats = [
    {
      label: "Trạng thái",
      value: cameraId ? "Đang hoạt động" : "Chưa cấu hình",
      icon: CircleIcon,
    },
    { label: "Giao thức xem", value: "WebRTC", icon: VideoIcon },
    { label: "Media server", value: "MediaMTX", icon: GaugeIcon },
    {
      label: "Camera ID",
      value: cameraId ?? "Chưa có",
      icon: Clock3Icon,
    },
  ]

  useEffect(() => {
    if (state.status === "success") {
      toast.success(state.message)
    }
    if (state.status === "error") {
      toast.error(state.message)
    }
  }, [state])

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {cameraStats.map((stat) => (
          <Card key={stat.label} size="sm">
            <CardHeader>
              <CardDescription>{stat.label}</CardDescription>
              <CardAction>
                <stat.icon className="size-4 text-muted-foreground" />
              </CardAction>
              <CardTitle>{stat.value}</CardTitle>
            </CardHeader>
          </Card>
        ))}
      </div>

      <div className="grid flex-1 gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(22rem,0.6fr)]">
        <Card>
          <CardHeader>
            <CardTitle>{cameraName}</CardTitle>
            <CardDescription>
              Hình ảnh trực tiếp từ camera đã lưu trên MediaMTX.
            </CardDescription>
            <CardAction>
              <Badge variant="secondary">
                <CircleIcon data-icon="inline-start" className="fill-current" />
                {cameraId ? "Trực tuyến" : "Chưa kết nối"}
              </Badge>
            </CardAction>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col gap-4">
            <LiveCameraPlayer cameraId={cameraId} cameraName={cameraName} />
            <Separator />
            <div className="grid gap-4 text-sm sm:grid-cols-3">
              <div>
                <p className="text-muted-foreground">Nguồn</p>
                <p className="font-medium">RTSP stream</p>
              </div>
              <div>
                <p className="text-muted-foreground">Phát trực tiếp</p>
                <p className="font-medium">WebRTC</p>
              </div>
              <div>
                <p className="text-muted-foreground">Trung gian</p>
                <p className="font-medium">MediaMTX</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Cấu hình nguồn</CardTitle>
            <CardDescription>
              Nhập URL đầy đủ, bao gồm tài khoản nếu camera yêu cầu.
            </CardDescription>
          </CardHeader>
          <form action={formAction} className="flex flex-1 flex-col">
            <CardContent className="grid gap-5">
              <div className="grid gap-2">
                <Label htmlFor="camera-name">Tên camera</Label>
                <Input
                  id="camera-name"
                  name="name"
                  placeholder="Camera hành lang"
                  defaultValue={initialCamera?.name}
                  required
                />
              </div>

              <div className="grid gap-2">
                <Label htmlFor="camera-source">Địa chỉ RTSP</Label>
                <Input
                  id="camera-source"
                  name="source"
                  placeholder="rtsp://username:password@camera.local/stream"
                  defaultValue={initialCamera?.source}
                  required
                />
              </div>

              <Separator />

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="grid gap-2">
                  <Label htmlFor="open-timeout">Open timeout (ms)</Label>
                  <Input
                    id="open-timeout"
                    name="open_timeout_ms"
                    type="number"
                    defaultValue={initialCamera?.openTimeoutMs ?? 5000}
                    min="0"
                    max="120000"
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="read-timeout">Read timeout (ms)</Label>
                  <Input
                    id="read-timeout"
                    name="read_timeout_ms"
                    type="number"
                    defaultValue={initialCamera?.readTimeoutMs ?? 5000}
                    min="0"
                    max="120000"
                  />
                </div>
              </div>

            </CardContent>
            <CardFooter className="mt-auto justify-end border-t">
              <Button type="submit" disabled={pending}>
                {pending ? (
                  <LoaderCircleIcon
                    data-icon="inline-start"
                    className="animate-spin"
                  />
                ) : (
                  <SaveIcon data-icon="inline-start" />
                )}
                {pending ? "Đang kiểm tra..." : "Kiểm tra và lưu"}
              </Button>
            </CardFooter>
          </form>
        </Card>
      </div>
    </div>
  )
}
