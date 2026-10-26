"""Resumable download of one HF file with Range + retry, progress log to stdout."""
import sys, time, os, re, urllib.request

URL = "https://huggingface.co/unsloth/Ornith-1.5-122B-GGUF/resolve/main/" + sys.argv[1]
OUT = sys.argv[2]
TOTAL = int(sys.argv[3]) if len(sys.argv) > 3 else 0
TMP = OUT + ".part"

def open_range(start):
    req = urllib.request.Request(URL, headers={"Range": f"bytes={start}-", "User-Agent": "strata-fetch/1.0"})
    return urllib.request.urlopen(req, timeout=120)

pos = os.path.getsize(TMP) if os.path.exists(TMP) else 0
attempt = 0
t_prev, b_prev = time.time(), pos
speed_path = OUT + ".speed"
while True:
    if TOTAL and pos >= TOTAL:
        break
    try:
        r = open_range(pos)
        p = os.path.getsize(TMP) if os.path.exists(TMP) else 0
        if p != pos:                                   # concurrent trim/resume mismatch
            pos = p
            r.close()
            continue
        cl = r.headers.get("Content-Length")
        end = pos + int(cl) if cl else TOTAL
        mode = "ab" if pos else "wb"
        with open(TMP, mode) as f, open(speed_path, "w") as sp:
            while True:
                b = r.read(1 << 22)
                if not b:
                    break
                f.write(b)
                pos += len(b)
                now = time.time()
                if now - t_prev >= 5:
                    mbps = (pos - b_prev) / ((now - t_prev) * 1e6)
                    pct = (pos / end * 100) if end else 0
                    line = f"{pos/1e9:6.2f}/{(end/1e9):6.2f} GB  {pct:5.1f}%  {mbps:6.1f} MB/s"
                    print(line, flush=True)
                    sp.write(line + "\n")
                    t_prev, b_prev = now, pos
        r.close()
        if TOTAL and pos >= TOTAL:
            break
        attempt = 0
        if TOTAL == 0:
            break                                      # unknown length: single GET implies end
        if pos == 0:
            attempt += 1
            if attempt > 60:
                print("giving up: no progress", flush=True)
                sys.exit(2)
            time.sleep(5)
    except Exception as e:
        attempt += 1
        print(f"retry {attempt} at {pos/1e9:.2f} GB: {type(e).__name__} {e}", flush=True)
        if attempt > 240:
            print("too many retries", flush=True)
            sys.exit(2)
        time.sleep(min(attempt * 2, 30))
if TOTAL and abs(os.path.getsize(TMP) - TOTAL) > 64:
    print(f"size mismatch: have {os.path.getsize(TMP)}, want {TOTAL}", flush=True)
    sys.exit(3)
os.replace(TMP, OUT)
print("DONE " + OUT, flush=True)
