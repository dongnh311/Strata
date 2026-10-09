"""tools/ab_stats.py - is B really faster than A?  A bootstrap verdict for speed A/B runs.

The rule of the local-ai-registry lab (github.com/sybil-solutions/local-ai-registry, lab/compare.py, MIT): B is
called faster only when the whole 95% confidence interval of median(B) / median(A) lies above 1.0, slower when it
lies below, and otherwise "no measured difference" - however good one run looked.  Resampling each side 10,000
times with replacement gives the interval without assuming the speeds are normally distributed.

    python tools/ab_stats.py 50.5,51.7,52.5,51.7 52.8,52.6,53.0,53.5          # two lists of samples
    python tools/ab_stats.py --lower-is-better 1771,2083,1755 1462,1585,1430  # times: smaller is better

    from ab_stats import verdict; verdict(a_samples, b_samples)

Samples should be independent measurements (one per request or per run), taken interleaved (A B B A ...) so drift
in the PC (temperatures, other programs, the expert cache) lands on both sides.
"""
from __future__ import annotations

import argparse
import random
import statistics


def ratio_ci(a: list[float], b: list[float], iters: int = 10000, seed: int = 0, level: float = 0.95) -> tuple[float, float, float]:
    """median(b) / median(a) and its bootstrap confidence interval."""
    if not a or not b:
        raise ValueError("both sides need at least one sample")
    rng = random.Random(seed)
    ratios = sorted(statistics.median(rng.choices(b, k=len(b))) / statistics.median(rng.choices(a, k=len(a)))
                    for _ in range(iters))
    lo = ratios[int((1 - level) / 2 * iters)]
    hi = ratios[min(iters - 1, int((1 + level) / 2 * iters))]
    return statistics.median(b) / statistics.median(a), lo, hi


def verdict(a: list[float], b: list[float], lower_is_better: bool = False, **kw) -> dict:
    r, lo, hi = ratio_ci(a, b, **kw)
    if lower_is_better:                     # a time: B is better when its ratio is BELOW 1
        better, worse = hi < 1.0, lo > 1.0
    else:
        better, worse = lo > 1.0, hi < 1.0
    word = "B better" if better else "B worse" if worse else "no measured difference"
    out = {"ratio": round(r, 4), "ci95": [round(lo, 4), round(hi, 4)], "verdict": word,
           "n": [len(a), len(b)], "median": [statistics.median(a), statistics.median(b)]}
    if min(len(a), len(b)) < 5:             # a bootstrap of 2-4 samples has too few distinct resamples to mean much
        out["warning"] = "fewer than 5 samples on a side: the interval is not reliable"
    return out


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("a", help="comma-separated samples of A")
    p.add_argument("b", help="comma-separated samples of B")
    p.add_argument("--lower-is-better", action="store_true", help="the samples are times (smaller is better)")
    p.add_argument("--iters", type=int, default=10000)
    args = p.parse_args(argv)
    a = [float(x) for x in args.a.split(",") if x.strip()]
    b = [float(x) for x in args.b.split(",") if x.strip()]
    v = verdict(a, b, args.lower_is_better, iters=args.iters)
    print(f"median A {v['median'][0]:g} (n={v['n'][0]})  B {v['median'][1]:g} (n={v['n'][1]})  "
          f"B/A {v['ratio']:.3f}  95% CI [{v['ci95'][0]:.3f}, {v['ci95'][1]:.3f}]  ->  {v['verdict']}"
          + (f"  ({v['warning']})" if v.get("warning") else ""))


if __name__ == "__main__":
    main()
