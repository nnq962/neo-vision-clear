"use client"

import { useCallback, useEffect, useState } from "react"
import {
  CameraIcon,
  CircleIcon,
  Loader2Icon,
  PlusIcon,
  Trash2Icon,
  VideoIcon,
} from "lucide-react"
import { toast } from "sonner"

import { CameraForm } from "./camera-form"
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
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { deleteCamera, getCameras } from "@/lib/server/cameras"
import type { Camera } from "@/lib/types/camera"

function formatCameraSource(source: string) {
  try {
    const url = new URL(source)
    return `${url.protocol}//${url.host}${url.pathname}`
  } catch {
    return "Nguồn RTSP đã cấu hình"
  }
}

export default function CamerasPage() {
  const [cameras, setCameras] = useState<Camera[]>([])
  const [loaded, setLoaded] = useState(false)
  const [formOpen, setFormOpen] = useState(false)
  const [deletingCameraId, setDeletingCameraId] = useState<string | null>(null)

  useEffect(() => {
    void getCameras().then((items) => {
      setCameras(items)
      setLoaded(true)
    })
  }, [])

  const handleCameraAdded = useCallback((camera: Camera) => {
    setCameras((current) => {
      if (current.some((item) => item.id === camera.id)) return current
      return [...current, camera]
    })
    setFormOpen(false)
  }, [])

  const handleDeleteCamera = useCallback(async (camera: Camera) => {
    const confirmed = window.confirm(
      `Bạn có chắc muốn xoá camera “${camera.name}”? Baseline của camera này vẫn sẽ được giữ lại.`
    )
    if (!confirmed) return

    setDeletingCameraId(camera.id)
    const result = await deleteCamera(camera.id)

    if (!result.success) {
      toast.error(result.message)
      setDeletingCameraId(null)
      return
    }

    setCameras((current) => current.filter((item) => item.id !== camera.id))
    setDeletingCameraId(null)
    toast.success(`Đã xoá camera “${camera.name}”.`)
  }, [])

  return (
    <div className="flex flex-1 flex-col gap-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Camera</h1>
          <p className="text-muted-foreground">
            Quản lý các nguồn RTSP được xử lý theo batch trong hệ thống.
          </p>
        </div>

        <Sheet open={formOpen} onOpenChange={setFormOpen}>
          <SheetTrigger render={<Button />}>
            <PlusIcon data-icon="inline-start" />
            Thêm camera
          </SheetTrigger>
          <SheetContent>
            <SheetHeader>
              <SheetTitle>Thêm camera</SheetTitle>
              <SheetDescription>
                Khai báo nguồn RTSP mới. Phần vùng giám sát sẽ được cấu hình riêng
                ở bước sau.
              </SheetDescription>
            </SheetHeader>
            <CameraForm onCameraAdded={handleCameraAdded} />
          </SheetContent>
        </Sheet>
      </div>

      {!loaded ? (
        <div className="grid gap-6 md:grid-cols-2 2xl:grid-cols-3">
          {[0, 1].map((item) => (
            <Card key={item}>
              <CardHeader>
                <Skeleton className="h-5 w-40" />
                <Skeleton className="h-4 w-56" />
              </CardHeader>
              <CardContent>
                <Skeleton className="aspect-video w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : cameras.length === 0 ? (
        <Card>
          <CardContent className="flex min-h-72 flex-col items-center justify-center gap-3 text-center">
            <CameraIcon className="size-10 text-muted-foreground" />
            <div>
              <p className="font-medium">Chưa có camera</p>
              <p className="text-sm text-muted-foreground">
                Thêm nguồn RTSP đầu tiên để bắt đầu theo dõi hành lang.
              </p>
            </div>
            <Button onClick={() => setFormOpen(true)}>
              <PlusIcon data-icon="inline-start" />
              Thêm camera
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-6 md:grid-cols-2 2xl:grid-cols-3">
          {cameras.map((camera) => (
            <Card key={camera.id}>
              <CardHeader>
                <CardTitle>{camera.name}</CardTitle>
                <CardDescription className="truncate">
                  {formatCameraSource(camera.source)}
                </CardDescription>
                <CardAction>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary">
                      <CircleIcon data-icon="inline-start" className="fill-current" />
                      Đã cấu hình
                    </Badge>
                    <Button
                      variant="destructive"
                      size="icon-sm"
                      type="button"
                      aria-label={`Xoá camera ${camera.name}`}
                      title={`Xoá camera ${camera.name}`}
                      disabled={deletingCameraId !== null}
                      onClick={() => void handleDeleteCamera(camera)}
                    >
                      {deletingCameraId === camera.id ? (
                        <Loader2Icon className="animate-spin" />
                      ) : (
                        <Trash2Icon />
                      )}
                    </Button>
                  </div>
                </CardAction>
              </CardHeader>
              <CardContent>
                <LiveCameraPlayer
                  cameraId={camera.id}
                  cameraName={camera.name}
                />
              </CardContent>
              <CardFooter className="justify-between border-t text-xs text-muted-foreground">
                <span className="inline-flex items-center gap-1.5">
                  <VideoIcon className="size-3.5" />
                  WebRTC qua MediaMTX
                </span>
                <span>ID: {camera.id}</span>
              </CardFooter>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
