"""Six fixed questions + one code task, temperature 0: python qa-qwen.py <port> <model> <label>"""
import json
import sys
import urllib.request

PORT = int(sys.argv[1])
MODEL = sys.argv[2]
LABEL = sys.argv[3] if len(sys.argv) > 3 else "run"
BASE = f"http://127.0.0.1:{PORT}"
KEY = json.load(open(r"D:\GitHub\Strata\terminal\strata-iq2_xs-tuned.json", encoding="utf-8")).get("api_key")
QS = [
    "What is 17 * 23? Answer with the number only.",
    "A farmer has 17 sheep. All but 9 die. How many are left? Answer with the number only.",
    "Reverse the string 'strata'. Answer with the reversed string only.",
    "If today is Wednesday, what day of the week is 100 days from now? Answer with the day only.",
    "Write a Python function parse_duration(s) that turns 'HH:MM:SS' into seconds. Code only, no explanation.",
    "Tra loi trong mot cau ngan: con meo dang nam o dau?",
]


def ask(q):
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": q}],
                       "max_tokens": 400, "temperature": 0, "stream": False,
                       "reasoning_effort": "none"}).encode()
    req = urllib.request.Request(BASE + "/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    d = json.loads(urllib.request.urlopen(req, timeout=900).read())
    return (d["choices"][0]["message"].get("content") or "").strip().replace("\n", " | ")


for i, q in enumerate(QS, 1):
    print(f"[{LABEL} {i}] {ask(q)[:300]}", flush=True)
