# Qwen3.8 Q2_0: vì sao "40-60 tok/s mà vẫn chậm" (đo 27/10/2026)

Máy: RTX 3060 12 GB, i7-14700K, engine 0.1.51, pack q2_0, config
`strata-q2_0-v144-refusal.json` (262,144 ctx, KV q4_0, kv-resident 32K,
spec 4 + MTP, conversation cache 10 GB / 6 slot, reasoning budget 22,288).

## Cách đo
- Log server thật: 5,426 request (`strata-q2_0-v144-refusal.log`).
- Test riêng: prompt 3.5K → 65K token (cold), rồi nối thêm delta ở context 83K.

## Số đo
Decode (sinh token) — 5,201 request có >=50 token sinh ra:
- median **52.0 tok/s**, p10 43.7, max 90, min 20.2
- 9 request <30 tok/s (đó là lúc VRAM căng)
→ Con số 40-60 tok/s của bạn là đúng, và đây gần như **giới hạn của 3060 12 GB**
(GPU 100%, 160 W khi chạy).

Prefill (đọc prompt) — đo riêng:
| prompt | kiểu | thời gian | tok/s |
|---|---|---|---|
| 3.5K | cold | 5.2 s | 689 |
| 13.7K | cold | 13.8 s | 997 |
| 27.4K | cold | 27.9 s | 983 |
| 54.7K | cold | 55.3 s | 989 |
| 82.5K | cold | 103.7 s | 796 |
| +2K delta @83K | cache hit | 5.3 s | ~380 |
| +5.8K delta @83K | cache hit | 11.0 s | ~530 |

Từ log thật (request >=64K context):
- **4,695 request chạy ở context >=64K, trung bình 141,711 token**.
- Prefill chunk lớn: ~900 tok/s (median 909 khi cold >=50K; 616-911 khi có cache).
- **91 request cache miss hoàn toàn** (reused=0): TB 116,780 token → **129 s chỉ để đọc prompt**;
  50 request >120 s. Top chậm nhất: 342 s (165K prompt, 189 s prefill + 7,728 token sinh ra 153 s).
- 132 request prefill >60 s; 333 request sinh >2K token; 103 >4K; 3 request chạm 12,288 token (≈4 phút).
- Phân bố tổng thời gian 1 request ở context >=64K: p50 9.3 s, p90 36 s, p95 66 s.
- 33 cảnh báo VRAM: chỉ còn 992-1,016 MiB trống (ngưỡng engine là 1,024).

## Nguyên nhân, xếp theo mức ảnh hưởng
1. **Context quá lớn (120-200K token/phiên).** Mỗi turn agent thêm trung bình ~12-13K token
   (tool output, file đọc, diff) → 12-15 s prefill; resume/khôi phục phiên mà mất cache KV
   = prefill lại 116K token ≈ **2 phút trước chữ đầu tiên**. Đây là chi phí lớn nhất.
2. **Mất cache KV khi restart / đổi model.** Router đổi qwen↔ds = engine khởi động lại
   (35-50 s) + cache trống → request đầu tiên trả giá prefill toàn bộ context (2-4 phút).
   91 lần cache miss trong log là loại này.
3. **Thinking token.** `reasoning_budget_tokens = 22,288`; 3 request đã sinh 12,288 token
   liên tục ≈ 4 phút không hiện ra cho người dùng. Trung bình 1 request sinh 366 token,
   nhưng 333 request >2K và 103 >4K token.
4. **VRAM sát trần.** Chỉ 992 MiB trống → engine tự cảnh báo có thể page ra RAM;
   9 request decode tụt <30 tok/s (min 20.2).
5. **Nhỏ:** chunk prefill <1024 token chạy CPU share (~110 tok/s thay vì ~800) → mỗi request
   ngắn tốn thêm ~0.3-1.5 s; switch model 35-50 s.

## Việc nên làm (ước tính)
1. **Giữ context <32K**: session mới cho mỗi task, `/compact` thường xuyên.
   Cold prefill 32K ≈ 32 s thay vì 129-180 s; turn sau nhanh gấp 3-5 lần.
   Đây là mức cải thiện lớn nhất, không cần đổi phần cứng.
2. **Không đổi model giữa chừng**: mỗi session một model. Đổi model = 35-50 s + prefill lại
   2-4 phút. Đừng để webchat Qwen mở song song với opencode dùng DS.
3. **Hạ thinking budget**: 22,288 → 4,096-6,144 (`reasoning_budget_tokens` trong config).
   Step khó giảm từ tối đa 4-7 phút xuống 1-2 phút.
4. **Thêm `--vram-reserve-mib 1472`** (engine tự khuyến nghị) để tránh paging.
5. **`STRATA_PREFILL_CPU_SHARE=0`** (đặt trong môi trường server) cho prompt ngắn;
   đo lại kỳ vọng 110 → 500-900 tok/s. Không ảnh hưởng chunk lớn.
6. **Đọc file có chọn lọc** (grep/range thay vì dump cả file): mỗi 10K token tool output
   ở context 140K tốn thêm ~11-16 s prefill.

## Kết luận
40-60 tok/s là **decode**, đã sát giới hạn GPU. Chỗ chậm thật nằm ở **prefill của context
khổng lồ + thinking + mất cache khi switch/restart**, không phải tốc độ sinh token.
Với phiên 140K: 1 turn trung bình 9 s nhưng p90 36 s; resume phiên = 2-4 phút.
## Đã áp dụng (27/10/2026)
- `--vram-reserve-mib` 1408 -> **1472** (`strata-q2_0-v144-refusal.json`, backup `.bak-20261027`):
  VRAM trống khi load 992 -> **1,250 MiB**, hết cảnh báo "below 1024 MiB".
