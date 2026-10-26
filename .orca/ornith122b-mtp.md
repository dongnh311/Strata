# Ornith-1.5-122B — MTP speculative decoding (llama.cpp b11669)

## Cách chạy (đo ngày 21-10-2026)

Server tự dựng **MTP draft context từ chính file GGUF chính** (block nextn `blk.48`),
không cần file draft riêng. Build b11669 có `graph_mtp@llama_model_qwen35moe` sẵn trong `llama.dll`.

Cấu hình đo được tốt nhất — đã set trong `ornith122b-serve.ps1`:

```
--spec-type draft-mtp --spec-draft-n-max 2 --spec-draft-n-min 1
```

(tìm thấy qua `llama-server --help` → mục "speculative params"; cờ `--draft-max` cũ đã bị bỏ)

## Số đo (RTX 3060 12 GB + 48 GB RAM, quant UD-Q2_K_XL, experts trên CPU, ctx 32K, KV q8_0)

| Cấu hình | t/s decode (warm) | draft acceptance | mean len |
|---|---|---|---|
| baseline, không MTP | 12.5 | — | — |
| MTP n-max 2 | 11.9–17.45 | 0.76–0.81 | 2.48–2.62 |
| MTP n-max 3 | 14.86 | 0.85 | 3.50 |

- Lần đo nhanh nhất n-max 2: **17.45 t/s** (1.4× baseline) khi máy yên tĩnh.
- Cùng cấu hình đo lại khi có nhiễu nền: 11.9–13.7 t/s ≈ baseline.
- n-max 3 chậm hơn n-max 2 (chốt không dùng).
- Lần chạy đầu sau restart chậm (page-in file 44.5 GB): ~8–10 t/s, bình thường sau vài request.
- Acceptance rất ổn định với cùng prompt/temperature (đúng từng con số giữa các lần đo).

## Lưu ý serve

- Restart bằng `powershell -ExecutionPolicy Bypass -File 'D:\GitHub\Strata\.orca\ornith122b-serve.ps1'`
- llama.cpp ghi log vào **stderr** — file `.err` mới chứa timing (`serve.log`/stdout gần như rỗng).
- Request phải gửi UTF-8 bytes (PowerShell string body làm hỏng encoding — xem launcher test cũ).
