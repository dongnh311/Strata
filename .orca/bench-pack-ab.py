"""Bench UD-IQ1_M after the MTP fix: prefill 13K/55K, cache reuse, decode tok/s.

Same style as the playbook (cold 13K ~904 tok/s, 55K ~989, decode 73 median,
92-99.6 cached). Reads numbers from the server's own /metrics (engine-side tok/s).

Usage: python bench_ud.py [config.json]   - the api_key of that config is sent as a bearer token.
"""
import json, time, urllib.request, sys

BASE = "http://127.0.0.1:18080"
KEY = None
if len(sys.argv) > 1:
    KEY = json.load(open(sys.argv[1], encoding="utf-8")).get("api_key")

PARA = ("The harbor town woke slowly that morning, gulls tracing circles over the wet "
        "roofs while the fishing boats knocked gently against the quay. Salt air moved "
        "through the narrow streets, and the market women unfolded their canvases one by "
        "one, arranging apples, herbs and small bundles of dried fish beneath the pale "
        "light. Nobody hurried. The bell in the old tower rang the hour, answered by a "
        "second bell farther up the hill, and a dog trotted along the wall without any "
        "particular interest in the sea. ")

def hdr():
    h = {"Content-Type": "application/json"}
    if KEY:
        h["Authorization"] = "Bearer " + KEY
    return h

def ask(prompt, max_tokens=400, temperature=0.3):
    body = json.dumps({"messages": [{"role": "user", "content": prompt}],
                       "max_tokens": max_tokens, "temperature": temperature}).encode()
    t0 = time.time()
    with urllib.request.urlopen(urllib.request.Request(BASE + "/v1/chat/completions", data=body, headers=hdr()), timeout=600) as r:
        data = json.loads(r.read())
    return round(time.time() - t0, 1), data["usage"]

def metrics():
    with urllib.request.urlopen(urllib.request.Request(BASE + "/metrics", headers=hdr()), timeout=20) as r:
        return json.loads(r.read())

def show(tag):
    m = metrics()
    e = m["engine"]
    print(f"[{tag}] drafting={e.get('drafting')} spec={e.get('spec')} pcie={e.get('pcie_frac')} "
          f"minp={e.get('spec_min_p')} slots={e.get('expert_slots')} vram_free={e.get('vram_free_mib')}MiB")
    for r in m.get("requests", [])[:1]:
        print(f"      prompt={r['prompt_tokens']} reused={r.get('reused')} read={r['prompt_read']} "
              f"prompt_ms={r['prompt_ms']:.0f} ({r['prompt_tokens']/max(r['prompt_ms'],1)*1000:.0f} tok/s) "
              f"decode={r['decode_tok_s']:.1f} tok/s first={r['first_engine_token_s']:.2f}s "
              f"drafts={r['drafts_accepted']}/{r['drafts_offered']} hit={r['hit_rate']:.3f}")

p13 = PARA * 84 + "\nQuestion: In one short sentence, what is happening in the town?"
p55 = PARA * 352 + "\nQuestion: In one short sentence, what is happening in the town?"

print("== warm (short prompt) ==")
print(ask("Say OK.", 8))
show("warm")
print("== cold 13K ==")
print(ask(p13))
show("13K-cold")
print("== repeat 13K (cache) ==")
print(ask(p13))
show("13K-cache")
print("== short follow-up ==")
print(ask("And the dogs?", 120))
show("follow")
print("== cold 55K ==")
print(ask(p55))
show("55K-cold")
