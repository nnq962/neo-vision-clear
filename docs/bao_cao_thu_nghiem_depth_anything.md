# Báo cáo thử nghiệm nhận diện vật cản trên lối đi

## 1. Mục tiêu

Mục tiêu của thử nghiệm là xây dựng phương án phát hiện sự xuất hiện của vật cản trong một
vùng lối đi được xác định trước. Hệ thống cần có khả năng nhận diện nhiều loại vật thể khác
nhau, kể cả những vật chưa xuất hiện trong dữ liệu huấn luyện, đồng thời hạn chế cảnh báo sai
do thay đổi của môi trường.

## 2. Các phương án đã thử nghiệm

### 2.1. Nhận diện vật thể bằng YOLO

Phương án đầu tiên là sử dụng mô hình object detection YOLO. Mô hình có thể phát hiện tốt
các lớp vật thể đã biết và cho phép xác định vị trí của chúng trong lối đi.

Tuy nhiên, phương án này phụ thuộc vào các lớp đối tượng có trong tập dữ liệu huấn luyện.
Khi xuất hiện một vật thể chưa được định nghĩa hoặc chưa từng được fine-tune trong dataset,
mô hình có thể không nhận diện được. Vì mục tiêu của bài toán là phát hiện bất kỳ vật cản
nào trên lối đi, YOLO chưa bao quát được toàn bộ trường hợp thực tế.

### 2.2. Đánh giá bằng sai khác hình ảnh

Phương án tiếp theo là tạo ảnh baseline khi lối đi trống, sau đó so sánh ảnh hiện tại với
baseline để tìm vùng thay đổi.

Cách làm này đơn giản nhưng rất nhạy với điều kiện ánh sáng. Những thay đổi như vệt nắng,
bóng đổ hoặc độ sáng của camera có thể tạo ra sai khác lớn dù không có vật cản. Ví dụ,
baseline không có vệt nắng nhưng ảnh thực tế xuất hiện vệt nắng thì hệ thống vẫn có thể
đánh giá nhầm đó là vật cản. Do đó, phương pháp so sánh trực tiếp hình ảnh tạo ra nhiều
nhiễu và cảnh báo không cần thiết.

### 2.3. Ước lượng độ sâu bằng Depth Anything V2

Phương án hiện tại sử dụng Depth Anything V2 để tạo bản đồ độ sâu tương đối của khung hình.
Hệ thống thu một baseline depth khi lối đi trống, sau đó so sánh depth của từng frame mới
với baseline trong vùng ROI đã chọn.

Kết quả thử nghiệm bước đầu cho thấy phương pháp này có khả năng phát hiện vật thể mà không
cần biết trước lớp của vật. So với việc so sánh trực tiếp ảnh RGB, thông tin độ sâu cũng ít
phụ thuộc hơn vào những thay đổi màu sắc và độ sáng thông thường. Các bước lọc không gian,
lọc theo thời gian và loại nhiễu ở biên ROI tiếp tục được áp dụng để ổn định vùng phát hiện.

Depth Anything V2 vẫn tạo ra relative depth thay vì khoảng cách tuyệt đối và có thể dao động
giữa các frame. Vì vậy, hệ thống cần căn chỉnh depth với baseline và tiếp tục tinh chỉnh
ngưỡng trên dữ liệu thực tế.

## 3. Phương án được lựa chọn

Sau các thử nghiệm ban đầu, phương án sử dụng Depth Anything V2 được lựa chọn để tiếp tục
phát triển. Lý do chính là phương án này không phụ thuộc vào danh sách lớp vật thể cố định,
có khả năng bao quát tốt hơn các vật cản chưa biết và cho kết quả bước đầu ổn định hơn so
với phương pháp sai khác ảnh RGB.

Trong giai đoạn tiếp theo, hệ thống sẽ được thử nghiệm thêm với nhiều kích thước vật thể,
điều kiện ánh sáng và thời gian vật đứng yên khác nhau. Các ngưỡng depth, diện tích vùng thay
đổi và bộ lọc theo thời gian sẽ được tinh chỉnh trước khi đưa ra kết luận về khả năng triển
khai thực tế.

## 4. Kết luận

Depth Anything V2 hiện là hướng tiếp cận phù hợp nhất trong các phương án đã thử. Kết quả
hiện tại mới ở mức thử nghiệm và chưa phải kết luận cuối cùng, nhưng đủ tích cực để tiếp tục
đánh giá và phát triển giải pháp nhận diện vật cản trên lối đi theo hướng sử dụng thông tin
độ sâu.
