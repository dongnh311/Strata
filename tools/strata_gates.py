"""tools/strata_gates.py - a quick pass/fail check of a running Strata server, for after an update or a config change.

Six gates, as the local-ai-registry lab runs them (github.com/sybil-solutions/local-ai-registry, lab/lab.py, MIT),
asked through each API a client of this server uses: OpenAI chat (`/v1/chat/completions`), Anthropic
(`/v1/messages`, Claude Code) and Responses (`/v1/responses`, Codex).

  load       /v1/models answers and names the served model
  chat       "Name three primary colors" with thinking on ends by itself (a thinking loop that runs into the
             ceiling fails here) and names red, blue and yellow (or green)
  reasoning  17 * 23: the thinking comes back apart from the answer, and the answer is 391
  tools      the model calls get_weather for Paris, then uses the tool's result (17 C) in its reply
  context    a code planted near the end of a long prompt is recalled (--context tokens, OpenAI only)
  speed      decode tok/s of a ~600-word story with thinking off, from the server's own /metrics (OpenAI only)
  story      the same story with thinking on ends by itself with 300+ words (a model that deliberates without
             end fails here; not one of the lab's six, OpenAI only)

    python tools/strata_gates.py --config strata-q2_0.json                    # key and port from the config
    python tools/strata_gates.py --url http://127.0.0.1:18090 --key KEY --context 400000 --json out.json

Answers are never cut short on purpose: every request has a high ceiling (--max-tokens, default 16384), and a
request that reaches it fails its gate, since the lab's gates run uncapped. The context gate uses one long prompt
(default 32K tokens, about 35 s at 950 tok/s; the lab uses 85% of the window, which is --context 445000 for a
524288-token server, about 8 minutes on an RTX 3060). Temperature 0.6, as the lab.

Exit code 0 when every gate passed, 1 otherwise. Nothing here changes the server's settings.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

WEATHER = {"city": "Paris", "temp_c": 17, "sky": "overcast"}
COLORS_PROMPT = "Name three primary colors, comma separated."
MATH_PROMPT = "What is 17 * 23? Reply with only the number."
TOOL_PROMPT = "What's the weather in Paris right now? Use the tool."
STORY_PROMPT = "Write a detailed 600-word story about a lighthouse keeper."
CODE = "58213"


class Client:
    def __init__(self, url: str, key: str | None, model: str | None, max_tokens: int, timeout: float):
        self.url, self.key, self.model, self.max_tokens, self.timeout = url.rstrip("/"), key, model, max_tokens, timeout

    def call(self, path: str, body: dict | None = None, timeout: float | None = None) -> tuple[dict, float]:
        headers = {"Content-Type": "application/json", "anthropic-version": "2023-06-01"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers=headers)
        t0 = time.monotonic()
        with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
            out = json.loads(r.read() or b"{}")
        return out, time.monotonic() - t0

    def newest_request(self) -> dict:
        """The server's record of the request that finished last (decode tok/s, prompt tokens, finish)."""
        reqs = self.call("/metrics?requests=all", timeout=30)[0].get("requests") or []
        return max(reqs, key=lambda r: r.get("time", 0)) if reqs else {}


def has_colors(text: str) -> bool:
    t = text.lower()
    return "red" in t and "blue" in t and ("yellow" in t or "green" in t)


