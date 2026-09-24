# Neo Vision Clear

Dự án được tổ chức thành các workspace độc lập:

- `backend/`: toàn bộ ứng dụng Python, môi trường `uv`, model, test và dữ liệu runtime.
- `frontend/`: dashboard Next.js được build thành static export.
- `mediamtx/`: cấu hình MediaMTX cho RTSP và WebRTC.

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
