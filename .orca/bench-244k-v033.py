"""The 244K row of the floor, on engine 0.1.62 (build-v033).

Same page as .orca/bench-pack-ab.py, repeated to ~236K tokens, one request. Prints the
engine's own /metrics row (prefill tok/s, decode, draft acceptance).

Usage: python bench-244k-v033.py <config.json>
"""
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:18080"
KEY = json.load(open(sys.argv[1], encoding="utf-8")).get("api_key") if len(sys.argv) > 1 else None

PARA = ("The harbor town woke slowly that morning, gulls tracing circles over the wet "
        "roofs while the fishing boats knocked gently against the quay. Salt air moved "
        "through the narrow streets, and the market women unfolded their canvases one by "
        "one, arranging apples, herbs and small bundles of dried fish beneath the pale "
        "light. Nobody hurried. The bell in the old tower rang the hour, answered by a "
        "second bell farther up the hill, and a dog trotted along the wall without any "
        "particular interest in the sea. ")

REPEATS = 2340
prompt = PARA * REPEATS + "\nQuestion: In one short sentence, what is happening in the town?"


def hdr():
    h = {"Content-Type": "application/json"}
    if KEY:
        h["Authorization"] = "Bearer " + KEY
    return h


body = json.dumps({"messages": [{"role": "user", "content": prompt}],
                   "max_tokens": 200, "temperature": 0.3}).encode()
print(f"prompt chars {len(prompt)}, ~{len(prompt) // 4} tokens guessed", flush=True)
t0 = time.time()
with urllib.request.urlopen(urllib.request.Request(BASE + "/v1/chat/completions", data=body,
                                                   headers=hdr()), timeout=7200) as r:
    data = json.loads(r.read())
wall = time.time() - t0
print(f"wall {wall:.0f}s usage {data['usage']}")
m = json.load(urllib.request.urlopen(urllib.request.Request(BASE + "/metrics", headers=hdr()), timeout=30))
e = m["engine"]
print(f"engine {e.get('version')} drafting={e.get('drafting')} spec={e.get('spec')} slots={e.get('expert_slots')} "
      f"vram_free={e.get('vram_free_mib')}MiB cvec={e.get('cvec')}")
r0 = m["requests"][0]
rate = r0["prompt_tokens"] / max(r0["prompt_ms"], 1) * 1000
print(f"prompt={r0['prompt_tokens']} reused={r0.get('reused')} read={r0['prompt_read']} "
      f"prompt_ms={r0['prompt_ms']:.0f} ({rate:.0f} tok/s) decode={r0['decode_tok_s']:.1f} tok/s "
      f"first={r0['first_engine_token_s']:.2f}s drafts={r0['drafts_accepted']}/{r0['drafts_offered']} "
      f"hit={r0['hit_rate']:.3f}")
