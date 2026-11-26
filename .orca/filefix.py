"""Fix the 29 KB page: python filefix.py <port> <model> <label> <out.html>"""
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

PORT = int(sys.argv[1])
MODEL = sys.argv[2]
LABEL = sys.argv[3] if len(sys.argv) > 3 else "run"
OUT = sys.argv[4] if len(sys.argv) > 4 else r"D:\GitHub\Strata\.orca\car-page-fixed.html"
BASE = f"http://127.0.0.1:{PORT}"
KEY = json.load(open(r"D:\GitHub\Strata\terminal\strata-ud-q2_0-tuned.json", encoding="utf-8")).get("api_key")
PAGE = Path(r"D:\GitHub\Strata\.orca\car-page-buggy.html").read_text(encoding="utf-8")
PROMPT = (PAGE + "\n\nThis HTML page has one syntax error: a missing arrow (=>) after the "
          "parameters of a function. Fix that syntax error and return the complete corrected "
          "file in one html code block. Change nothing else.")

body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": PROMPT}],
                   "max_tokens": 32768, "temperature": 0, "stream": False,
                   "reasoning_effort": "high"}).encode()
t0 = time.time()
req = urllib.request.Request(BASE + "/v1/chat/completions", data=body,
                             headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
d = json.loads(urllib.request.urlopen(req, timeout=7200).read())
wall = time.time() - t0
msg = d["choices"][0]
text = msg["message"].get("content") or ""
m = re.search(r"```(?:html)?\s*\n(.*?)```", text, re.S)
fixed = m.group(1) if m else text
Path(OUT).write_text(fixed, encoding="utf-8")

scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", fixed, re.S | re.I)
syntax_ok = bool(scripts)
errors = []
for i, s in enumerate(scripts):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(s)
        name = f.name
    r = subprocess.run(["node", "--check", name], capture_output=True, text=True)
    if r.returncode != 0:
        syntax_ok = False
        errors.append((r.stderr or "").strip().splitlines()[-1][:160] if (r.stderr or "").strip() else "node --check failed")
arrow = "(x, j, i) => {" in fixed
print(f"[{LABEL}] finish={msg.get('finish_reason')} tokens={d['usage']['completion_tokens']} wall={wall:.0f}s "
      f"scripts={len(scripts)} syntax={'OK' if syntax_ok else 'FAIL'} arrow={arrow} "
      f"{'PASS' if syntax_ok and arrow else 'FAIL'}", flush=True)
for e in errors:
    print("   ", e, flush=True)
