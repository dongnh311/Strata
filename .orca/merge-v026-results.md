# Merge v0.2.6 → windows-coding (26/10/2026)

## Trạng thái

- **Merge hoàn tất + đã build + đã qua host gates + A/B boot thật.** Commit merge: **`e6446982`**
  `Merge remote-tracking branch 'upstream/main' into merge-v026`, trên branch **`merge-v026`**
  (nhánh riêng — `windows-coding` giữ nguyên, serve chính không đổi).
- Đầu nhánh (merge-base) = v0.2.2 (`011c9e60`); upstream ăn thêm **577 commit, tags v0.2.3 → v0.2.6**
  (README, docs 7 ngôn ngữ, DeepSeek V4.1-Flash engine, uninstaller fixes, serve fixes, engine C++
  prefill/gemm `generate.cpp` 442 dòng + `draft_policy.cpp` 144 dòng + `native_expert.cpp`).
- Engine mới: **strata 0.1.51** — build vào `D:\GitHub\Strata-data\build-v026` (flags copy đúng
  `build-wc`: CUDA ON riêng của Strata, arch 86, native experts + Q6K experts + MMQ K-quants +
  TQ overlay ON, MMQ tab/prefill MMQ/ORCA Q4KS OFF, tests OFF, portable ON). 165 bước, chỉ warning
  C4458/C4459 (loại thường gặp). Log `.orca\build-v026-log.txt`; parity targets log
  `.orca\build-v026-parity-log.txt`. Third-party `third_party/llama.cpp` gitignored — không đổi.

## Giải 6 conflict (quyết định từng hunk)

- **serve/server.py (3 hunk):**
  - OpenAI run path: dùng `self.parser_cls(...)` (upstream, cho DSML DeepSeek parser) **cộng**
    `aliases=aliases` (fork, bare-name MCP matching với số đo RTX 3060 3/10→0/10).
  - Anthropic route: upstream `svc.force_text(forced_call(...))` + giữ fork `max_req` +
   icester fork MCP block (`_wants_mcp`, `--own-page` gate, `template_tools(exclude=own)`).
  - Tokenizer loader: giữ hàm helper `load_tokenizer()` của fork (1 chỗ định nghĩa, 2 where dùng),
    **nâng cấp** theo upstream: đọc thêm `tokenizer.json` (tcfg → `pre` + `special_ids`,
    hỗ trợ DeepSeek tokenizer), vẫn giữ fallback `or ByteTokenizer()` của fork.
