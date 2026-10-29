# Strata local — Playbook tốc độ (Qwen3.8 Q2_0 & DeepSeek 1.75)

Máy: RTX 3060 12 GB, i7-14700K (20 core / 28 thread), 48 GB RAM, Windows.
Engine 0.1.52, pack Q2_0, router v1.2 (chỉ còn qwen — DeepSeek ds41f đã xoá 29/10).
Cập nhật: 29/10/2026.

Mọi số "đo" dưới đây là đo trên máy này bằng log engine (`strata serve: prompt … read in … ms`,
`… generated in … ms (… tok/s)`), không phải suy đoán. Số "docs" là từ `docs/DETAILS.md`.

---

## 0. TL;DR

- **Reading (prefill) ~900–1.100 tok/s** — GPU 100% ở 160 W; đây là trần của 3060 với pack Q2_0.
  Prompt 13K mới tinh = **12–13 s**; prompt 55K = **46 s**.
- **Turn đã có cache: 0.15–0.6 s** đọc + thời gian thinking.
- **Decode 50–90 tok/s** tuỳ nội dung (draft MTP được chấp nhận nhiều hay ít).
- Đã thử 4 đòn (host-core `last`, adapt-overlap, lookup-chain 4, spec 6): **không cái nào thắng**.
- 3 việc đáng thử tiếp: `--mtp-q4` + `--mtp-draft-vocab`, `STRATA_EXPDEC=1`, `--pool-tasks`.
- Đòn **không** thắng trên máy này: `--prefill auto:16384`, `--pcie-frac` auto,
  `STRATA_EMB_REUSE_ACCOUNT=1`, affinity P-core, `--experts 4`, DSpark.

---

## 1. Đã áp dụng và đo được

| # | Thay đổi | Trước | Sau | Ghi chú |
|---|---|---|---|---|
| 1 | DeepSeek **1.75bpw** thay 2.00bpw | 7.71 tok/s decode | **9.02 tok/s** | +17%; đọc 112 GB/token thay 129.8 GB |
| 2 | DeepSeek preset: `--ssd-cache 36`, `--max-context 262144` | store 18.9 GB | store 36 GB, 4.136 slot | KV 256K chỉ 0.24 GB |
| 3 | `--vram-reserve-mib 1472` (qwen) | 992 MiB VRAM trống | **1.250 MiB** | hết cảnh báo "below 1024 MiB" |
| 4 | `STRATA_PREFILL_CPU_SHARE=0` | prompt ngắn 1.3–1.6 s | **0.86–1.13 s** | bỏ CPU share cho chunk <1024 |
| 5 | **`effort_position: "end"`** | đổi effort/thinking giữa phiên = đọc lại **11.5 s** | **0.2–0.6 s** | prefix giữ nguyên, chỉ tail đổi |
| 6 | `reasoning_budget_tokens` 22.288 → **12.288** | có reply 12.288 token (~4 phút) | trần 12K | budget là trần cứng |
| 7 | `reasoning_effort: "low"` mặc định (qwen) | request không gửi effort → xhigh | low | request tự gửi thì vẫn thắng |
| 8 | opencode: `"reasoning": true` + `options.reasoningEffort = low` | opencode gửi **không có field effort** | gửi `reasoning_effort: "low"` | đo bằng proxy, không phải đọc code |
| 9 | Router 1.1: gộp model vào `/metrics`, `POST /v1/load` nền | web chỉ thấy qwen+ornith | web thấy qwen + DeepSeek | switch qwen↔ds 30–40 s |
| 10 | Xoá Ornith (42 GB) | picker có ornith | picker còn 2 model | D: +41.9 GB |
| 11 | **Xoá DeepSeek ds41f-1017** (29/10) | D: dùng 521 GB, PLE probe **12.7K rows/s (WARN)** | D: dùng 297 GB, PLE probe **153K rows/s (fine)** | -224 GB; `pagefile C:` không còn bị 95% đầy kéo theo |
| 12 | Cờ mới chưa từng A/B (29/10): `--short-read 128`, `--prompt-cache-spread`, `--mtp-q4 all`, `env: STRATA_EXPDEC=1, STRATA_PLE_AUTO_MMAP=1`, `env_to_user/tool_call_recovery/anthropic_thinking` (server) | baseline: 13K 904 / 55K 989 tok/s, decode ngắn median 73.3 | 13K **897.5** / 55K **978.5** (±1%, không giảm), decode cached **92–99.6** tok/s, drafts accepted 94–95%; mtp-q4 nhả 183 MiB đầu draft nhưng expert slot **không tăng** (3376 vs 3405 = nhiễu WDDM) | router v1.2 + `/v1/load {"restart":true}`; theo dõi KL/accept vài ngày, revert `--mtp-q4` nếu accept giảm |

