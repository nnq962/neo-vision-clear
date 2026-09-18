"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import {
  ActivityIcon,
  BotIcon,
  CableIcon,
  CheckCircle2Icon,
  CircleIcon,
  Clock3Icon,
  Code2Icon,
  PlugZapIcon,
  RadioTowerIcon,
  RefreshCwIcon,
  SaveIcon,
  Settings2Icon,
  Trash2Icon,
  UnplugIcon,
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
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"

type MessageDirection = "rx" | "tx"
type MessageFilter = "all" | MessageDirection

type UartStatus = {
  port: string
  baudrate: number
  timeout: number
  auto_connect: boolean
  connected: boolean
  is_listening: boolean
  last_error: string | null
  last_connected_at: number | null
  last_disconnected_at: number | null
  last_received_at: number | null
}

type UartMessage = {
  sequence: number
  timestamp: number
  direction: MessageDirection
  message_type: string
  robot_id: number
  request_id: number
  summary: string
  frame: string
  checksum_valid: boolean
}

type UartStreamPayload = {
  type: "uart_update"
  status: UartStatus
  messages: UartMessage[]
}

const BAUD_RATES = ["9600", "19200", "38400", "57600", "115200", "230400"]

function uartWebSocketUrl(): string {
  const configuredUrl = process.env.NEXT_PUBLIC_SERVER_WS_URL?.replace(/\/$/, "")
  if (configuredUrl) {
    const baseUrl = configuredUrl.replace(/\/ws\/(corridor|overview|uart)$/, "")
    return `${baseUrl}/ws/uart`
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
  return `${protocol}//${window.location.host}/ws/uart`
}

function isUartStatus(value: unknown): value is UartStatus {
  if (typeof value !== "object" || value === null) return false
  const payload = value as Record<string, unknown>
  return (
    typeof payload.port === "string" &&
    typeof payload.baudrate === "number" &&
    typeof payload.timeout === "number" &&
    typeof payload.auto_connect === "boolean" &&
    typeof payload.connected === "boolean" &&
    typeof payload.is_listening === "boolean"
  )
}

function mergeMessages(
  current: UartMessage[],
  incoming: UartMessage[]
): UartMessage[] {
  const messages = new Map(current.map((message) => [message.sequence, message]))
  for (const message of incoming) messages.set(message.sequence, message)
  return Array.from(messages.values()).sort((a, b) => b.sequence - a.sequence)
}

function MessageItem({ message }: { message: UartMessage }) {
  const received = message.direction === "rx"
  const timestamp = new Date(message.timestamp * 1000).toLocaleTimeString("vi-VN", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    fractionalSecondDigits: 3,
  })

  return (
    <div className="grid gap-3 px-5 py-4 lg:grid-cols-[7rem_minmax(0,1fr)_auto]">
      <div className="flex items-start gap-2 text-xs text-muted-foreground">
        <Clock3Icon className="mt-0.5 size-3.5" />
        <span className="font-mono tabular-nums">{timestamp}</span>
      </div>
      <div className="min-w-0 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={received ? "secondary" : "outline"}>
            {received ? "RX" : "TX"}
          </Badge>
          <span className="font-medium">{message.message_type}</span>
          <span className="text-xs text-muted-foreground">
            Robot {message.robot_id} · Request {message.request_id}
          </span>
        </div>
        <p className="text-sm text-muted-foreground">{message.summary}</p>
        <div className="overflow-x-auto rounded-lg bg-muted/60 px-3 py-2">
          <code className="whitespace-nowrap font-mono text-xs">{message.frame}</code>
        </div>
      </div>
      <Badge variant="outline" className="self-start">
        <CheckCircle2Icon data-icon="inline-start" />
        Checksum OK
      </Badge>
    </div>
  )
}

