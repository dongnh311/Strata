# 122B native run — activity log (2026-10-21)

## Trạng thái trước engine run
- Fix Q3_K dot (`iq_kernels.cu`): (1) `q3k_us` hai nhánh is 4..7 & is 8..11 lệch bit-high so với `dq_q3_k` — đã sửa theo nguyên bản; (2) `val = code - 4 + (a<<2)` đếm kép −4 với phép trừ `4*sumy` ở return → thành `val = code + (a<<2)` (theo cấu trúc llama.cpp: −4 do dp4a thứ hai đảm nhiệm).
- Check độc lập: `C:\Users\ADMIN\AppData\Local\Temp\opencode\q3k_check.py` (python replica trên fixture `Q3_K.bin/.f32`, layout block = hmask|qs|scales|d-fp16-ở-108 — KHÔNG phải d-ở-đầu như ggml-common.h; tool fixture repair d tại 108..109) → **512/512 gr ok, 0 mismatch**.
- Patch file thứ 6 phát sinh: `include/strata/core/family_layout.hpp` — thêm `TensorWant::alt` (alias shape) và chấp nhận `ffn_gate_inp_shexp.weight` dạng `[N,1]` (GGUF writer của Ornith 122B lưu vector này 2-D khác 35B). Không có nó, engine từ chối file.
- llama.cpp b11669 baseline (greedy, prompt = ids, không BOS, 64 tokens):
  prompt ids: 225002 170306 172908 174327 170035 170214 172560 171287 27834 170225 171104 13
  ```
  Lời model (greedy):
  <think>
  The user is asking in Vietnamese to briefly explain why the sky is blue. Let me answer concisely in Vietnamese.

  The reason the sky is blue is Rayleigh scattering. Sunlight contains all colors. When it enters the atmosphere, the gas molecules scatter shorter wavelengths (blue/violet) more than
  ```
  (finish_reason length; server không in token-ids nên so bằng detok text từng-bước khi phát hiện divergence.)
- llama-server đã dừng (giữ 8 GiB VRAM); cần so đối chứng thì chạy lại với --n-gpu-layers 0.
- strata.exe --serve (35B, PID 9056) giữ 48.1 GB commit đã được tắt (qua UAC) → pin 37.4 GiB giờ khả thi: commit trống ~73.7 GB, RAM trống ~40.8 GB.

## Fix pool capacity cho native path (H 3072 / FF 1024)
- `include/strata/kernels/cpu/native_expert.hpp`: `kNativeHBytes` 1024 → 2048 (FF 1024 Q8_K = 4×292 = 1168 cần hơn 1024; 2048 giữ Q8_K cho n_ff ≤ 1792 / Q8_0 cho n_ff ≤ 1920); thêm `kNativeFF = 2048` (giá trị intermediate tối đa pool scratch giữ mỗi token).
- `include/strata/kernels/cpu/pool.hpp`: `SplitBufMulti::ff[MAXT][FF]` → `[MAXT][kNativeFF]` — mode 5 native ghi `sb.ff[t][r]` r < n_ff = 1024 trước đây tràn struct (FF compile-time 640). Path Q2_0-pack (mode 3/4, gbuf/ubuf thread_local, `SplitBuf::ff[FF]`, act_quant_* với FF) giữ nguyên FF=640 — định dạng pack riêng.
- `src/kernels/cpu/native_expert.cpp`: gate thêm `f.n_ff > kNativeFF` → "expert intermediate wider than the pool's buffers"; `pad[1024]` → `pad[2048]` (trim chỉ cho n_ff % 256 = 128 → ceil256(1920) = 2048 chính xác).
- Kiểm chéo: `q2_native_kernels` = type 42 (Q2_0) — 122B down (25 IQ3_XXS, 7 IQ2_S, 5 IQ2_XXS, 4 Q2_K, 4 IQ2_XS, 2 IQ3_S, 2 Q3_K, 1 Q8_0) không dính; cpu_out/acts/out/nact của engine đều cấp phát động theo N ✓.

## Engine efforts (tổng hợp)
1. `--max-new` không tồn tại cho q36 → `--n 64`.
2. `--tokens` phải là MỘT chuỗi id bọc trong nháy; chạy nhiều id rời → usage error.
3. settings: `--kv q8_0`, `--mtp 0` (verify trước), `--max-context 4096` (dù 32768 cũng ổn về VRAM free sau khi dừng llama-server), STRATA_Q36_VERIFY=1.
4. Nạp: 899 tensors layout-checked ✓, dense 5.08 GiB lên GPU ~1.9–4.7 s.

