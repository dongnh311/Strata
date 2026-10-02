# Running a ds4 "Q4KDownPad768" Qwen3.8-Flash-Next GGUF (manual setup, experimental)

For files made for antirez/ds4 (for example `...IQ2XXS-Q4KDownPad768-DenseQ4Kselimat-MTP.gguf`), which differ from what Strata reads in two ways:

1. **49 blocks**: the 48 trunk blocks plus an embedded MTP layer (`blk.48.*`, `qwen4exp.nextn_predict_layers` 1). Strata builds its MTP runtime from the original model's draft layer (docs/ORCA.md), so the embedded one is dropped.
2. **Routed down experts are Q4_K (or Q2_K) with a physical input of 768** for the logical 640 (`ds4.qwen4.down.*`). K-quants need blocks of 256 and 640 is 2.5 of them, so ds4 pads each row with 128 columns that meet zero activations.
   The native expert path needs `n_ff` to be whole blocks of the down type (`native_expert.cpp:46-49`) and refuses that geometry. In the file measured here the dropped columns hold exactly 0.

`tools/unpad_down.py` converts such a file into one `tools/iq_pack.py` can pack:

```sh
python tools/unpad_down.py IN.gguf  OUT-00001-of-00002.gguf  --split 2 1224            # lossless: Q4_K [768] -> Q5_1 [640]
python tools/unpad_down.py IN.gguf  OUT-00001-of-00002.gguf  --down q2_0 --workers 12 --split 2 1224   # 2-bit, re-quantized (smaller, NOT the same weights)
```

- `--down q5_1` (default, Q4_K source only) repacks block by block: a Q4_K sub-block is `A*q - B` with q in 0..15 and a Q5_1 block is `d*q + m`, so d = A, m = -B and q is copied. Only the fp16 rounding of A and B changes a weight
  (worst block 1.54e-3 of its largest value on the real file; the tool stops above 2^-9). Cost: 6 instead of 4.5 bits per value in the down experts.
- `--down q4_0` / `q2_0` re-quantize the dequantized values (`q2_0` = Strata's 64-value blocks as `tools/mtp_pack.py` writes them); both accept a Q2_K source too. These change the down weights.
- `--split COUNT TENSORS` writes `split.no/count/tensors.count` so that the file is "shard 1 of COUNT" beside the PLE table's GGUF; the loader requires it (`native_dense.cpp:88-99`). `TENSORS` = this file's tensors + 1 (the PLE table). The ds4 file has no `per_layer_token_embd.weight`:
  use the PLE shard of an existing Strata model, named `<name>-00002-of-00002.gguf` beside the converted file (a hard link is enough), and pack with `tools/iq_pack.py --gguf <name>-00001-of-00002.gguf --out packs/<name> --compat-bf16`.
- Everything else is copied byte for byte; `ds4.*` metadata is dropped. `python -m unittest discover -s tools -p test_unpad_down.py` (26 tests; the oracle is gguf-py's dequantizers and Strata's own Q2_0 decoder).

Measured on one PC (RTX 3060 12 GB, 47.7 GiB DDR4-2400, engine 0.1.34; experts 47.5 GiB with the lossless down, 29.9 GiB with `q2_0`):

| variant | experts in RAM | decode, 512K context (YaRN x2, `--kv q4_0`, no vision) |
|---|---|---|
| `q5_1` (lossless), `--resident-budget-gib 24`, rest read from the SSD | 24 GiB | 14-16 tok/s (calibrated `--spec-min-p 0.7 --pcie-frac 0`) |
| `q2_0` (re-quantized) | all | 28-33 tok/s at 1-20K, 30 at 100K and 199K, 27 at 398K |

Whether a re-quantized down projection keeps what a fine-tune put into it is not something this tool can promise: it reports only the numeric error. On ordinary prompts the `q2_0` file's greedy answers diverge from the lossless file's much more than the engine's own run-to-run noise.
