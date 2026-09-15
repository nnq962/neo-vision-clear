export async function GET(
  _request: Request,
  context: RouteContext<"/api/calibration/[baselineId]/images/[imageType]">
) {
  const { baselineId, imageType } = await context.params
  const apiUrl = process.env.SERVER_API_URL ?? "http://127.0.0.1:8000"

  if (imageType !== "preview" && imageType !== "depth") {
    return Response.json({ detail: "Loại ảnh không hợp lệ." }, { status: 422 })
  }

  try {
    const response = await fetch(
      `${apiUrl}/api/calibration/${encodeURIComponent(baselineId)}/images/${imageType}`,
      { cache: "no-store" }
    )
    if (!response.ok || !response.body) {
      return Response.json(
        { detail: "Ảnh baseline chưa sẵn sàng." },
        { status: response.status }
      )
    }

    return new Response(response.body, {
      status: 200,
      headers: {
        "Content-Type": response.headers.get("Content-Type") ?? "image/jpeg",
        "Cache-Control": "no-store",
      },
    })
  } catch {
    return Response.json(
      { detail: "Không kết nối được backend calibration." },
      { status: 502 }
    )
  }
}
