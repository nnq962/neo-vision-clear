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
data/walkway_baseline.preview.jpg
data/walkway_baseline.depth.jpg
```

File NPZ chứa reference depth, noise map, polygon ROI chuẩn hóa và metadata calibration.
Ảnh preview giúp kiểm tra trực quan ROI đã chọn; ảnh depth là heatmap của reference depth
có vẽ polygon ROI. Có thể đổi đường dẫn heatmap bằng `--depth-preview`. Dữ liệu calibration
cục bộ không được commit.

## Bước 2: phát hiện vật cản

Detection đọc full frame và resize về đúng độ phân giải đã lưu trong baseline. Detector tạo
`check_area` bằng cách mở rộng ROI thêm một lớp padding mỏng. Depth thô của mỗi frame được
căn chỉnh scale/shift bằng robust alignment trên ROI rồi mới so sánh với `reference_depth`.
Phép fit chỉ giữ nhóm pixel khớp baseline nhất, vì vậy người và vật cản được xem như outlier
thay vì kéo lệch toàn bộ depth map. Không có bộ lọc theo thời gian: trạng thái và mask vẫn
phản ánh ngay frame hiện tại. So sánh depth và morphology sử dụng check area, sau đó mask
được cắt lại về ROI trước khi tính trạng thái và hiển thị. Những thay đổi nằm ngoài check area
không được xét. Nguồn detection phải đến từ cùng camera, cùng góc nhìn và cùng tỷ lệ khung
hình với nguồn đã dùng để calibration.

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

- Frame có ROI, lớp padding của check area màu xanh và vùng depth thay đổi tô đỏ trong ROI.
- Vạch cam đánh dấu lát cắt đang có khoảng trống liên tục hẹp nhất.
- Depth thô và depth sau robust alignment ở hai panel bên phải, dùng cùng dải màu cố định
  theo baseline. Panel cuối hiển thị `scale`, `shift` và tỷ lệ pixel dùng để fit.
- Trạng thái `LỐI ĐI TRỐNG` hoặc `CÓ VẬT CẢN` được kết luận ngay trên từng frame.

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
| `--noise-multiplier` | `6.0` | Nhân noise map của baseline để tạo threshold từng pixel |
| `--minimum-difference` | `0.03` | Ngưỡng depth gần hơn baseline tối thiểu |
| `--minimum-free-width-ratio` | `0.55` | Lối đi phải còn một khoảng trống liên tục rộng ít nhất 55% |
| `--width-smoothing-rows` | `9` | Lấy median 9 hàng để loại lát cắt nhiễu đơn lẻ |
| `--depth-blur-kernel` | `5` | Làm mượt depth trước khi so sánh |
| `--check-area-padding` | `12` | Mở rộng ROI 12 pixel để so sánh và làm sạch mask |
| `--no-depth-alignment` | Tắt | Bỏ căn chỉnh và so sánh trực tiếp depth raw với baseline |
| `--alignment-inlier-ratio` | `0.55` | Giữ 55% pixel ROI khớp baseline nhất để fit scale/shift |
| `--display-minimum-area-ratio` | `0.001` | Loại component nhỏ hơn 0.1% ROI khỏi mask và quyết định bề rộng |

Mask thô chỉ lấy depth gần camera hơn baseline trong check area. Sau khi morphology, mask
được cắt về ROI và loại component nhỏ. Trên từng hàng của polygon, detector coi bề rộng ROI
là 100% rồi tìm khoảng trống liên tục lớn nhất. Median của các hàng lân cận tạo ra
`minimum_free_width_ratio`; trạng thái là `OCCUPIED` nếu tỷ lệ này thấp hơn ngưỡng yêu cầu.
Vật dài sát mép có thể chiếm nhiều diện tích nhưng vẫn cho `CLEAR` nếu phần rộng còn lại đủ
đi qua. Detector có robust alignment nhưng không voting theo thời gian, nên cả trạng thái lẫn
mask phản ánh ngay frame hiện tại. Robust fit giả định hơn một nửa ROI vẫn là nền có thể khớp
với baseline. Detector không kiểm tra toàn bộ vùng ngoài ROI; người vận hành phải bảo đảm
camera không đổi vị trí.

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
│   └── pipeline.py
└── depth/
    ├── alignment.py
    └── estimator.py
```

Detection đang chạy theo từng frame và trả trực tiếp `CLEAR` hoặc `OCCUPIED`.
