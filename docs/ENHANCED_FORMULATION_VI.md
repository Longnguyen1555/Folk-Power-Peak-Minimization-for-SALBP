# Mô hình bổ sung cho SALB3PM: staircase, Multiple/Incremental SAT, Gurobi

## 1. Kế thừa repo gốc

Dữ liệu `.3pm` giữ nguyên dạng `n m c`, sau đó `n` cặp `(d_j,w_j)`, tiếp theo là các cung trước–sau `i,j` (đánh số từ 1) kết thúc bằng `-1,-1`. Repo đã có sẵn SAT-SU, SAT-BS, STR, MaxSAT E/I, PBO E/I, CP-SAT và Gurobi đọc mô hình `.lp`. Cải tiến dùng model đầu vào và tính hợp lệ như gốc; không gỡ bỏ cấu hình có sẵn.

## 2. Bài toán và mục tiêu

Với mỗi công việc `j`, chọn trạm `K_j in {0,...,m-1}` và thời điểm bắt đầu `S_j in {0,...,c-d_j}`.

- Mỗi việc được xử lý tại một trạm, một thời điểm bắt đầu, liên tục trong `d_j` đơn vị.
- Trong mỗi đơn vị thời gian, mỗi trạm xử lý tối đa một việc.
- Cung `(i,j)` yêu cầu `K_i <= K_j`; nếu `K_i=K_j` thì `S_i+d_i <= S_j`.
- Định nghĩa `A_{j,t}=[S_j <= t < S_j+d_j]`, `P(t)=sum_j w_j A_{j,t}`.
- **Peak:** `min max_{t=0}^{c-1} P(t)`.
- **Total power (discrete integral):** `sum_t P(t) = sum_j d_j w_j`, hằng số. Cả `total_energy` và `total_power` chỉ gọi giải khả thi và báo đúng số này. Nếu muốn độ đo khác không hằng, cần đổi tên và định nghĩa rõ.
- `peak_then_total_power` giữ nghiệm tối ưu peak do mục tiêu thứ hai bất biến.
- **Độ đo mở rộng tùy chọn:** `station_peak_sum = sum_k max({w_j:K_j=k} ∪ {0})`, khác peak và khác total energy.

## 3. Staircase (order) encoding, với mốc và biên chính xác

- `Q_{j,k}` biểu diễn `K_j <= k`, với `k = 0,...,m-2`.
- `B_{j,t}` biểu diễn `S_j <= t`, với `t = 0,...,c-d_j-1`.
- Mệnh đề đơn điệu `¬Q_{j,k} ∨ Q_{j,k+1}`, `¬B_{j,t} ∨ B_{j,t+1}` tạo cầu thang.
- Quy ước biên: `B_{j,t}=false` nếu `t<0`, `B_{j,t}=true` nếu `t >= c-d_j`.
- Với mọi cung `i->j`, thêm `¬Q_{j,k} ∨ Q_{i,k}` để cấm trạm i sau trạm j.
- `A_{j,t} ↔ (B_{j,t} ∧ ¬B_{j,t-d_j})` (ba mệnh đề CNF, tối giản ở biên).
- Với hai việc i,j cùng trạm k, nếu j bắt đầu không muộn hơn t thì i phải bắt đầu không muộn hơn `t-d_i`; biểu diễn bằng `(K_i!=k) ∨ (K_j!=k) ∨ ¬B_{j,t} ∨ B_{i,t-d_i}`.
- Cấm trùng trạm và thời điểm: `(K_i!=k) ∨ (K_j!=k) ∨ ¬A_{i,t} ∨ ¬A_{j,t}`.
- Điều kiện `K_i!=k` là một hoặc hai literal Q (ở biên chỉ một), nên không cần biến one-hot X trong mô hình staircase. Pairwise baseline sử dụng one-hot cho trạm và start, thêm pairwise conflicts.

**Đúng đắn:** Chuỗi `Q`/`B` đơn điệu xác định duy nhất một nhãn trạm/start, kể cả khi không có ngưỡng nào true (chọn giá trị cuối). Liên kết A tương đương hoạt động thực tế tại mỗi slot. Do đó mỗi mô hình thỏa CNF giải mã thành lịch hợp lệ. Chiều ngược: lịch hợp lệ gán ngưỡng `Q`, `B` theo so sánh `<=` và gán `A` theo khoảng hoạt động, thỏa mọi mệnh đề. Hai encoding giữ cùng tập nghiệm lịch khi chiếu bỏ biến phụ.

## 4. Siết cận bằng PBEnc của PySAT

