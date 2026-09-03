# media-sources

`media-sources` giúp đọc frame từ nhiều loại nguồn media bằng một interface thống nhất:
ảnh, numpy array, video file, webcam, RTSP/RTMP và YouTube.

Mục tiêu chính của project là phục vụ các pipeline computer vision như YOLO, RetinaFace,
tracking, OCR hoặc các task inference cần nhận `list[numpy.ndarray]` theo batch.

## Cài đặt

```bash
uv sync
```

Mặc định project cài `opencv-python` từ PyPI. Bản này có thể không được build kèm
GStreamer tùy nền tảng.

Nếu cần RTSP low-latency qua GStreamer, hãy tự build OpenCV wheel có GStreamer trên máy
deploy rồi cài đè vào venv:

```bash
uv pip install --force-reinstall /path/to/opencv_python-*.whl
```

Kiểm tra OpenCV hiện tại có GStreamer hay không:

```bash
uv run python - <<'PY'
import cv2
print("GStreamer: YES" if "GStreamer:                   YES" in cv2.getBuildInformation() else "GStreamer: NO")
PY
```

Nếu OpenCV không có GStreamer, `RtspReader` vẫn fallback sang FFMPEG.

## Dùng nhanh với nhiều nguồn

Dùng `MediaSources` khi bạn muốn đọc một hoặc nhiều nguồn theo batch.

```python
from media_sources import MediaSources

sources = [
    "rtsp://cam1",
    "rtsp://cam2",
]

with MediaSources(sources) as ms:
    for frames, infos in ms:
        # frames[0] là frame mới nhất của cam1
        # frames[1] là frame mới nhất của cam2
        results = model.predict(frames)
```

Mỗi vòng lặp trả về:

```python
frames, infos
```

Trong đó:

- `frames`: `list[numpy.ndarray]`, frame BGR 3-channel, đúng thứ tự `sources`.
- `infos`: `list[SourceMeta]`, metadata tương ứng với từng frame.

Quan hệ index luôn được giữ:

```python
frames[i] <-> infos[i] <-> sources[i]
```

## Một nguồn cũng là batch

`MediaSources` luôn trả về batch, kể cả khi bạn truyền một nguồn.

```python
from media_sources import MediaSources

with MediaSources("video.mp4") as ms:
    for frames, infos in ms:
        frame = frames[0]
        info = infos[0]
        process(frame)
```

Nếu bạn muốn API đọc một nguồn trả thẳng `frame, meta`, xem phần `create_media_source`.

## Realtime camera: lấy frame mới nhất

Với `RTSP`, `RTMP` và `webcam`, `MediaSources` dùng background thread cho từng nguồn.
Nếu model chạy chậm hơn camera, frame cũ sẽ bị bỏ để giữ realtime.

Ví dụ camera 25 FPS nhưng model mất 500ms:

```python
with MediaSources(["rtsp://cam1", "rtsp://cam2"]) as ms:
    for frames, infos in ms:
        model.predict(frames)
```

Trong lúc model đang chạy, reader vẫn đọc frame mới ở nền. Khi vòng lặp quay lại, bạn nhận
batch mới nhất, không bị backlog các frame cũ.

Lưu ý hiện tại: với nhiều stream, batch chỉ được trả khi tất cả nguồn đều có frame mới hơn
lần trả trước. Nếu một camera bị chậm hoặc mất tín hiệu, toàn bộ batch có thể chờ hoặc raise
`StreamError`.

## Video và ảnh: đọc tuần tự

Với video file, image và YouTube video, batch được đọc theo kiểu lockstep.

```python
with MediaSources(["video1.mp4", "video2.mp4"]) as ms:
    for frames, infos in ms:
        # mỗi vòng đọc frame kế tiếp từ mọi video
        results = model.predict(frames)
```

Không có frame bị drop. Nếu model chậm, tốc độ đọc video sẽ chậm theo.

## Các loại nguồn hỗ trợ

| Loại | Ví dụ | Cách đọc |
|---|---|---|
| Ảnh path | `"image.jpg"` | đọc một lần |
| Ảnh numpy | `np.ndarray` | chuẩn hóa về BGR |
| Video file | `"clip.mp4"` | đọc tuần tự đến hết file |
| Webcam | `0`, `1` | stream realtime |
| RTSP / RTMP | `"rtsp://..."` | stream realtime, có reconnect |
| YouTube | `"https://youtu.be/..."` | resolve bằng `yt-dlp` rồi đọc như video |

Batch phải đồng nhất loại nguồn. Ví dụ này không hợp lệ:

```python
MediaSources(["video.mp4", "image.jpg"])
```

Nếu trộn nhiều loại nguồn trong cùng một batch, project sẽ raise `ValueError` khi khởi tạo.

## `MediaSources` hay `create_media_source`?

Dùng `MediaSources` cho pipeline vision thông thường.

```python
with MediaSources(["cam1", "cam2"]) as ms:
    for frames, infos in ms:
        model.predict(frames)
```

