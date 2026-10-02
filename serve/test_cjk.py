"""serve/test_cjk.py - the optional filter that removes stray Chinese/CJK characters from the ANSWER (config `"strip_cjk": true`),
against the mock engine (no GPU, no pack).

    python -m unittest serve.test_cjk -v

Why it exists: a heavily quantized model now and then writes a Chinese word in the middle of a sentence in another language
(a measured case: "thêm ánh nắng更强, hoặc ..."). The engine has no logit-bias or token-ban, so the stray characters cannot be
prevented at sampling time; they are removed from the answer text on the way out. Off by default.
"""
from __future__ import annotations

import json
import sys
import threading
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from serve.frontend import ChatTemplate  # noqa: E402
from serve.server import ByteTokenizer, Service, serve  # noqa: E402
from serve.test_mcp import ROOT, ScriptedEngine  # noqa: E402


class Stripper(unittest.TestCase):
    def feed_all(self, pieces):
        from serve.server import CjkStripper
        f = CjkStripper()
        return "".join(f.feed(p) for p in pieces), f

    def test_removes_a_word_and_the_space_it_leaves(self):
        out, f = self.feed_all(["Hello 更强 world"])
        self.assertEqual(out, "Hello world")
        self.assertEqual(f.removed, 2)

    def test_the_same_when_the_text_arrives_in_pieces(self):
        for pieces in (["Hello ", "更", "强", " world"], list("Hello 更强 world"), ["Hello 更", "强 world"]):
            with self.subTest(pieces=pieces):
                out, _ = self.feed_all(pieces)
                self.assertEqual(out, "Hello world")

    def test_punctuation_of_that_script_goes_too(self):
        out, f = self.feed_all(["Xong rồi，好的。 Tiếp"])
        self.assertEqual(out, "Xong rồi Tiếp")
        self.assertEqual(f.removed, 4)

    def test_other_text_is_untouched(self):
        for text in ("Giá vàng SJC hôm nay: 144.100.000 đ/lượng 🌞", "def f(x):\n    return x  # 1 < 2\n", "ASCII only.", ""):
            with self.subTest(text=text):
                out, f = self.feed_all([text])
                self.assertEqual(out, text)
                self.assertEqual(f.removed, 0)

    def test_the_spacing_of_a_sentence_that_ends_in_a_removed_word(self):
        out, _ = self.feed_all(["Đây là kết quả 更强", "。\n\nTiếp theo."])
        self.assertEqual(out, "Đây là kết quả \n\nTiếp theo.")


    def test_it_remembers_where_it_cut(self):
        out, f = self.feed_all(["Thêm ánh nắng ", "更", "强", ", hoặc mèo ", "抓取", " nữa"])
        self.assertEqual(out, "Thêm ánh nắng , hoặc mèo nữa")
        self.assertEqual(f.samples, [("Thêm ánh nắng ", "更强"), ("Thêm ánh nắng , hoặc mèo ", "抓取")])

    def test_the_context_is_short_and_the_samples_are_few(self):
        out, f = self.feed_all(["a" * 100, "更"] + ["b", "更"] * 9)
        self.assertEqual(len(f.samples), 5)
        self.assertEqual(len(f.samples[0][0]), 40)
        self.assertEqual(f.removed, 10)


class WhoMayWriteChinese(unittest.TestCase):
    def has(self, req):
        from serve.server import request_has_cjk
        return request_has_cjk(req)

    def test_a_user_who_writes_chinese_gets_it(self):
        self.assertTrue(self.has({"messages": [{"role": "user", "content": "翻译这句话: hello"}]}))

    def test_content_in_parts_and_a_system_prompt(self):
        self.assertTrue(self.has({"messages": [{"role": "user", "content": [{"type": "text", "text": "你好"}]}]}))
        self.assertTrue(self.has({"messages": [{"role": "system", "content": "请用中文回答"}, {"role": "user", "content": "hi"}]}))
        self.assertTrue(self.has({"system": [{"type": "text", "text": "用中文"}], "messages": [{"role": "user", "content": "hi"}]}))
        self.assertTrue(self.has({"system": "用中文", "messages": [{"role": "user", "content": "hi"}]}))

    def test_what_the_model_or_a_tool_wrote_does_not_count(self):
        """A leaked word in an earlier answer, or Chinese text a tool returned, must not switch the filter off."""
        self.assertFalse(self.has({"messages": [
            {"role": "user", "content": "Tìm giá vàng"},
            {"role": "assistant", "content": "Giá vàng 更强 hôm nay"},
            {"role": "tool", "content": "来源: 新闻"},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "x", "content": "抓取成功"}]},
            {"role": "user", "content": "cảm ơn"}]}))

    def test_nothing_to_read(self):
        for req in (None, {}, {"messages": None}, {"messages": [{"role": "user"}]}, {"messages": ["x"]}):
            with self.subTest(req=req):
                self.assertFalse(self.has(req))