Với cận peak U tại mỗi slot t, tạo CNF cho pseudo-Boolean `sum_j w_j A_{j,t} <= U` qua `pysat.pb.PBEnc.atmost(..., encoding=EncType.binmerge)`. Các biến phụ được cấp ID không trùng với biến hiện có và trước đó. Nếu chưa cài PySAT, có fallback liệt kê minimal overweight subsets cho n<=12 để kiểm thử nhỏ (không dùng làm hiệu năng công bố). 

### Multiple SAT

Giải CNF khả thi lần đầu. Từ peak hiện tại `v`, khởi tạo bộ giải **mới** với `base_CNF AND (P(t) <= v-1 for all t)`. Nếu SAT thì ghi nhận lịch mới và lặp. Nếu UNSAT thì lịch incumbent được chứng minh tối ưu. Khi đã đạt `max_j w_j`, dừng nhờ cận dưới.

### Incremental SAT

Cũng siết chặt từ `v` xuống `v-1`, nhưng khởi tạo **một** solver và `add_clause(...)` vào chính solver đang sống. Giữ lại các PB constraints và các clause học được trong CDCL (nếu dùng PySAT). Kết thúc tương tự khi UNSAT. DPLL dự phòng có add_clause đúng ngữ nghĩa nhưng không giữ learned clauses, không dùng để chứng minh lợi thế runtime của incremental CDCL.

### Binary SAT

Giữ `[LB,UB]` với LB=`max_j w_j`, UB từ nghiệm hiện có. Với `mid=floor((LB+UB)/2)`: SAT với peak<=mid thì cập nhật UB bằng peak nghiệm mới; UNSAT thì LB=mid+1. Mỗi phép thử tái khởi tạo SAT backend. Khi LB=UB, tối ưu được chứng minh.

### Paper Cuts

Dựa ý tưởng Py et al. (2024): từ một thời điểm đạt peak hiện tại, trích tập việc cùng hoạt động với tổng công suất >= incumbent rồi cấm tập đó đồng thời hoạt động tại mọi slot. Lặp với solver hiện hành đến UNSAT.

## 5. MIP trực tiếp từ `.3pm` và RC2

- **Gurobi:** biến X nhị phân trạm, Y nhị phân thời điểm bắt đầu, biểu thức hoạt động A từ Y, biến peak nguyên. Ràng buộc đúng về assignment, trước–sau, nonoverlap và công suất mỗi slot. Mục tiêu peak / total_energy / station_peak_sum. Không cần mô hình `.lp` tạo ngoài. Trình giải gốc đọc `.lp` vẫn dùng được.
- **CP-SAT:** biến trạm và interval tùy chọn, `NoOverlap` trên mỗi trạm, reified precedence và activity; hỗ trợ cùng bộ metrics.
- **RC2 MaxSAT:** cứng = CNF khả thi staircase/pairwise + PB constraints, mềm = phủ định các ngưỡng peak unary; tổng soft-weight tối ưu bằng peak. Việc xuất WCNF E/I gốc được giữ nguyên.
- **PB OPB gốc:** `--objective total_power` tạo một biến cố định bằng 1 với hệ số `sum d_j w_j`. Bài toán tối ưu trở thành quyết định tính khả thi, đúng bản chất mục tiêu bất biến.

## 6. Kiểm thử và báo cáo thực nghiệm

- `tests/test_enhanced.py`: ví dụ công bố, enumeration brute force, tính tương đương hai encoding khi chiếu mô hình, bất biến năng lượng và optional backend tests.
- `tests/test_integration.py`: 12 DAG ngẫu nhiên kiểm tra peak tối ưu cho cả ba chiến lược SAT, kiểm tra tái khởi tạo solver, tính tương thích CLI từ các file upstream.
- `scripts/encoding_stats.py`: so sánh biến/mệnh đề **base feasibility CNF**, không trộn size PB objective và khác biệt chiến lược tìm kiếm.
- `scripts/experiment_matrix.py`: so sánh các methods với time limit cứng mỗi process, lấy peak, energy, thời gian, trạng thái; `OPTIMAL` chỉ khi có chứng chỉ từ solver chính xác.

**Lưu ý:** Các số smoke trong ZIP được chạy bằng DPLL fallback do thiếu PySAT/OR-Tools/Gurobi ở môi trường xây dựng. Chưa có benchmark chính thức lớn và không được so sánh thời gian đó với bảng paper gốc. Kích thước CNF/ số biến là số thật của code chạy, độc lập backend.
