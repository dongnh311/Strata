#!/usr/bin/env python3
"""tools/unpad_down.py - a ds4 "Q4KDownPad768" Qwen3.8-Flash-Next GGUF -> a GGUF that tools/iq_pack.py can pack for Strata.

    python tools/unpad_down.py IN.gguf OUT.gguf [--keep 640] [--samples 4]

The files ds4 writes for this model differ from what Strata reads in two ways:

  * 49 blocks: the 48 trunk blocks plus the MTP layer (`blk.48.*`, `qwen4exp.nextn_predict_layers` 1).  Strata builds its
    own MTP runtime from the original model's draft layer (docs/ORCA.md), so the embedded layer is dropped and
    `qwen4exp.block_count` becomes 48.
  * the routed down projections are Q4_K with a PHYSICAL input of 768 for the logical 640 (`ds4.qwen4.down.*`): Q4_K needs
    blocks of 256 and 640 is 2.5 of them, so ds4 pads each row with 128 columns that meet zero activations.  The engine
    refuses that geometry (`native_expert.cpp`: "expert geometry is not whole blocks"; the qwen4exp schema is 640 wide).

Each down tensor is rewritten [768,2560,512] Q4_K -> [640,2560,512] Q5_1 by repacking the blocks, not by requantizing.
A Q4_K sub-block of 32 values is  A*q - B  with q in 0..15 (A = d*sc, B = dmin*m, both exact products in float32) and a
Q5_1 block is  d*q + m  with a 5-bit q, so d = A, m = -B and q is copied unchanged (fifth bit 0).  The only change to a
weight is rounding A and B to fp16 (relative 2^-11).  Q5_1 is 6 bits per value against Q4_K's 4.5: the down experts grow
from 26.1 to 28.1 GiB.  Every other tensor is copied byte for byte and the `ds4.*` metadata is dropped.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import time

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _paths import add_gguf_py  # noqa: E402

add_gguf_py()
import gguf  # noqa: E402
from gguf import GGMLQuantizationType as Q, GGUFValueType, quants  # noqa: E402

Q4K_BYTES, Q4K_VALUES = 144, 256
Q51_BYTES, Q51_VALUES = 24, 32
TOL = 2.0 ** -9            # of a 32-value block's largest |value|; the exact bound is 3 * 2^-11 (docs: pre-registration)
PADDED_IN, LOGICAL_IN = 768, 640
CHUNK_EXPERTS = 8          # experts repacked at a time: ~16 MB of temporaries

_BLOCK = re.compile(r"^blk\.(\d+)\.")
_DOWN = re.compile(r"^blk\.(\d+)\.ffn_down_exps\.weight$")


def q4k_to_q5_1(raw, keep_values: int = LOGICAL_IN) -> np.ndarray:
    """Q4_K rows (uint8, last axis = whole 144-byte blocks) -> Q5_1 rows of the first `keep_values` values of each row."""
    raw = np.asarray(raw)
    if raw.dtype != np.uint8:
        raise ValueError(f"expected raw bytes (uint8), got {raw.dtype}")
    if keep_values <= 0 or keep_values % Q51_VALUES:
        raise ValueError(f"keep_values {keep_values} is not a whole number of 32-value blocks")
    if raw.shape[-1] % Q4K_BYTES:
        raise ValueError(f"a row of {raw.shape[-1]} bytes is not whole Q4_K blocks ({Q4K_BYTES} bytes)")
    nb = raw.shape[-1] // Q4K_BYTES
    if keep_values > nb * Q4K_VALUES:
        raise ValueError(f"keep_values {keep_values} is more than the {nb * Q4K_VALUES} values in a row")
    lead = raw.shape[:-1]
    blk = np.ascontiguousarray(raw).reshape(-1, nb, Q4K_BYTES)
    n = blk.shape[0]
    d = np.ascontiguousarray(blk[:, :, 0:2]).view(np.float16).reshape(n, nb).astype(np.float32)
    dmin = np.ascontiguousarray(blk[:, :, 2:4]).view(np.float16).reshape(n, nb).astype(np.float32)
    s = blk[:, :, 4:16]
    sc = np.empty((n, nb, 8), np.uint8)
    mn = np.empty((n, nb, 8), np.uint8)
    # ggml get_scale_min_k4: sub-blocks 0-3 keep their 6 bits in bytes 0-3 / 4-7, sub-blocks 4-7 split them
    sc[:, :, :4] = s[:, :, 0:4] & 63
    mn[:, :, :4] = s[:, :, 4:8] & 63
    sc[:, :, 4:] = (s[:, :, 8:12] & 0x0F) | ((s[:, :, 0:4] >> 6) << 4)
    mn[:, :, 4:] = (s[:, :, 8:12] >> 4) | ((s[:, :, 4:8] >> 6) << 4)
    qs = blk[:, :, 16:144].reshape(n, nb, 4, 32)
    q = np.empty((n, nb, 8, 32), np.uint8)
    q[:, :, 0::2, :] = qs & 0x0F           # the 64 values of a group: low nibbles are the first 32 ...
    q[:, :, 1::2, :] = qs >> 4             # ... high nibbles the next 32
    n_sub = keep_values // Q51_VALUES
    a = (d[:, :, None] * sc).reshape(n, nb * 8)[:, :n_sub]          # A = d*sc: exact in float32
    b = (dmin[:, :, None] * mn).reshape(n, nb * 8)[:, :n_sub]       # B = dmin*m
    with np.errstate(over="ignore"):
        d5 = a.astype(np.float16)
        m5 = (-b).astype(np.float16)
    if not (np.isfinite(d5).all() and np.isfinite(m5).all()):
        raise ValueError("a block scale does not fit fp16")
    q5 = q.reshape(n, nb * 8, 32)[:, :n_sub]
    out = np.zeros((n, n_sub, Q51_BYTES), np.uint8)
    out[:, :, 0:2] = np.ascontiguousarray(d5).view(np.uint8).reshape(n, n_sub, 2)
    out[:, :, 2:4] = np.ascontiguousarray(m5).view(np.uint8).reshape(n, n_sub, 2)
    # bytes 4-7 (the fifth bits) stay 0: every q is 0..15.  Q5_1 packs value j (j<16) in the low nibble of byte j and j+16 in the high one
    out[:, :, 8:24] = q5[:, :, :16] | (q5[:, :, 16:] << 4)
    return out.reshape(*lead, n_sub * Q51_BYTES)


Q41_BYTES = 20


def q4k_to_q4_1(raw, keep_values: int = LOGICAL_IN) -> np.ndarray:
    """Q4_K rows -> Q4_1 rows: the q5_1 repack without its fifth bits.  Q4_1 is  d*q + m  with a 4-bit q, the same
    fp16 d and m and the same nibble order as Q5_1, so every weight decodes to the bit-identical value of the q5_1 file
    at 5 bits per value instead of 6 (the down experts shrink from 28.1 to 23.4 GiB)."""
    q5 = q4k_to_q5_1(raw, keep_values)
    lead = q5.shape[:-1]
    b = q5.reshape(-1, Q51_BYTES)
    if b[:, 4:8].any():
        raise AssertionError("a q5_1 fifth bit is set: the Q4_K repack produced q > 15")
    return np.concatenate([b[:, 0:4], b[:, 8:24]], axis=1).reshape(*lead, -1)


# --- the Q2K file's own rows, trimmed.  A Q2_K block is scales[16] (4-bit scale | 4-bit min per 16 values), qs[64]
# (2-bit codes; qs[0:32] hold values 0..127, qs[32:64] values 128..255), fp16 d, fp16 dmin = 84 bytes per 256 values.
# A down row of 640 values is 2 whole blocks and the first half of a third: the third keeps scales[0:8], qs[0:32] and
# d/dmin (44 bytes, in that order), so the row is 212 bytes instead of the padded 252 and every kept byte is the
# source's.  The same idea as ds4's trimmed Q4_K rows (ds4.c q4k_row_bytes), with Q2_K's field order.
Q2K_BYTES, Q2K_HALF = 84, 44


def kquant_row_bytes(qt, n: int) -> int:
    """Bytes of one row of `n` values: whole blocks, then a short block (Q2_K: 128 values) when the row ends inside one."""
    if qt != Q.Q2_K:
        raise ValueError(f"no trimmed row rule for {getattr(qt, 'name', qt)}")
    if n <= 0 or n % 128:
        raise ValueError(f"a Q2_K row of {n} values is not a whole number of 128-value halves")
    return n // 256 * Q2K_BYTES + (Q2K_HALF if n % 256 else 0)


def q2k_trim(raw, keep_values: int = LOGICAL_IN) -> np.ndarray:
    """Padded Q2_K rows (uint8, last axis = whole 84-byte blocks) -> trimmed rows of the first `keep_values` values."""
    raw = np.asarray(raw)
    if raw.dtype != np.uint8:
        raise ValueError(f"expected raw bytes (uint8), got {raw.dtype}")
    if raw.shape[-1] % Q2K_BYTES:
        raise ValueError(f"a row of {raw.shape[-1]} bytes is not whole Q2_K blocks ({Q2K_BYTES} bytes)")
    row = kquant_row_bytes(Q.Q2_K, keep_values)
    if keep_values > raw.shape[-1] // Q2K_BYTES * 256:
        raise ValueError(f"{keep_values} values asked of rows that hold {raw.shape[-1] // Q2K_BYTES * 256}")
    full = keep_values // 256 * Q2K_BYTES
    if row == full:
        return np.ascontiguousarray(raw[..., :full])
    last = raw[..., full:full + Q2K_BYTES]
    return np.concatenate([raw[..., :full], last[..., 0:8], last[..., 16:48], last[..., 80:84]], axis=-1)


def q2k_untrim(rows, n: int = LOGICAL_IN) -> np.ndarray:
    """Trimmed rows -> whole Q2_K blocks for gguf-py's dequantizer: the short block's missing half gets zero scales, mins
    and codes, so it decodes to zeros (a check only; the engine reads the trimmed rows as they are)."""
    rows = np.asarray(rows)
    row = kquant_row_bytes(Q.Q2_K, n)
    if rows.shape[-1] != row:
        raise ValueError(f"rows of {rows.shape[-1]} bytes, expected {row} for {n} values")
    full = n // 256 * Q2K_BYTES
    if row == full:
        return rows
    tail = rows[..., full:]
    block = np.zeros(rows.shape[:-1] + (Q2K_BYTES,), np.uint8)
    block[..., 0:8], block[..., 16:48], block[..., 80:84] = tail[..., 0:8], tail[..., 8:40], tail[..., 40:44]
    return np.concatenate([rows[..., :full], block], axis=-1)


def q2k_check(src_rows: np.ndarray, out_rows: np.ndarray, keep_values: int = LOGICAL_IN) -> tuple[float, float]:
    """(0.0 if every kept value equals the source's bit for bit, else inf; largest |value| in the dropped columns)."""
    a = quants.dequantize(np.ascontiguousarray(src_rows), Q.Q2_K)
    b = quants.dequantize(q2k_untrim(out_rows, keep_values), Q.Q2_K)[..., :keep_values]
    same = np.array_equal(a[..., :keep_values].view(np.uint32), b.view(np.uint32))
    return (0.0 if same else float("inf")), float(np.abs(a[..., keep_values:]).max()) if a.shape[-1] > keep_values else 0.0


# --- smaller down types.  q5_1 above is a repack (no loss beyond fp16).  The two below re-quantize the dequantized values:
# q4_0 (4.5 bits per weight) and q2_0 (2.25: Strata's own 64-value blocks, grid {-1,0,1,2} x d, fp16 d, as tools/mtp_pack.py
# writes them for the MTP head and as the base model's experts are stored).  They exist because the expert arena of the
# q5_1 file (47.5 GiB) does not fit this PC's RAM beside a 512K context.
CODECS = {"q5_1": (Q.Q5_1, Q51_VALUES, Q51_BYTES), "q4_1": (Q.Q4_1, 32, Q41_BYTES), "q4_0": (Q.Q4_0, 32, 18),
          "q2_0": (Q.Q2_0, 64, 18), "q2_k": (Q.Q2_K, 128, None)}   # q2_k: row bytes by kquant_row_bytes
LOSSLESS = {"q5_1": (q4k_to_q5_1, Q.Q5_1), "q4_1": (q4k_to_q4_1, Q.Q4_1)}   # repacks of a Q4_K source: no re-quantization
EXACT = {"q5_1": "q4_k", "q4_1": "q4_k", "q2_k": "q2_k"}   # the codecs that keep the source's weights, and their source type


def down_row_bytes(codec: str, keep_values: int) -> int:
    _, per_block, block_bytes = CODECS[codec]
    if codec == "q2_k":
        return kquant_row_bytes(Q.Q2_K, keep_values)
    if keep_values <= 0 or keep_values % per_block:
        raise ValueError(f"keep_values {keep_values} is not a whole number of {per_block}-value {codec} blocks")
    return keep_values // per_block * block_bytes


def encode_q2_0(w: np.ndarray) -> np.ndarray:
    """[..., n] float32 (n a multiple of 64) -> flat uint8 Q2_0 blocks: fp16 d, 16 bytes of 2-bit codes (code = q + 1, 4 per
    byte, q in -1..2).  d is the scale among 17 candidates (amax/2 .. amax) that minimizes the squared error, as in
    tools/mtp_pack.py q2_0; the codes are computed against the STORED fp16 scale."""
    x = np.asarray(w, dtype=np.float32).reshape(-1, 64)
    amax = np.abs(x).max(axis=1, keepdims=True)
    best_err = np.full((x.shape[0], 1), np.inf, dtype=np.float32)
    best_d = np.zeros_like(amax)
    for f in np.linspace(0.5, 1.0, 17, dtype=np.float32):
        d = amax * f
        inv = np.where(d > 0, 1.0 / np.where(d > 0, d, 1.0), 0.0)
        q = np.clip(np.rint(x * inv), -1, 2)
        err = ((q * d - x) ** 2).sum(axis=1, keepdims=True)
        better = err < best_err
        best_err = np.where(better, err, best_err)
        best_d = np.where(better, d, best_d)
    d16 = best_d.astype(np.float16)
    d = d16.astype(np.float32)
    inv = np.where(d > 0, 1.0 / np.where(d > 0, d, 1.0), 0.0)
    codes = (np.clip(np.rint(x * inv), -1, 2) + 1).astype(np.uint8).reshape(-1, 16, 4)
    out = np.empty((x.shape[0], 18), dtype=np.uint8)
    out[:, :2] = d16.view(np.uint8).reshape(-1, 2)
    out[:, 2:] = codes[:, :, 0] | (codes[:, :, 1] << 2) | (codes[:, :, 2] << 4) | (codes[:, :, 3] << 6)
    return out.reshape(-1)


def decode_q2_0(blocks: np.ndarray) -> np.ndarray:
    """[..., nb*18] uint8 -> [..., nb*64] float32 (the inverse of encode_q2_0; used for the sampled error check)."""
    b = np.ascontiguousarray(blocks).reshape(-1, 18)
    d = np.ascontiguousarray(b[:, :2]).view(np.float16).reshape(-1, 1).astype(np.float32)
    c = b[:, 2:]
    codes = np.stack([(c >> s) & 3 for s in (0, 2, 4, 6)], axis=-1).reshape(-1, 64).astype(np.float32)
    return ((codes - 1.0) * d).reshape(*blocks.shape[:-1], -1)


SOURCES = {"q4_k": Q.Q4_K, "q2_k": Q.Q2_K}      # the padded down types ds4 writes (the Q4K file and the Q2K file of the same repo)


def q4k_to_codec(raw, keep_values: int = LOGICAL_IN, codec: str = "q5_1", src_type: str = "q4_k") -> np.ndarray:
    """Padded K-quant rows -> rows of the first `keep_values` values in `codec` ("q5_1" / "q4_1" repacks, Q4_K source only; "q4_0" and
    "q2_0" re-quantize the dequantized values, from Q4_K or Q2_K)."""
    if codec not in CODECS:
        raise ValueError(f"unknown down codec {codec!r} (choose from {sorted(CODECS)})")
    if src_type not in SOURCES:
        raise ValueError(f"unknown source type {src_type!r} (choose from {sorted(SOURCES)})")
    if codec == "q2_k":
        if src_type != "q2_k":
            raise ValueError("q2_k keeps a Q2_K file's own rows: the source must be Q2_K")
        return q2k_trim(raw, keep_values)
    if codec in LOSSLESS:
        if src_type != "q4_k":
            raise ValueError(f"the lossless {codec} repack exists for a Q4_K source only")
        return LOSSLESS[codec][0](raw, keep_values)
    _, per_block, block_bytes = CODECS[codec]
    if keep_values <= 0 or keep_values % per_block:
        raise ValueError(f"keep_values {keep_values} is not a whole number of {per_block}-value {codec} blocks")
    vals = quants.dequantize(np.ascontiguousarray(raw), SOURCES[src_type])[..., :keep_values].astype(np.float32)
    if codec == "q4_0":
        return np.asarray(quants.quantize(vals, Q.Q4_0))
    return encode_q2_0(vals).reshape(*vals.shape[:-1], keep_values // per_block * block_bytes)


def _encode_job(job):
    raw, keep_values, codec, src_type = job
    return q4k_to_codec(raw, keep_values, codec, src_type)


def make_pool(workers: int):
    from concurrent.futures import ProcessPoolExecutor
    return ProcessPoolExecutor(max_workers=workers)


def encode_experts(pool, raw: np.ndarray, keep_values: int, codec: str, src_type: str = "q4_k") -> np.ndarray:
    """(experts, rows, bytes) -> (experts, rows, bytes') with one expert per job on the worker processes."""
    jobs = [(np.ascontiguousarray(raw[e]), keep_values, codec, src_type) for e in range(raw.shape[0])]
    return np.stack(list(pool.map(_encode_job, jobs, chunksize=4)))


def lossy_check(src_rows: np.ndarray, out_rows: np.ndarray, keep_values: int, codec: str,
                src_type: str = "q4_k") -> tuple[float, float]:
    """(relative RMS error of the kept columns, largest |value| in the dropped columns) for one expert's rows."""
    a = quants.dequantize(src_rows, SOURCES[src_type])
    b = quants.dequantize(out_rows, Q.Q4_0) if codec == "q4_0" else decode_q2_0(out_rows)
    ref = a[..., :keep_values]
    rms = float(np.sqrt(((ref - b) ** 2).mean() / max((ref ** 2).mean(), 1e-30)))
    return rms, (float(np.abs(a[..., keep_values:]).max()) if a.shape[-1] > keep_values else 0.0)


def _block_error(src_vals: np.ndarray, out_vals: np.ndarray) -> float:
    """max over 32-value blocks of |delta| / max|source block| (a block of zeros must stay zeros)."""
    s = src_vals.reshape(-1, 32)
    o = out_vals.reshape(-1, 32)
    scale = np.abs(s).max(axis=1)
    err = np.abs(s - o).max(axis=1)
    zero = scale == 0
    if (err[zero] > 0).any():
        return float("inf")
    return float((err[~zero] / scale[~zero]).max()) if (~zero).any() else 0.0


def check_experts(src_rows: np.ndarray, out_rows: np.ndarray, keep_values: int = LOGICAL_IN,
                  codec: str = "q5_1") -> tuple[float, float]:
    """(worst block error, largest |value| in the dropped columns) for some experts, by gguf-py's dequantizers."""
    a = quants.dequantize(src_rows, Q.Q4_K)
    b = quants.dequantize(out_rows, LOSSLESS[codec][1])
    tail = float(np.abs(a[..., keep_values:]).max()) if a.shape[-1] > keep_values else 0.0
    return _block_error(a[..., :keep_values], b), tail


def _field(reader, key):
    f = reader.get_field(key)
    return None if f is None else f.contents()


def _release_read_pages() -> None:
    """Hand the pages of the memory-mapped source back to Windows.  They stay in this process's working set once read,
    and the 51.6 GiB source drove the PC's available memory to 0.7 GiB halfway through a run; trimmed, they are clean
    file pages on the standby list, which Windows counts as available and reuses at once.  A no-op elsewhere."""
    if os.name != "nt":
        return
    import ctypes
    k32 = ctypes.windll.kernel32
    k32.GetCurrentProcess.restype = ctypes.c_void_p
    k32.SetProcessWorkingSetSize.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t]
    k32.SetProcessWorkingSetSize(k32.GetCurrentProcess(), ctypes.c_size_t(-1).value, ctypes.c_size_t(-1).value)


def _sync(writer) -> None:
    for f in writer.fout:
        f.flush()
        os.fsync(f.fileno())
    _release_read_pages()


def convert(src, dst, *, keep_values: int = LOGICAL_IN, samples: int = 4, progress=None,
            sync_bytes: int = 256 << 20, split=None, down: str = "q5_1", workers: int = 1) -> dict:
    """`sync_bytes`: flush the output to disk after this many bytes.  The first real run (53 GiB, 600 MiB layers) wrote
    faster than the disk took it, the dirty pages piled up and this PC's free memory fell to 379 MB.
    `split` = (count, tensors): write split.no 0 / split.count / split.tensors.count so that the file is "shard 1 of
    `count`" next to the PLE table's own GGUF, which Strata's native loader requires (native_dense.cpp:88-99); `tensors`
    is the total over both files (this file's tensors + the PLE table's 1).
    `down`: the type of the rewritten down experts - "q5_1" or "q4_1" (repacks, no loss), "q4_0" or "q2_0" (re-quantized; `workers`
    processes share the work, one expert per job)."""
    src, dst = pathlib.Path(src), pathlib.Path(dst)
    if down not in CODECS:
        raise ValueError(f"unknown down codec {down!r} (choose from {sorted(CODECS)})")
    down_qt = CODECS[down][0]
    row_out = down_row_bytes(down, keep_values)
    if dst.exists():
        raise FileExistsError(f"{dst} exists; refusing to overwrite it")
    reader = gguf.GGUFReader(str(src), "r")
    if _field(reader, "general.architecture") != "qwen4exp":
        raise ValueError("not a qwen4exp GGUF")
    blocks_in = int(_field(reader, "qwen4exp.block_count"))
    nextn = int(_field(reader, "qwen4exp.nextn_predict_layers") or 0)
    if nextn < 1:
        raise ValueError("no embedded MTP layer (qwen4exp.nextn_predict_layers is absent or 0): this tool is for ds4's 49-block files")
    blocks_out = blocks_in - nextn

    plan = []                      # (tensor, action)  action: "copy" | "down" | "drop"
    n_down = 0
    src_type = None                # "q4_k" or "q2_k": what the padded down experts of the source file are
    dropped_names = []
    for t in reader.tensors:
        m = _BLOCK.match(t.name)
        if m and int(m.group(1)) >= blocks_out:
            dropped_names.append(t.name)
            plan.append((t, "drop"))
            continue
        if _DOWN.match(t.name):
            dims = [int(x) for x in t.shape]
            kind = {Q.Q4_K: "q4_k", Q.Q2_K: "q2_k"}.get(t.tensor_type)
            if kind is None or dims[0] != PADDED_IN:
                raise ValueError(f"{t.name} is {t.tensor_type.name} {dims}, expected a padded Q4_K or Q2_K [{PADDED_IN}, rows, experts]")
            if src_type not in (None, kind):
                raise ValueError(f"{t.name} is {kind} but an earlier down tensor was {src_type}")
            src_type = kind
            plan.append((t, "down"))
            n_down += 1
        else:
            plan.append((t, "copy"))
    if n_down == 0:
        raise ValueError("no routed down tensors found")
    if down in EXACT and src_type != EXACT[down]:
        raise ValueError(f"--down {down} keeps the weights of a {EXACT[down].upper()} source only, this file's down "
                         f"experts are {src_type.upper()}; use --down q4_0 or q2_0 to re-quantize")

    writer = gguf.GGUFWriter(str(dst), "qwen4exp")
    for field in reader.fields.values():
        name = field.name
        if name == "general.architecture" or name.startswith("GGUF.") or name.startswith("ds4.") \
                or name == "qwen4exp.nextn_predict_layers":
            continue
        if name == "general.alignment":
            writer.add_custom_alignment(int(field.contents()))
            continue
        vtype = field.types[0]
        sub = field.types[-1] if vtype == GGUFValueType.ARRAY else None
        if name == "qwen4exp.block_count":
            writer.add_uint32(name, blocks_out)
        else:
            writer.add_key_value(name, field.contents(), vtype, sub_type=sub)

    if split:
        writer.add_uint16("split.no", 0)
        writer.add_uint16("split.count", int(split[0]))
        writer.add_int32("split.tensors.count", int(split[1]))

    for t, action in plan:
        if action == "drop":
            continue
        if action == "down":
            shp = list(t.data.shape)                      # (experts, rows, 3 blocks of 144 bytes)
            nbytes = shp[0] * shp[1] * row_out
            if down == "q2_k":
                # gguf-py derives the element shape from whole blocks (212 bytes -> 512 values, quants.py); give it the
                # element shape instead (a non-uint8 dtype skips that derivation) and the true byte count
                writer.add_tensor_info(t.name, (shp[0], shp[1], keep_values), np.dtype(np.int8), nbytes, down_qt)
            else:
                writer.add_tensor_info(t.name, (shp[0], shp[1], row_out), np.dtype(np.uint8), nbytes, down_qt)
        else:
            writer.add_tensor_info(t.name, t.data.shape, t.data.dtype, t.data.nbytes, t.tensor_type)

    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_ti_data_to_file()

    worst, worst_rms, tail_max, done, pending = 0.0, 0.0, 0.0, 0, 0
    rng = np.random.default_rng(0)
    t0 = time.time()
    pool = make_pool(workers) if workers > 1 and down not in EXACT else None
    try:
        for t, action in plan:
            if action == "drop":
                continue
            if action == "copy":
                writer.write_tensor_data(t.data, tensor_endianess=reader.endianess)
                pending += t.data.nbytes
                if pending >= sync_bytes:
                    _sync(writer)
                    pending = 0
                continue
            experts, rows, _ = t.data.shape
            if pool is not None:
                out = encode_experts(pool, t.data, keep_values, down, src_type)
            else:
                out = np.empty((experts, rows, row_out), np.uint8)
                for e0 in range(0, experts, CHUNK_EXPERTS):
                    out[e0:e0 + CHUNK_EXPERTS] = q4k_to_codec(t.data[e0:e0 + CHUNK_EXPERTS], keep_values, down, src_type)
            pick = np.unique(np.concatenate([[0, experts - 1], rng.integers(0, experts, size=max(0, samples - 2))])) if samples else []
            for e in pick:
                if down in EXACT:
                    if down == "q2_k":
                        err, tail = q2k_check(np.asarray(t.data[e]), out[e], keep_values)
                    else:
                        err, tail = check_experts(np.asarray(t.data[e]), out[e], keep_values, down)
                    worst, tail_max = max(worst, err), max(tail_max, tail)
                    if err > TOL:
                        writer.close()
                        raise RuntimeError(f"{t.name} expert {e}: block error {err:.3e} > {TOL:.3e}; {dst} is incomplete")
                else:
                    rms, tail = lossy_check(np.asarray(t.data[e]), out[e], keep_values, down, src_type)
                    worst_rms, tail_max = max(worst_rms, rms), max(tail_max, tail)
            writer.write_tensor_data(out, tensor_endianess=reader.endianess)
            pending += out.nbytes
            if pending >= sync_bytes:
                _sync(writer)
                pending = 0
            done += 1
            if progress:
                progress(done, n_down, t.name, time.time() - t0, worst if down in EXACT else worst_rms)
        _sync(writer)
        writer.close()
    finally:
        if pool is not None:
            pool.shutdown()
    return {"source": src.name, "output": dst.name, "blocks_in": blocks_in, "blocks_out": blocks_out, "down": down,
            "source_down_type": src_type,
            "down_tensors_converted": n_down, "dropped_tensors": dropped_names, "keep_values": keep_values,
            "max_block_error": worst, "max_rms_error": worst_rms, "dropped_tail_max_abs": tail_max,
            "samples_per_tensor": samples, "tolerance": TOL}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("src", type=pathlib.Path)
    ap.add_argument("dst", type=pathlib.Path)
    ap.add_argument("--keep", type=int, default=LOGICAL_IN, help="values kept per down row (default 640)")
    ap.add_argument("--samples", type=int, default=4, help="experts per down tensor compared against the source (default 4)")
    ap.add_argument("--sync-mib", type=int, default=256, help="flush the output to disk every N MiB (default 256)")
    ap.add_argument("--split", nargs=2, type=int, metavar=("COUNT", "TENSORS"),
                    help="write split.no 0 / split.count COUNT / split.tensors.count TENSORS (the file becomes shard 1 of "
                         "COUNT beside the PLE table's GGUF: 2 1224 for the PLE shard of the GSQ-RCO Q2_0 model)")
    ap.add_argument("--down", choices=sorted(CODECS), default="q5_1",
                    help="type of the rewritten down experts: q5_1 = lossless repack (default), q4_1 = the same weights in 5 bits instead of 6, q2_k = a Q2K file's own rows without the padding (byte for byte), q4_0 / q2_0 = re-quantized, smaller")
    ap.add_argument("--workers", type=int, default=1, help="worker processes for q4_0 / q2_0 (default 1)")
    a = ap.parse_args(argv)

    def progress(done, total, name, secs, worst):
        what = "worst block error" if a.down in EXACT else "worst relative RMS error"
        print(f"  [{done:2d}/{total}] {name}  {secs:6.0f}s  {what} so far {worst:.2e}", flush=True)

    m = convert(a.src, a.dst, keep_values=a.keep, samples=a.samples, progress=progress, sync_bytes=a.sync_mib << 20,
                split=tuple(a.split) if a.split else None, down=a.down, workers=a.workers)
    a.dst.with_suffix(a.dst.suffix + ".json").write_text(json.dumps(m, indent=1), encoding="utf-8")
    err = (f"worst sampled block error {m['max_block_error']:.2e} (limit {m['tolerance']:.2e})" if m["down"] in EXACT
           else f"worst sampled relative RMS error {m['max_rms_error']:.3f}")
    print(f"done: {m['down_tensors_converted']} down tensors rewritten as {m['down']}, {len(m['dropped_tensors'])} MTP tensors dropped, "
          f"blocks {m['blocks_in']} -> {m['blocks_out']}, {err}, largest value in the dropped columns {m['dropped_tail_max_abs']:.3g}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