class InTheServer(unittest.TestCase):
    """The filter in the real request path: answer text only, per request, opt-in, and counted in /v1/status."""

    def start(self, script, strip=True):
        tok = ByteTokenizer()
        self.engine = ScriptedEngine(tok, [script])
        self.svc = Service(self.engine, tok, ChatTemplate(ROOT / "serve/chat_template.jinja"))
        if strip is not None:
            self.svc.strip_cjk = strip
        self.httpd = serve(self.svc, port=0)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        httpd = getattr(self, "httpd", None)
        if httpd:
            httpd.shutdown()
            httpd.server_close()

    def post(self, path, body):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode()

    def chat(self, prompt="Tìm giá vàng", stream=False, **extra):
        text = self.post("/v1/chat/completions", {"model": "m", "stream": stream, "max_tokens": 200,
                                                   "messages": [{"role": "user", "content": prompt}], **extra})
        if not stream:
            msg = json.loads(text)["choices"][0]["message"]
            return msg.get("content") or "", msg.get("reasoning_content") or ""
        cs = [json.loads(l[6:]) for l in text.splitlines() if l.startswith("data: {")]
        deltas = [c["choices"][0]["delta"] for c in cs if c.get("choices")]
        return "".join(d.get("content") or "" for d in deltas), "".join(d.get("reasoning_content") or "" for d in deltas)

    def status(self):
        with urllib.request.urlopen(self.base + "/v1/status", timeout=10) as r:
            return json.loads(r.read())

    ANSWER = "</think>\n\nGiá vàng 更强 hôm nay là 144 triệu."

    def test_a_console_that_cannot_print_chinese_does_not_break_the_request(self):
        """Strata runs without PYTHONUTF8 and a redirected console is cp1252 on Windows: logging what was cut must never
        fail the answer (the first live run lost answers to exactly that)."""
        import io
        self.start(self.ANSWER)
        real = sys.stdout
        sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
        try:
            for stream in (False, True):
                with self.subTest(stream=stream):
                    self.assertEqual(self.chat(stream=stream)[0], "Giá vàng hôm nay là 144 triệu.")
            sys.stdout.flush()
            logged = sys.stdout.buffer.getvalue().decode("cp1252")
        finally:
            sys.stdout = real
        self.assertEqual(self.status()["strip_cjk"]["requests_touched"], 2)
        self.assertIn("removed 2 stray CJK character(s)", logged)
        self.assertIn("[\\u66f4\\u5f3a]", logged)             # what the console cannot show is written as an escape

    def test_off_by_default(self):
        self.start(self.ANSWER, strip=None)
        self.assertEqual(self.chat()[0], "Giá vàng 更强 hôm nay là 144 triệu.")
        self.assertEqual(self.status()["strip_cjk"], {"enabled": False, "requests_touched": 0, "chars_removed": 0})

    def test_on_it_removes_the_word_in_both_modes(self):
        self.start(self.ANSWER)
        self.assertEqual(self.chat()[0], "Giá vàng hôm nay là 144 triệu.")
        self.assertEqual(self.chat(stream=True)[0], "Giá vàng hôm nay là 144 triệu.")
        self.assertEqual(self.status()["strip_cjk"], {"enabled": True, "requests_touched": 2, "chars_removed": 4})

    def test_a_user_who_writes_chinese_is_not_filtered(self):
        self.start(self.ANSWER)
        self.assertEqual(self.chat(prompt="用中文: giá vàng")[0], "Giá vàng 更强 hôm nay là 144 triệu.")
        self.assertEqual(self.status()["strip_cjk"]["chars_removed"], 0)

    def test_only_the_answer_is_filtered_not_the_thinking(self):
        self.start("想一想 the price</think>\n\nGiá vàng 更强 đây.")
        content, reasoning = self.chat()
        self.assertEqual(content, "Giá vàng đây.")
        self.assertIn("想一想", reasoning)

    def test_the_anthropic_door_too(self):
        self.start(self.ANSWER)
        out = json.loads(self.post("/v1/messages", {"model": "m", "max_tokens": 200, "messages": [{"role": "user", "content": "Tìm giá vàng"}]}))
        text = "".join(b.get("text", "") for b in out["content"] if b.get("type") == "text")
        self.assertEqual(text, "Giá vàng hôm nay là 144 triệu.")

    def test_tool_call_arguments_are_never_touched(self):
        from serve.test_mcp import call_script
        self.start(call_script("lookup", q="更强", tags='["更强"]'))
        tools = [{"name": "lookup", "parameters": {"type": "object", "properties": {"q": {"type": "string"},
                                                                           "tags": {"type": "array", "items": {"type": "string"}}}}}]
        ids, thinking, max_new = self.svc.prepare([{"role": "user", "content": "Tìm"}], tools, {}, 600)
        evs = [x for kind, x in self.svc.run(ids, thinking, tools, max_new, {"messages": [{"role": "user", "content": "Tìm"}]},
                                              threading.Event()) if kind == "event"]
        calls = [e.call for e in evs if e.kind == "tool_call"]
        self.assertEqual([(c.name, c.arguments) for c in calls], [("lookup", {"q": "更强", "tags": ["更强"]})])
        streamed = "".join(e.text for e in evs if e.kind == "tool_args")      # what a streaming client assembles
        self.assertEqual(json.loads(streamed), {"q": "更强", "tags": ["更强"]})
        self.assertEqual("".join(e.text for e in evs if e.kind == "content").strip(), "Let me check.")


if __name__ == "__main__":
    unittest.main()
