"""tools/test_unpad_down.py - tests for tools/unpad_down.py (ds4 "Q4KDownPad768" GGUF -> a GGUF Strata can pack).

    STRATA_GGUF_PY=<llama.cpp>/gguf-py python -m unittest discover -s tools -p test_unpad_down.py

The oracle is gguf-py's own dequantizers, never the repack's own unpacking.
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _paths import add_gguf_py  # noqa: E402

add_gguf_py()
import gguf  # noqa: E402
from gguf import GGMLQuantizationType as Q, quants  # noqa: E402

import unpad_down as U  # noqa: E402

TOL = 2.0 ** -9          # of the block's largest |value|: 3 * 2^-11 is the exact bound (see the pre-registration)


def make_q4k(rng, rows, nb=3):
    """Random but valid Q4_K rows: any bit pattern of scales and qs is valid; d/dmin are ordinary positive halves."""
    raw = rng.integers(0, 256, size=(rows, nb, 144), dtype=np.uint8)
    for col, lo, hi in ((0, 0.002, 0.03), (2, 0.0005, 0.01)):
        h = rng.uniform(lo, hi, size=(rows, nb)).astype(np.float16)
        raw[:, :, col:col + 2] = h.view(np.uint8).reshape(rows, nb, 2)
    return raw.reshape(rows, nb * 144)


def blockwise_error(src_vals, out_vals):
    """max over 32-value blocks of |delta| / max|source block| (blocks whose source is all zero are skipped)."""
    s = src_vals.reshape(-1, 32)
    o = out_vals.reshape(-1, 32)
    worst = 0.0
    scale = np.abs(s).max(axis=1)
    err = np.abs(s - o).max(axis=1)
    ok = scale > 0
    if ok.any():
        worst = float((err[ok] / scale[ok]).max())
    return worst, float(err[~ok].max()) if (~ok).any() else 0.0


class Repack(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(1234)
        self.src = make_q4k(self.rng, rows=24)

    def test_values_survive_the_repack(self):
        out = U.q4k_to_q5_1(self.src, 640)
        a = quants.dequantize(self.src, Q.Q4_K).reshape(24, 768)[:, :640]
        b = quants.dequantize(out, Q.Q5_1).reshape(24, 640)
        rel, absolute = blockwise_error(a, b)
        self.assertLessEqual(rel, TOL, f"worst block error {rel:.2e} of its largest value")
        self.assertEqual(absolute, 0.0)

    def test_the_error_check_can_fail(self):
        # a repack that is off by one level in a block must exceed TOL, or the test above cannot catch a wrong mapping
        out = U.q4k_to_q5_1(self.src, 640).copy()
        out[:, 8] ^= 0x01        # one low nibble of the first block's quants
        a = quants.dequantize(self.src, Q.Q4_K).reshape(24, 768)[:, :640]
        b = quants.dequantize(out, Q.Q5_1).reshape(24, 640)
        rel, _ = blockwise_error(a, b)
        self.assertGreater(rel, TOL)

    def test_row_is_20_q5_1_blocks_and_keeps_the_leading_columns(self):
        out = U.q4k_to_q5_1(self.src, 640)
        self.assertEqual(out.shape, (24, 20 * 24))
        self.assertEqual(out.dtype, np.uint8)
        # the LAST 128 columns are the ones dropped: columns 0..639 match, so compare the first 32 exactly
        a = quants.dequantize(self.src, Q.Q4_K).reshape(24, 768)
        b = quants.dequantize(out, Q.Q5_1).reshape(24, 640)
        self.assertLessEqual(blockwise_error(a[:, :32], b[:, :32])[0], TOL)
        self.assertLessEqual(blockwise_error(a[:, 608:640], b[:, 608:640])[0], TOL)

    def test_leading_dimensions_are_kept(self):
        out = U.q4k_to_q5_1(self.src.reshape(2, 3, 4, 432), 640)
        self.assertEqual(out.shape, (2, 3, 4, 480))
        flat = U.q4k_to_q5_1(self.src, 640)
        self.assertTrue(np.array_equal(out.reshape(24, 480), flat))

    def test_bad_arguments_are_refused(self):
        with self.assertRaises(ValueError):
            U.q4k_to_q5_1(self.src, 641)          # not whole 32-blocks
        with self.assertRaises(ValueError):
            U.q4k_to_q5_1(self.src, 800)          # more than the row has
        with self.assertRaises(ValueError):
            U.q4k_to_q5_1(self.src[:, :431], 640)  # not whole Q4_K blocks


def write_fixture(path, *, block_count=3, nextn=1, down_type=Q.Q4_K):
    """A tiny GGUF shaped like the real file: layers 0-1 + an embedded MTP layer 2, ds4 keys, a tokenizer."""
    rng = np.random.default_rng(99)
    w = gguf.GGUFWriter(str(path), "qwen4exp")
    w.add_uint32("qwen4exp.block_count", block_count)
    w.add_uint32("qwen4exp.nextn_predict_layers", nextn)
    w.add_uint32("qwen4exp.expert_count", 2)
    w.add_uint32("ds4.qwen4.down.logical_input", 640)
    w.add_uint32("ds4.qwen4.down.physical_input", 768)
    w.add_string("ds4.orca.revision", "abc123")
    w.add_string("general.name", "fixture")
    w.add_string("tokenizer.ggml.model", "gpt2")
    w.add_array("tokenizer.ggml.tokens", ["alpha", "beta", "gamma", "δ"])
    w.add_array("tokenizer.ggml.token_type", [1, 1, 1, 3])
    tensors = {}
    for layer in range(3):
        if down_type == Q.Q4_K:
            down = make_q4k(rng, rows=2 * 4).reshape(2, 4, 432)
        else:
            down = rng.integers(0, 256, size=(2, 4, 480), dtype=np.uint8)
        tensors[f"blk.{layer}.ffn_down_exps.weight"] = (down, down_type)
        gate = rng.integers(0, 256, size=(2, 4, 68), dtype=np.uint8)           # 64 values of Q8_0
        tensors[f"blk.{layer}.ffn_gate_exps.weight"] = (gate, Q.Q8_0)
        tensors[f"blk.{layer}.attn_norm.weight"] = (rng.standard_normal(8).astype(np.float32), None)
    for name, (arr, qt) in tensors.items():
        if qt is None:
            w.add_tensor(name, arr)
        else:
            w.add_tensor(name, arr, raw_dtype=qt)
    w.write_header_to_file()
    w.write_kv_data_to_file()
    w.write_tensors_to_file()
    w.close()
    return tensors


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.src = self.dir / "in.gguf"
        self.dst = self.dir / "out.gguf"
        self.tensors = write_fixture(self.src)

    def tearDown(self):
        self.tmp.cleanup()

    def run_convert(self, **kw):
        return U.convert(self.src, self.dst, **kw)

    def test_metadata(self):
        self.run_convert()
        r = gguf.GGUFReader(str(self.dst))
        self.assertEqual(r.get_field("qwen4exp.block_count").contents(), 2)
        for k in r.fields:
            self.assertFalse(k.startswith("ds4."), k)
        self.assertNotIn("qwen4exp.nextn_predict_layers", r.fields)
        self.assertEqual(r.get_field("general.name").contents(), "fixture")
        self.assertEqual(r.get_field("tokenizer.ggml.tokens").contents(), ["alpha", "beta", "gamma", "δ"])
        self.assertEqual(r.get_field("tokenizer.ggml.token_type").contents(), [1, 1, 1, 3])
        self.assertEqual(r.get_field("qwen4exp.expert_count").contents(), 2)
        self.assertEqual(r.get_field("general.architecture").contents(), "qwen4exp")

    def test_tensors(self):
        self.run_convert()
        r = gguf.GGUFReader(str(self.dst))
        names = [t.name for t in r.tensors]
        self.assertFalse([n for n in names if n.startswith("blk.2.")], names)       # the MTP layer is gone
        self.assertEqual(sorted(names), sorted(n for n in self.tensors if not n.startswith("blk.2.")))
        for t in r.tensors:
            src_arr, src_type = self.tensors[t.name]
            if t.name.endswith("ffn_down_exps.weight"):
                self.assertEqual(t.tensor_type, Q.Q5_1, t.name)
                self.assertEqual([int(x) for x in t.shape], [640, 4, 2], t.name)
                a = quants.dequantize(src_arr, Q.Q4_K)[..., :640]
                b = quants.dequantize(np.asarray(t.data), Q.Q5_1)
                self.assertLessEqual(blockwise_error(a, b)[0], TOL, t.name)
            else:
                self.assertEqual(t.tensor_type, src_type if src_type is not None else Q.F32, t.name)
                self.assertTrue(np.array_equal(np.asarray(t.data).reshape(-1).view(np.uint8),
                                               np.asarray(src_arr).reshape(-1).view(np.uint8)), t.name)

    def test_manifest_reports_what_it_did(self):
        m = self.run_convert()
        self.assertEqual(m["blocks_in"], 3)
        self.assertEqual(m["blocks_out"], 2)
        self.assertEqual(m["down_tensors_converted"], 2)
        self.assertEqual(sorted(m["dropped_tensors"]),
                         sorted(n for n in self.tensors if n.startswith("blk.2.")))
        self.assertLessEqual(m["max_block_error"], TOL)

    def test_a_file_without_the_padding_is_refused(self):
        other = self.dir / "other.gguf"
        write_fixture(other, down_type=Q.Q5_1)
        with self.assertRaises(ValueError):
            U.convert(other, self.dir / "x.gguf")

    def test_a_file_without_an_embedded_mtp_layer_is_refused(self):
        other = self.dir / "nomtp.gguf"
        write_fixture(other, block_count=3, nextn=0)
        with self.assertRaises(ValueError):
            U.convert(other, self.dir / "y.gguf")

    def test_output_is_flushed_to_disk_as_it_goes(self):
        # the first real run wrote 600 MiB layers faster than the disk took them and the dirty pages pushed this PC's
        # free memory to 379 MB, so the writer must fsync every `sync_bytes` bytes, not only at the end
        import os
        from unittest import mock
        with mock.patch("os.fsync", wraps=os.fsync) as fs:
            self.run_convert(sync_bytes=1)
        kept = sum(1 for n in self.tensors if not n.startswith("blk.2."))
        self.assertGreaterEqual(fs.call_count, kept)

    def test_the_default_still_syncs_once_at_the_end(self):
        import os
        from unittest import mock
        with mock.patch("os.fsync", wraps=os.fsync) as fs:
            self.run_convert()
        self.assertGreaterEqual(fs.call_count, 1)

    def test_the_output_is_not_overwritten(self):
        self.dst.write_bytes(b"x")
        with self.assertRaises(FileExistsError):
            self.run_convert()
        self.assertEqual(self.dst.read_bytes(), b"x")


if __name__ == "__main__":
    unittest.main()
