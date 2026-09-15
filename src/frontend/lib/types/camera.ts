export type Camera = {
  id: string
  name: string
  source: string
  openTimeoutMs: number
  readTimeoutMs: number
}

export type CameraIdentity = Pick<Camera, "id" | "name">
