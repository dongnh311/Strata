"""Needle-in-a-haystack at a chosen context length for Inkling-2-Mini.

The code is placed at 50% depth; the question is at the end. Reports the engine's own
prompt/decode timings and the answer. Usage: python bench-inkling-needle.py <port> <reps>
(one rep of the paragraph is about 119 tokens).
"""
import json
import sys
import time
import urllib.request

PORT = int(sys.argv[1])
REPS = int(sys.argv[2])
BASE = f"http://127.0.0.1:{PORT}"
KEY = json.load(open(r"D:\GitHub\Strata\terminal\strata-ud-q2_0-tuned.json", encoding="utf-8")).get("api_key")
MODEL = "inkling-2-mini-sq-10"
PARA = ("The harbor town woke slowly that morning, gulls tracing circles over the wet "
        "roofs while the fishing boats knocked gently against the quay. Salt air moved "
        "through the narrow streets, and the market women unfolded their canvases one by "
        "one, arranging apples, herbs and small bundles of dried fish beneath the pale "
        "light. Nobody hurried. The bell in the old tower rang the hour, answered by a "
        "second bell farther up the hill, and a dog trotted along the wall without any "
        "particular interest in the sea. ")

half = REPS // 2
prompt = (PARA * half + "\nThe secret code is ORANGE-7421.\n" + PARA * (REPS - half)
          + "\nQuestion: What is the secret code mentioned in the text? Answer with the code only.")
body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                   "max_tokens": 32, "temperature": 0, "stream": False,
                   "reasoning_effort": "none"}).encode()
print(f"reps {REPS}, request {len(body) / 1e6:.1f} MB", flush=True)
t0 = time.time()
req = urllib.request.Request(BASE + "/v1/chat/completions", data=body,
                             headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
d = json.loads(urllib.request.urlopen(req, timeout=21600).read())
wall = time.time() - t0
msg = d["choices"][0].get("message", {})
print("usage", d.get("usage"), "finish", d["choices"][0].get("finish_reason"), flush=True)
print("answer:", repr((msg.get("content") or "").strip()), flush=True)
m = json.loads(urllib.request.urlopen(urllib.request.Request(BASE + "/metrics",
                                                            headers={"Authorization": "Bearer " + KEY}),
                                      timeout=60).read())
x = (m.get("requests") or [{}])[0]
print("engine:", json.dumps({k: x.get(k) for k in ("prompt_tokens", "reused", "prompt_ms", "decode_tok_s",
                                                    "first_engine_token_s", "drafts_accepted", "drafts_offered")}))
print(f"wall {wall:.0f}s")
