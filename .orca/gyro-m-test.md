# Test Gyro-M (TQ2_0) — kết quả đầy đủ (2026-10-22)

## Tải
- `gyro-dl.py` (ThreadPoolExecutor + Range resume) xong, byte-count chuẩn:
  `Qwen3.8-Flash-Next-Gyro-M-TQ2_0.gguf` = 91,965,774,272 B (85.65 GiB); `mtp-...-draft.gguf` = 2,697,439,648 B (2.51 GiB).
  Ở `models\Qwen3.8-Flash-Next-Gyro-GGUF\`. PLE (320,001,536 rows) nằm sẵn trong file — không cần --ple-gguf.

## Pack riêng (bắt buộc)
- Pack `q2_0` bị từ chối: `ArenaExpertSource: ... is TQ2_T, the pack says type 42` → pack theo model.
- Tạo: `python tools/iq_pack.py --gguf <Gyro-M.gguf> --out D:\GitHub\Strata-data\packs\gyro-m --compat-bf16`
  - `--base packs\q2_0` FAIL: pack cũ thiếu `manifest.json` (khung mới của tool) → dùng standalone.
  - Không `--compat-bf16` FAIL: 363 tensor `hc_*` (hyper-connection) lưu Q8_0, engine cần BF16 → tool làm tròn (max |err| 0.0144).
  - Kết quả: dense.bin 1.485 GB, index.txt 1079 tensors (303 native), arena 1.38 GiB, hadamard.txt 48 lớp, tokenizer tự xuất từ GGUF (vocab 248320, pre qwen35).
- `strata-gyro-m.json`: `--pack packs\gyro-m`, `tokenizer` = pack gyro-m.

## Chuỗi nguyên nhân "chết im lặng" khi boot (đã dùng hết để chẩn đoán)
1. **VRAM contention boot đôi**: khi q2_0 engine còn giữ VRAM mà gyro engine load → LiveKernelEvent **141 (TDR)** 10:49:32 → chỉ boot một engine mỗi lần.
2. **Commit limit**: pagefile C: 40 GiB cài cứng, peak 40,942/40,959 MB; mode 92 GB model cần headroom → **đã tạo `D:\pagefile.sys` 96 GiB (98304 MB)** qua `.orca\set-pagefile.ps1` (Set-WmiInstance, UAC) + reboot → limit 87.7 → 167.7 GiB. Giữ nguyên — phục vụ model lớn.
3. **Nguyên nhân chất thật (cả 3 boot đầu chết vì cái này)**: pack native (IQ) **bắt buộc `--spec T>=2` + `--prefill`** ("it needs --native SHARD1, --spec T (T >= 2) and --prefill CHUNK" — kernel i-quant multi-token); Verifier init là bắt buộc ở serve mode và cần bảng residency từ `--expert-profile` (khác: generate.cpp:8831 `vh.d_res = thits.d_res`, chỉ fill khi `!profile.empty()`; verify.cpp:706 reject khi `hits.d_res == nullptr`); caller in `strata serve: verify: needs the profile-filled VRAM expert tier...` rồi `return 1` (generate.cpp:9044) — dòng dòng đó trong log CHÍNH LÀ lỗi chết, không phải note.
   - Thử bỏ `--spec`/`--mtp` để chạy plain → KHÔNG được (pack native yêu cầu spec >= 2).

## Fix hoạt động
- Khôi phục `--spec 4 --spec-min-p 0.7 --mtp D:\GitHub\Strata-data\mtp\rt` + thêm `--expert-profile D:\GitHub\Strata\data\expert-profile.bin`.
- **Profile tái dùng được giữa các quant cùng base model** (router giống nhau; các config AB gia đình unc48L q4_1/q5_1 cũng vậy) → q2_0 profile ăn trên Gyro-M.
- Pattern cộng đồng: `--expert-profile <file>` trỏ vào chính file `--expert-profile-save` + `--expert-profile-save-every 10` = vòng tự học.
- Config: `expert_profile_save` = `expert-profile-learned-gyro-m.bin` (KHÔNG trỏ file learned q2_0 cho gyro — tránh ghi đè profile serve chính); hiện chưa file nào được ghi (chưa đủ 10 request trong một boot).
- Boot test: chạy `server.py` trực tiếp với Start-Process + RedirectStandardOutput/Err vào `.orca\gyro-serve-out.txt` / `-err.txt` (bat thường không bắt stdout của server.py).

## Số đo A/B (engine 0.1.47, cùng máy, cùng prompt story n=256)
- **Gyro-M** (85.65 GB 1 file, pack gyro-m, profile q2_0): steady decode **33.2 tok/s** (2 window cùng 33.2; draft accept 73%/56%), wall **9.1 s / 256 tok ≈ 28 tok/s**; prefill prompt mới 62.1 tok/s.
- **Serve chính q2_0** (62 GB 2 shard): steady **40.1 / 49.4 tok/s** (draft accept 70%/65%), wall **8.1 s / 256 tok ≈ 32 tok/s**; prefill prompt mới 50.9 tok/s.
- → Trên máy này **q2_0 serve NHANH HƠN Gyro-M** (~+17% đến +49%各 window; wall +14%). Claim "+11%" của upstream Gyro-M không tái hiện ở setup serve này (có thể họ đo với profile học theo gyro / điều kiện khác).
- Lưu ý các prompt ngắn n=64 đo tay: 27.4–38.7 tok/s (variance lớn).

## Trạng thái sau test
- Serve chính: relaunch detached `run-q2_0-v144-refusal.bat` (18080 LISTEN, metrics có 0.1.47, Tailscale 8443 qua ts.net HTTP 200 — test phải qua tên **ts.net**, không phải 127.0.0.1).
- **MCP gateway 8090/8096 không tự chạy lại sau reboot** (python elevated do user khởi động) — user cần bật lại thủ công nếu cần tool MCP (chat vẫn tốt không gateway).
- Gyro-M test serve đã tắt sạch; reboot giữ nguyên ứng dụng.
- Pagefile: C: 24576/40960 (giữ nguyên) + D: 98304/98304 (mới).
- D free sau test: ~275 GiB (pagefile D chiếm 96 GiB; models vẫn giữ unc48L đã dọn trước đó).

## Cleanup options (nếu user muốn)
- `models\Qwen3.8-Flash-Next-Gyro-GGUF\` (88.1 GiB) + `packs\gyro-m` (~1.5 GB) + `_parts` rác — nếu không dùng tiếp Gyro-M.
- `.orca\curl-parts.ps1` + manager cũ đã lỗi thời.
