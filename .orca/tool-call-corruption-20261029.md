# Tool-call corruption — nguyên nhân & workaround (29/10/2026)

## Triệu chứng (Claude Code + OpenCode, model local `qwen38-q2_0-refusal`)

- Code trong tool-call `arguments` **mất sạch `[` `]`**: `data[:4096]` → `data:4096`,
  `out[i] ^= key[i % n]` → `outi ^= keyi % n`, `bytes([k])` → `bytes(k)`.
- Header call thành `<function=shell=` (dấu `<` đầu bị nuốt, `=+"` cuối thành `=`).
- Client báo `OpenAI Chat tool call delta is missing id or name`, session fail.
- Xảy ra ở phiên DÀI (~40–70K token), lặp liên tục nhiều ngày.

## Đã loại trừ bằng đo, không suy đoán

| Nghi phạm | Test | Kết quả |
|---|---|---|
| Engine Strata local | 8 tool-call ép copy nguyên văn 5 cặp `[]`, temp 0, stream + non-stream, 400 token | **8/8 exact** — engine không cắt bracket khi call đúng format |
| Control vector speed-projection (`:1.0`, mặc định ON cho mọi request — `server.py:1485` "Absent = on") | A/B 8 run trên + off | như nhau → **không phải thủ phạm** |
| Client OpenCode/Claude Code riêng lẻ | cả hai cùng lỗi, cùng chữ ký | không phải parser một client |
| Cloud cùng họ model | chính phiên này (qwen3.8-flash trên Token Plan) fail `missing id or name` đúng chữ ký | **họ model Qwen3.8-Flash, tầng model + protocol** |

## Kết luận

Context càng dài, model càng dễ **tự viết lại** markup `
`
bằng text thường thay vì phát đúng token đặc biệt (`<` `)` `]` rơi khỏi đường sampling greedy — chữ ký lossy quen thuộc của hàng 2-bit). OpenCode thấy markup giả trong content, "repair" thành tool call → bracket bị nuốt tiếp ở bước parse → call fail. Lỗi nằm ở **model khi context dài**, không ở Strata, vector, hay client.

## Workaround (theo thứ tự hiệu quả)

1. **Giữ phiên ngắn**: compact/restart trước ~32K token (đang là luật trong
   `~/.config/opencode/local-speed.md`). Đây là nguyên nhân số 1.
2. **Code nhiều bracket → file-first**: thay vì heredoc trong `command`,
   dùng tool Write tạo file rồi chạy `python file.py`. Arguments ngắn, ít `[] lồng nhau`.
3. Giảm nhiệt độ sampling của fork: **0.2–0.4** (card để trống `sampling` → fork mặc định cao)
   — thêm `"sampling": {"temperature": 0.3}` vào `strata-q2_0-v144-refusal.json`.
4. Session nào hay fail thì **thinking off**: per-request `reasoning_effort: "none"`,
   hoặc `thinking_off: true` trong shared-settings cho webchat.
5. Lặp lại được thì lặp: lỗi là stochastic, cùng câu lệnh chạy lại thường pass.
6. Nếu họ model này tiếp tục fail nhiều cho agent: cân nhắc pack **Coder IQ1_M**
   (pruned cho code) hoặc route tác vụ agent dài sang cloud.

## Ghi chú kỹ thuật

- `docs/DETAILS.md` mục Thinking levels; effort map trong `serve/frontend.py:132-150`
  (`none/off/minimal → tắt thinking`).
- Vector on/off per-request: gửi `experimental_speed_projection: false` trong sampling
  (webchat đã để `true` mặc định qua `strata-q2_0-v144-refusal.shared-settings.json`).
- Bản reproduce tool-call sạch 8/8: `C:\Users\ADMIN\AppData\Local\Temp\opencode\ab-toolcall.py`
  (model + heredoc ngắn, stream/non-stream × vector on/off).
