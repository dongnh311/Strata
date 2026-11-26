"""Prompt-length ladder for Inkling-2-Mini SQ-10 (abliterated) on the RTX 3060.

The paragraph is ~119 tokens, so the repeats give about 2K, 8K, 16K, 24K and 32K
tokens (the exact count is in the usage). Reports the engine's own timings.
"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8000"
PARA = ("The harbor town woke slowly that morning, gulls tracing circles over the wet "
        "roofs while the fishing boats knocked gently against the quay. Salt air moved "
        "through the narrow streets, and the market women unfolded their canvases one by "
        "one, arranging apples, herbs and small bundles of dried fish beneath the pale "
        "light. Nobody hurried. The bell in the old tower rang the hour, answered by a "
        "second bell farther up the hill, and a dog trotted along the wall without any "
        "particular interest in the sea. ")


def ask(prompt, max_tokens=100):
    body = json.dumps({"model": "inkling-2-mini-sq-10", "messages": [{"role": "user", "content": prompt}],
                       "max_tokens": max_tokens, "temperature": 0, "stream": False}).encode()
    t0 = time.time()
    req = urllib.request.Request(BASE + "/v1/chat/completions", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3600) as r:
        d = json.loads(r.read())
    wall = time.time() - t0
    m = json.load(urllib.request.urlopen(BASE + "/metrics", timeout=30))
    r0 = m["requests"][0]
    return d, r0, wall


print(f"{'reps':>5} {'tokens':>7} {'prefill tok/s':>13} {'decode tok/s':>12} {'first s':>8} {'drafts':>9} {'wall s':>7}")
for reps in (17, 68, 136, 204, 272):
    prompt = PARA * reps + "\nQuestion: In one short sentence, what is happening in the town?"
    d, r0, wall = ask(prompt)
    tok = d["usage"]["prompt_tokens"]
    rate = tok / max(r0["prompt_ms"], 1) * 1000
    drafts = f"{r0.get('drafts_accepted')}/{r0.get('drafts_offered')}"
    print(f"{reps:>5} {tok:>7} {rate:>13.0f} {r0['decode_tok_s']:>12.1f} {r0['first_engine_token_s']:>8.2f} "
          f"{drafts:>9} {wall:>7.1f}", flush=True)
    if tok > 32000:
        break

print("== cache: repeat the 16K prompt ==")
prompt = PARA * 136 + "\nQuestion: In one short sentence, what is happening in the town?"
d, r0, wall = ask(prompt)
tok = d["usage"]["prompt_tokens"]
print(f"tokens {tok} reused {r0.get('reused')} prompt_ms {r0['prompt_ms']:.0f} first {r0['first_engine_token_s']:.2f}s "
      f"decode {r0['decode_tok_s']:.1f} tok/s wall {wall:.1f}s")
