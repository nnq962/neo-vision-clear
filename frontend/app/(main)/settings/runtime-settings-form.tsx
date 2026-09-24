"use client"

import { useMemo, useRef, useState, useTransition } from "react"
import {
  ActivityIcon,
  CameraIcon,
  ChevronDownIcon,
  Layers3Icon,
  LoaderCircleIcon,
  RotateCcwIcon,
  SaveIcon,
  Settings2Icon,
} from "lucide-react"
import { toast } from "sonner"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Switch } from "@/components/ui/switch"
import type { BaselineConfig } from "@/lib/types/calibration"
import type { CameraIdentity } from "@/lib/types/camera"
import type { RuntimeConfig, RuntimeDetectionConfig } from "@/lib/types/runtime"

import { saveRuntimeConfig } from "./actions"

const DEFAULT_RUNTIME: RuntimeConfig = {
  enabled: false,
  activeBaselineIds: [],
  snapshotMaxAgeSeconds: 2,
  logIntervalSeconds: 2,
  detection: {
    noiseMultiplier: 6,
    minimumDifference: 0.03,
    bevPixelsPerMeter: 100,
    morphologyDivisor: 180,
    depthBlurKernel: 5,
    checkAreaPadding: 12,
    depthAlignment: true,
    alignmentInlierRatio: 0.55,
    displayMinimumAreaRatio: 0.001,
  },
}

type NumberFieldProps = {
  id: string
  label: string
  name: string
  defaultValue: number
  min?: number
  max?: number
  step?: number
}

function NumberField({
  id,
  label,
  name,
  defaultValue,
  min,
  max,
  step = 1,
}: NumberFieldProps) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        name={name}
        type="number"
        defaultValue={defaultValue}
        min={min}
        max={max}
        step={step}
        required
      />
    </div>
  )
}

