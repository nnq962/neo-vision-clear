# Neo Vision Clear

Demo phát hiện một vùng trong hình ảnh camera cố định đang trống hay bị chiếm dụng.
Chương trình chỉ dùng các thuật toán xử lý ảnh của OpenCV, không dùng model ML.
Ảnh hiện tại được so với nền bằng khoảng cách màu Lab để phân biệt các vật thể có
độ sáng gần giống nền nhưng khác màu.

## Cài đặt

Dự án yêu cầu Python 3.10 trở lên. Nếu dùng `uv`:

```bash
uv sync
```

Hoặc dùng `venv` và `pip`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Cấu hình camera

Đặt URL camera trong biến môi trường. Không ghi URL chứa mật khẩu vào source code:

```bash
export CAMERA_RTSP_URL='rtsp://username:password@camera-address:554/path'
```

Có thể dùng webcam bằng cách truyền `--source 0`, hoặc dùng video có sẵn bằng cách
truyền đường dẫn file vào `--source`.

## 1. Chụp nền trống và chọn ROI

```bash
uv run python main.py --setup
```

Trong cửa sổ preview:

1. Đảm bảo không có người, xe hoặc vật cản trong khu vực.
2. Nhấn `Space` để chụp ảnh nền.
3. Click chuột trái lần lượt để đặt các đỉnh của polygon.
4. Click chuột phải để xóa đỉnh vừa đặt, hoặc nhấn `C` để vẽ lại.
5. Nhấn `Enter` sau khi có ít nhất 3 đỉnh để xác nhận ROI.

Chỉ phần ảnh bao quanh polygon được lưu làm nền trong thư mục `data/`; khi xử lý,
các pixel nằm ngoài polygon bị loại bỏ hoàn toàn. Toàn bộ frame không được lưu.

## 2. Chạy detector

```bash
uv run python main.py
```

- Khung xanh: `EMPTY`.
- Khung đỏ: `OCCUPIED`.
- `changed` là tỷ lệ diện tích trong ROI khác với ảnh nền.
- Nhấn `M` để bật/tắt mask và `Q` để thoát.

Cửa sổ mặc định hiển thị ở 65% kích thước ảnh gốc. Có thể thu nhỏ thêm mà
không ảnh hưởng độ phân giải xử lý:

```bash
uv run python main.py --display-scale 0.5
```

Tham số này cũng dùng được trong bước setup, ví dụ:

```bash
uv run python main.py --setup --display-scale 0.5
```

## Tinh chỉnh

Sau bước setup, có thể sửa `data/config.json`:

- `pixel_threshold`: khoảng cách màu Lab tối thiểu của một pixel.
- `occupied_ratio`: tỷ lệ diện tích thay đổi để báo occupied.
- `min_contour_area`: bỏ qua các vùng nhiễu nhỏ hơn giá trị này.
- `enter_frames`: số frame liên tiếp trước khi chuyển sang occupied.
- `exit_frames`: số frame liên tiếp trước khi trở lại empty.

Giá trị ban đầu ưu tiên giảm nhiễu. Điều kiện ánh sáng thực tế có thể cần tinh chỉnh.
