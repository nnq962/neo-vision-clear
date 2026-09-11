# Walkway Monitor

Project tạo baseline depth của một lối đi trống để chuẩn bị cho việc phát hiện vật cản
bằng Depth Anything V2. Camera được giả định là cố định hoàn toàn.

## Bước 1: tạo baseline

### Chuẩn bị

```bash
uv sync
```

Đặt checkpoint Depth Anything V2 vào thư mục `weights/`. Tên mặc định theo encoder:

```text
weights/depth_anything_v2_vits.pth
weights/depth_anything_v2_vitb.pth
weights/depth_anything_v2_vitl.pth
```

`vits` là encoder mặc định và phù hợp để bắt đầu thử nghiệm.

### Tạo baseline từ RTSP

```bash
uv run walkway-monitor calibrate \
  --source 'rtsp://user:password@camera/stream' \
  --encoder vits \
  --frames 60 \
  --output data/walkway_baseline.npz
```

Nếu OpenCV không có GStreamer hoặc pipeline GStreamer không phù hợp:

```bash
uv run walkway-monitor calibrate \
  --source 'rtsp://user:password@camera/stream' \
  --no-gstreamer
```

### Tạo baseline từ video

Phần đầu video dùng để calibration phải quay cảnh lối đi trống.

```bash
uv run walkway-monitor calibrate \
  --source assets/examples_video/hospital_corridor.mp4 \
  --frames 60 \
  --output data/walkway_baseline.npz
```

Quy trình tương tác:

1. Click trái để thêm điểm ROI, click phải hoặc Backspace để xóa điểm.
2. Chọn đúng bốn góc theo thứ tự P1 trên-trái, P2 trên-phải, P3 dưới-phải,
   P4 dưới-trái rồi nhấn Enter. Thứ tự này xác định cạnh vào P1-P2 và cạnh ra P4-P3.
3. Dọn sạch lối đi rồi nhấn Enter hoặc Space để bắt đầu.
4. Chờ model xử lý đủ số frame đã cấu hình.

### Baseline được tạo như thế nào

Frame đầu tiên được thu nhỏ về `--process-width` (mặc định 960, không phóng lớn ảnh nhỏ)
và dùng để chọn ROI. Sau khi người dùng xác nhận lối đi trống, pipeline thu đúng số frame
được cấu hình bởi `--frames` và xử lý như sau:

```text
Các full frame của cảnh trống
        ↓ Depth Anything V2 chạy trên từng full frame
Các relative depth map có shape (height, width), dtype float32
        ↓ căn chỉnh scale và shift giữa các depth map
Các depth map được đưa về cùng một thang giá trị
        ↓ lấy median tại từng pixel
reference_depth của cảnh trống
        ↓ đo độ lệch của từng depth map so với reference_depth
noise_map mô tả độ dao động bình thường tại từng pixel
```

Depth Anything V2 trả về depth tương đối, không phải khoảng cách theo mét. Cùng một cảnh
trống, scale và shift của các giá trị depth vẫn có thể dao động giữa các frame. Vì vậy,
pipeline thực hiện hai lượt căn chỉnh affine theo công thức gần đúng
`reference ≈ scale × current + shift`, rồi mới lấy median cuối cùng. Median giúp giảm ảnh
hưởng của một vài frame hoặc pixel có dự đoán bất thường.

Hai map quan trọng được tạo ra là:

- `reference_depth[y, x]`: giá trị depth chuẩn khi cảnh trống tại pixel `(y, x)`.
- `noise_map[y, x]`: mức dao động bình thường của depth tại pixel đó. Khi detection, pixel
  có noise lớn sẽ cần sai khác lớn hơn mới được xem là thay đổi thật.

Ở bước calibration hiện tại, model luôn chạy trên toàn bộ frame. ROI không được dùng để
crop ảnh, căn chỉnh depth, tính `reference_depth` hoặc tính `noise_map`. ROI chỉ được kiểm
tra, hiển thị và lưu cùng baseline. Đến bước detection, ROI được dùng để tìm vật cản; một lớp
padding mỏng bên ngoài cung cấp thêm ngữ cảnh khi so sánh và làm sạch mask. Phần còn lại của
khung cảnh không được xét.

Kết quả gồm:

```text
data/walkway_baseline.npz
data/walkway_baseline.json
data/walkway_baseline.preview.jpg
data/walkway_baseline.depth.jpg
```

