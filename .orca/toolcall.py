"""Tool call and a 29 KB page fix: python toolcall.py <port> <model> <label>"""
import json
import sys
import urllib.request

PORT = int(sys.argv[1])
MODEL = sys.argv[2]
LABEL = sys.argv[3] if len(sys.argv) > 3 else "run"
BASE = f"http://127.0.0.1:{PORT}"
KEY = json.load(open(r"D:\GitHub\Strata\terminal\strata-iq2_xs-tuned.json", encoding="utf-8")).get("api_key")
TOOLS = [{"type": "function", "function": {
    "name": "get_weather",
    "description": "Get the current weather for a city",
    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}]

body = json.dumps({"model": MODEL,
                   "messages": [{"role": "user", "content": "What is the weather in Hanoi right now? Use the get_weather tool."}],
                   "tools": TOOLS, "tool_choice": "auto", "max_tokens": 200,
                   "temperature": 0, "stream": False, "reasoning_effort": "none"}).encode()
req = urllib.request.Request(BASE + "/v1/chat/completions", data=body,
                             headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
d = json.loads(urllib.request.urlopen(req, timeout=900).read())
msg = d["choices"][0]["message"]
calls = msg.get("tool_calls") or []
if calls:
    fn = calls[0].get("function", {})
    print(f"[{LABEL}] tool {fn.get('name')} args {fn.get('arguments')} "
          f"{'PASS' if fn.get('name') == 'get_weather' and 'hanoi' in str(fn.get('arguments')).lower() else 'FAIL'}")
else:
    print(f"[{LABEL}] no tool call, finish={d['choices'][0].get('finish_reason')} content={(msg.get('content') or '')[:120]!r} FAIL")
