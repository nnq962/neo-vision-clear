"use client"

import { useState, useTransition } from "react"
import {
  ActivityIcon,
  GaugeIcon,
  InfoIcon,
  LoaderCircleIcon,
  RotateCcwIcon,
  SaveIcon,
  SlidersHorizontalIcon,
} from "lucide-react"
import { toast } from "sonner"

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

const NO_BASELINE = "__none__"

const DEFAULT_RUNTIME: RuntimeConfig = {
  enabled: false,
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
  description: string
  name: string
  value: number
  min?: number
  max?: number
  step?: number
  disabled?: boolean
  onChange: (value: number) => void
}

function NumberField({
  id,
  label,
  description,
  name,
  value,
  min,
  max,
  step = 1,
  disabled,
  onChange,
}: NumberFieldProps) {
  return (
    <div className="grid gap-2">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        name={name}
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        onChange={(event) => onChange(Number(event.target.value))}
        required
      />
      <p className="text-xs text-muted-foreground">{description}</p>
    </div>
  )
}

export function RuntimeSettingsForm({
  camera,
  baselines,
  artifactAvailability,
  initialRuntime,
}: {
  camera?: CameraIdentity
  baselines: BaselineConfig[]
  artifactAvailability: Record<string, boolean>
  initialRuntime: RuntimeConfig
}) {
  const [runtime, setRuntime] = useState(initialRuntime)
  const [pending, startTransition] = useTransition()
  const availableBaselines = baselines.filter(
    (baseline) => artifactAvailability[baseline.id]
  )
  const canEnable = Boolean(camera && runtime.activeBaselineId)

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
    setRuntime((current) => ({
      ...DEFAULT_RUNTIME,
      activeBaselineId: current.activeBaselineId,
    }))
  }

  return (
    <div className="flex flex-1 flex-col gap-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Cài đặt runtime</h1>
          <p className="text-muted-foreground">
            Chọn baseline và điều chỉnh cách hệ thống phát hiện vật cản.
          </p>
        </div>
        <Badge variant={runtime.enabled ? "default" : "secondary"}>
          <ActivityIcon data-icon="inline-start" />
          {runtime.enabled ? "Runtime được bật" : "Runtime đang tắt"}
        </Badge>
      </div>

      {!camera ? (
        <Alert variant="destructive">
          <InfoIcon />
          <AlertTitle>Chưa có camera</AlertTitle>
          <AlertDescription>
            Hãy cấu hình camera trước khi thiết lập runtime.
          </AlertDescription>
        </Alert>
      ) : availableBaselines.length === 0 ? (
        <Alert>
          <InfoIcon />
          <AlertTitle>Chưa có baseline hoàn tất</AlertTitle>
          <AlertDescription>
            Hãy calibration ít nhất một baseline trước khi bật runtime.
          </AlertDescription>
        </Alert>
      ) : (
        <Alert>
          <InfoIcon />
          <AlertTitle>Camera đang sử dụng: {camera.name}</AlertTitle>
          <AlertDescription>
            Chỉ các baseline đã tạo đủ artifact mới có thể được chọn.
          </AlertDescription>
        </Alert>
      )}

      <form action={handleSubmit} className="grid gap-6">
        <input type="hidden" name="enabled" value={String(runtime.enabled)} />
        <input
          type="hidden"
          name="depth_alignment"
          value={String(runtime.detection.depthAlignment)}
        />

        <Card>
          <CardHeader>
            <CardTitle>Trạng thái và baseline</CardTitle>
            <CardDescription>
              Chọn dữ liệu chuẩn mà worker sẽ dùng khi phân tích camera.
            </CardDescription>
            <CardAction>
              <Switch
                checked={runtime.enabled}
                disabled={!canEnable && !runtime.enabled}
                onCheckedChange={(checked) =>
                  setRuntime((current) => ({ ...current, enabled: checked }))
                }
                aria-label="Bật runtime"
              />
            </CardAction>
          </CardHeader>
          <CardContent className="grid gap-5">
            <div className="grid gap-2">
              <Label htmlFor="active-baseline">Baseline đang hoạt động</Label>
              <Select
                name="active_baseline_id"
                items={[
                  { label: "Chưa chọn baseline", value: NO_BASELINE },
                  ...baselines.map((baseline) => ({
                    label: baseline.name,
                    value: baseline.id,
                  })),
                ]}
                value={runtime.activeBaselineId ?? NO_BASELINE}
                onValueChange={(value) =>
                  setRuntime((current) => ({
                    ...current,
                    activeBaselineId:
                      value && value !== NO_BASELINE ? value : undefined,
                    enabled:
                      value && value !== NO_BASELINE ? current.enabled : false,
                  }))
                }
              >
                <SelectTrigger id="active-baseline" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectLabel>Baseline của {camera?.name ?? "camera"}</SelectLabel>
                    <SelectItem value={NO_BASELINE}>Chưa chọn baseline</SelectItem>
                    {baselines.map((baseline) => (
                      <SelectItem
                        key={baseline.id}
                        value={baseline.id}
                        disabled={!artifactAvailability[baseline.id]}
                      >
                        {baseline.name}
                        {!artifactAvailability[baseline.id] && " · chưa hoàn tất"}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Runtime đọc artifact trong thư mục mang ID của baseline này.
              </p>
            </div>

            <Separator />

            <div className="grid gap-4 sm:grid-cols-2">
              <NumberField
                id="snapshot-max-age"
                name="snapshot_max_age_seconds"
                label="Tuổi snapshot tối đa"
                description="Sau khoảng thời gian này, kết quả được đánh dấu là stale."
                value={runtime.snapshotMaxAgeSeconds}
                min={0.1}
                step={0.1}
                onChange={(value) =>
                  setRuntime((current) => ({
                    ...current,
                    snapshotMaxAgeSeconds: value,
                  }))
                }
              />
              <NumberField
                id="log-interval"
                name="log_interval_seconds"
                label="Chu kỳ ghi log"
                description="Số giây giữa hai lần ghi hiệu năng; đặt 0 để tắt."
                value={runtime.logIntervalSeconds}
                min={0}
                step={0.1}
                onChange={(value) =>
                  setRuntime((current) => ({
                    ...current,
                    logIntervalSeconds: value,
                  }))
                }
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Phát hiện thay đổi depth</CardTitle>
            <CardDescription>
              Điều chỉnh độ nhạy và bước làm sạch mask vật cản.
            </CardDescription>
            <CardAction>
              <SlidersHorizontalIcon className="size-5 text-muted-foreground" />
            </CardAction>
          </CardHeader>
          <CardContent className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
            <NumberField
              id="noise-multiplier"
              name="noise_multiplier"
              label="Hệ số nhiễu"
              description="Tăng để giảm báo nhầm tại những pixel không ổn định."
              value={runtime.detection.noiseMultiplier}
              min={0}
              step={0.1}
              onChange={(value) => updateDetection("noiseMultiplier", value)}
            />
            <NumberField
              id="minimum-difference"
              name="minimum_difference"
              label="Sai khác tối thiểu"
              description="Ngưỡng depth nhỏ nhất để xem là thay đổi thật."
              value={runtime.detection.minimumDifference}
              min={0.001}
              step={0.001}
              onChange={(value) => updateDetection("minimumDifference", value)}
            />
            <NumberField
              id="minimum-area-ratio"
              name="display_minimum_area_ratio"
              label="Tỷ lệ diện tích tối thiểu"
              description="Loại các vùng thay đổi quá nhỏ so với ROI."
              value={runtime.detection.displayMinimumAreaRatio}
              min={0}
              max={0.999}
              step={0.001}
              onChange={(value) =>
                updateDetection("displayMinimumAreaRatio", value)
              }
            />
            <NumberField
              id="blur-kernel"
              name="depth_blur_kernel"
              label="Kernel làm mượt depth"
              description="Phải là số lẻ: 3, 5, 7…"
              value={runtime.detection.depthBlurKernel}
              min={1}
              step={2}
              onChange={(value) => updateDetection("depthBlurKernel", value)}
            />
            <NumberField
              id="check-padding"
              name="check_area_padding"
              label="Padding vùng kiểm tra"
              description="Số pixel mở rộng quanh ROI để làm sạch mask."
              value={runtime.detection.checkAreaPadding}
              min={0}
              onChange={(value) => updateDetection("checkAreaPadding", value)}
            />
            <NumberField
              id="morphology-divisor"
              name="morphology_divisor"
              label="Ước số morphology"
              description="Điều khiển kernel morphology theo độ phân giải ảnh."
              value={runtime.detection.morphologyDivisor}
              min={1}
              onChange={(value) => updateDetection("morphologyDivisor", value)}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Căn chỉnh và đo BEV</CardTitle>
            <CardDescription>
              Cấu hình robust alignment và độ phân giải phép đo theo mét.
            </CardDescription>
            <CardAction>
              <GaugeIcon className="size-5 text-muted-foreground" />
            </CardAction>
          </CardHeader>
          <CardContent className="grid gap-5">
            <div className="flex items-center justify-between gap-4">
              <div className="grid gap-1">
                <Label htmlFor="depth-alignment">Căn chỉnh depth</Label>
                <p className="text-xs text-muted-foreground">
                  Bù scale và shift giữa frame hiện tại với baseline.
                </p>
              </div>
              <Switch
                id="depth-alignment"
                checked={runtime.detection.depthAlignment}
                onCheckedChange={(checked) =>
                  updateDetection("depthAlignment", checked)
                }
              />
            </div>

            <Separator />

            <div className="grid gap-4 sm:grid-cols-2">
              <NumberField
                id="alignment-inlier-ratio"
                name="alignment_inlier_ratio"
                label="Tỷ lệ inlier alignment"
                description="Phần pixel gần baseline nhất được giữ lại khi fit."
                value={runtime.detection.alignmentInlierRatio}
                min={0.501}
                max={1}
                step={0.001}
                onChange={(value) =>
                  updateDetection("alignmentInlierRatio", value)
                }
              />
              <NumberField
                id="bev-pixels-per-meter"
                name="bev_pixels_per_meter"
                label="Pixel BEV trên mỗi mét"
                description="Tăng để đo chi tiết hơn nhưng tốn thêm xử lý."
                value={runtime.detection.bevPixelsPerMeter}
                min={1}
                step={1}
                onChange={(value) =>
                  updateDetection("bevPixelsPerMeter", value)
                }
              />
            </div>
          </CardContent>
          <CardFooter className="justify-between border-t">
            <Button type="button" variant="outline" onClick={resetDefaults}>
              <RotateCcwIcon data-icon="inline-start" />
              Khôi phục mặc định
            </Button>
            <Button type="submit" disabled={pending || !camera}>
              {pending ? (
                <LoaderCircleIcon data-icon="inline-start" className="animate-spin" />
              ) : (
                <SaveIcon data-icon="inline-start" />
              )}
              {pending ? "Đang lưu..." : "Lưu cấu hình runtime"}
            </Button>
          </CardFooter>
        </Card>
      </form>
    </div>
  )
}