File NPZ chứa reference depth, noise map, polygon ROI chuẩn hóa và metadata calibration.
File JSON cùng tên chứa một bản metadata và polygon ROI chuẩn hóa dễ đọc, sẵn sàng để bổ
sung `world_coordinates` tương ứng theo thứ tự các đỉnh mà không cần tạo lại các depth map.
Khi trường này tồn tại, cửa sổ detection hiển thị nhãn `P# (X, Y) đơn_vị` cạnh từng đỉnh ROI.
Ảnh preview giúp kiểm tra trực quan ROI đã chọn; ảnh depth là heatmap của reference depth
có vẽ polygon ROI. Có thể đổi đường dẫn heatmap bằng `--depth-preview`. Dữ liệu calibration
cục bộ không được commit.

## Bước 2: phát hiện vật cản

Detection đọc full frame và resize về đúng độ phân giải đã lưu trong baseline. Detector tạo
`check_area` bằng cách mở rộng ROI thêm một lớp padding mỏng. Depth thô của mỗi frame được
căn chỉnh scale/shift bằng robust alignment trên ROI rồi mới so sánh với `reference_depth`.
Phép fit chỉ giữ nhóm pixel khớp baseline nhất, vì vậy người và vật cản được xem như outlier
thay vì kéo lệch toàn bộ depth map. Không có bộ lọc theo thời gian: mask và số đo phản ánh
ngay frame hiện tại. So sánh depth và morphology sử dụng check area, sau đó mask được cắt
lại về ROI trước khi đo và hiển thị. Những thay đổi nằm ngoài check area không được xét.
Nguồn detection phải đến từ cùng camera, cùng góc nhìn và cùng tỷ lệ khung hình với nguồn
đã dùng để calibration.

### Chạy với RTSP

```bash
uv run walkway-monitor detect \
  --source 'rtsp://user:password@camera/stream' \
  --baseline data/walkway_baseline.npz
```

### Chạy với video

```bash
uv run walkway-monitor detect \
  --source assets/examples_video/hospital_corridor.mp4 \
  --baseline data/walkway_baseline.npz
```

Checkpoint mặc định được chọn từ encoder lưu trong baseline. Ví dụ baseline dùng `vits` thì
CLI tự đọc `weights/depth_anything_v2_vits.pth`.

Cửa sổ debug hiển thị theo lưới 2x2:

- Frame camera có ROI, lớp padding của check area màu xanh và vùng depth thay đổi tô đỏ.
- Góc nhìn BEV chiếu ROI lên mặt phẳng theo tọa độ thực trong JSON; mask vật cản vẫn tô đỏ.
- Vạch cam đánh dấu nút thắt trên tuyến trống liên thông từ đầu tới cuối hành lang.
- Depth thô và depth sau robust alignment ở hàng dưới, dùng cùng dải màu cố định
  theo baseline. Panel cuối hiển thị `scale`, `shift` và tỷ lệ pixel dùng để fit.
- Panel BEV liệt kê từng dòng số đo theo mét; module không kết luận lối đi trống hay bị chặn.

Hai heatmap được bật mặc định. Có thể ẩn hàng heatmap để cửa sổ chỉ còn camera và BEV:

```bash
uv run walkway-monitor detect \
  --source 'rtsp://user:password@camera/stream' \
  --baseline data/walkway_baseline.npz \
  --no-depth-heatmaps
```

Dùng `--depth-heatmaps` để bật lại khi flag được cấu hình từ script hoặc alias khác.

Nhấn `Q` hoặc `Esc` để dừng. Với video hoặc môi trường không có màn hình, có thể dùng
`--no-display`.

Khi chạy không hiển thị, pipeline vẫn log FPS và thời gian từng công đoạn mỗi 2 giây:

```bash
uv run walkway-monitor detect \
  --source 'rtsp://user:password@camera/stream' \
  --baseline data/walkway_baseline.npz \
  --no-display \
  --log-interval 2
```

Ví dụ log:

```text
FPS=18.62 | inference=42.1ms | analysis=3.4ms | render=0.0ms | bề rộng đi xuyên suốt=0.82m/1.75m | nút thắt Y=2.35m
```

Đặt `--log-interval 0` nếu muốn tắt log hiệu năng định kỳ.

