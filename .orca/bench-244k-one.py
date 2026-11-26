"""One long prompt against a Qwen server: python bench-244k-one.py <port> <reps>"""
import json
import sys
import time
import urllib.request

PORT = int(sys.argv[1])
REPS = int(sys.argv[2])
BASE = f"http://127.0.0.1:{PORT}"
KEY = json.load(open(r"D:\GitHub\Strata\terminal\strata-iq2_xs-tuned.json", encoding="utf-8")).get("api_key")
MODEL = json.load(open(r"D:\GitHub\Strata\terminal\strata-iq2_xs-tuned.json", encoding="utf-8")).get("model_name")
PARA = ("The harbor town woke slowly that morning, gulls tracing circles over the wet "
        "roofs while the fishing boats knocked gently against the quay. Salt air moved "
        "through the narrow streets, and the market women unfolded their canvases one by "
        "one, arranging apples, herbs and small bundles of dried fish beneath the pale "
        "light. Nobody hurried. The bell in the old tower rang the hour, answered by a "
        "second bell farther up the hill, and a dog trotted along the wall without any "
        "particular interest in the sea. ")

half = REPS // 2
p = (PARA * half + "\nThe secret code is ORANGE-7421.\n" + PARA * (REPS - half)
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
print("usage", d.get("usage"), "finish", d["choices"][0].get("finish_reason"))
print("answer:", repr((d["choices"][0]["message"].get("content") or "").strip()))
print("engine:", json.dumps({k: x.get(k) for k in ("prompt_tokens", "reused", "prompt_ms", "decode_tok_s",
                                                    "first_engine_token_s", "drafts_accepted", "drafts_offered")}))
print(f"wall {wall:.0f}s")
