# Neo Vision Clear Frontend

Dashboard Next.js được static export và chạy độc lập với FastAPI backend.

## Docker

Build image từ thư mục gốc của repository:

```bash
docker build -t neo-vision-clear-frontend ./frontend
```

Container phục vụ frontend tại cổng `3000`. Mặc định Nginx chuyển tiếp `/api`
và `/ws` tới `http://backend:8000`, phù hợp khi service FastAPI trong Docker
Compose có tên `backend`. `/webrtc` được chuyển tiếp tới
`http://mediamtx:8889` và bỏ prefix trước khi gửi sang MediaMTX.

Có thể chạy image trong network được tạo bởi Compose của MediaMTX:

```bash
docker run --rm \
  -p 3000:3000 \
  --network neo-vision-clear \
  -e BACKEND_UPSTREAM=http://backend:8000 \
  -e MEDIAMTX_UPSTREAM=http://mediamtx:8889 \
  neo-vision-clear-frontend
```

Image không đóng gói `.env.local`. Vì vậy URL WebRTC mặc định được suy ra từ
origin của frontend dưới `/webrtc`, tránh gắn cứng IP máy build. Media WebRTC
vẫn đi trực tiếp tới cổng ICE `8189` TCP/UDP do MediaMTX công bố.

## Phát triển cục bộ

Tạo file `.env.local` để Next.js dev server proxy tới backend và MediaMTX
đang chạy trên cùng máy:

```env
BACKEND_UPSTREAM=http://127.0.0.1:8000
NEXT_PUBLIC_MEDIAMTX_WEBRTC_URL=/webrtc
MEDIAMTX_UPSTREAM=http://127.0.0.1:8889
```

Sau đó chạy:

```bash
npm ci
npm run dev
```

Mở [http://localhost:3000](http://localhost:3000).