export function UartConsole() {
  const [status, setStatus] = useState<UartStatus>()
  const [port, setPort] = useState("/dev/ttyS4")
  const [baudRate, setBaudRate] = useState("115200")
  const [timeout, setTimeoutValue] = useState("1")
  const [autoConnect, setAutoConnect] = useState(false)
  const [availablePorts, setAvailablePorts] = useState<string[]>([])
  const [messages, setMessages] = useState<UartMessage[]>([])
  const [filter, setFilter] = useState<MessageFilter>("all")
  const [autoScroll, setAutoScroll] = useState(true)
  const [streamConnected, setStreamConnected] = useState(false)
  const [pending, setPending] = useState(false)
  const messageListRef = useRef<HTMLDivElement>(null)

  const filteredMessages = useMemo(
    () =>
      filter === "all"
        ? messages
        : messages.filter((message) => message.direction === filter),
    [filter, messages]
  )
  const receivedCount = messages.filter(
    (message) => message.direction === "rx"
  ).length
  const sentCount = messages.length - receivedCount

  useEffect(() => {
    let cancelled = false
    async function loadInitialState() {
      try {
        const [statusResponse, messagesResponse] = await Promise.all([
          fetch("/api/uart/status", { cache: "no-store" }),
          fetch("/api/uart/messages", { cache: "no-store" }),
        ])
        if (!statusResponse.ok || cancelled) return
        const nextStatus: unknown = await statusResponse.json()
        if (!isUartStatus(nextStatus)) return
        setStatus(nextStatus)
        setPort(nextStatus.port)
        setBaudRate(String(nextStatus.baudrate))
        setTimeoutValue(String(nextStatus.timeout))
        setAutoConnect(nextStatus.auto_connect)
        if (messagesResponse.ok) {
          const history = (await messagesResponse.json()) as UartMessage[]
          setMessages(history)
        }
      } catch {
        if (!cancelled) toast.error("Không tải được trạng thái UART.")
      }
    }
    void loadInitialState()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    let socket: WebSocket | undefined
    let reconnectTimer: number | undefined

    function connectStream() {
      if (cancelled) return
      socket = new WebSocket(uartWebSocketUrl())
      socket.onopen = () => setStreamConnected(true)
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(String(event.data)) as UartStreamPayload
          if (payload.type !== "uart_update" || !isUartStatus(payload.status)) return
          setStatus(payload.status)
          setMessages((current) => mergeMessages(current, payload.messages))
        } catch {
          toast.error("WebSocket UART trả dữ liệu không hợp lệ.")
        }
      }
      socket.onerror = () => setStreamConnected(false)
      socket.onclose = () => {
        setStreamConnected(false)
        if (!cancelled) reconnectTimer = window.setTimeout(connectStream, 2000)
      }
    }

    connectStream()
    return () => {
      cancelled = true
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [])

  useEffect(() => {
    if (autoScroll) {
      messageListRef.current?.scrollTo({ top: 0, behavior: "smooth" })
    }
  }, [autoScroll, messages])

  async function applyStatusRequest(url: string, init?: RequestInit) {
    setPending(true)
    try {
      const response = await fetch(url, { ...init, cache: "no-store" })
      const payload: unknown = await response.json()
      if (!response.ok || !isUartStatus(payload)) {
        throw new Error("Backend UART trả response không hợp lệ.")
      }
      setStatus(payload)
      return payload
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Không gọi được backend UART."
      )
      return undefined
    } finally {
      setPending(false)
    }
  }

  async function saveConfiguration() {
    const nextTimeout = Number(timeout)
    const nextBaudRate = Number(baudRate)
    if (!port.trim() || !Number.isFinite(nextTimeout) || nextTimeout < 0.05) {
      toast.error("Cấu hình UART chưa hợp lệ.")
      return
    }
    const nextStatus = await applyStatusRequest("/api/uart/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        port: port.trim(),
        baudrate: nextBaudRate,
        timeout: nextTimeout,
        auto_connect: autoConnect,
      }),
    })
    if (!nextStatus) return
    if (nextStatus.connected) {
      toast.success("Đã lưu và kết nối UART.")
    } else {
      toast.warning(
        `Đã lưu cấu hình nhưng chưa kết nối: ${nextStatus.last_error ?? "Không rõ lỗi."}`
      )
    }
  }

  async function toggleConnection() {
    const command = status?.connected ? "disconnect" : "connect"
    const nextStatus = await applyStatusRequest(`/api/uart/${command}`, {
      method: "POST",
    })
    if (!nextStatus) return
    if (nextStatus.connected) toast.success("Đã kết nối UART.")
    else if (command === "disconnect") {
      toast.info("Đã ngắt UART; FastAPI vẫn hoạt động.")
    } else toast.error(nextStatus.last_error ?? "Không thể mở cổng UART.")
  }

  async function scanPorts() {
    try {
      const response = await fetch("/api/uart/ports", { cache: "no-store" })
      if (!response.ok) throw new Error()
      const payload = (await response.json()) as { ports: string[] }
      setAvailablePorts(payload.ports)
      toast.info(
        payload.ports.length > 0
          ? `Tìm thấy ${payload.ports.length} cổng serial.`
          : "Chưa phát hiện cổng serial nào."
      )
    } catch {
      toast.error("Không quét được cổng UART.")
    }
  }

  async function clearMessages() {
    const response = await fetch("/api/uart/messages", { method: "DELETE" })
    if (response.ok) setMessages([])
    else toast.error("Không xóa được message log.")
  }

  return (
    <div className="flex flex-1 flex-col gap-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">UART</h1>
          <p className="text-muted-foreground">
            Quản lý cổng serial và theo dõi message trao đổi với robot.
          </p>
        </div>
        <Badge variant={streamConnected ? "default" : "secondary"}>
          <Code2Icon data-icon="inline-start" />
          {streamConnected ? "Backend trực tiếp" : "Đang nối backend"}
        </Badge>
      </div>

      {status?.last_error && !status.connected ? (
        <Alert variant="destructive">
          <Settings2Icon />
          <AlertTitle>UART chưa sẵn sàng — FastAPI vẫn hoạt động</AlertTitle>
          <AlertDescription>{status.last_error}</AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card size="sm">
          <CardHeader>
            <CardDescription>Trạng thái</CardDescription>
            <CardAction>
              <CircleIcon
                className={`size-4 ${status?.connected ? "fill-current text-foreground" : "text-muted-foreground"}`}
              />
            </CardAction>
            <CardTitle>{status?.connected ? "Đã kết nối" : "Chưa kết nối"}</CardTitle>
          </CardHeader>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardDescription>Cổng đang áp dụng</CardDescription>
            <CardAction><CableIcon className="size-4 text-muted-foreground" /></CardAction>
            <CardTitle className="font-mono">{status?.port ?? port}</CardTitle>
          </CardHeader>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardDescription>Baud rate</CardDescription>
            <CardAction><ActivityIcon className="size-4 text-muted-foreground" /></CardAction>
            <CardTitle>
              {(status?.baudrate ?? Number(baudRate)).toLocaleString("vi-VN")} baud
            </CardTitle>
          </CardHeader>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardDescription>Message trong phiên</CardDescription>
            <CardAction><RadioTowerIcon className="size-4 text-muted-foreground" /></CardAction>
            <CardTitle>
              {messages.length} message · {receivedCount} RX · {sentCount} TX
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,0.85fr)_minmax(24rem,1.15fr)]">
        <Card>
          <CardHeader>
            <CardTitle>Cấu hình kết nối</CardTitle>
            <CardDescription>Có thể đổi port ngay khi server đang chạy.</CardDescription>
            <CardAction>
              <Badge variant={status?.connected ? "default" : "outline"}>
                {status?.connected ? "Đang mở" : "Đang đóng"}
              </Badge>
            </CardAction>
          </CardHeader>
          <CardContent className="grid gap-5">
            <div className="grid gap-2">
              <Label htmlFor="uart-port">UART port</Label>
              <div className="flex gap-2">
                <Input
                  id="uart-port"
                  list="uart-ports"
                  value={port}
                  onChange={(event) => setPort(event.target.value)}
                  placeholder="/dev/ttyUSB0"
                />
                <datalist id="uart-ports">
                  {availablePorts.map((item) => <option key={item} value={item} />)}
                </datalist>
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  onClick={scanPorts}
                  disabled={pending}
                  aria-label="Quét cổng UART"
                >
                  <RefreshCwIcon />
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Lưu cấu hình sẽ reconnect ngay; lỗi chỉ ảnh hưởng UART.
              </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="grid gap-2">
                <Label htmlFor="uart-baud-rate">Baud rate</Label>
                <Select value={baudRate} onValueChange={(value) => value && setBaudRate(value)}>
                  <SelectTrigger id="uart-baud-rate" className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      <SelectLabel>Tốc độ phổ biến</SelectLabel>
                      {BAUD_RATES.map((rate) => (
                        <SelectItem key={rate} value={rate}>
                          {Number(rate).toLocaleString("vi-VN")}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="uart-timeout">Read timeout (giây)</Label>
                <Input
                  id="uart-timeout"
                  type="number"
                  min="0.05"
                  max="30"
                  step="0.05"
                  value={timeout}
                  onChange={(event) => setTimeoutValue(event.target.value)}
                />
              </div>
            </div>
            <Separator />
            <div className="flex items-center justify-between gap-4">
              <div className="grid gap-1">
                <Label htmlFor="uart-auto-connect">Tự kết nối khi khởi động</Label>
                <p className="text-xs text-muted-foreground">
                  Nếu thất bại, FastAPI vẫn khởi động bình thường.
                </p>
              </div>
              <Switch
                id="uart-auto-connect"
                checked={autoConnect}
                onCheckedChange={setAutoConnect}
              />
            </div>
          </CardContent>
          <CardFooter className="justify-between gap-3 border-t">
            <Button
              type="button"
              variant="outline"
              onClick={toggleConnection}
              disabled={pending}
            >
              {status?.connected ? (
                <UnplugIcon data-icon="inline-start" />
              ) : (
                <PlugZapIcon data-icon="inline-start" />
              )}
              {status?.connected ? "Ngắt kết nối" : "Thử kết nối lại"}
            </Button>
            <Button type="button" onClick={saveConfiguration} disabled={pending}>
              <SaveIcon data-icon="inline-start" />
              Lưu và áp dụng
            </Button>
          </CardFooter>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Giao thức robot</CardTitle>
            <CardDescription>
              Backend tự phản hồi bằng snapshot hành lang mới nhất.
            </CardDescription>
            <CardAction><BotIcon className="size-5 text-muted-foreground" /></CardAction>
          </CardHeader>
          <CardContent className="grid gap-5">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <Badge variant="secondary">RX · 0x10</Badge>
                  <span className="text-xs text-muted-foreground">8 byte</span>
                </div>
                <p className="font-medium">GET_CORRIDOR_INFO</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Robot gửi robot_id và request_id để yêu cầu snapshot.
                </p>
              </div>
              <div className="rounded-xl border p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <Badge variant="outline">TX · 0x11</Badge>
                  <span className="text-xs text-muted-foreground">26 byte</span>
                </div>
                <p className="font-medium">CORRIDOR_INFO</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Vision trả status, tuổi snapshot và số đo millimet.
                </p>
              </div>
            </div>
            <Separator />
            <div className="grid gap-4 text-sm sm:grid-cols-3">
              <div><p className="text-muted-foreground">Start byte</p><p className="font-mono font-medium">0xAA</p></div>
              <div><p className="text-muted-foreground">Byte order</p><p className="font-medium">Little-endian</p></div>
              <div><p className="text-muted-foreground">Checksum</p><p className="font-medium">CRC32 &amp; 0xFFFF</p></div>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Message monitor</CardTitle>
          <CardDescription>Message UART thật, mới nhất hiển thị trước.</CardDescription>
          <CardAction>
            <Badge variant={streamConnected ? "default" : "secondary"}>
              {streamConnected ? "Đang theo dõi" : "Mất kết nối UI"}
            </Badge>
          </CardAction>
        </CardHeader>
        <CardContent className="px-0">
          <div className="flex flex-col gap-3 px-5 pb-4 sm:flex-row sm:items-center sm:justify-between">
            <Tabs value={filter} onValueChange={(value) => setFilter(value as MessageFilter)}>
              <TabsList>
                <TabsTrigger value="all">Tất cả</TabsTrigger>
                <TabsTrigger value="rx">RX</TabsTrigger>
                <TabsTrigger value="tx">TX</TabsTrigger>
              </TabsList>
            </Tabs>
            <div className="flex items-center gap-2">
              <Label htmlFor="uart-auto-scroll" className="text-xs">Tự cuộn</Label>
              <Switch id="uart-auto-scroll" checked={autoScroll} onCheckedChange={setAutoScroll} />
              <Button
                type="button"
                variant="outline"
                onClick={clearMessages}
                disabled={messages.length === 0}
              >
                <Trash2Icon data-icon="inline-start" />
                Xóa log
              </Button>
            </div>
          </div>
          <Separator />
          <div ref={messageListRef} className="max-h-[34rem] divide-y overflow-y-auto">
            {filteredMessages.length > 0 ? (
              filteredMessages.map((message) => (
                <MessageItem key={message.sequence} message={message} />
              ))
            ) : (
              <div className="flex min-h-48 flex-col items-center justify-center gap-3 px-6 text-center">
                <RadioTowerIcon className="size-8 text-muted-foreground" />
                <div>
                  <p className="font-medium">Chưa có message</p>
                  <p className="text-sm text-muted-foreground">
                    Message sẽ xuất hiện khi robot gửi yêu cầu qua UART.
                  </p>
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
