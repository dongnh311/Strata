"""Cold speed ladder 4K..128K: python ladder.py <port> <model> <label>"""
import json
import secrets
import sys
import time
import urllib.request

PORT = int(sys.argv[1])
MODEL = sys.argv[2]
LABEL = sys.argv[3] if len(sys.argv) > 3 else "run"
BASE = f"http://127.0.0.1:{PORT}"
KEY = json.load(open(r"D:\GitHub\Strata\terminal\strata-ud-q2_0-tuned.json", encoding="utf-8")).get("api_key")
PARA = ("The harbor town woke slowly that morning, gulls tracing circles over the wet "
        "roofs while the fishing boats knocked gently against the quay. Salt air moved "
        "through the narrow streets, and the market women unfolded their canvases one by "
        "one, arranging apples, herbs and small bundles of dried fish beneath the pale "
        "light. Nobody hurried. The bell in the old tower rang the hour, answered by a "
        "second bell farther up the hill, and a dog trotted along the wall without any "
        "particular interest in the sea. ")
REPS = [34, 68, 136, 275, 550, 1100]

print(f"{'reps':>5} {'tokens':>7} {'prefill':>8} {'decode':>7} {'first':>6} {'drafts':>9} {'wall':>6}", flush=True)
for reps in REPS:
    p = ("Run %s.\n" % secrets.token_hex(4)) + PARA * reps + "\nQuestion: In one short sentence, what is happening in the town?"
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": p}],
                       "max_tokens": 80, "temperature": 0, "stream": False,
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
    drafts = "%s/%s" % (x.get("drafts_accepted"), x.get("drafts_offered"))
    print(f"{reps:>5} {tok:>7} {tok / max(x['prompt_ms'], 1) * 1000:>8.0f} {x['decode_tok_s']:>7.1f} "
          f"{x['first_engine_token_s']:>6.2f} {drafts:>9} {wall:>6.1f}", flush=True)