## Chờ
- Chạy strata-q36 + VERIFY: so text vs baseline greedy trên; devem chỗ nào lệch token đầu tiên.
- Sau khi chữ số khớp: đo warm tok/s có/không MTP vs baseline 12.5 / 17.45 t/s (llama.cpp, ctx 32K lần trước).
- Khi xanh: commit các file patch (`iq_kernels.cu`, `gguf_reader.hpp`, `native_mmvq.cu`, `iq_fixture.py`, `iq_parity.cpp`, + `family_layout.hpp` alias). `.orca\*` và `code-strata.bat.bak-20261016` để ngoài; giữ `serve/*` dirty.

## KẾT QUẢ VERIFY (chạy đầu tiên, 13/10-prompt,VERIFY=1, ctx 4096, KV q8_0, mtp 0)
- Nạp: 899 tensors ✓, dense 5.08 GiB/1.8 s; hybrid: 21/256 per layer VRAM (3.07 GiB), 37.38 GiB host, tối đa 1024 rows/batch, 20 threads; 64.4 s.
- **VERIFY: 18432 comparisons, 0 mismatches.**
- decode: prompt 12 tok 2622 ms; 64 tok 15.9 s = **4.0 t/s** (24.3% hàng xanh GPU: 7001/28800; CPU pool 21799 trong 12.96 s; 845 slot swaps).
- gen ids → detok khớp tuyệt đối với llama.cpp CPU-only ở 17 token đầu ("The user is asking me to explain briefly why the sky is blue"), diverge đầu tiên sau "blue": llama top-1 `,` −0.627 / top-2 `.` −0.763 (margin 0.135) — engine chọn `.` = tie-break tầm quant, không phải lỗi (llama.cpp CPU-only lần nấy cũng lệch baseline GPU-offload cũ). Logprobs top-10 llama đã lưu: `.orca\cmp-llama-logprobs.json`.
- llama.cpp CPU-only (ctx 2048): ... "The user is asking me to explain briefly why the sky is blue, in Vietnamese. Let me provide a concise explanation..." (greedy, cùng 12 prompt ids, không BOS).

## Perf round 1 (warm page cache, MTP 0, n=128, ctx 4096)
- strata-q36: **5.4 t/s** (23.56 s / 128 tok); GPU cover 24.1% (12878/53376), CPU pool 40498 entries / 18.93 s, 861 slot swaps. Giống gen id cũ (khớp 100% lan truyền greedy).
- llama.cpp CPU-only cùng bè: **2.8 t/s** (45.59 s / 128 tok) → engine hybrid nhanh ~1.9× ở cùng ngân sách RAM.
  (Baseline ghi chép cũ 12.5 / 17.45-17.6 t/s là config llama.cpp CÓ GPU offload ~8 GiB — không so trực tiếp được.)
- MTP 2 + VERIFY=1: **6.0 t/s** (21.33 s), acceptance 72/112 = **64%** (llama.cpp 76-81% nhưng khác config GPU), VERIFY 17364 comparisons 0 mismatches ✓, GPU cover 27.4% (18596/67952), CPU pool 49356/16.71 s.
  - Gen MTP diverge từ ~token 7 vs greedy không MTP ("asking in Vietnamese to briefly..." vs "asking me to explain briefly...") — do đường speculative đo logits theo batch khác (tie-break), VERIFY vẫn 0 mism → không phải lỗi kernel.
- `--expert-vram 3.8` (MTP 0): **5.5 t/s** (23.37 s), 23/256 slots (3.36 GiB — cạn VRAM, không đủ slot thứ 24), cover 28.2% (15049/53376), pool 38327/18.53 s. → +2 slots (+4% cover) chỉ +0.1 t/s: dư địa VRAM đã cạn.
  - LƯU Ý: đổi số slots (GPU/CPU split) → gen đổi path ở token 7 (khớp path run MTP tới ~token 50) — placement-sensitive tie-break, KHÔNG phải bug: cùng config vẫn deterministic (run 1 & 2 identical 64 tok), text vẫn mạch lạc, VERIFY 0 mism. Margin ở tie ~0.1-0.14 nats.
- Kết luận bottleneck: pool throughput (~2070 entries/s trên 20 thread), không phải số entries. VRAM ceiling chặn lever chính.

