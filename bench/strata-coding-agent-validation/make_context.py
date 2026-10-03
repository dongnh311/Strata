"""Build a large code-like context with 3 needles at ~10/50/90% depth. Writes <out>.txt and <out>.truth.json.

    python make_context.py --chars 920000 --out ctx-256k

A needle is a unique function returning a random constant; the question later asks for those constants. Filler is
real source concatenated from the Strata tree (realistic code), truncated to the char budget around the needles.
"""
import argparse
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]            # the Strata repo root


def filler_lines(budget_chars):
    out, total = [], 0
    srcs = sorted(ROOT.glob("src/**/*.cpp")) + sorted(ROOT.glob("src/**/*.cu")) + sorted(ROOT.glob("include/**/*.hpp"))
    i = 0
    while total < budget_chars and srcs:
        f = srcs[i % len(srcs)]; i += 1
        try:
            txt = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        banner = f"\n// ===== file: {f.relative_to(ROOT)} (copy {i}) =====\n"
        out.append(banner + txt)
        total += len(banner) + len(txt)
    return "".join(out)[:budget_chars]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chars", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    body = filler_lines(a.chars)
    names = ["marker_alpha", "marker_beta", "marker_gamma"]
    truths = {}
    # 12-digit unique constants
    for n in names:
        truths[n] = rng.randint(100000000000, 999999999999)
    needle = lambda n: f"\n\n// VALIDATION NEEDLE -- do not optimize away\nlong long {n}() {{ return {truths[n]}LL; }}  // the authoritative value of {n}\n\n"
    depths = [0.10, 0.50, 0.90]
    # insert from the end so earlier offsets stay valid
    pieces = []
    last = 0
    order = sorted(zip(depths, names), key=lambda x: x[0])
    for d, n in order:
        pos = int(len(body) * d)
        # snap to a newline so we don't split a token mid-line
        nl = body.find("\n", pos)
        pos = nl if nl != -1 else pos
        pieces.append(body[last:pos]); pieces.append(needle(n)); last = pos
    pieces.append(body[last:])
    full = "".join(pieces)
    outtxt = Path(f"{a.out}.txt"); outtxt.write_text(full, encoding="utf-8")
    Path(f"{a.out}.truth.json").write_text(json.dumps({"truths": truths, "depths": dict(zip(names, depths)),
                                                       "chars": len(full)}, indent=1), encoding="utf-8")
    print(f"{outtxt} {len(full)} chars, needles at {dict(zip(names, depths))}")


if __name__ == "__main__":
    main()