Các thay đổi "hình thức" khác: vision ds41f (không ảnh hưởng tốc độ text), `env_to_user`
chưa bật, `aliases` qwen38-orca-q2k.

### Bảng đo TTFT (prompt ~12.9K token, cùng câu hỏi)

| Trường hợp | First reasoning | First answer | Ghi chú |
|---|---|---|---|
| Cold (prefix mới) | 11.6 s | 12.6 s | prefill ~1.100 tok/s + ~1 s thinking |
| Cùng prompt, cache hit | 0.16 s | 1.0 s | chỉ còn thinking |
| Đổi effort xhigh → low | 0.59 s | 1.3 s | nhờ `effort_position: end` |
| Bật/tắt thinking | 0.28 s | 0.23 s | prefix không đổi |
| opencode session mới #1 (sau restart) | — | 13.6 s | 13.131 token đọc cold |
| opencode session mới #2 | — | 0.63 s | 13.083/13.131 reused |

---

## 2. Config đang chạy (đối chiếu khi sửa)

### Qwen — `D:\GitHub\Strata\strata-q2_0-v144-refusal.json`

```
--pack packs\q2_0 --native ...Q2_0-00001-of-00002.gguf --ple-gguf ...00002-of-00002.gguf
--expert-profile data\expert-profile.bin --expert-cache auto
--prefill auto --spec 4 --spec-min-p 0.7 --mtp mtp\rt
--max-context 262144 --kv q4_0 --kv-resident 32768 --pcie-frac 0.00
--conversation-cache-mib 10078 --conversation-cache-slots 6
--conversation-cache-min-tokens 8000 --conversation-cache-min-free-mib 1536
--control-vector-scaled data\experimental-speed-projection\...gguf:1.0
--control-vector-layer-range 4 44 --cvec-mode project --cvec-dir per-layer
--vision --vram-reserve-mib 1472
```

Keys ngoài `args`: `models: []`, `expert_profile_save: expert-profile-learned-q2_0.bin`,
`reasoning_budget_tokens: 12288`, `reasoning_effort: "low"`, `effort_position: "end"`,
`strip_cjk: true`, `min_free_vram_mib: 9000`, `before_load`, `vision`, `mcp_servers`.

### DeepSeek — preset `ds41f` (Terminal)

```
--pack packs\deepseek-v4.1-flash-ist-das-1.75bpw --max-context 262144 --eos 1
--dspark auto --dspark-conf 0.65 --ssd-cache 36
```

### Môi trường (router + engine con)

```
run-router.bat: MODEL_ROUTER_PORT=8081
                STRATA_PREFILL_CPU_SHARE=0
```

### Profile / CPU

Log khởi động: profile học `expert-profile-learned-q2_0.bin` (24.576 cặp) **đã được load**,
pre-fill 3.423 slot; CPU pool **13 worker**, host thread ở core 0 (`--host-core first`).

---

## 3. Flag engine — nhóm ảnh hưởng tốc độ

`--` là đang dùng; `–` là chưa dùng (mặc định).

### 3.1 Reading / prefill / prompt cache