- **serve/frontend.py (2 hunk + 1 hunk lai auto-merge):**
  - `OutputParser.__init__` đang auto-merge thành trạng thái lai có **bug tiềm ẩn** (dòng 940 gán
    `self.aliases = dict(aliases or {})` rồi dòng 955-956 upstream ghi đè bằng alias namespace
    → MCP alias của fork bị mất im lặng). Sửa: `setdefault` — alias truyền vào (fork) thắng clash,
    alias namespace (upstream PR #3556) chèn khi không clash, đúng quy tắc "exactly declared wins".
  - 2 hunk `_finish_call`/body parse: dùng bản upstream (thêm `raw_name` + strip check, trả text
    khi tên có khoảng trắng), một trong hai vẫn gọi `self.aliases.get(...)` như fork.
- **serve/web/app.js (1 hunk):** refactor `saveApiKey(notify)` của upstream + trả lại hành vi
  fork: `onchange` gọi `loadMcp()` sau khi lưu key (boot-time GET /mcp từng bị từ chối khi chưa
  có key; nếu không reload lại, chat không bao giờ offer MCP tools).
- **serve/web/app.css (2 hunk):** union — `overflow-wrap: anywhere` (upstream) + `min-width: 0`
  của fork + giữ `.st-msg--user .st-bubble { max-width: 100% }`, `.st-msg__meta { flex-wrap: wrap }`
  và comment table scroll nhiều dòng của fork.
- **src/kernels/cpu/native_expert.cpp (1 hunk):** giữ branch `d_tail` Q8_K padding (custom quant
  lineage của fork) **và** dòng `act_dump_record(f.layer, 1, h, f.n_ff)` (upstream, diagnostic) —
  dump trước, custom branch sau.
- **docs/DETAILS.md (4 hunk):** hunk 681 và 1349 giữ cả hai phía (customize + upstream độc lập);
  hunk 872 giữ bên fork nguyên khối (Codex compaction bản dài có số đo 84,895/84,997, MCP section
  rich gồm X-Strata-MCP header + bare-name measurement — upstream ngắn hơn và mất custom), hunk
  1094 giữ bên fork (numb 0.1.13 giàu hơn bản 2 dòng của upstream).

## Kiểm chứng sau merge

### Host gates (không GPU) — TOÀN PASS
- `strata.exe --version` → **0.1.51**.
- `iq_parity` (11 fixtures, incl. Q2_0 type 42 + Q3_K): **0 failures**, dequant rel 0.00e+00 toàn bộ.
- `native_expert_parity --synthetic q4_K/q5_1`: 0 failures (cpu 1.37e-02 / gpu 1.25e-02, decode-once
  bitwise, khớp từng chữ số pre-merge).
- `--q2k-trim q4_K`: ok (212 B rows, 0/1,638,400 bit lệch — khớp baseline v0.2.2). Lưu ý cú pháp:
  v0.2.6 nhận MỘT token (`--q2k-trim q4_K`), không phải `iq2_xxs/q2_K` như doc cũ; biến thể
  `--q2k-trim q2_K`-thuần FAIL (trên binary CŨ build-wc cũng FAIL y hệt → không phải regression).
- `--q4_1-pair q4_1`: ok (0/7680 cpu + 0/7680 gpu bit lệch, fifth bits 0 blocks) — khớp baseline.

### Tests Python (mock engine)
- Full suite (test_server + test_mcp + test_frontend): **426 passed, 637 subtests passed, 3 skipped,
  6 FAILED**. So baseline trên worktree `D:\GitHub\Strata-wc-base` (windows-coding nguyên Zust): cùng
  **đúng 6 fail này** → **không có fail nào mới do merge** (tình trạng có sẵn của custom fork).
  Log `.orca\test-serve-v026-log.txt` + `.orca\test-baseline6-log.txt`.

### Gate GPU
- VERIFY q36 dạng cũ KHÔNG chạy được: file base `Ornith-1.5-122B-UD-Q2_K_XL.gguf` đã bị xóa khỏi máy
  (chỉ còn 2 file Ornith 35B-A3B).
- Thay thế = **A/B boot thật greedy trên serve** (cùng model q2_0, cùng config, port 18081,
  temperature 0, max_tokens 256, 3 prompt): outputs A (0.1.47) vs B (0.1.51) **KHÔNG khớp bitwise**
  — diverge từ token đầu (prefix chung 0/97/0 chars). Phán đoán: nhắm đúng như upstream tự ghi —
  "spec-split window is not bit-exact: batch-shape divergence" + generate.cpp/draft_policy đổi sâu +
  sm_86 switches mới bật mặc định. Chất lượng output B bình thường (câu chuyện coherent).
  Cả hai engine tự quaVerify window capture lúc boot (same procedure).
- Tok/s A/B cùng ngày (3 lượt, warm cache): A = 39.6 / 52.0 / 59.4→60.3; B = 38.6 / 52.8 / 56.5→57.0
  / 64.9 — parity trong ±3%: **không regression, không thắng rõ**. Drafts (MTP) hoạt động ở cả hai.

## Dọn dẹp cuối phiên (26/10/2026)

- Serve chính đã dừng ~2 lần cho gates/A/B và restart về đúng trạng thái ổn định:
  engine cũ 0.1.47 + `server.py` của **`windows-coding`** (một lần restart đầu lại rơi vào
  cây `merge-v026` đang checkout — đã switch `windows-coding` về `D:\GitHub\Strata` và
  restart lần cuối; smoke: health ok, MCP gateway=ready, image=ready).
- Worktree baseline `D:\GitHub\Strata-wc-base` đã xoá (`git worktree remove --force`).
- Branch `merge-v026` (`e6446982`) còn nguyên trong repo, chưa push, chưa merge vào
  `windows-coding` (`8f4564b8`).

## Chưa làm (tùy user duyệt)

- Serve chính 18080 vẫn chạy engine cũ (0.1.47) — nếu muốn đổi sang 0.1.51 chỉ cần swap
  `"exe"` trong `strata-q2_0-v144-refusal.json` trỏ sang `build-v026\strata.exe` (restart lại serve).
- trái远景 choices: (a) merge `merge-v026` vào `windows-coding` + push origin; (b) giữ
  `merge-v026` là branch riêng đợi thêm bench; (c) bỏ.
- Dọn worktree baseline `D:\GitHub\Strata-wc-base` sau decide.
- Cherry-pick các serve fixes nhỏ cũng có sẵn trong v0.2.6 nếu giữ nhánh cũ (single-token probe
  tok/s, no-message 400...).
- Cần chụp lại: `strata bench run` chính thức + VERIFY q36 khi Ornith-122B được tải lại về.

## Khác đáng chú ý trong v0.2.6 (đã vào cây)

- DeepSeek V4.1-Flash engine 0.1.51 (DSML parser, `--mmap-experts auto copy-all`, 8K context mặc
  định) — máy này không dùng (không model DS), nhưng code path sẵn sàng.
- Serve: single-token reply không in tok/s (tránh profit 1,250 tok/s giả), chat không message →
  400 như OpenAI, request ĐANG queue hiển thị đúng (`/api/requests`).
- Uninstaller Windows fix (stop process install-folder + remove folders còn lại).
- Monitor GPU: chốt bỏ iGPU nhỏ khỏi "All GPUs", hardware report CARD ID ổn định.
- README 7 ngôn ngữ + docs pack 0.2.5/0.2.6 (một installer mỗi hệ).
- Upsm_86 default switches (STRATA_ADAPT_NOWAIT, STRATA_SIDE_MIXER=2, STRATA_ATTN_DAILY, ...)
  + bảng per-arch sm_60/sm_120 trong DETAILS.md — giải thích outputs đổi bitwise.
