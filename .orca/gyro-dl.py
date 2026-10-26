# Tai Gyro-M + draft tu HF voi nhieu luong Range (resume, single writer moi part, khong xai luong).
import os, time, sys, urllib.request, socket
from concurrent.futures import ThreadPoolExecutor

socket.setdefaulttimeout(90)
REPO = "agentionai/Qwen3.8-Flash-Next-Gyro-GGUF"
OUT = r"D:\GitHub\Strata-data\models\Qwen3.8-Flash-Next-Gyro-GGUF"
FILES = [
    ("Qwen3.8-Flash-Next-Gyro-M-TQ2_0.gguf", 91965774272, 24),
    ("mtp-Qwen3.8-Flash-Next-draft.gguf", 2697439648, 6),
]

def log(msg):
    print(time.strftime("[%H:%M:%S] ") + msg, flush=True)

def pull(args):
    url, path, start, end, name = args
    expect = end - start + 1
    attempt = 0
    while True:
        have = os.path.getsize(path) if os.path.exists(path) else 0
        if have >= expect:
            return
        if have > expect:  # co ca sua
            log(f"LOI {name} part voi {start}: size {have} > ky vong {expect}")
            return
        first = os.path.exists(path)
        try:
            req = urllib.request.Request(
                url,
                headers={"Range": f"bytes={start+have}-{end}", "User-Agent": "strata-curl/1.0"},
            )
            with urllib.request.urlopen(req) as resp:
                if resp.status != 206 or "bytes" not in resp.headers.get("Content-Range", ""):
                    raise RuntimeError(f"resp {resp.status} Content-Range={resp.headers.get('Content-Range')} (khong phai 206)")
                with open(path, "ab") as f:
                    while True:
                        b = resp.read(1048576)
                        if not b:
                            break
                        f.write(b)
        except Exception as e:
            attempt += 1
            if attempt % 20 == 1:
                log(f"{name} part {start}: lan {attempt}: {type(e).__name__}: {e}")
            time.sleep(min(30.0, 3.0 + attempt))

def run_file(fname, total, parts):
    url = f"https://huggingface.co/{REPO}/resolve/main/{urllib.parse.quote(fname)}"
    work = os.path.join(OUT, "_parts", fname)
    os.makedirs(work, exist_ok=True)
    base = -(-total // parts)
    tasks = []
    for i in range(parts):
        s = i * base
        e = min(total, s + base) - 1
        if e < s:
            continue
        tasks.append((url, os.path.join(work, f"part_{i:03d}"), s, e, fname))
    t0 = time.time()
    mark = 0
    with ThreadPoolExecutor(max_workers=len(tasks)) as ex:
        futs = {ex.submit(pull, t): t[1] for t in tasks}
        while True:
            done = all(f.done() for f in futs)
            ship = 0
            for p in [k for k in ({os.path.join(work, f"part_{i:03d}") for i in range(parts)})]:
                if os.path.exists(p):
                    ship += os.path.getsize(p)
            if ship >= mark + 500 * 1024 * 1024 or done:
                log(f"{fname}: {ship/2**30:.2f} / {total/2**30:.2f} GiB ({(time.time()-t0):.0f}s, ~{(ship-max(mark,0))/max(time.time()-t0,1)/2**20:.1f} MiB/s trung binh)")
                mark = ship
            if done:
                break
            time.sleep(30)
    if ship != total:
        log(f"LOI {fname}: {ship} != {total}")
        return 0
    final = os.path.join(OUT, fname)
    log(f"{fname}: ghep {parts} part...")
    with open(final, "wb") as fo:
        for i in range(parts):
            p = os.path.join(work, f"part_{i:03d}")
            with open(p, "rb") as fi:
                while True:
                    b = fi.read(67108864)
                    if not b:
                        break
                    fo.write(b)
            fo.flush()
            os.remove(p)
    log(f"ALL DONE {fname}: {os.path.getsize(final):,} bytes")
    return os.path.getsize(final)

import urllib.parse
ok = True
for fname, total, parts in FILES:
    n = run_file(fname, total, parts)
    if n != total:
        ok = False
log("TOT CA 2 FILE OK" if ok else "CO FILE THAT BAI")
sys.exit(0 if ok else 1)