- **`STRATA_PREFILL_CPU_SHARE=0`** trong `run-router.bat` (router + engine con thừa hưởng;
  áp cho cả qwen và ds41f): dòng "prefill: the CPU share is ON" không còn trong log khởi động;
  prompt ngắn 57-64 token: 1.3-1.6 s -> **0.86-1.13 s**.
- **Router 1.1** (`model-router.py`, backup `.bak-20261027`):
  - `/metrics` gộp danh sách model của backend với DeepSeek -> web hiện
    `qwen38-q2_0-refusal`, `ornith-1.5-35b-ice-23g`, `deepseek-v4.1-flash`.
  - `POST /v1/load` chạy switch ở nền, trả 202 ngay; trong lúc switch `/metrics` trả cache
    cũ kèm `models.switching` để web hiện "Switching to ...".
  - `/v1/status`, `/health` cũng được hợp nhất (health của ds: `images: true`).
  - Đo: chuyển qwen -> ds **35 s**, ds -> qwen **30 s** (cold start, bình thường).
- **Opencode**: thêm `C:/Users/ADMIN/.config/opencode/local-speed.md` vào `instructions`
  (grep/range, lọc output, không đọc lại file, compact khi >32K, không switch model giữa phiên).

## Effort audit (27/10/2026) - harness nào gửi gì xuống server
Đo bằng proxy 8082 ghi lại body thật của từng harness:

| Harness | Field gửi xuống | Kết quả |
|---|---|---|
| **opencode** (local-strata, mặc định) | **không gửi gì** (reasoning_effort=null) | server dùng mặc định **xhigh** -> thinking tối đa |
| opencode sau khi thêm `"reasoning": true` + `"options": {"reasoningEffort": "low"}` | `reasoning_effort: "low"` | dung, server nhan **low** |
| **Claude Code** (`--effort low`) | `output_config: {"effort": "low"}` + `thinking: {"type":"adaptive"}` | dung, server nhan **low** |
| **Web Strata** | `reasoning_effort: settings.thinking` (mac dinh **high = xhigh**) | dung; phai chon low/medium trong menu Thinking |
| **App desktop (Harness)** | `chat_template_kwargs: {enable_thinking, reasoning_effort}` | dung (code profile.mjs) |

Ket qua do voi cung 1 bai (magic square 3x3):
- xhigh: 648 token thinking
- low: 109-900 token (dao dong manh; "low" chi la 1 cau trong prompt, khong phai cap)
- low + `reasoning_budget_tokens: 512`: dung 124 token -> **budget moi la cap cung**

Da doi:
- `reasoning_budget_tokens`: 22,288 -> **12,288** (config qwen; log xac nhan "thinking budget: 12288 tokens")
- them `reasoning_effort: "low"` vao config qwen lam mac dinh cho request khong gui effort
  (request nao tu gui thi van uu tien gia tri cua no)
- opencode: qwen model co `reasoning: true` + `options.reasoningEffort = low`
- Luu y: Claude Code tro vao router voi ten model `claude-*` se bi router mac dinh chuyen sang
  **DeepSeek** (pick() khong thay "qwen"), khong phai qwen.

## Ornith da xoa (27/10/2026)
- Xoa `D:\GitHub\Strata-data\models\Ornith\` (2 GGUF, **41.97 GB**), pack `ornith-ice23`, config
  `strata-ornith-ice23.json` va log. Config qwen: `models: []`.
- Web picker con: `qwen38-q2_0-refusal`, `deepseek-v4.1-flash` (da kiem tra /metrics sau restart).
- O cung sau khi xoa: **C: 110.9 GB free, D: 182.3 GB free** (truoc do D: 140.4 GB).
- Backup config truoc khi sua: `strata-q2_0-v144-refusal.json.bak-before-ornith-removal`.

## Reading / TTFT (27/10/2026)
Do bang streaming, prompt ~12.9K token, cung cau hoi:

| Truong hop | First reasoning | First answer | Ghi chu |
|---|---|---|---|
| Cold (prefix moi) | **11.6 s** | 12.6 s | prefill ~1,110 tok/s + ~1 s thinking |
| Cung prompt, cache hit | 0.16 s | 1.0 s | chi con thinking |
| Doi effort xhigh -> low | **0.59 s** (truoc: 11.5 s) | 1.3 s | nho `effort_position: end` |
| Bat/tat thinking | 0.28 s | 0.23 s | prefix khong doi -> cache giu |
| opencode session moi #1 (sau restart) | - | 13.6 s | 13,131 token doc cold |
| opencode session moi #2 | - | 0.63 s | 13,083/13,131 reused |

Da ap dung:
- `effort_position: "end"` (config qwen): doi effort/thinking giua phien khong con doc lai
  toan bo prompt (11.5 s -> 0.2-0.6 s).
- Thu `--prefill auto:16384`: engine tu chon 8960, toc do 930/997 tok/s (khong hon 8192),
  lai khong bit-exact -> **da revert ve `auto`**.

Gioi han phan cung: prefill 930-1,100 tok/s, GPU 100% o 160W (power limit 170W, max 187W).
RTX 5070 12GB trong docs dat 1,290 tok/s voi cung Q2_0 -> 3060 khong con nhieu du dia.
Cold 13K ~ 12-13 s la gia phai tra khi engine vua start/switch model; cac turn sau 0.2-0.6 s.
