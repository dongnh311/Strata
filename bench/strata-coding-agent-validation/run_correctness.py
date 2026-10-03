"""Dimension 3 - code correctness. Drives headless Claude Code (-> Strata) on real coding tasks across
languages, each with an automated check (pass = the check command exits 0). Writes correctness.json.

    python run_correctness.py [--only python,rust] [--timeout 360]

Needs: the cc-env.sh exports sourced into the environment (ANTHROPIC_* + CLAUDE_CODE_* context vars),
a seeded $CLAUDE_CONFIG_DIR, and the toolchains the tasks use (python, node, cargo, javac, MSVC cl.exe).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

SCRATCH = Path(os.environ["VAL_SCRATCH"])          # where task repos are created (scratchpad)
VCVARS = r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"


def sh(cmd, cwd, timeout=120, env=None):
    p = subprocess.run(cmd, cwd=cwd, timeout=timeout, capture_output=True, text=True, shell=isinstance(cmd, str), env=env)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def cl_check(cwd, src, run_args=""):
    """Compile src with MSVC and run; pass if it builds and runs (exit 0)."""
    cmd = f'call "{VCVARS}" >nul && cl /nologo /EHsc /std:c++17 {src} /Fe:prog.exe >build.log 2>&1 && prog.exe {run_args}'
    return sh(cmd, cwd, timeout=120)


# Each task: lang, prompt, seed files {path: content}, and check(cwd) -> (ok: bool, detail: str).
def py_test_check(cwd):
    rc, out = sh(["python", "-m", "pytest", "-q"], cwd, 120)
    return rc == 0, out.strip()[-400:]

def py_run_check(expect):
    def chk(cwd):
        rc, out = sh(["python", "main.py"], cwd, 60)
        return rc == 0 and expect in out, f"rc={rc} out={out.strip()[-200:]}"
    return chk

def node_run_check(expect):
    def chk(cwd):
        rc, out = sh(["node", "main.js"], cwd, 60)
        return rc == 0 and expect in out, f"rc={rc} out={out.strip()[-200:]}"
    return chk

def cargo_test_check(cwd):
    rc, out = sh("cargo test -q", cwd, 240)
    return rc == 0, out.strip()[-400:]

def java_run_check(expect, cls):
    def chk(cwd):
        rc, out = sh(f"javac {cls}.java && java {cls}", cwd, 120)
        return rc == 0 and expect in out, f"rc={rc} out={out.strip()[-200:]}"
    return chk

def cpp_check(expect):
    def chk(cwd):
        rc, out = sh(f'call "{VCVARS}" >nul && cl /nologo /EHsc /std:c++17 main.cpp /Fe:prog.exe >build.log 2>&1 && prog.exe', cwd, 120)
        return rc == 0 and expect in out, f"rc={rc} out={out.strip()[-200:]}"
    return chk


TASKS = [
    {"id": "py-fizzbuzz-test", "lang": "python",
     "seed": {"test_fb.py": "from fb import fizzbuzz\n\ndef test():\n    assert fizzbuzz(3)=='Fizz'\n    assert fizzbuzz(5)=='Buzz'\n    assert fizzbuzz(15)=='FizzBuzz'\n    assert fizzbuzz(7)=='7'\n"},
     "prompt": "There is a failing pytest in test_fb.py that imports fizzbuzz from fb.py, which does not exist yet. Create fb.py with a correct fizzbuzz(n) function so the test passes, then run pytest to confirm.",
     "check": py_test_check},
    {"id": "py-bugfix", "lang": "python",
     "seed": {"stats.py": "def median(xs):\n    xs = sorted(xs)\n    n = len(xs)\n    return xs[n // 2]\n",
              "test_stats.py": "from stats import median\n\ndef test():\n    assert median([1,2,3,4])==2.5\n    assert median([1,2,3])==2\n    assert median([5])==5\n"},
     "prompt": "test_stats.py fails: median() is wrong for an even number of elements (it should average the two middle values). Fix stats.py so the tests pass, then run pytest.",
     "check": py_test_check},
    {"id": "py-multifile", "lang": "python",
     "seed": {"app/__init__.py": "", "app/calc.py": "def add(a, b):\n    return a + b\n",
              "test_app.py": "from app.calc import add, mul\n\ndef test():\n    assert add(2,3)==5\n    assert mul(4,5)==20\n"},
     "prompt": "test_app.py imports both add and mul from app/calc.py, but mul is missing. Add a correct mul(a,b) to app/calc.py without breaking add, then run pytest.",
     "check": py_test_check},
    {"id": "rust-palindrome", "lang": "rust",
     "seed": {"Cargo.toml": "[package]\nname=\"t\"\nversion=\"0.1.0\"\nedition=\"2021\"\n",
              "src/lib.rs": "// implement is_palindrome\n\n#[cfg(test)]\nmod tests {\n    use super::*;\n    #[test]\n    fn t() {\n        assert!(is_palindrome(\"racecar\"));\n        assert!(!is_palindrome(\"rust\"));\n        assert!(is_palindrome(\"\"));\n    }\n}\n"},
     "prompt": "In src/lib.rs, implement a public function `is_palindrome(s: &str) -> bool` so the existing test compiles and passes. Run `cargo test` to confirm.",
     "check": cargo_test_check},
    {"id": "rust-borrowfix", "lang": "rust",
     "seed": {"Cargo.toml": "[package]\nname=\"t\"\nversion=\"0.1.0\"\nedition=\"2021\"\n",
              "src/lib.rs": "pub fn sum_lens(v: &Vec<String>) -> usize {\n    let mut total = 0;\n    for s in v {\n        total += s.len();\n    }\n    total\n}\n\n#[cfg(test)]\nmod tests {\n    use super::*;\n    #[test]\n    fn t() {\n        let v = vec![String::from(\"ab\"), String::from(\"cde\")];\n        assert_eq!(sum_lens(&v), 5);\n        // the vector is still usable after the call\n        assert_eq!(v.len(), 2);\n    }\n}\n"},
     "prompt": "Make `cargo test` pass for this crate. If it already compiles, just confirm; if not, fix it without changing the test. Run `cargo test`.",
     "check": cargo_test_check},
    {"id": "js-dedupe", "lang": "node",
     "seed": {},
     "prompt": "Create main.js that defines dedupe(arr) returning the array with duplicates removed, order preserved, and prints: console.log(JSON.stringify(dedupe([3,1,3,2,1,2]))). Then run `node main.js`. The output must be [3,1,2].",
     "check": node_run_check("[3,1,2]")},
    {"id": "cpp-gcd", "lang": "cpp",
     "seed": {},
     "prompt": "Create main.cpp (C++17) with a function int gcd(int a,int b) and a main() that prints gcd(48,36) followed by a newline. The program must print exactly 12. (It will be compiled with MSVC cl /std:c++17.)",
     "check": cpp_check("12")},
    {"id": "java-reverse", "lang": "java",
     "seed": {},
     "prompt": "Create Rev.java with a public class Rev whose main prints the reverse of the string \"hello\" (so: olleh) on its own line. It will be compiled with `javac Rev.java` and run with `java Rev`.",
     "check": java_run_check("olleh", "Rev")},
]


def run_task(t, base_env, timeout):
    cwd = SCRATCH / ("corr-" + t["id"])
    if cwd.exists():
        shutil.rmtree(cwd, ignore_errors=True)
    cwd.mkdir(parents=True, exist_ok=True)
    for rel, content in t.get("seed", {}).items():
        p = cwd / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    subprocess.run("git init -q && git add -A && git -c user.email=t@t -c user.name=t commit -qm seed",
                   cwd=cwd, shell=True, capture_output=True)
    t0 = time.time()
    try:
        p = subprocess.run(["claude", "-p", t["prompt"], "--output-format", "json",
                            "--dangerously-skip-permissions"],
                           cwd=cwd, env=base_env, capture_output=True, text=True, timeout=timeout)
        dur = time.time() - t0
        try:
            j = json.loads(p.stdout)
            turns, is_err = j.get("num_turns"), j.get("is_error")
        except Exception:
            turns, is_err = None, "no-json"
    except subprocess.TimeoutExpired:
        return {"id": t["id"], "lang": t["lang"], "pass": False, "detail": "TIMEOUT", "turns": None, "secs": timeout}
    ok, detail = t["check"](cwd)
    return {"id": t["id"], "lang": t["lang"], "pass": bool(ok), "detail": detail[:300],
            "turns": turns, "cc_error": is_err, "secs": round(dur, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--timeout", type=int, default=360)
    a = ap.parse_args()
    env = dict(os.environ)
    tasks = TASKS if not a.only else [t for t in TASKS if t["lang"] in a.only.split(",")]
    results = []
    for t in tasks:
        r = run_task(t, env, a.timeout)
        results.append(r)
        print(f"[{r['pass'] and 'PASS' or 'FAIL'}] {r['id']:20s} {r['lang']:7s} turns={r['turns']} {r['secs']}s  {('' if r['pass'] else r['detail'][:120])}", flush=True)
    out = SCRATCH / "correctness.json"
    out.write_text(json.dumps(results, indent=1), encoding="utf-8")
    npass = sum(r["pass"] for r in results)
    print(f"\nDimension 3: {npass}/{len(results)} passed  -> {out}")


if __name__ == "__main__":
    main()
