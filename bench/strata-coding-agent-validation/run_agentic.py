"""Dimension 2 - agentic tool use. Longer, multi-step, multi-file tasks through Claude Code's own tools. Records
turns, whether Claude Code reported an error (malformed tool calls surface here), and whether an automated check
passes (did it actually finish the job). Writes agentic.json.

    python run_agentic.py [--timeout 600]
"""
import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

SCRATCH = Path(os.environ["VAL_SCRATCH"])


def sh(cmd, cwd, timeout=180):
    p = subprocess.run(cmd, cwd=cwd, timeout=timeout, capture_output=True, text=True, shell=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def py_check(cmd, expect):
    def chk(cwd):
        rc, out = sh(cmd, cwd, 120)
        return (rc == 0 and expect in out), f"rc={rc} out={out.strip()[-200:]}"
    return chk

def cargo_check(cwd):
    rc, out = sh("cargo test -q", cwd, 240)
    return rc == 0, out.strip()[-300:]


TASKS = [
    {"id": "cli-json-flag", "lang": "python-multistep",
     "seed": {
        "cli.py": "import sys\nfrom counter import word_count\n\ndef main():\n    text = sys.stdin.read()\n    wc = word_count(text)\n    for w, c in wc:\n        print(f'{w}: {c}')\n\nif __name__ == '__main__':\n    main()\n",
        "counter.py": "from collections import Counter\n\ndef word_count(text):\n    c = Counter(text.split())\n    return c.most_common()\n",
        "README.md": "# wc cli\nReads text on stdin, prints 'word: count' lines, most common first.\n"},
     "prompt": "Add a `--json` flag to this CLI (cli.py). With `--json`, instead of the 'word: count' lines it must print a single JSON object mapping each word to its count, e.g. {\"a\": 2, \"b\": 1}. Keep the default (no flag) behaviour unchanged. Read the files to understand the structure first.",
     "check": py_check('echo a b a c b a | python cli.py --json', '"a": 3')},

    {"id": "rust-bug-multifile", "lang": "rust-multistep",
     "seed": {
        "Cargo.toml": "[package]\nname=\"geo\"\nversion=\"0.1.0\"\nedition=\"2021\"\n",
        "src/lib.rs": "pub mod point;\nuse point::Point;\n\npub fn perimeter(pts: &[Point]) -> f64 {\n    let mut total = 0.0;\n    for i in 0..pts.len() {\n        let a = &pts[i];\n        let b = &pts[i]; // BUG: should be the next point (wrapping)\n        total += a.dist(b);\n    }\n    total\n}\n\n#[cfg(test)]\nmod tests {\n    use super::*;\n    use point::Point;\n    #[test]\n    fn square() {\n        let pts = vec![Point::new(0.0,0.0), Point::new(1.0,0.0), Point::new(1.0,1.0), Point::new(0.0,1.0)];\n        assert!((perimeter(&pts) - 4.0).abs() < 1e-9);\n    }\n}\n",
        "src/point.rs": "pub struct Point { pub x: f64, pub y: f64 }\nimpl Point {\n    pub fn new(x: f64, y: f64) -> Self { Point { x, y } }\n    pub fn dist(&self, o: &Point) -> f64 { ((self.x-o.x).powi(2) + (self.y-o.y).powi(2)).sqrt() }\n}\n",
     },
     "prompt": "The test `square` in this crate fails because `perimeter` in src/lib.rs has a bug: it measures each point against itself instead of the next point (wrapping around to close the shape). Fix `perimeter` so the perimeter of the unit square is 4.0. Run `cargo test` to confirm.",
     "check": cargo_check},

    {"id": "py-rename-refactor", "lang": "python-multistep",
     "seed": {
        "shapes/__init__.py": "",
        "shapes/area.py": "import math\n\ndef area_of_circle(r):\n    return math.pi * r * r\n\ndef area_of_square(s):\n    return s * s\n",
        "report.py": "from shapes.area import area_of_circle, area_of_square\n\ndef summary():\n    return [round(area_of_circle(1), 4), area_of_square(3)]\n",
        "check_it.py": "from report import summary\nprint(summary())\n"},
     "prompt": "Rename the function `area_of_circle` to `circle_area` everywhere in this project (its definition in shapes/area.py and every caller), without changing behaviour. Then run `python check_it.py` which should still print [3.1416, 9].",
     "check": py_check("python check_it.py", "[3.1416, 9]")},
]


def run_task(t, env, timeout):
    cwd = SCRATCH / ("agt-" + t["id"])
    if cwd.exists():
        shutil.rmtree(cwd, ignore_errors=True)
    cwd.mkdir(parents=True, exist_ok=True)
    for rel, content in t["seed"].items():
        p = cwd / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content, encoding="utf-8")
    subprocess.run("git init -q && git add -A && git -c user.email=t@t -c user.name=t commit -qm seed",
                   cwd=cwd, shell=True, capture_output=True)
    t0 = time.time()
    try:
        p = subprocess.run(["claude", "-p", t["prompt"], "--output-format", "json", "--dangerously-skip-permissions"],
                           cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
        dur = time.time() - t0
        try:
            j = json.loads(p.stdout)
            turns, is_err, denials = j.get("num_turns"), j.get("is_error"), len(j.get("permission_denials") or [])
        except Exception:
            turns, is_err, denials = None, "no-json", None
    except subprocess.TimeoutExpired:
        return {"id": t["id"], "done": False, "detail": "TIMEOUT", "turns": None, "secs": timeout}
    ok, detail = t["check"](cwd)
    return {"id": t["id"], "lang": t["lang"], "done": bool(ok), "turns": turns, "cc_error": is_err,
            "permission_denials": denials, "secs": round(dur, 1), "detail": detail[:300]}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--timeout", type=int, default=600); a = ap.parse_args()
    env = dict(os.environ); results = []
    for t in TASKS:
        r = run_task(t, env, a.timeout)
        results.append(r)
        print(f"[{r['done'] and 'DONE' or 'MISS'}] {r['id']:22s} turns={r['turns']} err={r.get('cc_error')} {r['secs']}s  {('' if r['done'] else r['detail'][:120])}", flush=True)
        (SCRATCH / "agentic.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    ndone = sum(r["done"] for r in results)
    print(f"\nDimension 2: {ndone}/{len(results)} completed -> {SCRATCH/'agentic.json'}")


if __name__ == "__main__":
    main()
