# Neo Vision Clear — Tổng quan kỹ thuật và cơ sở phát triển business logic

Ngày cập nhật: 28/09/2026.

Tài liệu mô tả mã nguồn hiện tại, bao gồm cấu trúc output WebSocket mới của Aggregator. Các hướng phát triển cuối tài liệu là đề xuất nghiên cứu, chưa được triển khai. Cấu hình và phiên bản container thực tế có thể khác mã nguồn trong workspace.

## 1. Mục tiêu và kiến trúc

**Neo Vision Clear là hệ thống dùng camera cố định để ước lượng mức chiếm dụng của hành lang, rồi tổng hợp thành quyết định cho phép hoặc chưa cho phép đi qua.** Phương pháp hiện tại kết hợp depth tương đối, baseline cảnh trống và phép chiếu hình học xuống mặt phẳng hành lang.

| Thành phần | Chức năng |
|---|---|
| Backend trên Jetson | Đọc camera, chạy Depth Anything V2, so sánh baseline, tính số đo từng đoạn |
| Frontend | Quản lý camera, calibration, điều khiển detection, xem video và overlay |
| MediaMTX | Trung chuyển video RTSP sang WebRTC cho trình duyệt |
| Aggregator | Gom kết quả nhiều camera/Jetson, áp quy tắc hành lang, gửi kết luận tới WS server |

Luồng dữ liệu phân tích:

```text
Camera → Backend Jetson → Số đo từng camera
                              ↓
                          Aggregator
                              ↓
                  Quyết định cho cả hành lang
                              ↓
                          WS server
```

Video trực tiếp đi qua MediaMTX; kết quả phân tích đi qua WebSocket. Hai luồng này được xử lý riêng.

Backend dùng Python và FastAPI; frontend dùng Next.js, React và shadcn/ui. Frontend production được xuất tĩnh và phục vụ bằng Nginx, đồng thời proxy API và WebSocket sang backend. Backend Docker được thiết kế cho Jetson ARM64 chạy JetPack 5.1.6.

## 2. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa |
|---|---|
| `zone_code` | Mã của **cả hành lang** trên hệ thống nhận, ví dụ `ZONE_A` |
| `camera_id` | Camera cung cấp số đo |
| `source_id` / `source` | Jetson quản lý camera |
| `order` | Thứ tự vị trí camera trong cấu hình hành lang |
| ROI | Vùng hành lang được chọn trên ảnh camera |
| Zone nội bộ | Một đoạn nhỏ của ROI sau khi chiếu sang BEV |
| `blocked_zones: [2]` | Zone có index 2 của camera đó bị chặn; không có nghĩa là có hai zone bị chặn |

Một hành lang có thể được giám sát bởi nhiều camera; mỗi camera có nhiều zone nội bộ. Nếu cả zone 1 và zone 2 bị chặn thì `blocked_zones` là `[1, 2]`.

Hiện tại Aggregator dùng ánh xạ camera → hành lang và thứ tự vị trí. Nó chưa ghép các camera thành một bản đồ hình học chung hoặc xử lý trùng vùng quan sát giữa camera.

## 3. Calibration: học trạng thái hành lang trống

Camera phải cố định. Người vận hành chọn ROI bốn góc và khai báo tọa độ thực tương ứng, đơn vị mét.

Khi hành lang trống, hệ thống thu nhiều frame và chạy Depth Anything V2 trên **toàn bộ ảnh** để tạo các depth map.

Depth Anything V2 trả về **depth tương đối**. Giá trị này không trực tiếp cho biết vật cách camera bao nhiêu mét, và thang giá trị có thể thay đổi giữa các frame.

Vì vậy, hệ thống căn chỉnh các depth map theo:

```text
depth_căn_chỉnh = scale × depth_hiện_tại + shift
```

Sau hai lượt căn chỉnh, hệ thống xây dựng:

- `reference_depth`: median depth tại từng pixel, đại diện cảnh trống.
- `noise_map`: mức dao động depth bình thường tại từng pixel.

Trong code, noise được tính bằng:

```text
noise_map = 1.4826 × median(|depth_đã_căn_chỉnh − reference_depth|)
```