# ----------------------------------------------------------------------------------------------- OpenAI chat
def openai_gates(c: Client, context_tokens: int) -> dict:
    res = {}

    def chat(messages, **kw):
        body = {"model": c.model, "messages": messages, "temperature": 0.6, "max_tokens": c.max_tokens, **kw}
        out, secs = c.call("/v1/chat/completions", body)
        return out["choices"][0], out.get("usage") or {}, secs

    ch, _, secs = chat([{"role": "user", "content": COLORS_PROMPT}])
    text = ch["message"].get("content") or ""
    res["chat"] = {"ok": ch.get("finish_reason") == "stop" and has_colors(text), "finish": ch.get("finish_reason"),
                   "answer": text[-120:], "s": round(secs, 1)}

    ch, _, secs = chat([{"role": "user", "content": MATH_PROMPT}])
    m = ch["message"]
    thinking, text = m.get("reasoning_content") or m.get("reasoning") or "", m.get("content") or ""
    res["reasoning"] = {"ok": bool(thinking.strip()) and "391" in text and "<think>" not in text,
                        "thinking_chars": len(thinking), "answer": text[-80:], "s": round(secs, 1)}

    tool = {"type": "function", "function": {"name": "get_weather", "description": "Current weather for a city",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}
    msgs = [{"role": "user", "content": TOOL_PROMPT}]
    ch, _, secs = chat(msgs, tools=[tool])
    calls = ch["message"].get("tool_calls") or []
    try:
        args = json.loads(calls[0]["function"]["arguments"]) if calls else {}
    except (ValueError, KeyError, TypeError):
        args = {}
    first = bool(calls) and calls[0]["function"]["name"] == "get_weather" and "paris" in str(args.get("city", "")).lower()
    reply = ""
    if first:
        msgs += [{"role": "assistant", "content": ch["message"].get("content") or "", "tool_calls": calls[:1]},
                 {"role": "tool", "tool_call_id": calls[0].get("id", "0"), "content": json.dumps(WEATHER)}]
        ch2, _, s2 = chat(msgs, tools=[tool])
        reply, secs = ch2["message"].get("content") or "", secs + s2
    res["tools"] = {"ok": first and "17" in reply, "call": calls[0]["function"] if calls else None,
                    "reply": reply[-120:], "s": round(secs, 1)}

    if context_tokens > 0:
        lines = max(1, context_tokens // 24)   # ~23.6 tokens a line (the lab's measurement)
        filler = " ".join(f"Line {i}: the archive notes that shipment {i * 7 % 997} left dock {i % 13} on schedule."
                          for i in range(lines))
        prompt = (f"[{time.time()}] " + filler + f" The access code for the vault is {CODE}. Anything else is routine."
                  "\n\nWhat is the access code for the vault? Reply with only the code.")
        ch, usage, secs = chat([{"role": "user", "content": prompt}], chat_template_kwargs={"enable_thinking": False})
        got = usage.get("prompt_tokens") or 0
        text = ch["message"].get("content") or ""
        res["context"] = {"ok": CODE in text and got >= context_tokens * 0.6, "prompt_tokens": got,
                          "answer": text[-40:], "s": round(secs, 1),
                          "prefill_tok_s": round(got / secs) if secs else None}

    # speed with thinking off, so the number is decode speed and not how long the model deliberates
    ch, _, secs = chat([{"role": "user", "content": STORY_PROMPT}], temperature=0.8,
                       chat_template_kwargs={"enable_thinking": False})
    r = c.newest_request()
    tps = r.get("decode_tok_s") or 0
    res["speed"] = {"ok": ch.get("finish_reason") == "stop" and tps > 0, "decode_tok_s": tps,
                    "tokens": r.get("output_tokens"), "s": round(secs, 1)}
    # the same story with thinking on must end by itself: Q2_0 measured 2026-10-09 drafting the whole story in its
    # thinking and counting words until 16384 tokens ran out (3 of 3 tries), with no answer at all
    ch, _, secs = chat([{"role": "user", "content": STORY_PROMPT}], temperature=0.8)
    m = ch["message"]
    res["story"] = {"ok": ch.get("finish_reason") == "stop" and len((m.get("content") or "").split()) >= 300,
                    "finish": ch.get("finish_reason"), "thinking_chars": len(m.get("reasoning_content") or ""),
                    "words": len((m.get("content") or "").split()), "s": round(secs, 1)}
    return res


# -------------------------------------------------------------------------------------------- Anthropic messages
def anthropic_gates(c: Client) -> dict:
    res = {}

    def msg(messages, **kw):
        body = {"model": c.model, "max_tokens": c.max_tokens, "temperature": 0.6, "messages": messages,
                "thinking": {"type": "enabled", "budget_tokens": c.max_tokens - 1}, **kw}
        out, secs = c.call("/v1/messages", body)
        blocks = out.get("content") or []
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        thinking = "".join(b.get("thinking", "") for b in blocks if b.get("type") == "thinking")
        return out, blocks, text, thinking, secs

    out, _, text, _, secs = msg([{"role": "user", "content": COLORS_PROMPT}])
    res["chat"] = {"ok": out.get("stop_reason") == "end_turn" and has_colors(text), "finish": out.get("stop_reason"),
                   "answer": text[-120:], "s": round(secs, 1)}

    out, _, text, thinking, secs = msg([{"role": "user", "content": MATH_PROMPT}])
    res["reasoning"] = {"ok": bool(thinking.strip()) and "391" in text and "<think>" not in text,
                        "thinking_chars": len(thinking), "answer": text[-80:], "s": round(secs, 1)}

    tool = {"name": "get_weather", "description": "Current weather for a city",
            "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}
    msgs = [{"role": "user", "content": TOOL_PROMPT}]
    out, blocks, _, _, secs = msg(msgs, tools=[tool])
    uses = [b for b in blocks if b.get("type") == "tool_use"]
    first = bool(uses) and uses[0].get("name") == "get_weather" and "paris" in str((uses[0].get("input") or {}).get("city", "")).lower()
    reply = ""
    if first:
        msgs += [{"role": "assistant", "content": blocks},
                 {"role": "user", "content": [{"type": "tool_result", "tool_use_id": uses[0]["id"],
                                               "content": json.dumps(WEATHER)}]}]
        _, _, reply, _, s2 = msg(msgs, tools=[tool])
        secs += s2
    res["tools"] = {"ok": first and "17" in reply, "call": {k: uses[0].get(k) for k in ("name", "input")} if uses else None,
                    "reply": reply[-120:], "s": round(secs, 1)}
    return res


# --------------------------------------------------------------------------------------------- OpenAI Responses
def responses_gates(c: Client) -> dict:
    res = {}

    def resp(inp, **kw):
        body = {"model": c.model, "input": inp, "max_output_tokens": c.max_tokens, "temperature": 0.6,
                "reasoning": {"effort": "medium"}, **kw}
        out, secs = c.call("/v1/responses", body)
        items = out.get("output") or []
        text = "".join(p.get("text", "") for it in items if it.get("type") == "message"
                       for p in it.get("content") or [] if p.get("type") == "output_text")
        reasoning = [it for it in items if it.get("type") == "reasoning"]
        return out, items, text, reasoning, secs

    out, _, text, _, secs = resp(COLORS_PROMPT)
    res["chat"] = {"ok": out.get("status") == "completed" and has_colors(text), "status": out.get("status"),
                   "answer": text[-120:], "s": round(secs, 1)}

    out, _, text, reasoning, secs = resp(MATH_PROMPT)
    res["reasoning"] = {"ok": bool(reasoning) and "391" in text and "<think>" not in text,
                        "reasoning_items": len(reasoning), "answer": text[-80:], "s": round(secs, 1)}

    tool = {"type": "function", "name": "get_weather", "description": "Current weather for a city",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}
    inp = [{"role": "user", "content": TOOL_PROMPT}]
    out, items, _, _, secs = resp(inp, tools=[tool])
    calls = [it for it in items if it.get("type") == "function_call"]
    try:
        args = json.loads(calls[0].get("arguments") or "{}") if calls else {}
    except ValueError:
        args = {}
    first = bool(calls) and calls[0].get("name") == "get_weather" and "paris" in str(args.get("city", "")).lower()
    reply = ""
    if first:
        inp += items + [{"type": "function_call_output", "call_id": calls[0].get("call_id"), "output": json.dumps(WEATHER)}]
        _, _, reply, _, s2 = resp(inp, tools=[tool])
        secs += s2
    res["tools"] = {"ok": first and "17" in reply, "call": {k: calls[0].get(k) for k in ("name", "arguments")} if calls else None,
                    "reply": reply[-120:], "s": round(secs, 1)}
    return res


def run(c: Client, apis: list[str], context_tokens: int) -> dict:
    models = c.call("/v1/models", timeout=30)[0].get("data") or []
    ids = [m.get("id") for m in models]
    c.model = c.model or (ids[0] if ids else None)
    report = {"url": c.url, "model": c.model, "started": time.strftime("%Y-%m-%d %H:%M:%S"),
              "load": {"ok": bool(ids) and c.model in ids, "models": ids}}
    try:
        report["engine"] = c.call("/v1/status", timeout=30)[0].get("engine")
    except (urllib.error.URLError, ValueError):
        pass
    for api, fn in (("openai", lambda: openai_gates(c, context_tokens)), ("anthropic", lambda: anthropic_gates(c)),
                    ("responses", lambda: responses_gates(c))):
        if api not in apis:
            continue
        try:
            report[api] = fn()
        except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError) as e:
            body = e.read().decode(errors="replace")[:300] if isinstance(e, urllib.error.HTTPError) else ""
            report[api] = {"error": {"ok": False, "detail": f"{type(e).__name__}: {e} {body}".strip()}}
    report["passed"] = report["load"]["ok"] and all(g.get("ok") for api in apis for g in report.get(api, {}).values())
    return report


def print_report(rep: dict) -> None:
    print(f"{rep['url']}  model {rep['model']}  engine {rep.get('engine')}")
    print(f"  load       {'PASS' if rep['load']['ok'] else 'FAIL'}  {', '.join(rep['load']['models'])}")
    for api in ("openai", "anthropic", "responses"):
        for gate, g in (rep.get(api) or {}).items():
            extra = {k: v for k, v in g.items() if k != "ok"}
            print(f"  {api:9s}  {gate:9s} {'PASS' if g.get('ok') else 'FAIL'}  {json.dumps(extra, ensure_ascii=False)[:150]}")
    print("ALL PASSED" if rep["passed"] else "SOME GATES FAILED")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--config", help="a Strata run config: its port and api_key are used")
    p.add_argument("--url", help="server URL (default http://127.0.0.1:<config port or 8080>)")
    p.add_argument("--key", default=os.environ.get("STRATA_API_KEY"), help="API key (default $STRATA_API_KEY or the config's)")
    p.add_argument("--model", help="model name (default the first one /v1/models lists)")
    p.add_argument("--apis", default="openai,anthropic,responses")
    p.add_argument("--context", type=int, default=32768, help="context gate prompt size in tokens (0: skip)")
    p.add_argument("--max-tokens", type=int, default=16384)
    p.add_argument("--timeout", type=float, default=3600)
    p.add_argument("--json", help="write the full report here")
    a = p.parse_args(argv)
    key, port = a.key, 8080
    if a.config:
        cfg = json.loads(open(a.config, encoding="utf-8").read())
        key, port = key or cfg.get("api_key"), cfg.get("port", port)
    c = Client(a.url or f"http://127.0.0.1:{port}", key, a.model, a.max_tokens, a.timeout)
    rep = run(c, [x.strip() for x in a.apis.split(",") if x.strip()], a.context)
    print_report(rep)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(rep, f, indent=1, ensure_ascii=False)
    return 0 if rep["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
