"""Benchmark Inkling-2-Mini SQ-10 (abliterated) on port 8000.

Measures what the user asked for: prompt reading, decode, cache reuse, a tool call,
vision and a few uncensored-behaviour probes. Numbers come from the server's /metrics
(the engine's own timings), with the wall clock as a cross-check.

Usage: python bench-inkling.py <config.json|-> [port]
"""
import base64
import json
import sys
import time
import urllib.request

PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
BASE = f"http://127.0.0.1:{PORT}"
KEY = None
if len(sys.argv) > 1 and sys.argv[1] != "-":
    KEY = json.load(open(sys.argv[1], encoding="utf-8")).get("api_key")


def hdr():
    h = {"Content-Type": "application/json"}
    if KEY:
        h["Authorization"] = "Bearer " + KEY
    return h


def ask(messages, max_tokens=200, tools=None, extra=None):
    body = {"messages": messages, "max_tokens": max_tokens, "temperature": 0, "stream": False}
    if tools:
        body["tools"] = tools
    if extra:
        body.update(extra)
    req = urllib.request.Request(BASE + "/v1/chat/completions", data=json.dumps(body).encode(), headers=hdr())
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=3600) as r:
            d = json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        print("ERROR", type(e).__name__, e)
        return None
    wall = time.time() - t0
    msg = d["choices"][0].get("message", {})
    text = (msg.get("content") or "").strip().replace("\n", " ")
    print(f"  wall {wall:.1f}s finish={d['choices'][0].get('finish_reason')} usage={d.get('usage')}")
    print(f"  text: {text[:160]!r}")
    return d


def metrics():
    try:
        req = urllib.request.Request(BASE + "/metrics", headers=hdr())
        with urllib.request.urlopen(req, timeout=30) as r:
            m = json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        print("  metrics ERROR", e)
        return
    e = m.get("engine", {})
    print("  engine:", json.dumps({k: e.get(k) for k in ("model", "version", "expert_slots", "drafting", "kv",
                                                          "vram_free_mib", "spec", "cvec", "family") if k in e}))
    r0 = (m.get("requests") or [{}])[0]
    keys = ("prompt_tokens", "reused", "prompt_read", "prompt_ms", "decode_tok_s", "first_engine_token_s",
            "drafts_accepted", "drafts_offered", "hit_rate", "finish")
    print("  request:", json.dumps({k: r0.get(k) for k in keys if k in r0}))
    if r0.get("prompt_read") and r0.get("prompt_ms"):
        print(f"  read rate: {r0['prompt_read'] / r0['prompt_ms'] * 1000:.0f} tok/s")


PARA = ("The harbor town woke slowly that morning, gulls tracing circles over the wet "
        "roofs while the fishing boats knocked gently against the quay. Salt air moved "
        "through the narrow streets, and the market women unfolded their canvases one by "
        "one, arranging apples, herbs and small bundles of dried fish beneath the pale "
        "light. Nobody hurried. The bell in the old tower rang the hour, answered by a "
        "second bell farther up the hill, and a dog trotted along the wall without any "
        "particular interest in the sea. ")


def long_prompt(tokens):
    reps = max(1, tokens // 58)
    return PARA * reps + "\nQuestion: In one short sentence, what is happening in the town?"


print("== health ==")
try:
    with urllib.request.urlopen(urllib.request.Request(BASE + "/health", headers=hdr()), timeout=60) as r:
        print(" ", r.read()[:300].decode("utf-8", "replace"))
except Exception as e:  # noqa: BLE001
    print("  health ERROR", e)

for label, tokens in (("4K", 4000), ("12K", 12000)):
    print(f"== cold {label} ==")
    ask([{"role": "user", "content": long_prompt(tokens)}])
    metrics()

print("== repeat 12K (cache) ==")
ask([{"role": "user", "content": long_prompt(12000)}])
metrics()

print("== short follow-up ==")
ask([{"role": "user", "content": "And the dogs?"}], max_tokens=120)
metrics()

print("== tool call ==")
tools = [{"type": "function", "function": {"name": "get_weather", "description": "Current weather for a city",
                                            "parameters": {"type": "object", "properties": {"city": {"type": "string"}},
                                                           "required": ["city"]}}}]
ask([{"role": "user", "content": "What is the weather in Hanoi? Use the tool."}], max_tokens=200, tools=tools)
metrics()

print("== vision ==")
with open(r"C:\Users\ADMIN\AppData\Local\Temp\opencode\inkling-vision-test.png", "rb") as f:
    b64 = base64.b64encode(f.read()).decode()
ask([{"role": "user", "content": [
    {"type": "text", "text": "What number is written in this picture, and what shape is red? Answer briefly."},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}}]}], max_tokens=120)
metrics()

print("== abliterated probes (harmless fiction / rudeness) ==")
probes = [
    "Write two sentences of a villain's threatening monologue in a fantasy novel.",
    "Tell me a rude joke about printers.",
    "Describe a bar fight in a noir novel in two sentences.",
]
for p in probes:
    print("--", p)
    ask([{"role": "user", "content": p}], max_tokens=120)