Baseline còn lưu ROI, tọa độ thực, độ phân giải và thông tin model để dùng lại khi detection. Các artifact gồm dữ liệu NPZ, metadata JSON, ảnh preview và ảnh depth.

ROI không được dùng để crop ảnh đầu vào model trong bước calibration. Nó được lưu cùng baseline để phục vụ phân tích ở bước detection.

## 4. Detection: xác định vùng thay đổi gần camera hơn

Với mỗi frame mới, hệ thống:

1. Resize ảnh về kích thước baseline và chạy model.
2. Căn chỉnh depth hiện tại với baseline bằng robust alignment trên ROI.
3. Làm mượt depth.
4. So sánh với baseline để phát hiện vùng gần camera hơn cảnh trống.
5. Làm sạch mask bằng morphology, cắt về ROI và loại các vùng quá nhỏ.

Robust alignment ưu tiên nhóm pixel khớp baseline nhất, nhằm giảm ảnh hưởng của vật cản lên phép căn chỉnh.

Ngưỡng phát hiện được đặt theo từng pixel:

```text
threshold = max(
    minimum_difference,
    noise_multiplier × noise_map / depth_span
)
```

`depth_span` là khoảng chênh giữa percentile 95 và 5 của depth baseline trong vùng kiểm tra. Sai khác depth được chuẩn hóa theo cùng giá trị này trước khi so sánh với ngưỡng.

Ý nghĩa thực tế: pixel vốn dao động nhiều cần có thay đổi lớn hơn mới được xem là vật cản.

Hệ thống mở rộng ROI bằng một lớp padding để có thêm ngữ cảnh khi so sánh và làm sạch mask. Mask cuối cùng được cắt lại về ROI trước khi đo.

Đầu ra bước này là **mask vùng thay đổi depth**. Hệ thống hiện chưa phân loại đó là người, xe đẩy, thùng hàng hay loại vật thể nào khác.

## 5. BEV: chuyển sang mặt phẳng để đo

Hệ thống dùng bốn cặp điểm ảnh–tọa độ thực để tính homography, sau đó chiếu mask sang BEV — góc nhìn từ trên xuống của mặt phẳng hành lang.

BEV được raster hóa với mật độ mặc định **100 pixel/mét**. Đây là độ phân giải lưới tính toán; không có nghĩa hệ thống đạt độ chính xác đo thực tế 1 cm.

Nguồn của đơn vị mét/cm là **tọa độ thực được khai báo khi calibration**, không phải depth metric từ model. Baseline thiếu tọa độ thực phù hợp sẽ bị từ chối khi phân tích metric.

Một giới hạn quan trọng: homography đúng với các điểm trên mặt phẳng đã hiệu chuẩn. Khi chiếu toàn bộ silhouette của người hoặc vật cao xuống mặt phẳng này, hình chiếu có thể bị kéo giãn hoặc lệch so với diện tích tiếp xúc sàn thực tế. Vì vậy, số đo hiện tại nên được hiểu là **ước lượng mức chiếm dụng từ mask đã chiếu**.

## 6. Phép đo chính: tỷ lệ chiếm dụng từng đoạn

Các hàng hợp lệ của ROI trên BEV được chia thành `zone_count` nhóm theo trục Y. Mặc định là 10 đoạn.

Với một zone:

```text
occupancy_ratio = số pixel vật cản / số pixel ROI

free_ratio = 1 − occupancy_ratio
```

Ví dụ zone có 10.000 pixel ROI, trong đó 5.600 pixel là vật cản:

```text
occupancy_ratio = 0.56 = 56%
```

Hệ thống cũng quy đổi diện tích thành bề rộng trung bình:

```text
walkway_width = số pixel ROI / số hàng / pixels_per_meter

occupied_width = số pixel vật cản / số hàng / pixels_per_meter

free_width = walkway_width − occupied_width
```

Các bề rộng trong công thức có đơn vị mét. Các giá trị gửi tới Aggregator được đổi sang cm.

Ví dụ:

| Số đo | Giá trị |
|---|---:|
| Bề rộng hành lang trung bình | 200 cm |
| Tỷ lệ chiếm dụng | 56% |
| Bề rộng chiếm dụng tương đương | 112 cm |
| Bề rộng trống tương đương | 88 cm |