`MediaSources`:

- Luôn trả batch: `frames, infos`.
- Dùng tốt cho nhiều camera/video.
- Có context manager để tự mở và đóng tài nguyên.
- Không expose trực tiếp `.open()` và `.read()`.

Dùng `create_media_source` khi bạn muốn reader cấp thấp hơn.
Với một nguồn đơn, bạn có thể tự gọi `open/read/close`.

```python
from media_sources import create_media_source

reader = create_media_source("video.mp4")

reader.open()

while True:
    result = reader.read()
    if result is None:
        break

    frame, meta = result
    process(frame)

reader.close()
```

Nếu truyền một nguồn, `create_media_source(source)` trả reader đơn nguồn:

```python
frame, meta = reader.read()
```

Nếu truyền list, `create_media_source(list_sources)` trả batch reader. Batch reader có
`open/close` và iterate được:

```python
batch = create_media_source(["rtsp://cam1", "rtsp://cam2"])

with batch:
    for frames, infos in batch:
        process(frames)
```

## Lazy open

`MediaSources(...)` và `create_media_source(...)` không kết nối ngay lúc khởi tạo.
Nguồn chỉ được mở khi:

- vào `with`;
- iterate lần đầu;
- hoặc gọi `open()` trực tiếp với reader/batch từ `create_media_source`.

Ví dụ:

```python
ms = MediaSources(["rtsp://cam1", "rtsp://cam2"])
# chưa kết nối camera

with ms:
    # camera được mở tại đây
    ...
```

## Metadata

Mỗi frame có một `SourceMeta` đi kèm.

| Field | Kiểu | Ý nghĩa |
|---|---|---|
| `name` | `str` | tên file, webcam id hoặc URL |
| `source_type` | `SourceType` | `IMAGE`, `VIDEO`, `WEBCAM`, `RTSP`, `YOUTUBE` |
| `frame_index` | `int` | chỉ số frame của nguồn đó |
| `resolution` | `tuple[int, int]` | `(width, height)` |
| `fps` | `float | None` | FPS nếu đọc được |
| `total_frames` | `int | None` | tổng số frame, chủ yếu cho video file |
| `is_stream` | `bool` | `True` với webcam/RTSP/live stream |
| `timestamp` | `float` | thời điểm đọc frame, epoch seconds |

Ví dụ:

```python
from media_sources import MediaSources, SourceType

with MediaSources(["rtsp://cam1"]) as ms:
    for frames, infos in ms:
        if infos[0].source_type == SourceType.RTSP:
            print(infos[0].resolution)
```

## RTSP options

Các option này có thể truyền vào `MediaSources` hoặc `create_media_source`.

```python
with MediaSources(
    ["rtsp://cam1", "rtsp://cam2"],
    use_gstreamer=True,
    reconnect=True,
    reconnect_forever=True,
    reconnect_delay=2.0,
) as ms:
    for frames, infos in ms:
        model.predict(frames)
```

| Option | Mặc định | Ý nghĩa |
|---|---:|---|
| `use_gstreamer` | `True` | thử GStreamer trước, fallback FFMPEG |
| `reconnect` | `True` | tự reconnect khi mất tín hiệu |
| `reconnect_delay` | `2.0` | thời gian chờ ban đầu giữa các lần reconnect |
| `reconnect_forever` | `True` | reconnect vô hạn |
| `max_reconnect_attempts` | `5` | số lần thử khi `reconnect_forever=False` |
| `open_timeout_ms` | `5000` | timeout mở stream |
| `read_timeout_ms` | `5000` | timeout đọc frame |

Kwargs không áp dụng cho loại reader hiện tại sẽ được bỏ qua và log ở mức DEBUG.

## Logging

Library không tự cấu hình logging khi import. App có thể bật logging bằng:

```python
from media_sources.utils import set_logging

set_logging()
set_logging(debug=True)
```

## Xử lý lỗi stream

Stream lỗi không hồi phục sẽ raise `StreamError`.

```python
from media_sources import MediaSources, StreamError

try:
    with MediaSources(["rtsp://cam1"]) as ms:
        for frames, infos in ms:
            model.predict(frames)
except StreamError as exc:
    print(f"Stream lỗi: {exc}")
```

## Thiết kế bên trong

Project tách thành ba tầng:

```text
BaseReader
  đọc một nguồn: image, video, webcam, rtsp, youtube

SyncBatchReader
  gộp nhiều reader tuần tự: image, video, youtube

StreamBatchReader
  gộp nhiều reader realtime: webcam, rtsp/rtmp

MediaSources
  wrapper tiện dụng cho pipeline vision, luôn trả frames, infos
```

Điểm chính:

- Mỗi reader chỉ quản lý một nguồn.
- Batch giữ đúng thứ tự input.
- Stream realtime lấy frame mới nhất, không tích backlog.
- Video/image đọc tuần tự, không drop frame.
- Lazy open để khởi tạo object không làm mở camera ngay.
