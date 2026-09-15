"use client"

import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"

type CameraHost = {
  element: HTMLDivElement
  cameraId: string
  cameraName: string
}

type CameraBounds = {
  height: number
  left: number
  top: number
  width: number
  visible: boolean
}

type PersistentLiveCameraContextValue = {
  registerHost: (host: CameraHost) => () => void
}

const HIDDEN_BOUNDS: CameraBounds = {
  height: 0,
  left: 0,
  top: 0,
  width: 0,
  visible: false,
}

export const PersistentLiveCameraContext =
  createContext<PersistentLiveCameraContextValue | null>(null)

export function PersistentLiveCameraProvider({
  children,
}: {
  children: ReactNode
}) {
  const [host, setHost] = useState<CameraHost>()
  const [connectedCamera, setConnectedCamera] = useState<
    Pick<CameraHost, "cameraId" | "cameraName">
  >()
  const [bounds, setBounds] = useState<CameraBounds>(HIDDEN_BOUNDS)

  const registerHost = useCallback((nextHost: CameraHost) => {
    setHost(nextHost)
    setConnectedCamera({
      cameraId: nextHost.cameraId,
      cameraName: nextHost.cameraName,
    })

    return () => {
      setHost((currentHost) =>
        currentHost?.element === nextHost.element ? undefined : currentHost
      )
    }
  }, [])

  useEffect(() => {
    if (!host) {
      return
    }

    let animationFrame = 0
    const updateBounds = () => {
      window.cancelAnimationFrame(animationFrame)
      animationFrame = window.requestAnimationFrame(() => {
        const rectangle = host.element.getBoundingClientRect()
        setBounds({
          height: rectangle.height,
          left: rectangle.left + window.scrollX,
          top: rectangle.top + window.scrollY,
          width: rectangle.width,
          visible: rectangle.width > 0 && rectangle.height > 0,
        })
      })
    }

    updateBounds()
    const observer = new ResizeObserver(updateBounds)
    observer.observe(host.element)
    window.addEventListener("resize", updateBounds)

    return () => {
      window.cancelAnimationFrame(animationFrame)
      observer.disconnect()
      window.removeEventListener("resize", updateBounds)
    }
  }, [host])

  const contextValue = useMemo(
    () => ({ registerHost }),
    [registerHost]
  )
  const webrtcBaseUrl =
    process.env.NEXT_PUBLIC_MEDIAMTX_WEBRTC_URL ?? "http://127.0.0.1:8889"
  const playerParameters = new URLSearchParams({
    autoplay: "true",
    controls: "false",
    disablepictureinpicture: "true",
    muted: "true",
    playsinline: "true",
  })

  return (
    <PersistentLiveCameraContext.Provider value={contextValue}>
      {children}
      {connectedCamera ? (
        <iframe
          className="pointer-events-none absolute z-10 rounded-xl border bg-black"
          src={`${webrtcBaseUrl}/${encodeURIComponent(connectedCamera.cameraId)}/?${playerParameters}`}
          title={`Video trực tiếp từ ${connectedCamera.cameraName}`}
          allow="autoplay"
          tabIndex={-1}
          style={{
            height: bounds.height,
            left: bounds.left,
            opacity: host && bounds.visible ? 1 : 0,
            top: bounds.top,
            visibility: host && bounds.visible ? "visible" : "hidden",
            width: bounds.width,
          }}
        />
      ) : null}
    </PersistentLiveCameraContext.Provider>
  )
}
