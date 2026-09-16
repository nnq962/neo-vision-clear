"use client"

import {
  createContext,
  useCallback,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"

type CameraHost = {
  element: HTMLDivElement
  cameraId: string
  cameraName: string
}

type PersistentLiveCameraContextValue = {
  registerHost: (host: CameraHost) => () => void
}

const PLAYER_PARAMETERS = new URLSearchParams({
  autoplay: "true",
  controls: "false",
  disablepictureinpicture: "true",
  muted: "true",
  playsinline: "true",
}).toString()

function resolveWebRtcBaseUrl() {
  const configuredUrl = process.env.NEXT_PUBLIC_MEDIAMTX_WEBRTC_URL
  if (configuredUrl) return configuredUrl.replace(/\/$/, "")
  if (typeof window === "undefined") return ""

  return `${window.location.protocol}//${window.location.hostname}:8889`
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
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const webRtcBaseUrl = resolveWebRtcBaseUrl()

  const registerHost = useCallback((nextHost: CameraHost) => {
    setHost(nextHost)
    setConnectedCamera((current) =>
      current?.cameraId === nextHost.cameraId &&
      current.cameraName === nextHost.cameraName
        ? current
        : {
            cameraId: nextHost.cameraId,
            cameraName: nextHost.cameraName,
          }
    )

    return () => {
      setHost((currentHost) =>
        currentHost?.element === nextHost.element ? undefined : currentHost
      )
    }
  }, [])

  useLayoutEffect(() => {
    const iframe = iframeRef.current
    if (!host || !iframe) {
      if (iframe) iframe.style.visibility = "hidden"
      return
    }

    let animationFrame = 0
    const updateBounds = () => {
      window.cancelAnimationFrame(animationFrame)
      animationFrame = window.requestAnimationFrame(() => {
        const rectangle = host.element.getBoundingClientRect()
        iframe.style.height = `${rectangle.height}px`
        iframe.style.transform = `translate3d(${rectangle.left + window.scrollX}px, ${rectangle.top + window.scrollY}px, 0)`
        iframe.style.visibility =
          rectangle.width > 0 && rectangle.height > 0 ? "visible" : "hidden"
        iframe.style.width = `${rectangle.width}px`
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

  return (
    <PersistentLiveCameraContext.Provider value={contextValue}>
      {children}
      {connectedCamera ? (
        <iframe
          ref={iframeRef}
          className="pointer-events-none absolute left-0 top-0 z-10 rounded-xl border bg-black invisible"
          src={`${webRtcBaseUrl}/${encodeURIComponent(connectedCamera.cameraId)}/?${PLAYER_PARAMETERS}`}
          title={`Video trực tiếp từ ${connectedCamera.cameraName}`}
          allow="autoplay"
          tabIndex={-1}
        />
      ) : null}
    </PersistentLiveCameraContext.Provider>
  )
}
