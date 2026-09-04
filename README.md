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
2. Nhấn Enter sau khi polygon có ít nhất ba điểm.
3. Dọn sạch lối đi rồi nhấn Enter hoặc Space để bắt đầu.
4. Chờ model xử lý đủ số frame đã cấu hình.

Kết quả gồm:

```text
data/walkway_baseline.npz
data/walkway_baseline.preview.jpg
```

File NPZ chứa reference depth, noise map, polygon ROI chuẩn hóa và metadata calibration.
Ảnh preview giúp kiểm tra trực quan ROI đã chọn. Dữ liệu calibration cục bộ không được commit.

## Bước 2: phát hiện vật cản

Detection đọc full frame và resize về đúng độ phân giải đã lưu trong baseline. Project chưa
crop ROI ở bước này. Nguồn detection phải đến từ cùng camera, cùng góc nhìn và cùng tỷ lệ
khung hình với nguồn đã dùng để calibration.

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

Cửa sổ debug hiển thị:

- Frame có ROI và vùng depth thay đổi tô đỏ.
- Heatmap Depth Anything ở panel bên phải, dùng dải màu cố định theo baseline.
- Trạng thái `LỐI ĐI TRỐNG`, `CÓ VẬT CẢN` hoặc `KHÔNG XÁC ĐỊNH`.

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
FPS=18.62 | inference=42.1ms | detection=3.4ms | render=0.0ms | state=clear
```

Đặt `--log-interval 0` nếu muốn tắt log hiệu năng định kỳ.

### Tham số tuning ban đầu

| Tham số | Mặc định | Ý nghĩa |
|---|---:|---|
| `--noise-multiplier` | `4.0` | Nhân noise map của baseline để tạo threshold từng pixel |
| `--minimum-difference` | `0.015` | Ngưỡng sai khác depth chuẩn hóa tối thiểu |
| `--minimum-area-ratio` | `0.01` | Component lớn nhất phải chiếm ít nhất 1% ROI |
| `--occupied-frames` | `5` | Số frame liên tiếp để xác nhận có vật cản |
| `--clear-frames` | `8` | Số frame liên tiếp để xác nhận lối đi trống |

Nếu phần lớn vùng ngoài ROI thay đổi bất thường, detector trả `UNKNOWN` thay vì kết luận lối
đi trống. Điều này giúp nhận biết camera bị dịch chuyển hoặc khung cảnh không còn khớp baseline.

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
│   ├── components.py
│   ├── detector.py
│   ├── pipeline.py
│   └── temporal_filter.py
└── depth/
    ├── alignment.py
    └── estimator.py
```

Detection trả ba trạng thái `CLEAR`, `OCCUPIED` và `UNKNOWN`.
