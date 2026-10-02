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


def check_experts(src_rows: np.ndarray, out_rows: np.ndarray, keep_values: int = LOGICAL_IN) -> tuple[float, float]:
    """(worst block error, largest |value| in the dropped columns) for some experts, by gguf-py's dequantizers."""
    a = quants.dequantize(src_rows, Q.Q4_K)
    b = quants.dequantize(out_rows, Q.Q5_1)
    tail = float(np.abs(a[..., keep_values:]).max()) if a.shape[-1] > keep_values else 0.0
    return _block_error(a[..., :keep_values], b), tail


def _field(reader, key):
    f = reader.get_field(key)
    return None if f is None else f.contents()


def _sync(writer) -> None:
    for f in writer.fout:
        f.flush()
        os.fsync(f.fileno())


def convert(src, dst, *, keep_values: int = LOGICAL_IN, samples: int = 4, progress=None,
            sync_bytes: int = 256 << 20) -> dict:
    """`sync_bytes`: flush the output to disk after this many bytes.  The first real run (53 GiB, 600 MiB layers) wrote
    faster than the disk took it, the dirty pages piled up and this PC's free memory fell to 379 MB."""
    src, dst = pathlib.Path(src), pathlib.Path(dst)
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
    down = dropped = 0
    dropped_names = []
    for t in reader.tensors:
        m = _BLOCK.match(t.name)
        if m and int(m.group(1)) >= blocks_out:
            dropped_names.append(t.name)
            plan.append((t, "drop"))
            continue
        if _DOWN.match(t.name):
            dims = [int(x) for x in t.shape]
            if t.tensor_type != Q.Q4_K or dims[0] != PADDED_IN:
                raise ValueError(f"{t.name} is {t.tensor_type.name} {dims}, expected the padded Q4_K [{PADDED_IN}, rows, experts]")
            plan.append((t, "down"))
            down += 1
        else:
            plan.append((t, "copy"))
    if down == 0:
        raise ValueError("no routed down tensors found")

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

    for t, action in plan:
        if action == "drop":
            continue
        if action == "down":
            shp = list(t.data.shape)                      # (experts, rows, 3 blocks of 144 bytes)
            row_out = keep_values // Q51_VALUES * Q51_BYTES
            nbytes = shp[0] * shp[1] * row_out
            writer.add_tensor_info(t.name, (shp[0], shp[1], row_out), np.dtype(np.uint8), nbytes, Q.Q5_1)
        else:
            writer.add_tensor_info(t.name, t.data.shape, t.data.dtype, t.data.nbytes, t.tensor_type)

    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_ti_data_to_file()

    worst, tail_max, done, pending = 0.0, 0.0, 0, 0
    rng = np.random.default_rng(0)
    t0 = time.time()
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
        out = np.empty((experts, rows, keep_values // Q51_VALUES * Q51_BYTES), np.uint8)
        for e0 in range(0, experts, CHUNK_EXPERTS):
            out[e0:e0 + CHUNK_EXPERTS] = q4k_to_q5_1(t.data[e0:e0 + CHUNK_EXPERTS], keep_values)
        pick = np.unique(np.concatenate([[0, experts - 1], rng.integers(0, experts, size=max(0, samples - 2))])) if samples else []
        for e in pick:
            err, tail = check_experts(np.asarray(t.data[e]), out[e], keep_values)
            worst, tail_max = max(worst, err), max(tail_max, tail)
            if err > TOL:
                writer.close()
                raise RuntimeError(f"{t.name} expert {e}: block error {err:.3e} > {TOL:.3e}; {dst} is incomplete")
        writer.write_tensor_data(out, tensor_endianess=reader.endianess)
        pending += out.nbytes
        if pending >= sync_bytes:
            _sync(writer)
            pending = 0
        done += 1
        if progress:
            progress(done, down, t.name, time.time() - t0, worst)
    _sync(writer)
    writer.close()
    return {"source": src.name, "output": dst.name, "blocks_in": blocks_in, "blocks_out": blocks_out,
            "down_tensors_converted": down, "dropped_tensors": dropped_names, "keep_values": keep_values,
            "max_block_error": worst, "dropped_tail_max_abs": tail_max, "samples_per_tensor": samples,
            "tolerance": TOL}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("src", type=pathlib.Path)
    ap.add_argument("dst", type=pathlib.Path)
    ap.add_argument("--keep", type=int, default=LOGICAL_IN, help="values kept per down row (default 640)")
    ap.add_argument("--samples", type=int, default=4, help="experts per down tensor compared against the source (default 4)")
    ap.add_argument("--sync-mib", type=int, default=256, help="flush the output to disk every N MiB (default 256)")
    a = ap.parse_args(argv)

    def progress(done, total, name, secs, worst):
        print(f"  [{done:2d}/{total}] {name}  {secs:6.0f}s  worst block error so far {worst:.2e}", flush=True)

    m = convert(a.src, a.dst, keep_values=a.keep, samples=a.samples, progress=progress, sync_bytes=a.sync_mib << 20)
    a.dst.with_suffix(a.dst.suffix + ".json").write_text(json.dumps(m, indent=1), encoding="utf-8")
    print(f"done: {m['down_tensors_converted']} down tensors repacked, {len(m['dropped_tensors'])} MTP tensors dropped, "
          f"blocks {m['blocks_in']} -> {m['blocks_out']}, worst sampled block error {m['max_block_error']:.2e} "
          f"(limit {m['tolerance']:.2e}), largest value in the dropped columns {m['dropped_tail_max_abs']:.3g}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
