# Neo Vision Clear Aggregator

Dịch vụ độc lập nhận kết quả camera từ nhiều Jetson, ánh xạ camera vào vị trí
hành lang, tổng hợp `pass / blocked / unknown` và chủ động gửi kết luận tới một
WebSocket server đích.

## Cấu hình nghiệp vụ

Sửa [`config/config.json`](config/config.json) hoặc dùng dashboard tại
`http://<aggregator-ip>:8100`. `camera_id` lấy từ camera đã tạo
trên backend; `source_id` phải trùng `NVC_JETSON_ID` của máy đang quản lý camera:

```json
{
  "schema_version": 1,
  "corridor": {
    "corridor_id": "corridor-01",
    "corridor_name": "Hành lang tầng 1",
    "required_width_cm": 50
  },
  "cameras": [
    {
      "camera_id": "camera-01",
      "source_id": "jetson-a",
      "order": 1,
      "location_name": "Đầu hành lang"
    }
  ],
  "outbound": {
    "enabled": true,
    "websocket_url": "ws://robot-server:9000/ws/corridor-status",
    "reconnect_seconds": 2
  }
}
```

Aggregator không suy ra vị trí từ thứ tự message. Nó luôn dùng `camera_id` để tra
`order` và `location_name` trong file này. Camera không có trong config hoặc đến
từ sai `source_id` sẽ bị từ chối.

## Chạy local

```bash
cd aggregator
uv sync
uv run aggregator-server
```

Các biến hạ tầng tùy chọn:

```env
AGGREGATOR_HOST=0.0.0.0
AGGREGATOR_PORT=8100
AGGREGATOR_SOURCE_STALE_SECONDS=3
AGGREGATOR_CONFIG_PATH=/absolute/path/to/config.json
```

## API và WebSocket

```text
GET /
GET /health
GET /api/dashboard
GET /api/config
PUT /api/config
GET /api/sources
GET /api/sources/{source_id}/latest
GET /api/cameras
GET /api/decision
GET /api/outbound
WS  /ws/ingest/{source_id}
```

Dashboard tự refresh mỗi giây và hiển thị trạng thái hành lang, camera, Jetson,
payload nhận/gửi cuối cùng. `PUT /api/config` ghi file nguyên tử rồi áp dụng ánh
xạ camera cùng kết nối outbound mới ngay lập tức.

Jetson push message một chiều, không cần ACK:

```json
{
  "schema_version": 1,
  "camera_id": "camera-03",
  "camera_name": "Camera 3",
  "state": "blocked",
  "zone_count": 10,
  "blocked_zones": [4, 5],
  "minimum_free_ratio": 0.18,
  "max_passable_width_cm": 18,
  "reason": "insufficient_clearance",
  "observed_at": "2026-09-26T10:30:12.450Z"
}
```

Kết luận outbound khi hành lang tắc:

```json
{
  "schema_version": 1,
  "corridor_id": "corridor-01",
  "corridor_name": "Hành lang tầng 1",
  "state": "blocked",
  "can_pass": false,
  "required_width_cm": 50,
  "blocked_areas": [
    {
      "order": 3,
      "location_name": "Đoạn giữa B",
      "camera_id": "camera-03",
      "camera_name": "Camera 3",
      "blocked_zones": [4, 5],
      "zone_count": 10,
      "minimum_free_ratio": 0.18,
      "max_passable_width_cm": 18,
      "reason": "insufficient_clearance",
      "source": "jetson-b",
      "observed_at": "2026-09-26T10:30:12.450Z"
    }
  ],
  "unavailable_cameras": [],
  "decided_at": "2026-09-26T10:30:12.500Z"
}
```

Quy tắc tổng hợp:

- Có ít nhất một camera tắc hoặc độ rộng nhỏ hơn `required_width_cm`: `blocked`.
- Không tắc nhưng có camera thiếu, stale, warming-up hoặc error: `unknown`.
- Mọi camera đã cấu hình đều mới và đủ rộng: `pass`.

## Docker

```bash
docker compose --profile aggregator up -d --build aggregator
```

Compose mount thư mục `aggregator/config` để dashboard có thể lưu thay đổi. Chỉ
chạy service này trên máy được chọn làm điểm tập kết. `AGGREGATOR_UID` và
`AGGREGATOR_GID` trong `.env` phải trùng user sở hữu thư mục config; xem bằng
`id -u` và `id -g`. Backend cùng Compose có thể dùng
`NVC_AGGREGATOR_WS_BASE_URL=ws://aggregator:8100/ws/ingest`; backend trên Jetson
còn lại phải dùng IP LAN của máy tập kết, ví dụ
`ws://192.168.1.100:8100/ws/ingest`.

## Kiểm thử

```bash
uv run python -m unittest discover -s . -p 'test_*.py'
```