| Flag | Dùng | Tác dụng | Ghi chú |
|---|---|---|---|
| `--prefill CHUNK` | `auto` (8192) | chunk đọc prompt, auto = lớn nhất vừa cache | `auto:16384` đã thử: engine chọn 8960, **không nhanh hơn**, không bit-exact |
| `--short-read N` | – (64) | đọc N token mới qua decode window thay vì prefill | thử 128/256 cho turn nhỏ |
| `--prefill-head-alias` | – | nhả output head trong lúc đọc prompt | cho card 8 GB; thử trên 12 GB |
| `--prompt-cache N` | – (6) | số checkpoint giữa request | ~118 MB/cái |
| `--prompt-cache-every N` | – (16384) | checkpoint mỗi N token prompt | giảm → reuse mịn hơn, tốn RAM |
| `--prompt-cache-tail` | – | thêm checkpoint sát cuối prompt | cho client hay sửa đuôi |
| `--prompt-cache-spread` | – | checkpoint dày gần cuối | client rewrite history N token |
| `--return-progress` (config) | – | stream tiến độ đọc | chỉ để hiển thị |
| `STRATA_PREFILL_EQUAL=1` | – | chunk đều nhau | đổi rounding |
| `STRATA_PREFILL_AUTO_MAX=N` | – | trần chunk của auto | |
| `STRATA_PREFILL_RING=N` | – (96) | ring pipeline | |
| `STRATA_PREFILL_HOST_PLAN=0` | – | tắt chunk theo RAM host (Linux) | Windows N/A |

### 3.2 Decode / draft (MTP, suffix, lookup)

| Flag | Dùng | Tác dụng | Ghi chú |
|---|---|---|---|
| `--spec N` | `4` | số token MTP đề xuất mỗi lần verify | thử 6 |
| `--spec-min-p P` | `0.7` | độ chắc để nối thêm draft | setup mặc định 0.5; A/B 0.5–0.7 |
| `--suffix-draft N` | – (3) | draft từ đoạn lặp trong context | tăng 4–8 cho code |
| `--lookup-chain K` | – (0) | thêm K draft n-gram sau MTP, cửa sổ ≤8 | **ứng viên tốt cho code** |
| `--lookup-chain-min M` | – (3) | độ dài khớp tối thiểu | |
| `--mtp-max-t M` | – (0 = spec) | trần cửa sổ MTP | |
| `--mtp-q4 all\|proj\|head` | – | draft layer 4-bit | nhả ~0.5–0.7 GB VRAM cho expert |
| `--mtp-draft-vocab FILE` | – (CJK subset) | subset vocab của draft head | `en`/code: nhả ~110 MB, +1–2% |
| `--mtp-hnorm pooled\|stream` | – | norm của draft layer | |
| `--draft dflash2` | – | draft model khác | cần pack riêng |
| `STRATA_ROUTE_TAIL_SKIP` | on (7) | bỏ expert đuôi mọi token đều miss | +10–20% decode trên 12–16 GB |
| `STRATA_EXPDEC=1` | – | gate/up expert resident bằng shared memory | exact; thử |
| `STRATA_HC_UPMIX=1` | – | gộp up-projection + gr_mix_r | exact |
| `STRATA_HC_REQ8=1` | – | hyper-connection int8 | rounding; thêm slot expert |
| `STRATA_QSA_ROWS`, `ATTN_DAILY`, `SIDE_MIXER`, `B6_MMVQ_ROWS` | on (sm_86) | kernel decode mặc định | đã bật sẵn |
| `STRATA_ADAPT_OVERLAP=1` | – | copy cache expert chồng lên window sau | +4–8% trên A4000/P100; **thử trên 3060** |
| `STRATA_ADAPT_LAG=2` | on (sm_86) | swap trễ 2 window | đã bật |
| `STRATA_PCIE_BALANCE=1` | – | cân số expert đọc PCIe mỗi layer | +5.6% A4000, hại máy khác |

### 3.3 VRAM / expert cache / KV