export function RuntimeSettingsForm({
  cameras,
  baselines,
  artifactAvailability,
  initialRuntime,
}: {
  cameras: CameraIdentity[]
  baselines: BaselineConfig[]
  artifactAvailability: Record<string, boolean>
  initialRuntime: RuntimeConfig
}) {
  const [runtime, setRuntime] = useState(initialRuntime)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [pending, startTransition] = useTransition()
  const formRef = useRef<HTMLFormElement>(null)

  const readyBaselines = useMemo(
    () => baselines.filter((baseline) => artifactAvailability[baseline.id]),
    [artifactAvailability, baselines]
  )
  const selectedBaselines = runtime.activeBaselineIds
    .map((id) => baselines.find((baseline) => baseline.id === id))
    .filter((baseline): baseline is BaselineConfig => baseline !== undefined)
  const selectedByCamera = new Map(
    selectedBaselines.map((baseline) => [baseline.cameraId, baseline])
  )
  const batchSize = selectedBaselines.length
  const canEnable = batchSize > 0

  function cameraBaselines(cameraId: string) {
    const anchor = selectedBaselines.find(
      (baseline) => baseline.cameraId !== cameraId
    )
    return readyBaselines.filter(
      (baseline) =>
        baseline.cameraId === cameraId &&
        (!anchor ||
          (baseline.encoder === anchor.encoder &&
            baseline.inputSize === anchor.inputSize &&
            baseline.processWidth === anchor.processWidth))
    )
  }

  function replaceCameraBaseline(cameraId: string, baselineId?: string) {
    const retained = selectedBaselines.filter(
      (baseline) => baseline.cameraId !== cameraId
    )
    const replacement = baselineId
      ? baselines.find((baseline) => baseline.id === baselineId)
      : undefined
    const nextIds = cameras.flatMap((camera) => {
      const baseline =
        camera.id === cameraId
          ? replacement
          : retained.find((item) => item.cameraId === camera.id)
      return baseline ? [baseline.id] : []
    })
    setRuntime((current) => ({
      ...current,
      activeBaselineIds: nextIds,
      enabled: nextIds.length > 0 ? current.enabled : false,
    }))
  }

  function toggleCamera(cameraId: string, checked: boolean) {
    if (!checked) {
      replaceCameraBaseline(cameraId)
      return
    }
    const firstBaseline = cameraBaselines(cameraId)[0]
    if (firstBaseline) replaceCameraBaseline(cameraId, firstBaseline.id)
  }

  function updateDetection<K extends keyof RuntimeDetectionConfig>(
    field: K,
    value: RuntimeDetectionConfig[K]
  ) {
    setRuntime((current) => ({
      ...current,
      detection: { ...current.detection, [field]: value },
    }))
  }

  function handleSubmit(formData: FormData) {
    startTransition(async () => {
      const result = await saveRuntimeConfig(formData)
      if (result.status === "error" || !result.runtime) {
        toast.error(result.message)
        return
      }
      setRuntime(result.runtime)
      toast.success(result.message)
    })
  }

  function resetDefaults() {
    const defaults: Record<string, number> = {
      snapshot_max_age_seconds: DEFAULT_RUNTIME.snapshotMaxAgeSeconds,
      log_interval_seconds: DEFAULT_RUNTIME.logIntervalSeconds,
      noise_multiplier: DEFAULT_RUNTIME.detection.noiseMultiplier,
      minimum_difference: DEFAULT_RUNTIME.detection.minimumDifference,
      display_minimum_area_ratio:
        DEFAULT_RUNTIME.detection.displayMinimumAreaRatio,
      depth_blur_kernel: DEFAULT_RUNTIME.detection.depthBlurKernel,
      check_area_padding: DEFAULT_RUNTIME.detection.checkAreaPadding,
      morphology_divisor: DEFAULT_RUNTIME.detection.morphologyDivisor,
      alignment_inlier_ratio: DEFAULT_RUNTIME.detection.alignmentInlierRatio,
      bev_pixels_per_meter: DEFAULT_RUNTIME.detection.bevPixelsPerMeter,
    }
    for (const [name, value] of Object.entries(defaults)) {
      const input = formRef.current?.elements.namedItem(name)
      if (input instanceof HTMLInputElement) input.value = String(value)
    }
    setRuntime((current) => ({
      ...current,
      snapshotMaxAgeSeconds: DEFAULT_RUNTIME.snapshotMaxAgeSeconds,
      logIntervalSeconds: DEFAULT_RUNTIME.logIntervalSeconds,
      detection: DEFAULT_RUNTIME.detection,
    }))
  }

  return (
    <div className="flex w-full flex-1 flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b pb-5">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Cài đặt</h1>
          <p className="text-muted-foreground">
            Chọn camera chạy cùng lúc và tinh chỉnh runtime.
          </p>
        </div>
        <Badge variant={runtime.enabled ? "default" : "secondary"}>
          <ActivityIcon data-icon="inline-start" />
          {runtime.enabled ? "Đang bật" : "Đang tắt"}
        </Badge>
      </div>

      {cameras.length === 0 ? (
        <Alert variant="destructive">
          <CameraIcon />
          <AlertTitle>Chưa có camera</AlertTitle>
          <AlertDescription>
            Thêm camera và hoàn tất calibration trước khi cấu hình runtime.
          </AlertDescription>
        </Alert>
      ) : readyBaselines.length === 0 ? (
        <Alert>
          <CameraIcon />
          <AlertTitle>Chưa có baseline sẵn sàng</AlertTitle>
          <AlertDescription>
            Runtime chỉ nhận camera đã có baseline hoàn tất.
          </AlertDescription>
        </Alert>
      ) : null}

      <form
        ref={formRef}
        action={handleSubmit}
        className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_20rem] 2xl:grid-cols-[minmax(0,1fr)_22rem]"
      >
        <input type="hidden" name="enabled" value={String(runtime.enabled)} />
        <input
          type="hidden"
          name="active_baseline_ids"
          value={JSON.stringify(runtime.activeBaselineIds)}
        />
        <input
          type="hidden"
          name="depth_alignment"
          value={String(runtime.detection.depthAlignment)}
        />

        <div className="grid min-w-0 content-start gap-6">
          <Card size="sm" className="min-w-0">
            <CardHeader className="border-b">
              <CardTitle>Camera trong batch</CardTitle>
              <CardDescription>
                Mỗi camera gửi một frame mới nhất vào cùng lượt suy luận.
              </CardDescription>
            </CardHeader>
            <CardContent className="divide-y">
              {cameras.map((camera) => {
                const options = cameraBaselines(camera.id)
                const readyCount = readyBaselines.filter(
                  (baseline) => baseline.cameraId === camera.id
                ).length
                const selected = selectedByCamera.get(camera.id)
                const available = options.length > 0
                const selectItems = options.map((baseline) => ({
                  label: baseline.name,
                  value: baseline.id,
                }))
                return (
                  <div
                    key={camera.id}
                    className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-3 py-3 first:pt-0 last:pb-0 lg:grid-cols-[minmax(0,1fr)_minmax(12rem,16rem)_auto]"
                  >
                    <div className="col-start-1 row-start-1 min-w-0">
                      <p className="truncate font-medium">{camera.name}</p>
                      <p className="text-sm text-muted-foreground">
                        {available
                          ? `${options.length} baseline sẵn sàng`
                          : readyCount > 0
                            ? "Không tương thích với batch hiện tại"
                            : "Chưa có baseline hoàn tất"}
                      </p>
                    </div>
                    <Select
                      items={selectItems}
                      value={selected?.id ?? null}
                      disabled={!selected || !available}
                      onValueChange={(value) => {
                        if (value) replaceCameraBaseline(camera.id, value)
                      }}
                    >
                      <SelectTrigger
                        className="col-span-2 row-start-2 w-full lg:col-span-1 lg:col-start-2 lg:row-start-1"
                        aria-label={`Baseline của ${camera.name}`}
                      >
                        <SelectValue placeholder="Chọn baseline" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectGroup>
                          <SelectLabel>Baseline</SelectLabel>
                          {selectItems.map((item) => (
                            <SelectItem key={item.value} value={item.value}>
                              {item.label}
                            </SelectItem>
                          ))}
                        </SelectGroup>
                      </SelectContent>
                    </Select>
                    <Switch
                      className="col-start-2 row-start-1 justify-self-end lg:col-start-3"
                      checked={Boolean(selected)}
                      disabled={!available}
                      onCheckedChange={(checked) =>
                        toggleCamera(camera.id, checked)
                      }
                      aria-label={`Chọn ${camera.name} vào batch`}
                    />
                  </div>
                )
              })}
            </CardContent>
          </Card>

          <Card size="sm" className="min-w-0">
            <CardHeader className="border-b">
              <CardTitle>Vận hành</CardTitle>
              <CardDescription>
                Các giá trị dùng chung cho toàn bộ camera trong batch.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <NumberField
                id="snapshot-max-age"
                name="snapshot_max_age_seconds"
                label="Tuổi snapshot tối đa (giây)"
                defaultValue={runtime.snapshotMaxAgeSeconds}
                min={0.1}
                step={0.1}
              />
              <NumberField
                id="log-interval"
                name="log_interval_seconds"
                label="Chu kỳ ghi log (giây)"
                defaultValue={runtime.logIntervalSeconds}
                min={0}
                step={0.1}
              />
            </CardContent>
          </Card>

          <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
            <Card size="sm">
              <CardHeader>
                <CollapsibleTrigger
                  render={
                    <button
                      type="button"
                      className="flex w-full items-center justify-between gap-4 text-left"
                    />
                  }
                >
                  <span className="flex items-center gap-3">
                    <Settings2Icon className="size-4 text-muted-foreground" />
                    <span>
                      <span className="block font-medium">Thiết lập nâng cao</span>
                      <span className="block text-xs text-muted-foreground">
                        Độ nhạy depth, alignment và BEV
                      </span>
                    </span>
                  </span>
                  <ChevronDownIcon
                    className={`size-4 transition-transform ${advancedOpen ? "rotate-180" : ""}`}
                  />
                </CollapsibleTrigger>
              </CardHeader>
              <CollapsibleContent keepMounted>
                <Separator className="my-4" />
                <CardContent className="grid gap-4 sm:grid-cols-2 2xl:grid-cols-3">
                  <NumberField
                    id="noise-multiplier"
                    name="noise_multiplier"
                    label="Hệ số nhiễu"
                    defaultValue={runtime.detection.noiseMultiplier}
                    min={0}
                    step={0.1}
                  />
                  <NumberField
                    id="minimum-difference"
                    name="minimum_difference"
                    label="Sai khác tối thiểu"
                    defaultValue={runtime.detection.minimumDifference}
                    min={0.001}
                    step={0.001}
                  />
                  <NumberField
                    id="minimum-area-ratio"
                    name="display_minimum_area_ratio"
                    label="Tỷ lệ diện tích tối thiểu"
                    defaultValue={runtime.detection.displayMinimumAreaRatio}
                    min={0}
                    max={0.999}
                    step={0.001}
                  />
                  <NumberField
                    id="blur-kernel"
                    name="depth_blur_kernel"
                    label="Kernel làm mượt"
                    defaultValue={runtime.detection.depthBlurKernel}
                    min={1}
                    step={2}
                  />
                  <NumberField
                    id="check-padding"
                    name="check_area_padding"
                    label="Padding vùng kiểm tra"
                    defaultValue={runtime.detection.checkAreaPadding}
                    min={0}
                  />
                  <NumberField
                    id="morphology-divisor"
                    name="morphology_divisor"
                    label="Ước số morphology"
                    defaultValue={runtime.detection.morphologyDivisor}
                    min={1}
                  />
                  <NumberField
                    id="alignment-inlier-ratio"
                    name="alignment_inlier_ratio"
                    label="Tỷ lệ inlier alignment"
                    defaultValue={runtime.detection.alignmentInlierRatio}
                    min={0.501}
                    max={1}
                    step={0.001}
                  />
                  <NumberField
                    id="bev-pixels-per-meter"
                    name="bev_pixels_per_meter"
                    label="Pixel BEV / mét"
                    defaultValue={runtime.detection.bevPixelsPerMeter}
                    min={1}
                  />
                  <div className="flex items-center justify-between gap-4 rounded-lg border px-3 py-2">
                    <Label htmlFor="depth-alignment">Căn chỉnh depth</Label>
                    <Switch
                      id="depth-alignment"
                      checked={runtime.detection.depthAlignment}
                      onCheckedChange={(checked) =>
                        updateDetection("depthAlignment", checked)
                      }
                    />
                  </div>
                </CardContent>
              </CollapsibleContent>
            </Card>
          </Collapsible>
        </div>

        <aside className="min-w-0 xl:sticky xl:top-6">
          <Card size="sm">
            <CardHeader className="border-b">
              <CardTitle>Runtime</CardTitle>
              <CardDescription>Trạng thái của cấu hình đang chọn.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4">
              <div className="flex items-center justify-between gap-4">
                <span className="text-muted-foreground">Camera trong batch</span>
                <Badge variant="secondary">
                  <Layers3Icon data-icon="inline-start" />
                  {batchSize} / {cameras.length}
                </Badge>
              </div>
              <Separator />
              <div className="flex items-center justify-between gap-4">
                <div>
                  <Label htmlFor="runtime-enabled">Bật runtime</Label>
                  <p className="text-xs text-muted-foreground">
                    Áp dụng sau khi lưu.
                  </p>
                </div>
                <Switch
                  id="runtime-enabled"
                  checked={runtime.enabled}
                  disabled={!canEnable}
                  onCheckedChange={(checked) =>
                    setRuntime((current) => ({ ...current, enabled: checked }))
                  }
                />
              </div>
            </CardContent>
            <CardFooter className="flex-wrap justify-end gap-2 border-t">
              <Button type="button" variant="ghost" onClick={resetDefaults}>
                <RotateCcwIcon data-icon="inline-start" />
                Mặc định
              </Button>
              <Button type="submit" disabled={pending || cameras.length === 0}>
                {pending ? (
                  <LoaderCircleIcon data-icon="inline-start" className="animate-spin" />
                ) : (
                  <SaveIcon data-icon="inline-start" />
                )}
                {pending ? "Đang lưu..." : "Lưu cài đặt"}
              </Button>
            </CardFooter>
          </Card>
        </aside>
      </form>
    </div>
  )
}
