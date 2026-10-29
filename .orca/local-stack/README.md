# Local stack: router 8081 + Qwen3.8 Q2_0 (DeepSeek ds41f removed 29/10/2026)

Bản lưu các file đang chạy trên máy này (27/10/2026) để không mất khi cài lại.
Chi tiết số đo và toàn bộ flag: [`../tok-speed-playbook.md`](../tok-speed-playbook.md).

```
app / opencode / web
        |
   router 8081  (model-router.py v1.2)
        |
   qwen 18080   (deepseek 8080 đã xoá ngày 29/10)
```

## File nào đi đâu

| File ở đây | Đích |
|---|---|
| `model-router.py` | `%LOCALAPPDATA%\strata-stack\model-router.py` |
| `run-router.bat` | `%LOCALAPPDATA%\strata-stack\run-router.bat` |
| `qwen.config.example.json` | `D:\GitHub\Strata\strata-q2_0-v144-refusal.json` — **điền `api_key`** |
| `ds41f.preset.json` | preset sống (`%LOCALAPPDATA%\Strata\launch\ds41f.json`) đã xoá 29/10 cùng DeepSeek; bản này chỉ còn lưu trữ |
| `opencode.example.json` | merge vào `~/.config/opencode/opencode.json` — **điền key cloud** |
| `pr4178-vision.patch` / `pr4193-launch-options.patch` | áp cho Terminal sau khi update (xem dưới) |

`api_key` trong hai file example là chỗ giữ (**không** commit key thật).

## Router 1.2 làm gì

- Model duy nhất: qwen (`qwen38-q2_0-refusal` + aliases). Request còn gọi
  `deepseek`/`ds41` nhận 404 `model_removed` (không âm thầm rơi sang engine khác).
- `POST /v1/load {"model": ..., "restart": true}`: bật lại engine sau khi sửa config
  (không còn DS để mà "đi nhờ" như trước).
- `/v1/models`: liệt kê qwen (+ aliases từ config).
- `/metrics`: lấy của backend đang chạy rồi **gộp danh sách model** để
  thanh chọn model trên web đọc đúng nguồn.
- `POST /v1/load {"model": ...}`: chạy switch ở nền, trả 202 ngay; trong lúc switch
  `/metrics` trả cache cũ kèm `models.switching` để web hiện "Switching to ...".
- `/health`, `/v1/status`: hợp nhất; khi đang switch trả trạng thái tạm.

## Cài / chạy

1. Copy `model-router.py` + `run-router.bat` vào `%LOCALAPPDATA%\strata-stack\`.
2. Tạo `strata-q2_0-v144-refusal.json` từ file example, điền `api_key` (hoặc để trống rồi
   dùng `--new-key` của Terminal).
3. `run-router.bat` (hoặc để `start-all.ps1` gọi qua `stack.env`: `STRATA_BAT=...run-router.bat`,
   `STRATA_PORT=8081`, `STRATA_URL=http://127.0.0.1:8081`).
4. Web: mở qua router, không mở thẳng 18080 (xem "Truy cập" dưới).

## Truy cập (giữ cả hai đường)

| Đường | URL | Ghi chú |
|---|---|---|
| **LAN (cùng mạng công ty)** | `http://172.16.14.244:8081` | **HTTP** (không phải https), đúng cổng **8081**. IP là DHCP — lease 2 giờ, có thể đổi sau reboot/renew. |
| **Tailscale** | `https://pc-dik-win.tail1b3f7b.ts.net:8443` | Ổn định; `tailscale serve` ánh xạ 8443 → 127.0.0.1:8081, chỉ nghe trên IP Tailscale `100.115.8.1`. |

- `:8443` **không** mở trên LAN (chỉ Tailscale). Đừng dùng `https://172.16.14.244:8443`.
- `:18080` (qwen trực tiếp) bị firewall chặn vì server chạy bằng `.venv\Scripts\python.exe`
  (rule hiện có chỉ cho `...\Python312\python.exe`). Luôn đi qua router 8081.
- Muốn IP LAN cố định: nhờ IT đặt **DHCP reservation** cho MAC này; đừng tự đặt static IP
  trên mạng công ty (dễ trùng IP / vi phạm policy). Địa chỉ ổn định để dùng là tên Tailscale.

`run-router.bat` đặt `STRATA_PREFILL_CPU_SHARE=0` — biến này phải nằm trong môi trường của
**server**, không phải chỉ trong config (config `"env"` chỉ tới engine).

## Cấu hình đang dùng (không commit vì có key)

- qwen: `--max-context 262144 --kv q4_0 --kv-resident 32768 --pcie-frac 0.00 --prefill auto
  --spec 4 --spec-min-p 0.7 --vram-reserve-mib 1472`, conversation cache 10 GB / 6 slot.
- qwen keys: `reasoning_effort: "low"`, `reasoning_budget_tokens: 12288`,
  `effort_position: "end"`, `models: []`.
- ~~DeepSeek: pack 1.75bpw, `--ssd-cache 36`, `--dspark auto`, `--max-context 262144`~~ — đã xoá 29/10.

## Terminal update làm mất patch vision

(Không còn hiệu lực từ 29/10: patch này chỉ để DeepSeek đọc ảnh, mà DeepSeek đã bị xoá.
Ghi lại để nếu cài lại DS41 làm đúng các bước dưới.)

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