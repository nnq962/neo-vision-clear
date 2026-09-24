"use client"

import Image from "next/image"
import Link from "next/link"
import { useEffect, useMemo, useRef, useState, useTransition } from "react"
import {
  CameraIcon,
  CheckCircle2Icon,
  Clock3Icon,
  FocusIcon,
  ImageIcon,
  LoaderCircleIcon,
  MapPinnedIcon,
  SaveIcon,
  Trash2Icon,
  TriangleAlertIcon,
} from "lucide-react"
import { toast } from "sonner"

import {
  CalibrationCameraWorkspace,
  type CalibrationCameraWorkspaceHandle,
} from "@/components/camera/calibration-camera-workspace"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
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
import { Progress, ProgressLabel } from "@/components/ui/progress"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import type {
  BaselineConfig,
  CalibrationPoint,
  CalibrationRunStatus,
} from "@/lib/types/calibration"
import type { CameraIdentity } from "@/lib/types/camera"

import { deleteBaseline, saveAndStartBaseline } from "./actions"

const FORM_ID = "calibration-form"
const DEFAULT_WORLD_POINTS: CalibrationPoint[] = [
  [0, 0],
  [1.75, 0],
  [1.75, 4.55],
  [0, 4.55],
]

const encoderItems = [
  { label: "ViT-S — nhanh", value: "vits" },
  { label: "ViT-B — cân bằng", value: "vitb" },
  { label: "ViT-L — chất lượng cao", value: "vitl" },
]

const inputSizeItems = [
  { label: "140 px — rất nhanh", value: "140" },
  { label: "196 px — ưu tiên tốc độ", value: "196" },
  { label: "224 px — nhanh hơn", value: "224" },
  { label: "280 px — nhanh", value: "280" },
  { label: "392 px — cân bằng", value: "392" },
  { label: "518 px — chất lượng cao", value: "518" },
]

type CalibrationDraft = {
  name: string
  encoder: BaselineConfig["encoder"]
  frameCount: string
  inputSize: string
  processWidth: string
  worldPoints: [string, string][]
}

function isCalibrationRunStatus(
  value: unknown
): value is CalibrationRunStatus {
  if (typeof value !== "object" || value === null) return false
  const payload = value as Record<string, unknown>
  return (
    typeof payload.baselineId === "string" &&
    (payload.status === "idle" ||
      payload.status === "running" ||
      payload.status === "completed" ||
      payload.status === "failed") &&
    typeof payload.processedFrames === "number" &&
    typeof payload.totalFrames === "number" &&
    typeof payload.artifactAvailable === "boolean"
  )
}

function createEmptyDraft(fallbackNumber: number): CalibrationDraft {
  return {
    name: `Baseline ${fallbackNumber}`,
    encoder: "vits",
    frameCount: "60",
    inputSize: "518",
    processWidth: "960",
    worldPoints: DEFAULT_WORLD_POINTS.map(([xValue, yValue]) => [
      String(xValue),
      String(yValue),
    ]),
  }
}

function normalizeBaselineName(name: string): string {
  return name.trim().toLocaleLowerCase("vi-VN")
}

function nextBaselineNumber(baselines: BaselineConfig[]): number {
  const usedNames = new Set(
    baselines.map((baseline) => normalizeBaselineName(baseline.name))
  )
  let candidate = 1
  while (usedNames.has(`baseline ${candidate}`)) candidate += 1
  return candidate
}

function statusLabel(run: CalibrationRunStatus | undefined): string {
  if (!run || run.status === "idle") return "Chưa chạy"
  if (run.status === "running") {
    return `Đang xử lý ${run.processedFrames}/${run.totalFrames}`
  }
  if (run.status === "completed") return "Hoàn tất"
  return "Thất bại"
}

function statusBadgeVariant(
  run: CalibrationRunStatus | undefined
): "outline" | "secondary" | "destructive" | "default" {
  if (run?.status === "completed") return "default"
  if (run?.status === "running") return "secondary"
  if (run?.status === "failed") return "destructive"
  return "outline"
}