**`free_width_cm = 88` không đảm bảo có một khe trống liên tục rộng 88 cm để robot đi qua.** Khoảng trống có thể bị chia thành nhiều phần hoặc đổi vị trí theo chiều dài zone.

## 7. Phép đo tuyến trống liên thông vẫn có trong code

Ngoài tỷ lệ chiếm dụng, backend còn tính:

- `maximum_passable_width_meters`.
- Vị trí nút thắt.
- Các khoảng X còn trống tại nút thắt.

Thuật toán thử các bề rộng footprint, thu hẹp vùng tâm có thể đi và kiểm tra có thành phần liên thông nối cạnh vào với cạnh ra hay không. Nó dùng tìm kiếm nhị phân để tìm bề rộng lớn nhất thỏa điều kiện.

Phép đo này hiện vẫn được tính nhưng **không dùng để quyết định `pass/blocked` gửi lên Aggregator**. Payload camera → Aggregator hiện tập trung vào số đo theo zone.

Đây là nền tảng có thể nghiên cứu thêm cho nghiệp vụ “robot cụ thể có đi qua được không”. Tuy nhiên, thuật toán hiện chưa mô hình hóa đầy đủ chiều dài robot, bán kính quay hoặc chuyển động của vật cản.

## 8. Business logic hiện tại

Backend áp ngưỡng của backend để đánh dấu camera. Aggregator nhận tỷ lệ chiếm dụng và **tự tính lại bằng ngưỡng của Aggregator**.

Điều kiện chặn một zone:

```text
occupancy_ratio >= occupancy_threshold_ratio
```

Ngưỡng mặc định là 40%. Riêng file cấu hình Aggregator trong workspace tại thời điểm viết tài liệu đang đặt **60%**; giá trị thực tế phụ thuộc cấu hình service đang chạy.

Quy tắc cả hành lang:

| Điều kiện | Trạng thái |
|---|---|
| Có ít nhất một zone hợp lệ đạt/vượt ngưỡng | `blocked` |
| Chưa có bằng chứng bị chặn, nhưng có camera thiếu/lỗi/quá hạn dữ liệu | `unknown` |
| Mọi camera có dữ liệu hợp lệ, mọi zone dưới ngưỡng | `pass` |

`blocked` được ưu tiên nếu đồng thời có camera khác không khả dụng. Vì vậy, `blocked_areas` và `unavailable_cameras` có thể cùng có phần tử.

Ví dụ với ngưỡng 40%: camera có hai zone, zone 1 chiếm dụng 18%, zone 2 chiếm dụng 56%. Kết quả camera có `blocked_zones: [2]`, và toàn hành lang được kết luận `blocked` dù các camera khác vẫn thông.

Hiện chưa có bộ lọc theo thời gian hoặc hysteresis cho quyết định chiếm dụng. Một frame vượt ngưỡng có thể làm trạng thái đổi ngay; frame tiếp theo xuống dưới ngưỡng có thể làm nó đổi lại.

## 9. Dữ liệu mới/cũ và cơ chế truyền

Aggregator giữ kết quả gần nhất của từng camera trong bộ nhớ:

- Camera chưa gửi dữ liệu: `missing`.
- Dữ liệu quá hạn: `stale`.
- Camera đang khởi tạo hoặc lỗi: không đủ dữ liệu để xác nhận thông.

Ngưỡng stale mặc định là **3 giây**, tính từ thời điểm Aggregator nhận message. Có tác vụ kiểm tra mỗi khoảng 0,5 giây để cập nhật khi dữ liệu hết hạn, kể cả không nhận thêm message mới.

Hai điểm cần lưu ý khi nghiên cứu độ trễ:

- `observed_at` hiện được tạo từ timestamp lúc detector hoàn tất phân tích; chưa phải timestamp phơi sáng gốc của camera.
- Tuổi dữ liệu tại Aggregator dựa trên thời điểm nhận, nên chưa đo được đầy đủ độ trễ camera → decode → inference → mạng.

Hàng đợi outbound ưu tiên kết quả mới nhất và tự reconnect. Đây là luồng cập nhật trạng thái, chưa phải cơ chế lưu lịch sử đầy đủ hay xác nhận ứng dụng phía nhận đã xử lý message.