| Flag | Dùng | Tác dụng | Ghi chú |
|---|---|---|---|
| `--expert-cache N\|auto` | `auto` | số expert blob trong VRAM | auto đã tối đa theo VRAM trống |
| `--expert-profile P` | `data\expert-profile.bin` | nạp trước expert theo profile | profile học đã được load tự động |
| `--expert-profile-save P` | `expert-profile-learned-q2_0.bin` | lưu profile học mỗi 10 phút | đã bật |
| `--pcie-frac F` | **`0.00`** | share expert miss copy sang GPU (0 = CPU làm hết) | **đã đo: auto 0.35 chậm hơn 3–4%**; CPU 23 GB/s vs PCIe 24 GB/s |
| `--kv q4_0\|k8v4\|int8\|fp16` | `q4_0` | dung lượng KV | k8v4 = 816 B/cell, nhiều VRAM hơn q4_0 |
| `--kv-resident N` | `32768` | KV nằm VRAM mỗi layer | 262K context stream từ RAM |
| `--kv-grow` | – | KV chiếm VRAM theo nhu cầu | cần whole KV in VRAM; 262K không hợp |
| `--vram-elastic` | – | expert cache chia segment, nhả VRAM khi rảnh | không tăng tốc |
| `--vram-reserve-mib N` | `1472` | giữ VRAM trống | đã áp dụng |
| `--max-context N` | `262144` | KV capacity | giảm → ít RAM/VRAM hơn |
| `--conversation-cache-mib N` | `10078` | RAM cho hội thoại park | |
| `--conversation-cache-slots N` | `6` | số hội thoại giữ | |
| `--conversation-cache-min-tokens N` | `8000` | chỉ park hội thoại ≥ N | |
| `--conversation-cache-park-gain N` | – | chỉ park khi tiến thêm N token | |
| `--shared-expert-arena FILE` | – | chia sẻ expert arena giữa process | |

### 3.4 CPU pool / thread

| Flag | Dùng | Tác dụng | Ghi chú |
|---|---|---|---|
| `--pool-workers N` | – (13) | số worker tính expert | log: 13 worker (P-core + nửa E-core) |
| `--pool-tasks N` | – (0 = 3/thread) | số task mỗi pha gate/up, down | thử 192 để cân tải |
| `--pool-cores LIST` | – | core nào chạy pool | |
| `--pool-affinity all\|p-cores\|measure` | – (all) | layout worker | **affinity P-core đã thử: chậm 2,6×** |
| `--host-core first\|last\|sibling` | – (first) | core của host thread | docs: `last` +8% trên 1 box Windows |
| `--aux-cpus SET` | – | CPU phụ cho việc khác | |

### 3.5 Batching / nhiều request

| Flag | Dùng | Tác dụng | Ghi chú |
|---|---|---|---|
| `--batch N` / `--slots N` | – | N request decode song song (2–8) | **mỗi slot cần VRAM như session chính → không hợp 12 GB** |
| `--batch-mtp` | – | mỗi slot verify 1 MTP | cần `--batch` |
| `--batch-groups G` | – | nhóm slot qua layer split | multi-GPU |
| server `--parallel N` | – (1) | số slot engine | như trên |
| `--max-queue N`, `--queue-timeout S` | – | hàng đợi | |

### 3.6 Chẩn đoán (không dùng khi chạy thật)

`--no-token-graph`, `--no-fused-gr`, `--no-hit-poke`, `--no-ple-prefetch`, `--no-pool`,
`--gpu-stages`, `--stage-timing`, `--stats`, `--graph-only`, `--gpu-only-full`,
`--window-hashes`, `STRATA_DECODE_TIMING=1`, `STRATA_VERIFY_PROFILE=1`.

---

## 4. Config keys của server (`strata-<model>.json`, ngoài `args`)

