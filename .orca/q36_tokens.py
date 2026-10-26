"""Tokenize / detokenize via the running llama-server on 127.0.0.1:8080 (UTF-8-safe).

Usage:
  python q36_tokens.py tok "<prompt>"        -> prints space-joined token ids
  python q36_tokens.py detok "123 124 ..."   -> prints the detokenized text
  python q36_tokens.py gen "<prompt>" [n]    -> greedy completion text via /v1/completions
"""
import json, sys, urllib.request

BASE = "http://127.0.0.1:8080"

def post(path, payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.loads(r.read().decode("utf-8"))

def main():
    cmd = sys.argv[1]
    if cmd == "tok":
        r = post("/tokenize", {"content": sys.argv[2], "add_special": False,
                               "with_special": False})
        print(" ".join(str(t) for t in r["tokens"]))
    elif cmd == "detok":
        payload = {"tokens": [int(x) for x in sys.argv[2].split()]}
        req = urllib.request.Request(BASE + "/detokenize", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=1800) as r:
            print(json.loads(r.read().decode())["content"])
    elif cmd == "gen":
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 64
        r = post("/v1/completions", {"prompt": sys.argv[2], "temperature": 0,
                                     "n_predict": n, "echo": False})
        print(repr(r["choices"][0]["text"]))

if __name__ == "__main__":
    main()
