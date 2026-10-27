# DeepSeek V4.1-Flash serve chinh (26/10/2026)

## Dang chay gi

- **DeepSeek V4.1-Flash-1017, IST-DAS 1.75bpw** (doi tu 2.00bpw ngay 26/10) - preset terminal `ds41f`,
  port **8080**, context **256K** (262,144), speed **Faster** (5/6 experts), DSpark auto, `--ssd-cache 36`.
- Engine rieng: `D:\GitHub\Strata\engine-dsv41\0.1.51-windows-x86_64-cuda-cuda13\strata-dsv41.exe`.
- Model files: `D:\GitHub\Strata-data\models\deepseek-v4.1-flash-IST-DAS-1.75bpw` + pack
  `packs\deepseek-v4.1-flash-ist-das-1.75bpw`. **GiU nguyen** `models\deepseek-v4.1-flash-shared`
  (Engram IQ4_NL 110.4 GiB, dung chung moi set IST-DAS).
- Gateway 8090 + picture sidecar 8096 khong doi; tailnet `pc-dik-win...:8443` -> 8080, `:8444` -> 8096.

## So neo truoc khi doi (ban 2.00bpw, cung ngay 26/10)

- Engine decode: **7.42 / 8.34 / 7.38 tok/s** (ssd-cache 36; truoc do 6.18-7.41 voi store auto)
- Store: hit 79.9%, doc 241.7 MB/token, CPU wait 54 ms/token
- A/B khac: threads 16/28 = khong khac; DSpark on = 3.27 (hai); experts 4 = EOS ngay.

## Chat luong 1.75bpw (theo the HF + docs Strata)

- Task avg **92.32 vs 93.54** (-1.22): AIME25 100.00 (giu nguyen), GPQA-D 88.38 (-2.53), LCB v6 88.57 (-1.14)
- Perplexity **+21% vs +16%**; code/agent +8.9%/+10.2%; "weaker on plain prose"
- Doi lai 2.00: `strata launch --family deepseek41 --model ist-das-2.00bpw ...` (Engram da co, chi tai ~146 GB)

## Khong chong DNS-rebinding qua tailnet

`STRATA_ALLOWED_HOSTS=pc-dik-win.tail1b3f7b.ts.net` phai nam trong **os.environ cua server Python**:
- `run-ds41.bat` tu `set` bien nay (duong boot chuan)
- Bien dat o **user environment** (persistent) cho shell moi
- `--set STRATA_ALLOWED_HOSTS=...` trong preset KHONG du (no chi vao `env` cua engine, server khong doc)

## Boot tu dong (StrataStack task, trigger boot + logon)

- `stack.env`: `STRATA_BAT=D:\GitHub\Strata\run-ds41.bat`, `STRATA_CONFIG=strata-ds41-gateway.json`,
  `STRATA_URL=http://127.0.0.1:8080`, `STRATA_PORT=8080`
- `start-all.ps1`: port theo `STRATA_PORT`, `/mcp` trong khong lam fail
- `restart-strata.ps1`: stop theo `STRATA_PORT`
- `strata-ds41-gateway.json`: model_name + `--max-context 8192` cho gateway

## Stop/serve khi can

- Serve do terminal dung co the chay integrity cao hon shell thuong -> taskkill bi Access denied.
  Dung: `strata launch --stop [--preset ds41f]`
- Mo lai: `D:\GitHub\Strata\run-ds41.bat` (hoac `strata launch --preset ds41f --yes --no-tui` tu cua so
  mo sau khi dat user env - shell cu se thieu allowed_hosts)

## Vision: CA HAI model deu co (do lai 26/10)

