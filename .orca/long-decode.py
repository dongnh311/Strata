"""Long-context decode: python long-decode.py <port> <config> <reps> <max_tokens> <label>"""
import json
import secrets
import sys
import time
import urllib.request

PORT = int(sys.argv[1])
CFG = sys.argv[2]
REPS = int(sys.argv[3])
MAXT = int(sys.argv[4])
LABEL = sys.argv[5] if len(sys.argv) > 5 else "run"
_cfg = json.load(open(CFG, encoding="utf-8"))
KEY = _cfg.get("api_key")
MODEL = _cfg.get("model_name")
BASE = f"http://127.0.0.1:{PORT}"
PARA = ("The harbor town woke slowly that morning, gulls tracing circles over the wet "
        "roofs while the fishing boats knocked gently against the quay. Salt air moved "
        "through the narrow streets, and the market women unfolded their canvases one by "
        "one, arranging apples, herbs and small bundles of dried fish beneath the pale "
        "light. Nobody hurried. The bell in the old tower rang the hour, answered by a "
        "second bell farther up the hill, and a dog trotted along the wall without any "
        "particular interest in the sea. ")

p = ("Run %s.\n" % secrets.token_hex(4)) + PARA * REPS + \
    "\nTask: continue the story above with about 150 more words, in the same style. Do not answer a question, just write the next part."
body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": p}],
                   "max_tokens": MAXT, "temperature": 0, "stream": False,
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
tok = d["usage"]["prompt_tokens"]
print(f"[{LABEL}] tokens={tok} gen={d['usage']['completion_tokens']} "
      f"prefill={tok/max(x['prompt_ms'],1)*1000:.0f} tok/s decode={x['decode_tok_s']:.1f} tok/s "
      f"first={x['first_engine_token_s']:.1f}s drafts={x.get('drafts_accepted')}/{x.get('drafts_offered')} "
      f"slots={m['engine'].get('expert_slots')} wall={wall:.0f}s", flush=True)
