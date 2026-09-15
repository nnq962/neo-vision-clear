"use client"

import {
  forwardRef,
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
}

export const CalibrationCameraWorkspace = forwardRef<
  CalibrationCameraWorkspaceHandle,
  CalibrationCameraWorkspaceProps
>(function CalibrationCameraWorkspace(
  { camera, initialPoints = [], formId },
  ref
) {
  const [points, setPoints] = useState<RoiPoint[]>(() =>
    initialPoints.map(([x, y]) => ({ x: x * VIEW_WIDTH, y: y * VIEW_HEIGHT }))
  )
  const [draggingIndex, setDraggingIndex] = useState<number | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)

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
      setDraggingIndex(selectedIndex)
    } else if (points.length < MAX_POINTS) {
      const newPoints = [...points, nextPoint]
      setPoints(newPoints)
      setDraggingIndex(newPoints.length - 1)
      if (newPoints.length === MAX_POINTS) {
        toast.success("Đã chọn đủ 4 điểm ROI.")
      }
    }
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  function handlePointerMove(event: PointerEvent<SVGSVGElement>) {
    if (draggingIndex === null) return

    const nextPoint = pointFromEvent(event)
    setPoints((currentPoints) =>
      currentPoints.map((point, index) =>
        index === draggingIndex ? nextPoint : point
      )
    )
  }

  function handlePointerUp(event: PointerEvent<SVGSVGElement>) {
    setDraggingIndex(null)
    if (svgRef.current?.hasPointerCapture(event.pointerId)) {
      svgRef.current.releasePointerCapture(event.pointerId)
    }
  }

  function resetPoints() {
    setPoints([])
    setDraggingIndex(null)
  }

  useImperativeHandle(ref, () => ({ resetPoints }))

  const polylinePoints = points.map((point) => `${point.x},${point.y}`).join(" ")

  return (
    <Card>
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
      <CardHeader>
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
      <CardContent className="flex flex-1 flex-col gap-4">
        <div className="relative">
          <LiveCameraPlayer
            cameraId={camera?.id}
            cameraName={camera?.name}
            className="min-h-80 pointer-events-none"
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
          <Badge className="pointer-events-none absolute left-4 top-4 z-30" variant="outline">
            ROI · {points.length} điểm
          </Badge>
        </div>

        <div className="grid gap-3 sm:grid-cols-4">
          {Array.from({ length: MAX_POINTS }, (_, index) => {
            const point = points[index]
            return (
              <div key={index} className="flex items-center gap-2">
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
