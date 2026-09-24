export type CalibrationPoint = [number, number]

export type BaselineConfig = {
  id: string
  name: string
  cameraId: string
  roiPoints: CalibrationPoint[]
  worldPoints: CalibrationPoint[]
  unit: "m"
  origin: string
  xAxis: string
  yAxis: string
  encoder: "vits" | "vitb" | "vitl"
  frameCount: number
  inputSize: number
  processWidth: number
  createdAt: string
  updatedAt: string
}

export type CalibrationRunStatus = {
  baselineId: string
  status: "idle" | "running" | "completed" | "failed"
  processedFrames: number
  totalFrames: number
  error?: string
  artifactAvailable: boolean
  noiseP99?: number
  alignmentMedianError?: number
}
