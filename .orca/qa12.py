"""Twelve fixed reasoning questions, auto-scored: python qa12.py <port> <model> <label>"""
import json
import re
import sys
import urllib.request

PORT = int(sys.argv[1])
MODEL = sys.argv[2]
LABEL = sys.argv[3] if len(sys.argv) > 3 else "run"
BASE = f"http://127.0.0.1:{PORT}"
KEY = json.load(open(r"D:\GitHub\Strata\terminal\strata-ud-q2_0-tuned.json", encoding="utf-8")).get("api_key")
QS = [
    ("What is 17 * 23? Answer with the number only.", "num", 391),
    ("A farmer has 17 sheep. All but 9 die. How many are left? Answer with the number only.", "num", 9),
    ("Reverse the string 'strata'. Answer with the reversed string only.", "str", "atarts"),
    ("If today is Wednesday, what day of the week is 100 days from now? Answer with the day only.", "str", "friday"),
    ("What is 2^10? Answer with the number only.", "num", 1024),
    ("A bat and a ball cost $1.10 together. The bat costs $1.00 more than the ball. How much does the ball cost, in dollars? Answer with the number only.", "num", 0.05),
    ("How many times does the letter 'r' appear in the word 'strawberry'? Answer with the number only.", "num", 3),
    ("If 5 machines take 5 minutes to make 5 widgets, how many minutes do 100 machines take to make 100 widgets? Answer with the number only.", "num", 5),
    ("What is the next number in the sequence 2, 6, 12, 20, 30? Answer with the number only.", "num", 42),
    ("What is the angle in degrees between the hour and minute hands of a clock at 3:15? Answer with the number only.", "num", 7.5),
    ("Sort these words alphabetically and answer with the list only: banana, apple, cherry.", "str", "apple, banana, cherry"),
    ("In Python, what does len('hello') return? Answer with the number only.", "num", 5),
]


def ask(q):
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": q}],
                       "max_tokens": 600, "temperature": 0, "stream": False,
                       "reasoning_effort": "none"}).encode()
    req = urllib.request.Request(BASE + "/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    d = json.loads(urllib.request.urlopen(req, timeout=900).read())
    return (d["choices"][0]["message"].get("content") or "").strip()


ok = 0
for i, (q, kind, want) in enumerate(QS, 1):
    ans = ask(q)
    low = ans.lower().replace("\n", " ")
    if kind == "num":
        nums = re.findall(r"-?\d+(?:\.\d+)?", low)
        good = any(abs(float(n) - want) < 0.011 for n in nums)
    else:
        good = want in re.sub(r"\s+", " ", low)
    ok += good
    print(f"[{LABEL}] {i:2d} {'PASS' if good else 'FAIL'}  {low[:120]}", flush=True)
print(f"[{LABEL}] score {ok}/{len(QS)}", flush=True)