| Key | Mặc định | Đang dùng | Tác dụng / ghi chú |
|---|---|---|---|
| `reasoning_effort` | model (high) | **low** | mức cho request không gửi |
| `reasoning_budget_tokens` | 0 | **12288** | trần thinking cứng |
| `effort_position` | start | **end** | đổi effort không mất cache |
| `answer_room` | on | on | chừa chỗ cho câu trả lời |
| `fit_max_tokens` | true | true | cắt max_tokens theo context |
| `parallel` | 1 | 1 | batch slots (không hợp 12 GB) |
| `env_to_user` | off | off | ổn định system prompt opencode cho disk prefix cache |
| `tool_call_recovery` | off | off | đọc tool call "lệch" → ít retry |
| `anthropic_thinking` | model | model | `on_request` cho Claude Code helper |
| `codex_thread_titles` | off | off | title Codex không gọi engine |
| `codex_compaction_cache` | off | off | |
| `fit_max_tokens`, `strip_cjk` | true/true | true/true | strip_cjk: bỏ CJK khỏi trả lời |
| `sampling` | model card | card | temperature/top_p/top_k mặc định |
| `repeat_stop_tokens` | 256 | 256 | cắt vòng lặp lặp token |
| `reasoning_loop_recovery` | off | off | phát hiện thinking lặp |
| `reasoning_close_retry` | off | off | đóng thinking khi reply hết chỗ |
| `prevent_sleep` | off | off | giữ PC thức khi chạy |
| `idle_unload_s` / `lazy_load` | off | off | nhả VRAM khi rảnh (chậm lần sau) |
| `min_free_vram_mib` | – | 9000 | chờ VRAM trước khi load |
| `aliases` | – | `qwen38-orca-q2k-refusal` | tên phụ |
| `mcp_servers`, `mcp` | – | gateway, image | tool MCP (tăng system prompt) |

---

## 5. Biến môi trường `STRATA_*` (đáng biết)

| Biến | Mặc định | Đang dùng | Tác dụng / nhận xét |
|---|---|---|---|
| `STRATA_PREFILL_CPU_SHARE` | auto | **0** | CPU share cho chunk <1024; tắt = prompt ngắn nhanh hơn |
| `STRATA_ROUTE_TAIL_SKIP` | 7 | 7 | bỏ expert đuôi; +10–20% decode 12–16 GB |
| `STRATA_TAIL_SKIP_MAX_CACHED` | 90 | – | ngưỡng tắt tail skip |
| `STRATA_ADAPT_OVERLAP` | 0 | 0 | chồng copy cache; **thử** |
| `STRATA_ADAPT_LAG` | 2 (sm_86) | 2 | swap trễ |
| `STRATA_ADAPT_NOWAIT` | on (sm_86) | on | |
| `STRATA_PCIE_FRAC_DEFAULT` | auto | auto | `old` = chỉ probe |
| `STRATA_PCIE_BALANCE` | 0 | 0 | cân PCIe |
| `STRATA_EMB_REUSE_ACCOUNT` | 0 | 0 | **đã thử: +1% (nhiễu), chunk vẫn 8192 → revert** |
| `STRATA_MMQ_DIRECT` | 0 | 0 | cần build `-DSTRATA_MMQ_TAB=ON`; nhanh khi mọi expert resident |
| `STRATA_PF_FUSED` | auto | auto | cần ≥80 SM (3060 có 28 → không) |
| `STRATA_GDN_CHUNKED` | auto | auto | cần ≥128 SM → không |
| `STRATA_DEQUANT_WIDE` | on (sm_86) | on | wide dequant Q4_K/Q5_K/Q6_K/IQ4_XS |
| `STRATA_CPU_IQ_ALL_EXACT1` | on (sm_86) | on | |
| `STRATA_Q2_BITPLANE` | 0 | 0 | bit-plane kernel Q2_0 (AVX2) |
| `STRATA_ATTN_DAILY` | on (sm_86) | on | decode attention 2 cell/step |
| `STRATA_QSA_ROWS` | on (sm_86) | on | |
| `STRATA_SIDE_MIXER` | on (sm_86) | on | |
| `STRATA_B6_MMVQ_ROWS` | on (sm_86) | on | |
| `STRATA_EXPDEC` | 0 | 0 | **thử** (exact) |
| `STRATA_HC_UPMIX` | 0 | 0 | exact |
| `STRATA_HC_REQ8` | 0 | 0 | rounding; thêm slot |
| `STRATA_HOST_CORE` | first | first | **thử `last`** trên Windows hybrid |
| `STRATA_SM86_PERF` | on | on | tắt cả bộ kernel sm_86 (để A/B) |
| `STRATA_PREFILL_EQUAL` | 0 | 0 | chunk đều |
| `STRATA_PREFILL_AUTO_MAX` | – | – | trần auto |
| `STRATA_PREFILL_RING` | 96 | 96 | ring |
| `STRATA_NUMA_POOL` | auto | auto | Windows chưa split |
| `STRATA_STAGER_SSD`, `STRATA_STAGER_THREADS`, `STRATA_STAGER_SLEEP` | auto | auto | staging GGUF |
| `STRATA_PLE_AUTO_MMAP`, `STRATA_PLE_*` | auto | auto | bảng PLE (đọc SSD) |
| `STRATA_DECODE_TIMING`, `STRATA_VERIFY_PROFILE` | 0 | 0 | profiling |
| `STRATA_ROUTE_PRIOR`, `STRATA_ROUTE_RESIDENT*` | 0 | 0 | tăng tốc + tăng KL, không khuyến nghị |
| `STRATA_GR_NORM_FAST`, `STRATA_GR_DOWN_TG`, `STRATA_RAM_ADAPT`, `STRATA_KV_HOST_REGISTER` | auto | auto | kernel/nhỏ |

