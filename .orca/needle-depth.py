"""Needle at a chosen depth: python needle-depth.py <port> <model> <reps> <depth_pct> <label>

reps * ~119 tokens; depth_pct 0-100 is where the code sits (0 = the start).
"""
import json
import sys
import time
import urllib.request

PORT = int(sys.argv[1])
MODEL = sys.argv[2]
REPS = int(sys.argv[3])
DEPTH = float(sys.argv[4])
LABEL = sys.argv[5] if len(sys.argv) > 5 else "run"
BASE = f"http://127.0.0.1:{PORT}"
KEY = json.load(open(r"D:\GitHub\Strata\terminal\strata-ud-q2_0-tuned.json", encoding="utf-8")).get("api_key")
PARA = ("The harbor town woke slowly that morning, gulls tracing circles over the wet "
        "roofs while the fishing boats knocked gently against the quay. Salt air moved "
        "through the narrow streets, and the market women unfolded their canvases one by "
        "one, arranging apples, herbs and small bundles of dried fish beneath the pale "
        "light. Nobody hurried. The bell in the old tower rang the hour, answered by a "
        "second bell farther up the hill, and a dog trotted along the wall without any "
        "particular interest in the sea. ")

at = int(REPS * DEPTH / 100.0)
p = (PARA * at + "\nThe secret code is ORANGE-7421.\n" + PARA * (REPS - at)
     + "\nQuestion: What is the secret code mentioned in the text? Answer with the code only.")
body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": p}],
                   "max_tokens": 32, "temperature": 0, "stream": False,
                   "reasoning_effort": "none"}).encode()
t0 = time.time()
req = urllib.request.Request(BASE + "/v1/chat/completions", data=body,
                             headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
d = json.loads(urllib.request.urlopen(req, timeout=7200).read())
wall = time.time() - t0
m = json.loads(urllib.request.urlopen(urllib.request.Request(BASE + "/metrics",
                                                            headers={"Authorization": "Bearer " + KEY}),
                                      timeout=60).read())
x = m["requests"][0]
ans = (d["choices"][0]["message"].get("content") or "").strip()
print(f"[{LABEL}] depth {DEPTH:.0f}%  tokens {d['usage']['prompt_tokens']}  answer {ans!r}  "
      f"prefill {x['prompt_tokens']/max(x['prompt_ms'],1)*1000:.0f} tok/s  decode {x['decode_tok_s']:.1f}  "
      f"wall {wall:.0f}s  {'PASS' if 'ORANGE-7421' in ans else 'FAIL'}", flush=True)
