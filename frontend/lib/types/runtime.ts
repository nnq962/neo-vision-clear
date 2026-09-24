export type RuntimeDetectionConfig = {
  noiseMultiplier: number
  minimumDifference: number
  bevPixelsPerMeter: number
  morphologyDivisor: number
  depthBlurKernel: number
  checkAreaPadding: number
  depthAlignment: boolean
  alignmentInlierRatio: number
  displayMinimumAreaRatio: number
}

export type RuntimeConfig = {
  enabled: boolean
  activeBaselineIds: string[]
  snapshotMaxAgeSeconds: number
  logIntervalSeconds: number
  detection: RuntimeDetectionConfig
}

export type RuntimeProcessStatus = {
  status: "stopped" | "starting" | "running" | "stopping" | "failed"
  activeBaselineIds: string[]
  snapshotAgeMs?: number
  error?: string
  startedAt?: string
}
