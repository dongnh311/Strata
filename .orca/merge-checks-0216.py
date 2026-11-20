"""The checklist's last probes on the merged tree: the webchat origin answers with MCP tools on,
an unknown origin is refused, and the router and the tailnet URL answer.

Usage: python .orca/merge-checks-0216.py
"""
import json
import urllib.error
import urllib.request

CFG = json.load(open(r"D:\GitHub\Strata\strata-ud-q2_0-tuned.json", encoding="utf-8"))
KEY = CFG["api_key"]
MODEL = "qwen3.8-flash-next-ud-q2_0"


def call(base, origin=None, mcp=True, prompt="Say OK in one word.", max_tokens=2048):
    body = {"model": MODEL, "messages": [{"role": "user", "content": prompt}],
            "stream": False, "max_tokens": max_tokens, "temperature": 0}
    if mcp:
        body["strata_mcp"] = True
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + KEY}
    if origin:
        headers["Origin"] = origin
    req = urllib.request.Request(base + "/v1/chat/completions", data=json.dumps(body).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            d = json.loads(r.read())
        msg = d["choices"][0]["message"]
        text = (msg.get("content") or "").strip().replace("\n", " ")
        return f"{r.status} finish={d['choices'][0].get('finish_reason')} text={text[:60]!r}"
    except urllib.error.HTTPError as e:
        return f"{e.code} {e.read()[:160]!r}"
    except Exception as e:  # noqa: BLE001
        return f"ERR {type(e).__name__}: {e}"


print("webchat origin + strata_mcp :", call("http://127.0.0.1:8081", "http://127.0.0.1:8081"))
print("unknown origin + strata_mcp:", call("http://127.0.0.1:8081", "http://evil.example"))

for url in ("http://127.0.0.1:8081/v1/models",
            "https://pc-dik-win.tail1b3f7b.ts.net:8443/v1/models"):
    try:
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + KEY})
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
        print(f"{url}: {r.status} ids={[m['id'] for m in d.get('data', [])]}")
    except Exception as e:  # noqa: BLE001
        print(f"{url}: ERR {e}")