Backend chỉ khởi tạo các service khi API khởi động. Detection được bật bằng thao tác start runtime riêng; khởi động lại backend không tự khôi phục chạy detection theo luồng hiện tại.

## 10. Output gửi tới WS server

Mỗi message outbound là JSON text với envelope `event` / `data`:

```json
{
  "event": "camera_report_zone",
  "data": {
    "zone_code": "ZONE_A",
    "is_blocked": false,
    "schema_version": 2,
    "corridor_id": "corridor-01",
    "corridor_name": "Hành lang tầng 1",
    "state": "pass",
    "can_pass": true,
    "occupancy_threshold_ratio": 0.4,
    "blocked_areas": [],
    "unavailable_cameras": [],
    "decided_at": "2026-09-28T08:30:12Z"
  }
}
```

Ánh xạ cho bên nhận:

| `state` | `is_blocked` | Ý nghĩa |
|---|---|---|
| `pass` | `false` | Đủ dữ liệu và đạt điều kiện thông |
| `blocked` | `true` | Có zone vượt ngưỡng |
| `unknown` | `true` | Chưa đủ dữ liệu để cho phép đi |

Vì vậy, `is_blocked` mang ý nghĩa nghiệp vụ **“hiện chưa cho phép đi qua”**. Muốn biết do vật cản hay do thiếu dữ liệu thì đọc thêm `state`.

Khi `unknown`, `can_pass` bị bỏ khỏi JSON outbound. Khi `pass`, payload hiện không chứa số đo chi tiết của tất cả camera; chi tiết camera bị chặn nằm trong `blocked_areas`.

Ví dụ đầy đủ khi bị chặn, với ngưỡng minh họa 40%:

```json
{
  "event": "camera_report_zone",
  "data": {
    "zone_code": "ZONE_A",
    "is_blocked": true,
    "schema_version": 2,
    "corridor_id": "corridor-01",
    "corridor_name": "Hành lang tầng 1",
    "state": "blocked",
    "can_pass": false,
    "occupancy_threshold_ratio": 0.4,
    "blocked_areas": [
      {
        "order": 1,
        "location_name": "Đầu hành lang",
        "camera_id": "camera-01",
        "camera_name": "Camera 1",
        "blocked_zones": [2],
        "zone_count": 2,
        "zones": [
          {
            "index": 1,
            "occupancy_ratio": 0.18,
            "walkway_width_cm": 200,
            "occupied_width_cm": 36,
            "free_width_cm": 164,
            "blocked": false
          },
          {
            "index": 2,
            "occupancy_ratio": 0.56,
            "walkway_width_cm": 200,
            "occupied_width_cm": 112,
            "free_width_cm": 88,
            "blocked": true
          }
        ],
        "maximum_occupancy_ratio": 0.56,
        "occupancy_threshold_ratio": 0.4,
        "reason": "occupancy_threshold_exceeded",
        "source": "jetson-a",
        "observed_at": "2026-09-28T08:30:12.450Z"
      }
    ],
    "unavailable_cameras": [],
    "decided_at": "2026-09-28T08:30:12.470Z"
  }
}
```

`zone_code` được cấu hình tại `corridor.zone_code` hoặc qua dashboard Aggregator. Cấu hình cũ chưa có trường này dùng mặc định `ZONE_A`.

`GET /api/decision` vẫn trả quyết định trực tiếp. Trường `last_payload` của `GET /api/outbound` hiển thị envelope đã gửi. Các trường có giá trị null được loại khỏi JSON outbound.

## 11. Những giới hạn ảnh hưởng trực tiếp đến business logic

