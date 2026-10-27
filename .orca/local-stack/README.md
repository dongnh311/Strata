# Local stack: router 8081 + Qwen3.8 Q2_0 + DeepSeek V4.1 1.75bpw

Bản lưu các file đang chạy trên máy này (27/10/2026) để không mất khi cài lại.
Chi tiết số đo và toàn bộ flag: [`../tok-speed-playbook.md`](../tok-speed-playbook.md).

```
app / opencode / web
        |
   router 8081  (model-router.py)
     |        |
 qwen 18080  deepseek 8080   (chỉ một cái chạy tại một thời điểm)
```

## File nào đi đâu

| File ở đây | Đích |
|---|---|
| `model-router.py` | `%LOCALAPPDATA%\strata-stack\model-router.py` |
| `run-router.bat` | `%LOCALAPPDATA%\strata-stack\run-router.bat` |
| `qwen.config.example.json` | `D:\GitHub\Strata\strata-q2_0-v144-refusal.json` — **điền `api_key`** |
| `ds41f.preset.json` | `%LOCALAPPDATA%\Strata\launch\ds41f.json` (Terminal tự tạo lại khi `strata launch`) |
| `opencode.example.json` | merge vào `~/.config/opencode/opencode.json` — **điền key cloud** |
| `pr4178-vision.patch` / `pr4193-launch-options.patch` | áp cho Terminal sau khi update (xem dưới) |

`api_key` trong hai file example là chỗ giữ (**không** commit key thật).

## Router 1.1 làm gì

- `model` của request chứa `deepseek`/`ds41` → DeepSeek 8080; chứa `qwen`/`ornith` → qwen 18080;
  còn lại mặc định DeepSeek.
- Trước khi bật model này, **dừng model kia** (một engine chiếm 12 GB).
- `/v1/models`: liệt kê cả hai.
- `/metrics`: lấy của backend đang chạy rồi **gộp danh sách model** (qwen + DeepSeek) để
  thanh chọn model trên web thấy cả hai.
- `POST /v1/load {"model": ...}`: chạy switch ở nền, trả 202 ngay; trong lúc switch
  `/metrics` trả cache cũ kèm `models.switching` để web hiện "Switching to ...".
- `/health`, `/v1/status`: hợp nhất; khi đang switch trả trạng thái tạm.

## Cài / chạy

1. Copy `model-router.py` + `run-router.bat` vào `%LOCALAPPDATA%\strata-stack\`.
2. Tạo `strata-q2_0-v144-refusal.json` từ file example, điền `api_key` (hoặc để trống rồi
   dùng `--new-key` của Terminal).
3. `run-router.bat` (hoặc để `start-all.ps1` gọi qua `stack.env`: `STRATA_BAT=...run-router.bat`,
   `STRATA_PORT=8081`, `STRATA_URL=http://127.0.0.1:8081`).
4. Web: mở qua router (ví dụ `https://pc-dik-win.tail1b3f7b.ts.net:8443` → 8081), không mở
   thẳng 18080, nếu muốn thấy DeepSeek trong picker.

`run-router.bat` đặt `STRATA_PREFILL_CPU_SHARE=0` — biến này phải nằm trong môi trường của
**server**, không phải chỉ trong config (config `"env"` chỉ tới engine).

## Cấu hình đang dùng (không commit vì có key)

- qwen: `--max-context 262144 --kv q4_0 --kv-resident 32768 --pcie-frac 0.00 --prefill auto
  --spec 4 --spec-min-p 0.7 --vram-reserve-mib 1472`, conversation cache 10 GB / 6 slot.
- qwen keys: `reasoning_effort: "low"`, `reasoning_budget_tokens: 12288`,
  `effort_position: "end"`, `models: []`.
- DeepSeek: pack 1.75bpw, `--ssd-cache 36`, `--dspark auto`, `--max-context 262144`.

## Terminal update làm mất patch vision

Terminal 0.1.51 đã được patch `serve/server.py` + `serve/dsv41_vision.py` (+ `setup.py`) để
DeepSeek đọc ảnh. Update Terminal sẽ ghi đè. Cách làm lại:

1. Backup `terminal\<ver>\serve\server.py`.
2. Copy `serve/dsv41_vision.py` từ repo này vào `terminal\<ver>\serve\`.
3. Áp `pr4178-vision.patch` cho `serve/server.py` (patch -p1) — **đừng** copy thẳng
   `serve/server.py` của repo nếu repo đang có thay đổi riêng của fork.
4. `setup.py` cũng cần patch để tải `mmproj-BF16.gguf` khi build pack.

## Report

- [`../tok-speed-playbook.md`](../tok-speed-playbook.md) — tốc độ, flag, config, biến môi trường,
  những gì đã thử và loại.
- [`../qwen-slow-report.md`](../qwen-slow-report.md) — prefill/TTFT, audit effort của harness.
- [`../deepseek-prod.md`](../deepseek-prod.md) — cấu hình DeepSeek local.