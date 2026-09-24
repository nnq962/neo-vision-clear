"use client"

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type PointerEvent,
} from "react"
import { CheckCircle2Icon, CircleDotIcon } from "lucide-react"
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
import type { CameraIdentity } from "@/lib/types/camera"

type RoiPoint = {
  x: number
  y: number
}

const VIEW_WIDTH = 1000
const VIEW_HEIGHT = 562.5
const MAX_POINTS = 4

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(Math.max(value, minimum), maximum)
}

export type CalibrationCameraWorkspaceHandle = {
  resetPoints: () => void
}

type CalibrationCameraWorkspaceProps = {
  camera?: CameraIdentity
  initialPoints?: [number, number][]
  formId?: string
  onPointCountChange?: (count: number) => void
}

export const CalibrationCameraWorkspace = forwardRef<
  CalibrationCameraWorkspaceHandle,
  CalibrationCameraWorkspaceProps
>(function CalibrationCameraWorkspace(
  { camera, initialPoints = [], formId, onPointCountChange },
  ref
) {
  const [points, setPoints] = useState<RoiPoint[]>(() =>
    initialPoints.map(([x, y]) => ({ x: x * VIEW_WIDTH, y: y * VIEW_HEIGHT }))
  )
  const svgRef = useRef<SVGSVGElement>(null)
  const draggingIndexRef = useRef<number | null>(null)
  const dragFrameRef = useRef(0)
  const pendingPointRef = useRef<RoiPoint | undefined>(undefined)

  function pointFromEvent(event: PointerEvent<SVGSVGElement>): RoiPoint {
    const bounds = event.currentTarget.getBoundingClientRect()
    return {
      x: clamp(((event.clientX - bounds.left) / bounds.width) * VIEW_WIDTH, 0, VIEW_WIDTH),
      y: clamp(((event.clientY - bounds.top) / bounds.height) * VIEW_HEIGHT, 0, VIEW_HEIGHT),
    }
  }

  function handlePointerDown(event: PointerEvent<SVGSVGElement>) {
    if (!camera) return

    const nextPoint = pointFromEvent(event)
    const thresholdX = (24 / event.currentTarget.clientWidth) * VIEW_WIDTH
    const thresholdY = (24 / event.currentTarget.clientHeight) * VIEW_HEIGHT
    const selectedIndex = points.findIndex(
      (point) =>
        Math.abs(point.x - nextPoint.x) <= thresholdX &&
        Math.abs(point.y - nextPoint.y) <= thresholdY
    )

    if (selectedIndex >= 0) {
      draggingIndexRef.current = selectedIndex
    } else if (points.length < MAX_POINTS) {
      const newPoints = [...points, nextPoint]
      setPoints(newPoints)
      draggingIndexRef.current = newPoints.length - 1
      if (newPoints.length === MAX_POINTS) {
        toast.success("Đã chọn đủ 4 điểm ROI.")
      }
    }
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  function handlePointerMove(event: PointerEvent<SVGSVGElement>) {
    if (draggingIndexRef.current === null) return

    // Giới hạn cập nhật React theo nhịp vẽ màn hình khi pointer phát sự kiện dày.
    pendingPointRef.current = pointFromEvent(event)
    if (dragFrameRef.current) return
    dragFrameRef.current = window.requestAnimationFrame(() => {
      dragFrameRef.current = 0
      const point = pendingPointRef.current
      const draggingIndex = draggingIndexRef.current
      if (!point || draggingIndex === null) return
      setPoints((currentPoints) =>
        currentPoints.map((currentPoint, index) =>
          index === draggingIndex ? point : currentPoint
        )
      )
    })
  }

  function handlePointerUp(event: PointerEvent<SVGSVGElement>) {
    if (dragFrameRef.current) {
      window.cancelAnimationFrame(dragFrameRef.current)
      dragFrameRef.current = 0
    }
    const point = pendingPointRef.current
    const draggingIndex = draggingIndexRef.current
    if (point && draggingIndex !== null) {
      setPoints((currentPoints) =>
        currentPoints.map((currentPoint, index) =>
          index === draggingIndex ? point : currentPoint
        )
      )
    }
    pendingPointRef.current = undefined
    draggingIndexRef.current = null
    if (svgRef.current?.hasPointerCapture(event.pointerId)) {
      svgRef.current.releasePointerCapture(event.pointerId)
    }
  }

  function resetPoints() {
    if (dragFrameRef.current) window.cancelAnimationFrame(dragFrameRef.current)
    setPoints([])
    pendingPointRef.current = undefined
    draggingIndexRef.current = null
  }

  useImperativeHandle(ref, () => ({ resetPoints }))
  useEffect(
    () => () => {
      if (dragFrameRef.current) window.cancelAnimationFrame(dragFrameRef.current)
    },
    []
  )
  useEffect(() => {
    onPointCountChange?.(points.length)
  }, [onPointCountChange, points.length])

  const polylinePoints = points.map((point) => `${point.x},${point.y}`).join(" ")

  return (
    <Card size="sm" className="min-w-0">
      {formId && (
        <input
          type="hidden"
          form={formId}
          name="roi_points"
          value={JSON.stringify(
            points.map((point) => [point.x / VIEW_WIDTH, point.y / VIEW_HEIGHT])
          )}
        />
      )}
      <CardHeader className="border-b">
        <CardTitle>Chọn vùng lối đi</CardTitle>
        <CardDescription>
          Nhấn để đặt P1 → P4, sau đó kéo từng điểm để chỉnh vị trí.
        </CardDescription>
        <CardAction>
          <Badge variant="secondary">
            <CircleDotIcon data-icon="inline-start" />
            {points.length} / {MAX_POINTS} điểm
          </Badge>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-3">
        <div className="relative">
          <LiveCameraPlayer
            cameraId={camera?.id}
            cameraName={camera?.name}
            className="min-h-64 pointer-events-none"
            emptyMessage="Hãy cấu hình camera trước khi chọn ROI"
          />
          <svg
            ref={svgRef}
            className="absolute inset-0 z-20 size-full touch-none cursor-crosshair rounded-xl"
            viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
            preserveAspectRatio="none"
            role="application"
            aria-label="Vẽ vùng ROI trên video camera"
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerUp}
          >
            {points.length >= 2 && points.length < MAX_POINTS && (
              <polyline
                points={polylinePoints}
                fill="none"
                stroke="#60a5fa"
                strokeWidth="4"
                vectorEffect="non-scaling-stroke"
              />
            )}
            {points.length === MAX_POINTS && (
              <polygon
                points={polylinePoints}
                fill="rgba(59, 130, 246, 0.16)"
                stroke="#60a5fa"
                strokeWidth="4"
                vectorEffect="non-scaling-stroke"
              />
            )}
            {points.map((point, index) => (
              <g key={index}>
                <circle
                  cx={point.x}
                  cy={point.y}
                  r="7"
                  fill="#18181b"
                  stroke="#93c5fd"
                  strokeWidth="2.5"
                  vectorEffect="non-scaling-stroke"
                />
                <text
                  x={point.x + 11}
                  y={point.y - 9}
                  fill="white"
                  fontSize="14"
                  fontWeight="600"
                >
                  P{index + 1}
                </text>
              </g>
            ))}
          </svg>
        </div>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {Array.from({ length: MAX_POINTS }, (_, index) => {
            const point = points[index]
            return (
              <div key={index} className="flex items-center gap-2 rounded-lg border px-2.5 py-2">
                <CircleDotIcon className="size-4 text-muted-foreground" />
                <div>
                  <p className="text-sm font-medium">P{index + 1}</p>
                  <p className="text-xs text-muted-foreground">
                    {point
                      ? `${(point.x / VIEW_WIDTH).toFixed(3)}, ${(point.y / VIEW_HEIGHT).toFixed(3)}`
                      : "Chưa chọn"}
                  </p>
                </div>
              </div>
            )
          })}
        </div>
      </CardContent>
      <CardFooter className="justify-between border-t">
        <Button type="button" variant="ghost" onClick={resetPoints} disabled={!points.length}>
          Vẽ lại ROI
        </Button>
        <Badge variant="outline">
          {points.length === MAX_POINTS && <CheckCircle2Icon data-icon="inline-start" />}
          {points.length === MAX_POINTS ? "ROI hợp lệ" : "Chưa đủ 4 điểm"}
        </Badge>
      </CardFooter>
    </Card>
  )
})
