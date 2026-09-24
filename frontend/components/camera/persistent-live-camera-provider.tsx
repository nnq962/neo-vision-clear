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

type CameraPlayer = {
  element?: HTMLDivElement
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

  return `${window.location.origin}/webrtc`
}

export const PersistentLiveCameraContext =
  createContext<PersistentLiveCameraContextValue | null>(null)

function PersistentCameraFrame({
  player,
  webRtcBaseUrl,
}: {
  player: CameraPlayer
  webRtcBaseUrl: string
}) {
  const iframeRef = useRef<HTMLIFrameElement>(null)

  useLayoutEffect(() => {
    const iframe = iframeRef.current
    const host = player.element
    if (!iframe || !host) {
      if (iframe) iframe.style.visibility = "hidden"
      return
    }

    let animationFrame = 0
    const updateBounds = () => {
      window.cancelAnimationFrame(animationFrame)
      animationFrame = window.requestAnimationFrame(() => {
        const rectangle = host.getBoundingClientRect()
        iframe.style.height = `${rectangle.height}px`
        iframe.style.transform = `translate3d(${rectangle.left + window.scrollX}px, ${rectangle.top + window.scrollY}px, 0)`
        iframe.style.visibility =
          rectangle.width > 0 && rectangle.height > 0 ? "visible" : "hidden"
        iframe.style.width = `${rectangle.width}px`
      })
    }

    updateBounds()
    const observer = new ResizeObserver(updateBounds)
    observer.observe(host)
    window.addEventListener("resize", updateBounds)

    return () => {
      window.cancelAnimationFrame(animationFrame)
      observer.disconnect()
      window.removeEventListener("resize", updateBounds)
    }
  }, [player.element])

  return (
    <iframe
      ref={iframeRef}
      className="pointer-events-none invisible absolute top-0 left-0 z-10 rounded-xl border bg-black"
      src={`${webRtcBaseUrl}/${encodeURIComponent(player.cameraId)}/?${PLAYER_PARAMETERS}`}
      title={`Video trực tiếp từ ${player.cameraName}`}
      allow="autoplay"
      tabIndex={-1}
    />
  )
}

export function PersistentLiveCameraProvider({
  children,
}: {
  children: ReactNode
}) {
  const [players, setPlayers] = useState<Map<string, CameraPlayer>>(new Map())
  const webRtcBaseUrl = resolveWebRtcBaseUrl()

  const registerHost = useCallback((nextHost: CameraHost) => {
    setPlayers((current) => {
      const next = new Map(current)
      next.set(nextHost.cameraId, nextHost)
      return next
    })

    return () => {
      setPlayers((current) => {
        const player = current.get(nextHost.cameraId)
        if (player?.element !== nextHost.element) return current

        const next = new Map(current)
        next.set(nextHost.cameraId, { ...player, element: undefined })
        return next
      })
    }
  }, [])

  const contextValue = useMemo(
    () => ({ registerHost }),
    [registerHost]
  )

  return (
    <PersistentLiveCameraContext.Provider value={contextValue}>
      {children}
      {Array.from(players.values()).map((player) => (
        <PersistentCameraFrame
          key={player.cameraId}
          player={player}
          webRtcBaseUrl={webRtcBaseUrl}
        />
      ))}
    </PersistentLiveCameraContext.Provider>
  )
}