### Tham số tuning ban đầu

| Tham số | Mặc định | Ý nghĩa |
|---|---:|---|
| `--noise-multiplier` | `6.0` | Nhân noise map của baseline để tạo threshold từng pixel |
| `--minimum-difference` | `0.03` | Ngưỡng depth gần hơn baseline tối thiểu |
| `--bev-pixels-per-meter` | `100` | Raster BEV dùng 100 pixel cho mỗi mét khi đo bề rộng |
| `--depth-blur-kernel` | `5` | Làm mượt depth trước khi so sánh |
| `--check-area-padding` | `12` | Mở rộng ROI 12 pixel để so sánh và làm sạch mask |
| `--no-depth-alignment` | Tắt | Bỏ căn chỉnh và so sánh trực tiếp depth raw với baseline |
| `--alignment-inlier-ratio` | `0.55` | Giữ 55% pixel ROI khớp baseline nhất để fit scale/shift |
| `--display-minimum-area-ratio` | `0.001` | Loại component nhỏ hơn 0.1% ROI khỏi mask và quyết định bề rộng |

Mask thô chỉ lấy depth gần camera hơn baseline trong check area. Sau morphology, mask được
cắt về ROI, loại component nhỏ rồi chiếu sang raster BEV theo tọa độ thực. Analyzer co vùng
trống theo từng bề rộng footprint ứng viên và kiểm tra connected component có nối từ đầu tới
cuối hành lang hay không. Kết quả là `maximum_passable_width_meters`, vị trí Y của nút thắt
và các khoảng X còn trống tại đó. Module chỉ trả số đo; hệ thống nhận dữ liệu tự áp dụng quy
tắc kết luận. Baseline không có `world_coordinates` sẽ bị từ chối thay vì trả số đo pixel dễ
gây hiểu nhầm. Camera phải giữ nguyên vị trí.

## FastAPI server và WebSocket

Package `server` nằm độc lập với `walkway_monitor`. FastAPI lifespan nạp model,
mở nguồn camera khi startup và yêu cầu worker dừng khi shutdown. Cấu hình server
được đọc từ các biến môi trường `WALKWAY_*`:

```bash
WALKWAY_SOURCE='rtsp://user:password@camera/stream' \
WALKWAY_BASELINE='data/walkway_baseline.npz' \
WALKWAY_HOST='0.0.0.0' \
WALKWAY_PORT='8000' \
uv run walkway-server
```

Robot kết nối tới `ws://<host>:8000/ws/corridor` và gửi:

```json
{"type": "get_corridor_info", "request_id": "req-01"}
```

Server trả dữ liệu mới nhất và giữ nguyên `request_id`:

```json
{
  "type": "corridor_info",
  "request_id": "req-01",
  "status": "ok",
  "age_ms": 24,
  "data": {
    "maximum_passable_width_meters": 0.82,
    "walkway_width_meters": 1.75,
    "bottleneck": {
      "y_meters": 2.35,
      "free_x_ranges_meters": [[0.0, 0.82]]
    },
    "frame_index": 120,
    "captured_at": 1789119256.74
  },
  "error": null
}
```

`status` có thể là `ok`, `warming_up`, `stale` hoặc `error`. Đây chỉ là trạng
thái của dữ liệu/camera; server không kết luận robot có đi qua được hay không.
Endpoint `GET /health` cung cấp cùng trạng thái để health-check service.

## Kiểm thử

```bash
uv run python -m unittest discover -s tests -p 'test_*.py'
```

Các test thuật toán không cần checkpoint hoặc GPU.

## Cấu trúc chính

```text
src/walkway_monitor/
├── cli.py
├── config.py
├── models.py
├── calibration/
│   ├── baseline_builder.py
│   ├── pipeline.py
│   ├── roi_selector.py
│   └── storage.py
├── detection/
│   ├── bev.py
│   ├── components.py
│   ├── detector.py
│   └── pipeline.py
└── depth/
    ├── alignment.py
    └── estimator.py

src/server/
├── app.py
├── lifespan.py
├── settings.py
├── dependencies.py
├── models/
│   └── messages.py
├── routes/
│   ├── health.py
│   └── websocket.py
└── services/
    ├── monitor.py
    └── snapshot_store.py
```

Detection chạy theo từng frame và chỉ trả mask cùng các phép đo trung lập.
