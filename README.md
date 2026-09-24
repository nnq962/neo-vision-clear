# Neo Vision Clear

Dự án được tổ chức thành các workspace độc lập:

- `backend/`: toàn bộ ứng dụng Python, môi trường `uv`, model, test và dữ liệu runtime.
- `frontend/`: dashboard Next.js được build thành static export.
- `mediamtx/`: cấu hình MediaMTX cho RTSP và WebRTC.

Danh sách lệnh development, Docker Compose, log và chẩn đoán nhanh nằm trong
[`COMMANDS.md`](COMMANDS.md).

## Backend

```bash
cd backend
uv sync
uv run walkway-server
```

Hướng dẫn calibration, detection, API và kiểm thử nằm trong
[`backend/README.md`](backend/README.md).

## Frontend

```bash
cd frontend
npm ci
npm run build
```

Frontend chạy độc lập với backend. Khi triển khai, frontend hoặc reverse proxy cần
chuyển tiếp `/api` và `/ws` sang service FastAPI.

## Chạy toàn bộ hệ thống bằng Docker Compose

Compose gốc quản lý ba service `mediamtx`, `backend` và `frontend` trong cùng
network `neo-vision-clear`. Tạo `.env` và điều chỉnh IP LAN của Jetson nếu
cần:

```bash
cp .env.example .env
```

Build và khởi động:

```bash
docker compose up -d --build
```

Theo dõi trạng thái và log:

```bash
docker compose ps
docker compose logs -f
```

Mở dashboard trong LAN tại `http://10.70.22.170:3000`. API backend và
MediaMTX signaling được frontend chuyển tiếp cùng origin; cổng WebRTC ICE
`8189` TCP/UDP được public trực tiếp.

Dừng hoặc khởi động lại từng service:

```bash
docker compose stop
docker compose restart backend
docker compose restart frontend
docker compose restart mediamtx
```

Gỡ các container và network mà không xóa dữ liệu bind mount:

```bash
docker compose down
```

Dữ liệu camera và calibration được giữ tại `backend/data` trên host,
không nằm trong vòng đời container.