| Giới hạn | Hệ quả cần đánh giá |
|---|---|
| Camera dịch chuyển hoặc đổi góc nhìn | Baseline và phép chiếu có thể không còn phù hợp |
| Depth tương đối và nhiễu dự đoán | Mask có thể thay đổi dù vật cản không thay đổi tương ứng |
| Vật cao bị chiếu xuống mặt phẳng sàn | Diện tích chiếm dụng có thể khác footprint thực |
| Tỷ lệ được lấy trung bình trong mỗi zone | Vật cản ngắn nhưng chắn ngang toàn chiều rộng có thể bị pha loãng bởi phần còn trống |
| Không xét tính liên thông trong quyết định hiện tại | Tỷ lệ trống cao chưa đảm bảo tồn tại đường đi |
| Không có bộ lọc thời gian | Trạng thái có thể dao động quanh ngưỡng |
| Không nhận dạng hoặc tracking vật thể | Chưa phân biệt vật tĩnh, người đang đi qua hoặc vật đang tiến tới |
| Chưa hợp nhất hình học giữa camera | Camera chồng lấn hoặc vùng khuất chưa được xử lý như bản đồ chung |

`zone_count` cũng là một tham số nghiệp vụ đáng chú ý: cùng một vật cản, chia zone dài hay ngắn có thể tạo tỷ lệ chiếm dụng khác nhau, từ đó thay đổi kết luận.

## 12. Hướng nghiên cứu tiếp theo

Phần này là đề xuất phát triển, chưa phải hành vi đã triển khai.

Nên tách logic thành ba lớp:

| Lớp | Câu hỏi cần trả lời |
|---|---|
| Chất lượng dữ liệu | Camera và số đo hiện có đủ tin cậy không? |
| Hình học đường đi | Có tuyến đi liên tục phù hợp với kích thước robot không? |
| Chính sách vận hành | Khi nào dừng, đi chậm, chờ xác nhận hoặc cho đi lại? |

Các hướng đáng thử:

- **Ổn định theo thời gian:** yêu cầu trạng thái kéo dài một khoảng thời gian; dùng ngưỡng vào/ra khác nhau để giảm dao động.
- **Theo kích thước robot:** kết hợp bề rộng tuyến liên thông với kích thước robot và khoảng đệm.
- **Phân biệt nguyên nhân:** giữ riêng `obstacle_blocked`, `sensor_unavailable`, `calibration_invalid` thay vì chỉ một boolean.
- **Theo vị trí và chiều di chuyển:** xét vùng robot sắp đi tới, khoảng cách tới vật cản và tuyến nhiệm vụ.
- **Đánh giá chất lượng calibration:** phát hiện camera bị lệch, vùng ảnh bị che hoặc baseline không còn phù hợp.
- **Lưu lịch sử nghiên cứu:** ghi số đo từng zone, cấu hình ngưỡng, trạng thái, timestamp và nhãn thực tế để so sánh các policy.

Để đánh giá policy mới, nên đo ít nhất:

- Tỷ lệ bỏ sót vật cản.
- Tỷ lệ báo chặn sai.
- Độ trễ phát hiện.
- Thời gian cho đi lại sau khi vật cản rời đi.
- Số lần trạng thái dao động trong một khoảng thời gian.

Các kết quả này cần lấy từ thử nghiệm thực tế; bộ test phần mềm hiện tại chưa chứng minh độ chính xác đo lường ngoài hiện trường.

## 13. Mã nguồn tham chiếu

Các đường dẫn dưới đây tính từ thư mục gốc repository:

| Nội dung | File |
|---|---|
| Tạo baseline | `backend/src/walkway_monitor/calibration/baseline_builder.py` |
| Căn chỉnh depth | `backend/src/walkway_monitor/depth/alignment.py` |
| Phát hiện vùng thay đổi depth | `backend/src/walkway_monitor/detection/detector.py` |
| Phép chiếu BEV | `backend/src/walkway_monitor/detection/bev.py` |
| Đo chiếm dụng và tuyến liên thông | `backend/src/walkway_monitor/detection/components.py` |
| Điều phối runtime | `backend/src/server/services/monitor.py` |
| Payload camera gửi Aggregator | `backend/src/server/models/aggregator.py` |
| Quyết định tổng hợp hành lang | `aggregator/src/neo_vision_clear_aggregator/registry.py` |
| Schema quyết định và envelope WS | `aggregator/src/neo_vision_clear_aggregator/models.py` |
| Gửi JSON tới WS server | `aggregator/src/neo_vision_clear_aggregator/outbound.py` |
| Cấu hình Aggregator | `aggregator/config/config.json` |
| Triển khai container | `docker-compose.yml` |