Biến môi trường đặt ở đâu:
- **engine**: object `"env": { ... }` trong config qwen (chỉ tới engine), hoặc
- **server + engine**: `set STRATA_...=...` trong `run-router.bat` (router thừa hưởng cho con).

---

## 6. Tính năng có sẵn (không phải flag tốc độ nhưng liên quan)

- **Vision**: `--vision` + `strata-vision` (mmproj). ds41f `images: true`; qwen CPU reader.
- **MCP tools** (`mcp_servers`): gateway/image; làm system prompt to hơn → chậm hơn.
- **Structured output** (json_object/json_schema): prompt + validate, không grammar.
- **Session save/restore** (`slot_save_path`, `/slots/0?action=save|restore`): lưu RAM/đĩa.
- **Conversation cache**: park hội thoại trong RAM (10 GB / 6 slot).
- **Prompt cache**: checkpoint KV (6 cái, mỗi 16K).
- **Model switching** (`POST /v1/load`, web): unload model cũ → mất cache.
- **Aliases**, **web chat**, **API OpenAI/Anthropic/Responses**.
- **Control vector** (`--control-vector-scaled ...:1.0`): đang bật; là steering chứ không phải tăng tốc.
- **Batching** (`--parallel`/`--batch`): không hợp 12 GB.
- **Replicas** (`--replicas`): nhiều process (multi-GPU).

---

## 7. Ứng viên CHƯA dùng — nên thử, xếp theo tiềm năng

> 29/10: #1 (`--mtp-q4 all`, chưa kèm draft-vocab), #2 (EXPDEC), #6 (`--prompt-cache-spread`)
> và `--short-read 128` + ba server keys (#9 env_to_user, #10 anthropic_thinking, #12
> tool_call_recovery) đã bật — kết quả đo ở mục 1 dòng 12. #3 `--pool-tasks`, #4 UPMIX/REQ8,
> #5 short-read 256, #7 head-alias còn mở.

> Cách đo: `.orca\bench-ab.py` hoặc `.orca\bench-code.py`. Mỗi lần đổi config: sửa file →
> `POST /v1/load` sang ds rồi về qwen (30–40 s mỗi chiều).
> Lưu ý khi đo: đặt `max_tokens` đủ lớn (≥600) để model tự dừng. Nếu chạm trần, server có thể
> nối tiếp và prompt lần sau dài hơn, làm sai lệch phép so.

