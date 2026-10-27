import json, time, urllib.request, uuid

import os
CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "strata-q2_0-v144-refusal.json")
KEY = os.environ.get("STRATA_API_KEY") or json.load(open(CFG, encoding="utf-8"))["api_key"]
URL = "http://127.0.0.1:18080/v1/chat/completions"
FILLER = ("the quick brown fox jumps over lazy dog while compiler optimizes loop and "
          "server streams expert weights from system memory into graphics card buffer ")
GEN = "Write the integers from 1 to 60 separated by commas, nothing else."


def call(prompt, max_tokens):
    body = json.dumps({"model": "qwen38-q2_0-refusal", "max_tokens": max_tokens,
                       "temperature": 0.0, "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=1800) as r:
        d = json.loads(r.read())
    return time.time() - t0, d["usage"]


context = "[ab " + uuid.uuid4().hex[:8] + "] " + FILLER * 430 + "\n" + GEN
print("== cold ~13K ==")
dt, u = call(context, 1)
print("prefill: %d tok in %.1fs = %.0f tok/s" % (u["prompt_tokens"], dt, u["prompt_tokens"] / dt), flush=True)
print("== 3x generate on cached prompt (max 250) ==")
for i in range(3):
    dt, u = call(context, 250)
    print("run%d: %d tok in %.1fs" % (i + 1, u["completion_tokens"], dt), flush=True)
print("== cold ~55K ==")
big = "[ab2 " + uuid.uuid4().hex[:8] + "] " + FILLER * 1830 + "\nReply:"
dt, u = call(big, 1)
print("prefill: %d tok in %.1fs = %.0f tok/s" % (u["prompt_tokens"], dt, u["prompt_tokens"] / dt), flush=True)