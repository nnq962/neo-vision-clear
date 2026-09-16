# Neo Vision Clear UART Message Spec

Tài liệu này mô tả giao thức nhị phân để robot yêu cầu và nhận thông tin lối đi
từ Neo Vision Clear. Giao thức chỉ có hai message:

- `GET_CORRIDOR_INFO`: robot yêu cầu snapshot mới nhất.
- `CORRIDOR_INFO`: Vision trả trạng thái và số đo lối đi.

Định nghĩa Python tương ứng nằm trong `src/uart/messages.py`.

## 1. UART wire frame

Mọi message sử dụng cùng một frame:

```text
+------------+------------+----------------------+--------------------+
|    0xAA    |   length   |       payload        |      checksum      |
+------------+------------+----------------------+--------------------+
    1 byte       1 byte        N byte              2 byte, LE
```

| Thành phần | Kiểu | Ý nghĩa |
|---|---|---|
| `start_byte` | `uint8` | Luôn bằng `0xAA` |
| `length` | `uint8` | Số byte nằm sau trường này, bằng `len(payload) + 2` |
| `payload` | Tùy message | Byte đầu tiên luôn là `message_type` |
| `checksum` | `uint16`, little-endian | Checksum chỉ tính trên `payload` |

`start_byte` và `length` không tham gia checksum. Giá trị `length` tối đa là
255, do đó `payload + checksum` không được vượt quá 255 byte.

## 2. Byte order và checksum

Mọi số nhiều byte đều dùng little-endian.

Checksum giữ nguyên công thức của giao thức Robot Dispatch trước đây:

```python
checksum = binascii.crc32(payload) & 0xFFFF
```

Hai byte checksum được ghi bằng `uint16` little-endian:

```python
packet = payload + struct.pack("<H", checksum)
```

Khi checksum sai, bên nhận phải bỏ toàn bộ frame. Không được sử dụng một phần
dữ liệu từ frame lỗi.

## 3. Message type

| Giá trị | Tên | Hướng |
|---:|---|---|
| `0x10` | `GET_CORRIDOR_INFO` | Robot → Vision |
| `0x11` | `CORRIDOR_INFO` | Vision → Robot |

Các giá trị `0x00` đến `0x05` từng được dùng bởi giao thức Robot Dispatch cũ
và không được tái sử dụng trong phiên bản này.

## 4. GET_CORRIDOR_INFO

Robot gửi message này để yêu cầu snapshot lối đi mới nhất.

```python
struct.Struct("<BBH")
```

| Offset | Size | Field | Kiểu | Ý nghĩa |
|---:|---:|---|---|---|
| 0 | 1 | `message_type` | `uint8` | Luôn bằng `0x10` |
| 1 | 1 | `robot_id` | `uint8` | ID robot gửi yêu cầu |
| 2 | 2 | `request_id` | `uint16`, LE | ID dùng để đối chiếu response |

| Thành phần | Byte |
|---|---:|
| Start byte | 1 |
| Length | 1 |
| Payload | 4 |
| Checksum | 2 |
| Tổng UART frame | 8 |

Byte `length` luôn bằng `6`.

### Quy tắc request ID

- Mỗi robot tự cấp `request_id` từ `0` đến `65535`, sau đó quay vòng.
- Một robot chỉ nên có tối đa một request đang chờ response.
- Vision phải copy nguyên `robot_id` và `request_id` vào response.
- Gửi lại cùng request ID là an toàn vì thao tác đọc snapshot không tạo side effect.

Ví dụ:

```python
request = GetCorridorInfo(robot_id=3, request_id=120)
```

Payload trước checksum:

```text
10 03 78 00
```

## 5. CORRIDOR_INFO

Vision trả message này cho mỗi `GET_CORRIDOR_INFO` hợp lệ.

```python
struct.Struct("<BBHBBIHHiI")
```

| Offset | Size | Field | Kiểu | Ý nghĩa |
|---:|---:|---|---|---|
| 0 | 1 | `message_type` | `uint8` | Luôn bằng `0x11` |
| 1 | 1 | `robot_id` | `uint8` | Copy từ request |
| 2 | 2 | `request_id` | `uint16`, LE | Copy từ request |
| 4 | 1 | `status` | `uint8` | Trạng thái snapshot |
| 5 | 1 | `flags` | `uint8` | Cờ mô tả payload |
| 6 | 4 | `age_ms` | `uint32`, LE | Tuổi snapshot tính bằng millisecond |
| 10 | 2 | `maximum_passable_width_mm` | `uint16`, LE | Bề rộng lớn nhất có tuyến đi xuyên suốt |
| 12 | 2 | `walkway_width_mm` | `uint16`, LE | Tổng bề rộng lối đi tại BEV |
| 14 | 4 | `bottleneck_y_mm` | `int32`, LE | Tọa độ Y của nút thắt |
| 18 | 4 | `frame_index` | `uint32`, LE | Chỉ số frame tạo snapshot |

| Thành phần | Byte |
|---|---:|
| Start byte | 1 |
| Length | 1 |
| Payload | 22 |
| Checksum | 2 |
| Tổng UART frame | 26 |

Byte `length` luôn bằng `24`.

## 6. Corridor status