| # | Thử gì | Kỳ vọng | Rủi ro | Cách bật |
|---|---|---|---|---|
| 1 | `--mtp-q4 all` + `--mtp-draft-vocab` (subset en/code) | nhả ~0.6–0.8 GB VRAM → thêm expert slot; docs +1–2% | draft kém hơn chút | `args` + `tools/draft_vocab.py` |
| 2 | `STRATA_EXPDEC=1` | exact, decode +vài % | không | `"env"` |
| 3 | `--pool-tasks 192` / `--pool-workers` A/B | cân tải CPU pool | nhiễu, phải đo kỹ | `args` |
| 4 | `STRATA_HC_UPMIX=1`, `STRATA_HC_REQ8=1` | gộp kernel / thêm slot | REQ8 đổi rounding | `"env"` |
| 5 | `--short-read 128`/`256` | TTFT cho turn thêm ít token | chưa đo | `args` |
| 6 | `--prompt-cache-tail`, `--prompt-cache-spread` | reuse tốt hơn khi client sửa đuôi history | tốn RAM | `args` |
| 7 | `--prefill-head-alias` | nhả output head khi đọc prompt | cho card 8 GB | `args` |
| 8 | `STRATA_PREFILL_EQUAL=1` | chunk đều, ít đuôi ngắn | đổi rounding | `"env"` |
| 9 | `env_to_user: true` | system prompt opencode ổn định qua ngày → disk prefix cache | đổi vị trí `<env>` | config key |
| 10 | `anthropic_thinking: "on_request"` | Claude Code helper không thinking | chỉ ảnh hưởng /v1/messages | config key |
| 11 | `codex_thread_titles: true` | title Codex không gọi engine | chỉ Codex | config key |
| 12 | `tool_call_recovery: true` | 98.3% vs 92.9% tool call đọc đúng → ít retry | có thể nhận call "lạ" | config key |
| 13 | `nvidia-smi -pl 187` | +~5% (170→187 W) | nóng/ồn, cần admin | admin |
| 14 | `--batch 2` / `--parallel 2` | 2 request cùng lúc | **không đủ VRAM 12 GB** | không nên |

### Ghi chú cho 3 ứng viên đầu

**1. `--mtp-q4 all`**: draft layer ~820 MB VRAM; 4-bit giảm khoảng một nửa → thêm vài trăm
expert slot. Đo kèm `drafts accepted` (chấp nhận giảm bao nhiêu) và VRAM free sau khi bật.

**2. `STRATA_EXPDEC=1`**: kernel exact (gate/up của expert resident bằng shared memory).
Docs đo trên 3060/A4000: lợi ích nhỏ nhưng miễn phí, không đổi đáp án.

**3. `--pool-tasks 192`**: CPU pool 13 worker; nhiều task hơn có thể giảm lệch tải giữa core.
A/B với `0` (mặc định 3 task/thread), cùng số worker.

## 8. Đã thử và KHÔNG thắng (đừng thử lại)

| Thử | Kết quả đo | Kết luận |
|---|---|---|
| `--prefill auto:16384` | engine chọn 8960; 13K: 930 tok/s, 55K: 997 tok/s (so 8192: 904/989) | không hơn, lại không bit-exact → revert `auto` |
| `--pcie-frac` auto (0.35) | decode 66/86/86 vs 74/90/90 tok/s (pcie 0.00) | CPU 23 GB/s ≈ PCIe 24 GB/s → giữ `0.00` |
| `STRATA_EMB_REUSE_ACCOUNT=1` | chunk vẫn 8192; 13K 913 vs 904 (nhiễu) | revert |
| Affinity P-core (0xFFFF) | chậm **2,6×** | bỏ |
| `--experts 4` | EOS ngay | bỏ |
| DSpark trên 12 GB | 3,27 tok/s | tắt auto |
| `--prefill` nhỏ hơn 8192 | (lịch sử) không hơn | giữ auto |
| `--batch` | cần VRAM mỗi slot | không hợp 12 GB |
| `--host-core last` | 13K 905 / 55K 991 tok/s (baseline 915/992); log vẫn "host thread on 0" | không đổi; flag dường như không áp dụng trên máy này |
| `STRATA_ADAPT_OVERLAP=1` + `LAG=1`, `NOWAIT=0` | decode 68,3/86,3/85,9 vs baseline 72,9/93,4/91,0 | **chậm hơn 5–7%** → tắt |
| `--lookup-chain 4` | decode 74,9/93,6/90,5 vs baseline 72,9/93,4/91,0 | không đổi |
| `--spec 6` | 400 token: 7,2 s (lần 1) nhưng 8,0 s (lần 2) vs 7,6 s | nhiễu, không kết luận → giữ `--spec 4` |

