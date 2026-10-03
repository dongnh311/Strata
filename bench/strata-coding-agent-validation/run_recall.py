"""Dimension 1 - long-context recall. For each size, pipe the needle context to Claude Code via stdin and ask for
the three needle constants; score each (size x depth) cell. Writes recall.json.

    python run_recall.py                 # uses contexts built by make_context.py (ctx-*.txt beside VAL_SCRATCH)

The prompt instructs a direct answer (no tools): the whole context is in the user message, so recall is the model's,
not a grep's. The engine log line `prompt N tokens` (read from the Strata log) gives the real token size per run.
"""
import json
import os
import re
import subprocess
import time
from pathlib import Path

SCRATCH = Path(os.environ["VAL_SCRATCH"])
LOG = Path(r"D:\GitHub\Strata\strata-unc48l-q2ktrim-refusal.log")
SIZES = [("128k", 460000), ("256k", 920000), ("512k", 1760000)]   # char budgets -> ~128/256/512K tokens (verify via log)

QUESTION = (
    "\n\n----\nThe text above is a large code file containing three functions named marker_alpha, marker_beta, and "
    "marker_gamma, each returning a specific 12-digit integer constant. Report the exact integer each one returns. "
    "Answer with exactly three lines and nothing else:\nmarker_alpha=<value>\nmarker_beta=<value>\nmarker_gamma=<value>\n")


def last_prompt_tokens():
    try:
        for line in reversed(LOG.read_text(encoding="utf-8", errors="ignore").splitlines()):
            m = re.search(r"prompt (\d+) tokens", line)
            if m:
                return int(m.group(1))
    except Exception:
        pass
    return None


def run_size(tag, chars, env):
    out = SCRATCH / f"ctx-{tag}"
    subprocess.run(["python", str(Path(__file__).with_name("make_context.py")), "--chars", str(chars), "--out", str(out)],
                   check=True, capture_output=True, text=True)
    truth = json.loads(Path(f"{out}.truth.json").read_text())["truths"]
    prompt = Path(f"{out}.txt").read_text(encoding="utf-8") + QUESTION
    cwd = SCRATCH / f"recall-{tag}"; cwd.mkdir(exist_ok=True)
    t0 = time.time()
    p = subprocess.run(["claude", "-p", "--output-format", "json"], cwd=cwd, env=env,
                       input=prompt, capture_output=True, text=True, timeout=1800)
    dur = time.time() - t0
    try:
        j = json.loads(p.stdout); ans = j.get("result") or ""
    except Exception:
        ans = p.stdout
    cells = {}
    for name, val in truth.items():
        cells[name] = str(val) in ans
    toks = last_prompt_tokens()
    return {"size": tag, "char_budget": chars, "prompt_tokens": toks, "secs": round(dur, 1),
            "recall": cells, "n_correct": sum(cells.values()), "answer_head": ans.strip()[:200]}


def main():
    env = dict(os.environ)
    results = []
    for tag, chars in SIZES:
        r = run_size(tag, chars, env)
        results.append(r)
        print(f"[{tag}] tokens={r['prompt_tokens']} {r['secs']}s recall={r['recall']} ({r['n_correct']}/3)", flush=True)
        (SCRATCH / "recall.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"\nDimension 1 -> {SCRATCH / 'recall.json'}")


if __name__ == "__main__":
    main()