| Giá trị | Tên | Có thể dùng để điều khiển robot? |
|---:|---|---|
| `0` | `OK` | Có |
| `1` | `WARMING_UP` | Không; runtime chưa có snapshot đầu tiên |
| `2` | `STALE` | Không; snapshot đã quá cũ |
| `3` | `ERROR` | Không; runtime hoặc camera đang lỗi |

Robot chỉ được xem kết quả là dữ liệu điều khiển hợp lệ khi:

```text
status == OK && (flags & DATA_AVAILABLE) != 0
```

`STALE` và `ERROR` có thể kèm snapshot cuối để chẩn đoán, nhưng robot không nên
dùng snapshot đó làm căn cứ tiếp tục di chuyển.

## 7. Flags

| Bit | Tên | Ý nghĩa |
|---:|---|---|
| 0 | `DATA_AVAILABLE` | Các trường số đo chứa một snapshot |
| 1–7 | Reserved | Phải gửi bằng 0 |

Giá trị hiện được hỗ trợ:

```text
0x00 = không có snapshot
0x01 = có snapshot
```

| Status | `DATA_AVAILABLE` |
|---|---:|
| `OK` | Bắt buộc bằng 1 |
| `WARMING_UP` | Bắt buộc bằng 0 |
| `STALE` | Bắt buộc bằng 1 |
| `ERROR` | Có thể bằng 0 hoặc 1 |

## 8. Quy ước khi không có dữ liệu

Khi `DATA_AVAILABLE=0`, response phải sử dụng đúng các giá trị sau:

| Field | Giá trị |
|---|---:|
| `age_ms` | `0xFFFFFFFF` |
| `maximum_passable_width_mm` | `0` |
| `walkway_width_mm` | `0` |
| `bottleneck_y_mm` | `0` |
| `frame_index` | `0` |

Không được suy luận rằng độ rộng bằng 0 là phép đo thật khi
`DATA_AVAILABLE=0`.

## 9. Đơn vị và chuyển đổi

Backend lưu số đo theo mét dạng số thực. Khi tạo message, Vision chuyển sang
millimeter bằng cách làm tròn:

```python
millimeters = round(meters * 1000)
```

| Field | Miền biểu diễn |
|---|---|
| Các field độ rộng `uint16` | `0` đến `65.535 m` |
| `bottleneck_y_mm` kiểu `int32` | Khoảng `-2147 km` đến `+2147 km` |

`bottleneck_y_mm` dùng số có dấu vì gốc tọa độ thực có thể không nằm tại đầu
lối đi. Nếu giá trị không nằm trong miền kiểu dữ liệu, Vision phải trả trạng
thái `ERROR` thay vì để số bị tràn.

## 10. Ánh xạ với Neo Vision Clear

| Message field | Nguồn backend |
|---|---|
| `status` | `SnapshotRead.status` |
| `age_ms` | `SnapshotRead.age_ms` |
| `maximum_passable_width_mm` | `CorridorSnapshot.maximum_passable_width_meters × 1000` |
| `walkway_width_mm` | `CorridorSnapshot.walkway_width_meters × 1000` |
| `bottleneck_y_mm` | `CorridorSnapshot.bottleneck_y_meters × 1000` |
| `frame_index` | `CorridorSnapshot.frame_index` |

`bottleneck_free_x_ranges_meters` và `captured_at` không được gửi qua UART để
giữ response nhỏ và có kích thước cố định. Nếu tương lai robot cần các khoảng
trống chi tiết, phải thêm message type mới thay vì thay đổi binary layout của
`CORRIDOR_INFO`.

## 11. Request-response và retry

```text
Robot                                      Vision
  │                                           │
  ├── GET_CORRIDOR_INFO(robot=3, req=120) ───►│
  │                                           │ đọc snapshot mới nhất
  │◄── CORRIDOR_INFO(robot=3, req=120) ───────┤
  │                                           │
```

Không sử dụng ACK riêng. `CORRIDOR_INFO` chính là xác nhận ở tầng ứng dụng.

Khuyến nghị phía robot:

1. Gửi request và chờ từ 200 đến 500 ms.
2. Chỉ nhận response có đúng `robot_id` và `request_id` đang chờ.
3. Nếu timeout, checksum sai hoặc response không khớp, gửi lại cùng request ID.
4. Thử tối đa 2 đến 3 lần.
5. Nếu vẫn không có response hợp lệ, xem Vision là unavailable và chuyển sang
   trạng thái an toàn.

Vision không cần cache response. Khi nhận request lặp, Vision trả snapshot mới
nhất tại thời điểm xử lý request đó.

## 12. Nhiều robot và môi trường truyền

`robot_id` giúp định tuyến response và `request_id` giúp đối chiếu request,
nhưng protocol không tự giải quyết xung đột vật lý khi nhiều thiết bị cùng phát.

- UART point-to-point hoặc gateway đã serialize packet: không cần cơ chế bổ sung.
- RS-485 nhiều node: cần master polling hoặc token/arbitration riêng.
- LoRa: gateway cần chuyển nguyên frame và bảo đảm response tới đúng robot.

## 13. Quy tắc tương thích

- Không đổi layout của một message type đã phát hành.
- Khi cần thêm hoặc thay field, tạo message type mới.
- Reserved flag phải gửi bằng 0 và bên nhận phải từ chối flag chưa biết.
- Byte đầu payload luôn là `message_type`.
- Frame sai length, checksum hoặc kích thước payload phải bị bỏ.
- Robot không được dùng dữ liệu khi status khác `OK`.