---

## 9. Quy trình A/B chuẩn (để không bị nhiễu)

1. Sửa config (backup trước): `Copy-Item strata-q2_0-v144-refusal.json ...bak-<tên>`.
2. Restart engine: `POST http://127.0.0.1:8081/v1/load {"model":"deepseek-v4.1-flash"}`
   → chờ `/metrics` current=ds → `POST .../v1/load {"model":"qwen38-q2_0-refusal"}` → chờ current=qwen.
   (Không cần admin; router tự kill/start.)
3. Chạy `.venv\Scripts\python.exe .orca\bench-ab.py`.
4. Đọc log engine:
   `Select-String strata-q2_0-v144-refusal.log -Pattern 'prompt \d+ tokens = ' | Select-Object -Last 5`
   - prefill: `read in … ms (… tok/s)`
   - decode: `generated in … ms (… tok/s)`
5. Lặp lại 2–3 lần (nhiễu ±5%), so **trung vị**, không so một lần.
6. Nếu thắng: giữ + ghi vào mục 1. Nếu không: revert file `.bak` và restart.

Biến môi trường: đặt trong `"env": {"TÊN":"1"}` của config (engine) — không cần restart router.
Nếu cần cho cả server: thêm `set TÊN=1` vào `run-router.bat` rồi restart router (admin).

---

## 10. Phụ lục — nhóm flag còn lại (ít liên quan tốc độ)

- **Model/pack**: `--pack`, `--native`, `--ple-gguf`, `--embd-gguf`, `--native-dense-gguf`,
  `--native-head-gguf`, `--no-ple`, `--ple-io`, `--ple-row-cache`, `--ple-inflight`.
- **Context/RoPE**: `--max-context`, `--rope-scaling`, `--rope-scale`, `--rope-freq-base`,
  `--rope-freq-scale`, `--yarn-*`.
- **Sampling**: `--greedy`, `--seed`, `--top-k`, `--top-p`, `--temperature`.
- **Control vector**: `--control-vector-scaled`, `--control-vector-layer-range`, `--cvec-mode`, `--cvec-dir`.
- **Multi-GPU**: `--gpu`, `--prefill-pipe`, `--pipeline-windows`, `--trim-stage-weights`,
  `--peer-*`, `--batch-groups`.
- **Chẩn đoán/bench**: `--dump-*`, `--logits-stride`, `--spec-follow`, `--window-hashes`,
  `--check-logits`, `--sync-every-layer`, `--no-capture`, `--native-*` (A/B kernel).
- **Session**: `--session-min-free-mib`, `--session-save-reclaim`, `--slot-save-path`.
- **Server**: `--engine`, `--config`, `--host`, `--port`, `--api-key`, `--no-api-key`,
  `--tokenizer`, `--gpu`, `--offline`, `--mcp-config`, `--idle-unload`, `--lazy`,
  `--before-load`, `--api-monitor`, `--ready-file`, `--shutdown-timeout`, `--replicas`,
  `--batch-telemetry`, `--script*`.

Xem đầy đủ: `strata.exe --help` (146 flag) và `python serve/server.py --help` (30 flag).

---

## 11. Việc nên làm ngay (không cần đo)

- Giữ **một model** cho cả task: switch = 30–40 s + cold read 12–13 s.
- Session < 32K token; `/compact` khi dài; tool output nhỏ (grep/range).
- Dùng **thinking off / low** cho việc đơn giản: `effort_position=end` đã giữ cache.
- Đừng bật `parallel`/`batch` trên 12 GB.
- Nếu cần thêm tốc độ: thử mục 7 #1–#3 (mtp-q4, EXPDEC, pool-tasks).