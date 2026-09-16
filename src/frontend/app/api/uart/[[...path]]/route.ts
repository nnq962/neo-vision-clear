const API_URL = process.env.SERVER_API_URL ?? "http://127.0.0.1:8000"

async function proxyUartRequest(
  request: Request,
  context: RouteContext<"/api/uart/[[...path]]">
): Promise<Response> {
  const { path = [] } = await context.params
  const suffix = path.map(encodeURIComponent).join("/")
  const target = `${API_URL}/api/uart${suffix ? `/${suffix}` : ""}`

  try {
    const body = request.method === "GET" ? undefined : await request.text()
    const response = await fetch(target, {
      method: request.method,
      body: body || undefined,
      cache: "no-store",
      headers: body ? { "Content-Type": "application/json" } : undefined,
    })
    return new Response(response.body, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("Content-Type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    })
  } catch {
    return Response.json(
      { detail: "Không kết nối được backend UART." },
      { status: 502 }
    )
  }
}

export const dynamic = "force-dynamic"
export const GET = proxyUartRequest
export const PUT = proxyUartRequest
export const POST = proxyUartRequest
export const DELETE = proxyUartRequest
