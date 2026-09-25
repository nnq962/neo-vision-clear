# Lệnh thường dùng

Trừ khi có ghi chú khác, các lệnh trong tài liệu này được chạy từ thư
mục gốc:

```bash
cd /home/jetson/nnq962/neo-vision-clear
```

## Development có hot reload

Trong chế độ này, chỉ MediaMTX chạy trong Docker. Backend và frontend chạy
trực tiếp trên host để tự reload khi sửa code.

### Terminal 1: MediaMTX

```bash
docker compose up -d mediamtx
docker compose logs -f mediamtx
```

### Terminal 2: backend FastAPI

```bash
cd backend

LD_PRELOAD=/lib/aarch64-linux-gnu/libGLdispatch.so.0 \
MEDIAMTX_API_URL=http://127.0.0.1:9997/v3 \
MEDIAMTX_RTSP_URL=rtsp://127.0.0.1:8554 \
uv run uvicorn server.app:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload
```

Không cần hot reload:

```bash
cd backend

LD_PRELOAD=/lib/aarch64-linux-gnu/libGLdispatch.so.0 \
MEDIAMTX_API_URL=http://127.0.0.1:9997/v3 \
MEDIAMTX_RTSP_URL=rtsp://127.0.0.1:8554 \
uv run walkway-server
```

### Terminal 3: frontend Next.js

```bash
cd frontend
set -a
source ../.env
set +a
npm run dev -- --hostname 0.0.0.0
```

Chỉ cần cài dependency lần đầu hoặc khi `package-lock.json` thay đổi:

```bash
cd frontend
npm ci
```

Truy cập frontend development:

```text
http://<NVC_LAN_IP>:3000
```

Dừng backend và frontend bằng `Ctrl+C`, sau đó dừng MediaMTX:

```bash
docker compose stop mediamtx
```

## Production / test image

Tạo file môi trường lần đầu:

```bash
cp .env.example .env
```

Kiểm tra IP LAN trong `.env`:

```env
NVC_LAN_IP=<JETSON_LAN_IP>
```

Build image và khởi động cả ba service:

```bash
docker compose up -d --build
```

Ở lần build backend đầu tiên, Docker tự tải ba wheel dành cho JetPack
5.1.6 và checkpoint Depth Anything V2 từ Hugging Face, sau đó kiểm tra
SHA256 trước khi cài đặt. Không cần chép thủ công thư mục `backend/wheels`
hoặc `backend/weights` vào bản clone mới. Các lần build sau sẽ dùng lại
Docker layer cache nếu URL và checksum không thay đổi.

Những lần sau, khi code và Dockerfile không thay đổi:

```bash
docker compose up -d
```

Dashboard:

```text
http://<NVC_LAN_IP>:3000
```

### Trạng thái và log

```bash
docker compose ps
docker compose logs -f
```

Log riêng từng service:

```bash
docker compose logs -f --tail 100 backend
docker compose logs -f --tail 100 frontend
docker compose logs -f --tail 100 mediamtx
```

Log backend trong 10 phút gần nhất:

```bash
docker compose logs --since 10m backend
```

### Build hoặc restart riêng từng service

```bash
docker compose up -d --build backend
docker compose up -d --build frontend
docker compose restart mediamtx
```

Restart mà không build lại:

```bash
docker compose restart backend
docker compose restart frontend
```

### Dừng hệ thống

Dừng nhưng giữ container:

```bash
docker compose stop
docker compose start
```

Xóa container và network Compose:

```bash
docker compose down
```

Lệnh `down` không xóa dữ liệu bind mount trong `backend/data`.

## Health-check nhanh

Frontend Nginx:

```bash
curl -i http://127.0.0.1:3000/healthz
```

Frontend proxy tới backend:

```bash
curl -i http://127.0.0.1:3000/api/cameras
curl -i http://127.0.0.1:3000/api/runtime/status
```

Backend trực tiếp từ host:

```bash
curl -i http://127.0.0.1:8000/health
```

MediaMTX Control API:

```bash
curl -i http://127.0.0.1:9997/v3/config/global/get
curl -sS http://127.0.0.1:9997/v3/paths/list | python3 -m json.tool
```

## Kiểm tra network nội bộ

```bash
docker network inspect neo-vision-clear
```

Kiểm tra DNS từ backend tới MediaMTX:

```bash
docker compose exec backend getent hosts mediamtx
```

Kiểm tra DNS từ frontend:

```bash
docker compose exec frontend getent hosts backend
docker compose exec frontend getent hosts mediamtx
```

## Kiểm tra GPU và GStreamer

PyTorch có nhận CUDA hay không:

```bash
docker compose exec backend python -c \
  "import torch; print('CUDA:', torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

Plugin decoder Jetson:

```bash
docker compose exec backend gst-inspect-1.0 nvv4l2decoder
```

Theo dõi tài nguyên:

```bash
docker stats
sudo tegrastats
```

## Build image thủ công

Backend cần BuildKit và Buildx vì Dockerfile dùng cache mount. Xem phần
"Yêu cầu Docker trên Jetson" trong `README.md` để cài đặt và kiểm tra. Khi
build ngoài Compose, bật BuildKit rõ ràng bằng:

```bash
cd backend
DOCKER_BUILDKIT=1 docker build -t neo-vision-clear-backend .
```

Frontend:

```bash
cd frontend
docker build -t neo-vision-clear-frontend .
```

## UART tùy chọn

Jetson này có `/dev/ttyTHS4`, trong khi backend mặc định dùng `/dev/ttyS4`.
Khi cần UART, bỏ comment trong service `backend` của `docker-compose.yml`:

```yaml
devices:
  - /dev/ttyTHS4:/dev/ttyS4
```

Sau đó tái tạo backend:

```bash
docker compose up -d --force-recreate backend
```
