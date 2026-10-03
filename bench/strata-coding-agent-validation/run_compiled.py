"""Dimension 3, follow-up: the C++ and Kotlin tasks that the first run could not check (no compiler on the agent's
PATH). Run with the compiled-toolchain env sourced (MSVC cl via vcvars + kotlinc + MSYS_NO_PATHCONV). Writes
compiled.json.

    source cc-env-compiled.sh && python run_compiled.py
"""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

SCRATCH = Path(os.environ["VAL_SCRATCH"])


BASH = r"C:\Program Files\Git\usr\bin\bash.exe"

def sh(cmd, cwd, timeout=180):
    p = subprocess.run([BASH, "-c", cmd], cwd=cwd, timeout=timeout, capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def cpp_check(cwd):
    rc, out = sh("cl -nologo -EHsc -std:c++17 main.cpp -Fe:prog.exe >build.log 2>&1 && ./prog.exe", cwd, 120)
    return (rc == 0 and "12" in out), f"rc={rc} out={out.strip()[-200:]}"

def kotlin_check(cwd):
    rc, out = sh("kotlinc Gcd.kt -include-runtime -d Gcd.jar 2>kc.log && java -jar Gcd.jar", cwd, 300)
    return (rc == 0 and "12" in out), f"rc={rc} out={out.strip()[-200:]}"


TASKS = [
    {"id": "cpp-gcd", "lang": "cpp",
     "prompt": "Create main.cpp (C++17) with `int gcd(int a,int b)` and a main() that prints gcd(48,36) then a newline. "
               "Compile and run with: `cl -nologo -EHsc -std:c++17 main.cpp -Fe:prog.exe && ./prog.exe`  (MSVC is on PATH). "
               "It must print exactly 12.",
     "check": cpp_check},
    {"id": "kotlin-gcd", "lang": "kotlin",
     "prompt": "Create Gcd.kt with `fun gcd(a: Int, b: Int): Int` and a `fun main()` that prints gcd(48, 36). "
               "Compile and run with: `kotlinc Gcd.kt -include-runtime -d Gcd.jar && java -jar Gcd.jar`  (kotlinc is on PATH). "
               "It must print exactly 12.",
     "check": kotlin_check},
]


def run_task(t, env, timeout=420):
    cwd = SCRATCH / ("comp-" + t["id"])
    if cwd.exists():
        shutil.rmtree(cwd, ignore_errors=True)
    cwd.mkdir(parents=True, exist_ok=True)
    subprocess.run("git init -q && git commit --allow-empty -qm init -c user.email=t@t -c user.name=t",
                   cwd=cwd, shell=True, capture_output=True)
    t0 = time.time()
    try:
        p = subprocess.run(["claude", "-p", t["prompt"], "--output-format", "json", "--dangerously-skip-permissions"],
                           cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
        dur = time.time() - t0
        try:
            j = json.loads(p.stdout); turns, is_err = j.get("num_turns"), j.get("is_error")
        except Exception:
            turns, is_err = None, "no-json"
    except subprocess.TimeoutExpired:
        return {"id": t["id"], "lang": t["lang"], "pass": False, "detail": "TIMEOUT", "turns": None, "secs": timeout}
    ok, detail = t["check"](cwd)
    return {"id": t["id"], "lang": t["lang"], "pass": bool(ok), "turns": turns, "cc_error": is_err,
            "secs": round(dur, 1), "detail": detail[:300]}


def main():
    env = dict(os.environ); results = []
    for t in TASKS:
        r = run_task(t, env)
        results.append(r)
        print(f"[{r['pass'] and 'PASS' or 'FAIL'}] {r['id']:12s} {r['lang']:7s} turns={r['turns']} {r['secs']}s  {('' if r['pass'] else r['detail'][:140])}", flush=True)
        (SCRATCH / "compiled.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"\nC++/Kotlin: {sum(r['pass'] for r in results)}/{len(results)} passed")


if __name__ == "__main__":
    main()