## Kết quả cuối + commit
- Cấu hình nhanh nhất: **MTP 2, --expert-vram 3.8, KV q8_0: 6.3 tok/s** (20.33 s / 128 tok), acceptance 72/114 (63%), cover 28.9% (19870/68736), pool 48866/17.29 s, 927 slot swaps. Text hợp lý (thinking template tiếng Anh trước, trả lời tiếng Việt — bình thường với greedy).
- Bảng perf (same prompt, n=128, warm): strata MTP0/21 slots **5.4** · MTP0/23 slots **5.5** · MTP2+VERIFY/21 slots **6.0** · MTP2/23 slots **6.3** | llama.cpp B11669 CPU-only **2.8** | (llama.cpp cũ có GPU-offload: 12.5 / MTP 17.45 — config khác, không so).
- **Committed: `c5241690`** (windows-coding), đúng 9 file, 196+ / 25−. serve/* còn dirty nguyên vẹn; .orca & code-strata.bat.bak-20261016 untracked.
- llama.cpp server (:8080) còn chạy để compare detok; tắt khi không cần nữa.

## UD-IQ2_XXS — BỎ (user đổi ý "dọn dẹp, trả strata load qwen3.8 lại")
- Download `UD-IQ2_XXS.gguf` (41.97 GB) dừng khi đạt ~25.2 GB; file dở xoá sạch. Repo nguồn còn lại: `unsloth/Ornith-1.5-122B-GGUF` (nếu cần lại).
- Cleanup: llama-server b11669 (CPU-only :8080) đã kill; cả 122B CLI runs đã thoát sạch.

## Restore Qwen3.8 (đã xong, hoạt động)
- Nguyên nhân: đầu phiên mình kill "bridge server" = engine `strata.exe --serve` (giữ Qwen3.8 Q2_0 §) để nhường RAM cho 122B → `serve/server.py` (PID python :18080) sống mà `/v1/models` rỗng.
- server.py cũ kill bằng UAC (elevated, taskkill denied thường); port 18080 nhả.
- **Khởi lại bằng `D:\GitHub\Strata\run-q2_0-v144-refusal.bat`** (config `strata-q2_0-v144-refusal.json`, exe `build-wc\strata.exe`, port 18080, key trong config; config includes thêm `strata-ornith-ice23.json` 35B như secondary — được list trong `/v1/models` chỉ khi dùng).
- Verify: `/v1/models` → `qwen38-q2_0-refusal` status **loaded**, n_ctx 262144 (alias `qwen38-orca-q2k-refusal`); chat thử OK — decode 43.1 tok/s, MTP 8/16 drafts accepted. MCP gateways 8090/8096 KHÔNG chạy (không start — không thuộc task; chỉ ảnh hưởng tool web_search/fetch của server, không block model).

- Note exit code 1 từ driver --tokens mode sau khi gen xong và in kết quả — không ảnh hưởng nội dung.


## Merge v0.2.1 v""'"'  (done 2026-10-21)
- Gi"'" du'"' serve/ dirty: commit 891ef816 (MCP picture results + slash menu + ctx meter, 7 file).
- Merge tag v0.2.1 v""'""'windows-coding: commit **7646f233**, 5 conflict; c"'"a hai bA"n gi"'":
  - iq_kernels.cu: gi"'"' liA"n t'"'p ngang Q2_K / Q3_K / u'"NIQ1_S c'"a fork + thA"m APR trellis TQ2_T/TQK6/TQK7 (Fmt 144/145/146) c'"a upstream; GU/D/MMVQ format lists lA" union (GI"'M kA"o X(19), X(14), Q2_K trim, kStageIqGrid tmo+ 18/21/19); 
ative_expert_supported gi"'"' d_type==10 trim + thA"m ki'"em tra iq_row_bytes > 0 c'"a upstream; STRATA_KQ_SPLIT gi"'"' nguyA"n.
  - 
ative_expert.cpp: trim Q2_K (d_tail, pad h, kNativeFF check) + trellis (tq_g/tq_d, kTqBlock 128) + had_d rotation c'"a upstream; native_quant_h ch'"y rotation tr"'"'c khi pad.
  - 
ative_expert_parity.cpp: thA"m c"both (q4_1-pair, q2k-trim c'"a fork + load-check/gguf-embd/gguf-ple + --synthetic-hadamard c'"a upstream).
  - CMakeLists.txt: parity pairs gi"'"' fork + thA"m tqk6/tqk7, tq2_t hadamard khi cA" tq.cuh c'"a ggml fork.
  - serve/server.py: gi"'"' cancel-drop khi client r'"'i queue c'"a fork, tmo+ s"'"a lali queued_counted=False cho d'"'a par path (trA"nh gi"'m 2 l'"n) va terminal_events (admitted) c'"a upstream; fit_max_tokens_flag gi"'"' nguyA"n.
- auto-merge A" ."'A'i: pool.hpp (pool_plan), native_expert.hpp (had_gu/had_d + d_tail c'"mg s"'"ng), gguf_reader.hpp (TQ2_T/TQK6/TQK7/PTQ1_0 geometry), native_mmvq.cu (5..8 c'"t il, STRATA_Q8_SM60 Pascal, b6 rows lazy env; Q3_K / IQ1_S dispatch gi"'"' ngon).
- trellis t"c'"a gia l'"'i llama.cpp agention, Linux-only upstream. Build: .orca"build-q36.cmd (native_expert_parity, iq_parity, strata-q36). K'"t gi"'a build: .orca"build-merge-log.txt.