export function CalibrationPageContent({
  cameras,
  initialBaselines,
  initialRunStatuses,
}: {
  cameras: CameraIdentity[]
  initialBaselines: BaselineConfig[]
  initialRunStatuses: Record<string, CalibrationRunStatus>
}) {
  const initialCameraId = cameras[0]?.id ?? ""
  const [selectedCameraId, setSelectedCameraId] = useState(initialCameraId)
  const [allBaselines, setAllBaselines] = useState(initialBaselines)
  const camera = cameras.find((item) => item.id === selectedCameraId)
  const baselines = useMemo(
    () =>
      allBaselines.filter(
        (baseline) => baseline.cameraId === selectedCameraId
      ),
    [allBaselines, selectedCameraId]
  )
  const [draft, setDraft] = useState(() =>
    createEmptyDraft(
      nextBaselineNumber(
        initialBaselines.filter(
          (baseline) => baseline.cameraId === initialCameraId
        )
      )
    )
  )
  const workspaceRef = useRef<CalibrationCameraWorkspaceHandle>(null)
  const [roiPointCount, setRoiPointCount] = useState(0)
  const [runStatuses, setRunStatuses] = useState<
    Record<string, CalibrationRunStatus>
  >(initialRunStatuses)
  const [pending, startTransition] = useTransition()
  const [deletingBaselineId, setDeletingBaselineId] = useState<string>()
  const allBaselineIds = useMemo(
    () => allBaselines.map((baseline) => baseline.id),
    [allBaselines]
  )
  const runningIds = useMemo(
    () =>
      allBaselineIds.filter(
        (baselineId) => runStatuses[baselineId]?.status === "running"
      ),
    [allBaselineIds, runStatuses]
  )

  function resetEditor(nextNumber: number) {
    setDraft(createEmptyDraft(nextNumber))
    setRoiPointCount(0)
    workspaceRef.current?.resetPoints()
  }

  function handleSave(formData: FormData) {
    const submittedName = String(formData.get("name") ?? "").trim()
    const duplicate = baselines.some(
      (baseline) =>
        normalizeBaselineName(baseline.name) ===
        normalizeBaselineName(submittedName)
    )
    if (duplicate) {
      toast.error(`Tên baseline '${submittedName}' đã tồn tại cho camera này.`)
      return
    }

    startTransition(async () => {
      const result = await saveAndStartBaseline(formData)
      if (result.baseline) {
        const savedBaseline = result.baseline
        const nextBaselines = [
          savedBaseline,
          ...allBaselines.filter((item) => item.id !== savedBaseline.id),
        ]
        setAllBaselines(nextBaselines)
        resetEditor(
          nextBaselineNumber(
            nextBaselines.filter(
              (item) => item.cameraId === selectedCameraId
            )
          )
        )
      }
      if (result.status === "error" || !result.baseline || !result.run) {
        toast.error(result.message)
        return
      }

      setRunStatuses((current) => ({
        ...current,
        [result.baseline!.id]: result.run!,
      }))

      toast.success(result.message)
    })
  }

  function handleCameraChange(cameraId: string | null) {
    if (!cameraId || cameraId === selectedCameraId) return
    setSelectedCameraId(cameraId)
    resetEditor(
      nextBaselineNumber(
        allBaselines.filter((baseline) => baseline.cameraId === cameraId)
      )
    )
  }

  async function handleDeleteBaseline(baseline: BaselineConfig) {
    const confirmed = window.confirm(
      `Xoá baseline '${baseline.name}'? Cấu hình và toàn bộ ảnh kết quả sẽ bị xoá.`
    )
    if (!confirmed) return

    setDeletingBaselineId(baseline.id)
    const result = await deleteBaseline(baseline.id)
    setDeletingBaselineId(undefined)
    if (result.status === "error") {
      toast.error(result.message)
      return
    }

    setAllBaselines((current) =>
      current.filter((item) => item.id !== baseline.id)
    )
    setRunStatuses((current) => {
      const next = { ...current }
      delete next[baseline.id]
      return next
    })
    toast.success(result.message)
  }

  function updateWorldPoint(index: number, axis: 0 | 1, value: string) {
    setDraft((current) => ({
      ...current,
      worldPoints: current.worldPoints.map((point, pointIndex) => {
        if (pointIndex !== index) return point
        return axis === 0 ? [value, point[1]] : [point[0], value]
      }),
    }))
  }

  useEffect(() => {
    if (!runningIds.length) return

    let cancelled = false
    let timer: number | undefined
    const poll = async () => {
      if (document.hidden) return
      const results = await Promise.all(
        runningIds.map(async (baselineId) => {
          try {
            const response = await fetch(
              `/api/calibration/${encodeURIComponent(baselineId)}/status`,
              { cache: "no-store" }
            )
            if (!response.ok) return undefined
            const status: unknown = await response.json()
            return isCalibrationRunStatus(status) ? status : undefined
          } catch {
            return undefined
          }
        })
      )
      if (cancelled) return
      for (const result of results) {
        if (result?.status === "completed") {
          toast.success("Calibration hoàn tất và ảnh đã sẵn sàng.")
        } else if (result?.status === "failed") {
          toast.error(result.error ?? "Calibration thất bại.")
        }
      }
      setRunStatuses((current) => {
        const next = { ...current }
        for (const result of results) {
          if (result) {
            next[result.baselineId] = result
          }
        }
        return next
      })
      timer = window.setTimeout(poll, 1000)
    }
    const handleVisibilityChange = () => {
      if (document.hidden) {
        if (timer !== undefined) window.clearTimeout(timer)
        return
      }
      timer = window.setTimeout(poll, 0)
    }
    timer = window.setTimeout(poll, 1000)
    document.addEventListener("visibilitychange", handleVisibilityChange)
    return () => {
      cancelled = true
      if (timer !== undefined) window.clearTimeout(timer)
      document.removeEventListener("visibilitychange", handleVisibilityChange)
    }
  }, [runningIds])

  return (
    <div className="flex w-full flex-1 flex-col gap-6">
      <div className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Calibration</h1>
          <p className="text-muted-foreground">
            Chọn vùng lối đi và tạo baseline cho từng camera.
          </p>
        </div>
        {cameras.length > 0 && (
          <div className="grid w-full gap-1.5 sm:w-72">
            <Label htmlFor="calibration-camera">Camera đang hiệu chỉnh</Label>
            <Select
              items={cameras.map((item) => ({
                label: item.name,
                value: item.id,
              }))}
              value={selectedCameraId}
              onValueChange={handleCameraChange}
              disabled={pending}
            >
              <SelectTrigger
                id="calibration-camera"
                className="w-full"
              >
                <CameraIcon />
                <SelectValue placeholder="Chọn camera" />
              </SelectTrigger>
              <SelectContent alignItemWithTrigger={false}>
                <SelectGroup>
                  <SelectLabel>Camera đã cấu hình</SelectLabel>
                  {cameras.map((item) => (
                    <SelectItem key={item.id} value={item.id}>
                      {item.name}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
        )}
      </div>

      {cameras.length === 0 ? (
        <Alert variant="destructive">
          <TriangleAlertIcon />
          <AlertTitle>Chưa có camera để calibration</AlertTitle>
          <AlertDescription>
            Hãy thêm ít nhất một camera tại trang <Link href="/cameras">Camera</Link>{" "}
            trước khi thiết lập ROI.
          </AlertDescription>
        </Alert>
      ) : null}

      {cameras.length > 0 && (
        <>
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(20rem,0.85fr)]">
            <CalibrationCameraWorkspace
              ref={workspaceRef}
              camera={camera}
              formId={FORM_ID}
              onPointCountChange={setRoiPointCount}
            />

            <Card size="sm" className="min-w-0">
              <CardHeader className="border-b">
                <CardTitle>Baseline mới</CardTitle>
                <CardDescription>
                  Giữ camera cố định và bảo đảm lối đi đang trống.
                </CardDescription>
              </CardHeader>
              <form id={FORM_ID} action={handleSave} className="flex flex-1 flex-col">
                <input type="hidden" name="camera_id" value={selectedCameraId} />
                <CardContent>
                  <Tabs defaultValue="baseline">
                    <TabsList className="w-full">
                      <TabsTrigger value="baseline">
                        <FocusIcon />
                        Thu baseline
                      </TabsTrigger>
                      <TabsTrigger value="coordinates">
                        <MapPinnedIcon />
                        Tọa độ thực
                      </TabsTrigger>
                    </TabsList>

                    <TabsContent value="baseline" className="pt-3" keepMounted>
                      <div className="grid gap-4">
                        <div className="grid gap-1.5">
                          <Label htmlFor="baseline-name">Tên baseline</Label>
                          <Input
                            id="baseline-name"
                            name="name"
                            value={draft.name}
                            onChange={(event) =>
                              setDraft((current) => ({
                                ...current,
                                name: event.target.value,
                              }))
                            }
                            required
                          />
                        </div>

                        <div className="grid gap-1.5">
                          <Label htmlFor="encoder">Depth encoder</Label>
                          <Select
                            name="encoder"
                            items={encoderItems}
                            value={draft.encoder}
                            onValueChange={(value) => {
                              if (
                                value === "vits" ||
                                value === "vitb" ||
                                value === "vitl"
                              ) {
                                setDraft((current) => ({ ...current, encoder: value }))
                              }
                            }}
                          >
                            <SelectTrigger id="encoder" className="w-full">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectGroup>
                                <SelectLabel>Depth Anything V2</SelectLabel>
                                {encoderItems.map((item) => (
                                  <SelectItem key={item.value} value={item.value}>
                                    {item.label}
                                  </SelectItem>
                                ))}
                              </SelectGroup>
                            </SelectContent>
                          </Select>
                        </div>

                        <div className="grid gap-4 2xl:grid-cols-2">
                          <div className="grid gap-1.5">
                            <Label htmlFor="frame-count">Số frame</Label>
                            <Input
                              id="frame-count"
                              name="frame_count"
                              type="number"
                              min="5"
                              value={draft.frameCount}
                              onChange={(event) =>
                                setDraft((current) => ({
                                  ...current,
                                  frameCount: event.target.value,
                                }))
                              }
                              required
                            />
                          </div>
                          <div className="grid gap-1.5">
                            <Label htmlFor="input-size">Input size</Label>
                            <Select
                              name="input_size"
                              items={inputSizeItems}
                              value={draft.inputSize}
                              onValueChange={(value) => {
                                if (value) {
                                  setDraft((current) => ({
                                    ...current,
                                    inputSize: value,
                                  }))
                                }
                              }}
                            >
                              <SelectTrigger id="input-size" className="w-full">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectGroup>
                                  <SelectLabel>Kích thước suy luận</SelectLabel>
                                  {inputSizeItems.map((item) => (
                                    <SelectItem key={item.value} value={item.value}>
                                      {item.label}
                                    </SelectItem>
                                  ))}
                                </SelectGroup>
                              </SelectContent>
                            </Select>
                          </div>
                        </div>

                        <div className="grid gap-1.5">
                          <Label htmlFor="process-width">Process width</Label>
                          <Input
                            id="process-width"
                            name="process_width"
                            type="number"
                            min="0"
                            value={draft.processWidth}
                            onChange={(event) =>
                              setDraft((current) => ({
                                ...current,
                                processWidth: event.target.value,
                              }))
                            }
                            required
                          />
                        </div>
                      </div>
                    </TabsContent>

                    <TabsContent value="coordinates" className="pt-3" keepMounted>
                      <div className="grid gap-3">
                          <div className="grid gap-3 2xl:grid-cols-2">
                          {draft.worldPoints.map(([xValue, yValue], index) => (
                            <div key={index} className="grid gap-1.5">
                              <Label>P{index + 1}</Label>
                              <div className="grid grid-cols-2 gap-2">
                                <Input
                                  name={`world_${index}_x`}
                                  aria-label={`P${index + 1} tọa độ X`}
                                  type="number"
                                  step="any"
                                  value={xValue}
                                  onChange={(event) =>
                                    updateWorldPoint(index, 0, event.target.value)
                                  }
                                  required
                                />
                                <Input
                                  name={`world_${index}_y`}
                                  aria-label={`P${index + 1} tọa độ Y`}
                                  type="number"
                                  step="any"
                                  value={yValue}
                                  onChange={(event) =>
                                    updateWorldPoint(index, 1, event.target.value)
                                  }
                                  required
                                />
                              </div>
                            </div>
                          ))}
                        </div>
                        <p className="text-xs text-muted-foreground">
                          Các giá trị lần lượt là X và Y, đơn vị mét.
                        </p>
                      </div>
                    </TabsContent>
                  </Tabs>
                </CardContent>
                <CardFooter className="mt-auto justify-end border-t">
                  <Button
                    type="submit"
                    disabled={
                      pending || !camera || roiPointCount !== 4 || runningIds.length > 0
                    }
                  >
                    {pending ? (
                      <LoaderCircleIcon data-icon="inline-start" className="animate-spin" />
                    ) : (
                      <SaveIcon data-icon="inline-start" />
                    )}
                    {pending
                      ? "Đang lưu..."
                      : runningIds.length
                        ? "Đang calibration baseline khác"
                        : roiPointCount !== 4
                          ? "Chọn đủ 4 điểm ROI"
                        : "Calibration và lưu"}
                  </Button>
                </CardFooter>
              </form>
            </Card>
          </div>

          <section className="grid gap-4 border-t pt-6" aria-labelledby="baseline-results-title">
            <div className="flex items-center justify-between gap-4">
              <div>
                <h2 id="baseline-results-title" className="text-lg font-semibold tracking-tight">
                  Baseline đã tạo
                </h2>
                <p className="text-sm text-muted-foreground">
                  Ảnh ROI và depth của camera đang chọn.
                </p>
              </div>
              <Badge variant="secondary">{baselines.length} baseline</Badge>
            </div>

            {baselines.length === 0 ? (
              <Card size="sm">
                <CardContent className="flex min-h-32 items-center justify-center">
                  <div className="text-center text-muted-foreground">
                    <ImageIcon className="mx-auto mb-3 size-8" />
                    <p>Chưa có baseline nào được lưu.</p>
                  </div>
                </CardContent>
              </Card>
            ) : (
              <div className="grid gap-4 lg:grid-cols-2">
                {baselines.map((baseline) => {
                  const run = runStatuses[baseline.id]
                  const progress = run?.totalFrames
                    ? (run.processedFrames / run.totalFrames) * 100
                    : 0
                  const imageVersion = `${run?.status ?? "idle"}-${run?.processedFrames ?? 0}`

                  return (
                    <Card
                      key={baseline.id}
                      size="sm"
                      className="[contain-intrinsic-size:auto_32rem] [content-visibility:auto]"
                    >
                      <CardHeader className="border-b">
                        <CardTitle>{baseline.name}</CardTitle>
                        <CardDescription className="flex flex-wrap gap-1.5 pt-1">
                          <Badge variant="outline">{baseline.encoder.toUpperCase()}</Badge>
                          <Badge variant="outline">{baseline.frameCount} frame</Badge>
                          <Badge variant="outline">Input {baseline.inputSize}</Badge>
                          <Badge variant="outline">Width {baseline.processWidth}</Badge>
                        </CardDescription>
                        <CardAction className="flex items-center gap-2">
                          <Badge variant={statusBadgeVariant(run)}>
                            {run?.status === "running" ? (
                              <LoaderCircleIcon data-icon="inline-start" className="animate-spin" />
                            ) : run?.status === "completed" ? (
                              <CheckCircle2Icon data-icon="inline-start" />
                            ) : run?.status === "failed" ? (
                              <TriangleAlertIcon data-icon="inline-start" />
                            ) : (
                              <Clock3Icon data-icon="inline-start" />
                            )}
                            {statusLabel(run)}
                          </Badge>
                          <Button
                            type="button"
                            variant="destructive"
                            size="icon-sm"
                            aria-label={`Xoá baseline ${baseline.name}`}
                            disabled={
                              run?.status === "running" ||
                              deletingBaselineId === baseline.id
                            }
                            onClick={() => void handleDeleteBaseline(baseline)}
                          >
                            {deletingBaselineId === baseline.id ? (
                              <LoaderCircleIcon className="animate-spin" />
                            ) : (
                              <Trash2Icon />
                            )}
                          </Button>
                        </CardAction>
                      </CardHeader>
                      <CardContent>
                        {run?.status === "running" ? (
                          <Progress value={progress}>
                            <ProgressLabel>
                              Đang tạo baseline · {Math.round(progress)}%
                            </ProgressLabel>
                          </Progress>
                        ) : run?.status === "failed" ? (
                          <Alert variant="destructive">
                            <TriangleAlertIcon />
                            <AlertTitle>Calibration thất bại</AlertTitle>
                            <AlertDescription>{run.error}</AlertDescription>
                          </Alert>
                        ) : run?.artifactAvailable ? (
                          <Tabs defaultValue="preview">
                            <TabsList className="w-full">
                              <TabsTrigger value="preview">Ảnh ROI</TabsTrigger>
                              <TabsTrigger value="depth">Depth</TabsTrigger>
                            </TabsList>
                            <TabsContent value="preview" className="pt-3">
                              <Image
                                src={`/api/calibration/${baseline.id}/images/preview?v=${imageVersion}`}
                                alt={`Ảnh ROI của ${baseline.name}`}
                                width={960}
                                height={540}
                                unoptimized
                                className="h-auto w-full rounded-lg"
                              />
                            </TabsContent>
                            <TabsContent value="depth" className="pt-3">
                              <Image
                                src={`/api/calibration/${baseline.id}/images/depth?v=${imageVersion}`}
                                alt={`Heatmap depth của ${baseline.name}`}
                                width={960}
                                height={540}
                                unoptimized
                                className="h-auto w-full rounded-lg"
                              />
                            </TabsContent>
                          </Tabs>
                        ) : (
                          <p className="text-sm text-muted-foreground">
                            Baseline này chưa có ảnh kết quả.
                          </p>
                        )}
                      </CardContent>
                    </Card>
                  )
                })}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}
