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

## Yêu cầu Docker trên Jetson

Luồng Docker của dự án dành cho Jetson ARM64 chạy JetPack 5.1.6. Máy cần có:

- Docker Engine;
- Docker Compose V2, sử dụng lệnh `docker compose` thay vì `docker-compose`;
- Docker Buildx để Compose sử dụng BuildKit;
- NVIDIA Container Runtime để backend truy cập GPU và bộ giải mã Jetson.

Kiểm tra môi trường trước khi build:

```bash
docker --version
docker compose version
docker buildx version
docker buildx inspect --bootstrap
docker info --format '{{json .Runtimes}}' | grep -q '"nvidia"' \
  && echo "NVIDIA runtime: OK"
```

Trên JetPack 5.1.6/Ubuntu 20.04 sử dụng package Docker của Ubuntu, có thể cài
Engine, Buildx và Compose V2 bằng:

```bash
sudo apt update
sudo apt install docker.io docker-buildx docker-compose-v2
```

Nếu Docker được cài từ repository chính thức của Docker thay vì repository
Ubuntu, tên hai plugin tương ứng là `docker-buildx-plugin` và
`docker-compose-plugin`. Không trộn hai bộ package trong cùng một lệnh cài.

NVIDIA Container Runtime thường được JetPack cài sẵn. Nếu lệnh kiểm tra phía
trên không thấy runtime `nvidia`, cần hoàn tất cài đặt và cấu hình NVIDIA
Container Runtime trước khi chạy backend.

Cho phép user hiện tại chạy Docker mà không cần `sudo`:

```bash
sudo usermod -aG docker "$USER"
newgrp docker
```

Việc tham gia group `docker` cấp quyền quản trị tương đương root trên máy đó.
Có thể đăng xuất rồi đăng nhập lại thay cho `newgrp docker`.

BuildKit được Docker Compose V2 sử dụng tự động khi Buildx khả dụng. Dockerfile
backend cần BuildKit vì sử dụng cache mount.

## Chạy toàn bộ hệ thống bằng Docker Compose

Compose gốc quản lý ba service `mediamtx`, `backend` và `frontend` trong cùng
network `neo-vision-clear`. File `.env` là bắt buộc vì Compose không đặt IP LAN
dự phòng. Tạo file từ mẫu rồi sửa `NVC_LAN_IP` thành IP của Jetson:

```bash
cp .env.example .env
nano .env
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

Mở dashboard trong LAN tại `http://<NVC_LAN_IP>:3000`. API backend và
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