| | Qwen3.8 Q2_0 (local) | DeepSeek 1.75 (local) |
|---|---|---|
| Cach doc anh | `strata-vision` CPU reader (config vision on) | vision tower trong engine ds41 (PR #4178) |
| dog.jpg -> tra loi | "Dog" | "dog" |
| Thoi gian | **6.1 s** | 25.5 s |
| Prompt tokens | 351 | 894 (gom 402 image tokens) |

-> Anh don gian: Qwen nhanh hon ~4 lan. DeepSeek vision danh cho khi can reasoning sau anh.

## Vision cho DeepSeek (PR #4178) - DA BAT 26/10

- Nguon: upstream PR **#4178** (`serve/dsv41_vision.py`, server.py native_vision, setup.py mmproj).
  Da cherry-pick vao branch **`feat/dsv41-vision`** (`36cb5365`), push len fork.
- Pack 1.75 rebuild voi `--mmproj`: `models\deepseek-v4.1-flash-shared\mmproj-BF16.gguf` (927 MB,
  Unsloth rev f924b94) -> pack bao vision tower 32 blocks, image token 129264.
  Lenh build (dung dung recipe setup.py dsv41_pack_cmd):
  `python tools\dsv41\pack_gguf.py --model <model dir> --shards <4 IQ1_M> --engram <engram> --engram-meta <UD shard1> --dspark-gguf <dspark> --dspark-noise-token 128799 --dspark-markov-rank 256 --mmproj <mmproj> --out <pack>`
- Terminal 0.1.51 duoc patch cung file: `serve\server.py` + `serve\dsv41_vision.py` (+ `setup.py`).
  Backup: `server.py.bak-vision-20261026`, `setup.py.bak-vision-20261026` trong terminal 0.1.51.
  **Luu y: update Terminal se ghi de** - copy lai tu branch neu update.
- Ket qua test: `/health` -> `"images": true`; gui dog.jpg (OpenAI image_url, base64) ->
  tra loi **"dog"**, prompt 894 tokens (gom 402 image tokens), 25.5 s.
- Qwen sau patch van OK (35.7 s switch, tra loi dung).
- Test PR: `serve.test_dsv41_vision` 6/6 OK.

## Router 8081 + opencode (26/10)

- `%LOCALAPPDATA%\strata-stack\model-router.py` (Python, stdlib): mot endpoint cho 2 model.
  Request `model` chua "qwen" -> Qwen 18080; con lai -> DeepSeek 8080. Truoc khi bat model nay
  se **dung model kia** (taskkill cay tien trinh), cho `/v1/status.loaded` roi proxy (ho tro SSE).
  `/v1/models` liet ke ca hai; `/v1/status` luon loaded=true; `/mcp` rong khi chua co model.
- Boot: `stack.env` -> `STRATA_BAT=...\run-router.bat`, `STRATA_PORT=8081`,
  `STRATA_URL=http://127.0.0.1:8081`; start-all tu khoi dong router; tailscale 8443 -> 8081.
- opencode: provider `local-strata` (baseURL `http://127.0.0.1:8081/v1`) voi 2 model
  `deepseek-v4.1-flash` va `qwen38-q2_0-refusal` (limit 262144).
- Chuyen model: qwen cold ~35 s, ds cold ~45-50 s; chi 1 engine chay tai mot thoi diem.
- Webchat: trang lay tu model dang active; chat cua trang giu model do (nen web Qwen + opencode DS
  dung cung luc se danh nhau - tranh dung song song).

## Vong 3: quyen admin (UAC) - ket qua

- **Ultimate Performance**: da bat (persistent qua reboot) - giu.
- **Engine priority High**: ap duoc; khong do duoc gain ro (trong nhieu); mat khi engine restart.
- **Affinity vao 8 P-core (0xFFFF)**: **te hon gap 2.6 lan** (3.06 tok/s) - engine can ca E-core;
  da revert ve 0xFFFFFFF (8.22/8.40 tok/s).
- **Windows Defender exclusions** (Strata-data, Strata, AppData\Local\Strata + strata-dsv41.exe,
  python terminal): khong do duoc gain (8.30/8.33) - giu lai, vo hai, tranh scan sau nay.
- Ket luan: tran phan mem **8.3-8.4 tok/s** da dat; moi thu tiep theo la phan cung.

## Vong toi uu 2 (256K) - ket qua va tran

- Store 32 GB (RAM free 10.3 GiB): decode 7.71/7.67 - **khong nhanh hon** 36 GB (8.16/7.72), giu 36.
- Context 64K: 8.10/7.96; 256K: 8.16/7.72; 32K: 8.33/8.57 -> context lon gan nhu mien phi
  (KV MLA 0.24 GB o 256K).
- Power plan: may dang **Balanced**; Ultimate Performance can quyen admin (shell Medium) -> chua doi duoc.
- Tran thuc te voi phan mem: **~8-8.6 tok/s decode** (prompt ngan), ~7-8 khi context lon.
- Con lai phai phan cung: RAM 64 GB (store ~50 GB, hit cao hon + file cache nhieu hon), SSD co DRAM.
- Vision: **chua co** trong engine ds41 cua Strata (docs: `--vision` bi bo qua). Cloud Token Plan
  (deepseek-v4.1-flash-1017) co the nhan anh theo catalog - chua test.

## Context 256K (nang cuoi 26/10)

- `--context 256k` = **262,144** da luu preset; status tra `context.native=262144`.
- KV cache chi **0.24 GB** (MLA nen; 32K la 0.03 GB), VRAM experts giam nhe 364 -> 324.
- Test that: prompt **44,369 tokens** duoc chap nhan; **prefill 202.2 tok/s** (219 s cold);
  luot lap lai reuse 44,401 tok trong **1.7 s**; decode trong context 44K: 5.84 -> 7.06 tok/s.
- Uoc tinh prefill cold (theo 202 tok/s): 64K ~5.5 phut, 128K ~11 phut, 256K ~21 phut.
- Khuyen nghi dung: 32K-64K cho code thuong ngay; bat 256K khi that su can (chi phi nam o
  prefill lan dau, decode giam nhe).

## Context 32K (nang 26/10, sau khi chot 1.75 + ssd-cache 36)

- `--context 32k` (32768) da luu vao preset `ds41f`; prompt **11,819 tokens duoc chap nhan** (truoc 8K
  bi 400).
- Prefill 11.8K tokens: doc 11,819 tok trong **69.0 s = 171.3 tok/s (cold)**; luot tiep theo cung
  prefix reuse 11,851 tok trong **1.6 s** (conversation cache hoat dong o 32K).
- Decode: prompt ngan 8.3-8.6 tok/s (engine) / 6.8-7.3 wall; khi context da chua ~12K thi decode
  **6.1-6.2 tok/s** (attention/KV nhieu hon, CPU lane chi 5%).
- So voi 8K: toc do decode prompt ngan gan nhu khong doi; cai gia nam o prefill prompt dai va
  decode khi context lon.

## Ket qua 1.75bpw sau khi doi (do cung ngay 26/10)

Cung 3 prompt, max_tokens 200, temperature 0:

| Prompt | 2.00 decode / wall | 1.75 decode / wall |
|---|---|---|
| CPU cache | 7.42 / 6.39 | **8.57 / 7.34** |
| Turbocharger | 8.34 / 6.10 | **10.12 / 7.26** |
| Stock exchange | 7.38 / 5.77 | **8.38 / 6.74** |
| Trung binh | 7.71 / 6.09 | **9.02 / 7.11 (+17%)** |

Engine: CPU lane 112.2 GB (2.00: 129.8 GB); RAM store 4,136 slots x 8.7 MB, preload 3,880 expert
(26.9 GB) vs 3,248 (25.2 GB); VRAM expert 364 (2.00: 315 - plan uoc 970 nhung thuc te 364).

Chat luong (mau thuc te): khoa hoc va code tot (giai thich Rayleigh dung, LCS DP dung); tieng Viet
2/3 mau tot, 1 mau (temp 0.2) lung cung ("kha heu nhiet doi giua mua...") - dung nhu docs ghi
"weaker on plain prose". Neu van xuat hien nhieu -> quay lai 2.00 (Engram con nguyen, chi tai lai
~146 GB backbone).

## So do 2.00bpw luu lai (tham chieu van tat)

- Decode: 4.6 cold -> 5.5-7.3 warm (spec ~7.2); prefill 525 tok @26 / 957 @39 / 2,398 @59.5 /
  3,080 @66.5 / 4,634 @76.4 tok/s; context 8K cung (vuot -> 400 trong 0.4 s);
  conversation cache reuse gan toan prompt (989/1006 tok trong 1.5-3.3 s);
  `reasoning_effort` trong body khong ho tro (400) - mac dinh high(75).
