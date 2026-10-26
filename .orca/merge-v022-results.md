# Merge v0.2.2 → windows-coding (22/10/2026)

## Trạng thái

- **Merge hoàn tất chưa build/test** — máy đang dùng, build + gate + restart serve chờ user rảnh.
- Commit merge: **`8f4564b8`** `Merge tag 'v0.2.2' into windows-coding`.
- Trước đó commit `a1740668`: fix 1 dòng `app.css` (thanh Conversation cache cách nhãn 8px) lúc trước chưa commit.
- Đầu nhánh: `git describe` = `v0.2.2-64-g8f4564b8` (tag v0.2.2 + 64 commit fork).
- Working tree sạch, chỉ `.orca\*` + `code-strata.bat.bak-20261016` untracked (cố ý).
- Upstream: release **0.2.2 = engine 0.1.47** (297 commit, 400 file, +37 703/−1 355 so với v0.2.1).
- Conflict thực tế **ít hơn dự đoán**: dự đoán 13 file chỉ còn **4 file, 11 hunk**.

## Giải 4 conflict (quyết định từng hunk)

### serve/web/app.css (1 hunk)
- Đơn giản: bên fork đã có sẵn `main { ... min-width: 0; }` + chú thích = chính fix #2971 của upstream. Giữ fork.

### serve/frontend.py (2 hunk)
- Signature `OutputParser.__init__`: union `aliases` (fork, MCP `server__tool` → tên thật) + `recover` + `declared_only` (upstream #804/#3075).
- Body `__init__`: giữ cả hai — `self.aliases` của fork và `self.declared_only / self._alias / self.unread` của upstream. Hai cơ chế dùng chỗ khác nhau (fork áp ở dòng 1148/1547, upstream ở `_callable`/`_loose_open`), không đè nhau.

### src/kernels/cuda/iq_kernels.cu (2 hunk) — lại đúng vùng bảng của lần merge trước (+268/−14 fork vs +323/−39 upstream)
- `kStageIqGrid`= union: giữ `TY == 19` (IQ1_S của fork) + thêm `kTqType<TY>` (trellis 144/145/146) của upstream.
- `IqGridWords::value`: union — `(22||29||19) ? 2048 : (17||21||kTqType) ? 1024 : (16||18) ? 512 : 4`.
- Không đụng `native_expert.cpp`, `native_expert_parity.cpp` (upstream không đụng gần phần trim fork).

### serve/server.py (6 hunk)
- `run`/_`run_cjk`/_`run`: union tham số — `aliases` (fork) + `force` + `declared_only` (upstream). `_run_cjk` pass cả `declared_only` xuống `_run`.
- `OutputParser(...)` trong `_run`: truyền cả `aliases=` lẫn `declared_only=declared_only`.
- `run_with_mcp` inner: `svc.run(..., aliases, declared_only=True)` (kết hợp cả hai).
- `anthropic_events`: giữ cơ cấu fork (`run=None` để truyền event source run_with_mcp — **MCP trên /v1/messages vẫn là tính năng riêng của fork**, upstream 0.2.2 chỉ có MCP trên route OpenAI) + thêm `declared_only=True` vào nhánh fallback `svc.run` như upstream.
- Route Responses (7490) giữ nguyên `svc.run(...)` không `declared_only` — đúng chủ ý upstream ("Codex's compaction request relies on it").

## Kiểm chứng sau giải

- 0 conflict marker còn lại; `py_compile` sạch cho `server.py, frontend.py, test_server.py, test_mcp.py`.
- Grep còn sống: `queued_counted` 5 (cancel-drop), `fit_max_tokens` 14, `terminal_events` 3, `mcp_aliases` 3, `_run_cjk` 2, `declared_only` 9, `STRATA_TQ_SUB8` 2 (off-switch trellis của upstream).

## Gate sau merge v0.2.2 — ĐÃ CHẠY (22/10, serve dừng lúc build + VERIFY, đã restart)

- **Build**: 170 bước vào `build-wc` (`native_expert_parity`, `iq_parity`, `strata-q36`, `strata`) —
  chỉ warning C4458 (q36_engine.cu, thường gặp); log `.orca\build-v022-log.txt`.
  `strata.exe --version` → **strata 0.1.47**.
- **`iq_parity`** 11 fixtures: **0 failures** — dequant 0.00e+00 toàn bộ, gồm IQ1_S (19) và Q3_K (11);
  mmvq ncols 1..8 trong hạn.
- **`native_expert_parity`**: `--synthetic q4_K/q5_1` ok (cpu 1.37e-02 / gpu 1.25e-02, decode-once vs
  per-entry bitwise — khớp số pre-merge); `--q2k-trim iq2_xxs/q2_K + q4_K/q2_K` ok (212 B,
  dequant 0/1638400 bit lệch); `--q4_1-pair` ok (0/7680 giá trị lệch, dequant 0/4915200 bit).
  Đổi cú pháp nhỏ: `--synthetic` nhận MỘT token `gu/dn` với dấu `/` (`--synthetic q4_K/q5_1`);
  chạy kiểu `q4_K q5_1` rời sẽ báo "not a pair" — không phải lỗi merge.
- **`strata-q36` VERIFY trên Ornith-122B** (`STRATA_Q36_VERIFY=1`, 12 prompt id cũ, n=64, kv q8_0,
  ctx 4096, mtp 0): 899 tensors layout OK, 5.08 GiB/3.3 s, 21/256 slots, **18432 comparisons,
  0 mismatches** — khớp từng chữ số baseline; cold decode 4.1 t/s (pre-merge 4.0).
  Log `.orca\verify-v022-log.txt`.
- **Serve đã restart** (detached, Start-Process cmd, window minimized): engine PID 11688, :18080
  `/metrics` → **version 0.1.47**; smoke chat 57 tokens OK, MTP draft nhận 6/7, Tailscale
  `pc-dik-win...:8443` → HTTP 200.

## Còn treo (tùy user)

- Push `windows-coding` lên origin (merge commits + fix CSS) — chưa được duyệt.
- Perf A/B 122B (`strata bench run` hoặc lặp n=128 giống lần trước) — chưa đo; v0.2.2 sửa 4 lỗi bench.
- Thay đổi đáng chú ý v0.2.2 đã vào cây (xem phần trước): GPU roles, trellis Arc/Mac/NVIDIA, API key
  tuỳ chọn, NUMA (Linux 2 socket), một định nghĩa tốc độ, tool-call mở sai, retry NaN, v.v.

## Thay đổi đáng chú ý trong v0.2.2 (đã vào trong cây)

- Vai trò GPU Main/Helper/Off (`--gpu-roles`, Terminal/app/setup/Docker). Card ≤8 GB mặc định Off.
- Trellis (Gyro) trên Intel Arc + Mac metal; NVIDIA decode nhanh hơn (RTX 3060: Gyro-S +17%, Gyro-M +11%, câu trả lời bit-for-bit) — không đổi mô hình Q2_0/Q2_K của mình.
- Model hơi thiếu VRAM tự hạ context/chunk/reserve. API key tuỳ chọn (`--no-api-key`).
- NUMA pool chia socket (Linux 2 socket; máy 1 node chạy y hệt 0.2.1). `--pool-cores` thí nghiệm.
- Một định nghĩa tốc độ (mọi token ÷ thời gian decode) — footer/monitor/API số sẽ đổi nghĩa.
- Tool call mở sai vẫn nhận; request không khai tools không bao giờ trả `tool_calls` (trừ route Responses).
- Sửa chữ nan retry, spec hang HIP + prompt 1 token, bench run, download integrity, tuning lặp, v.v.
