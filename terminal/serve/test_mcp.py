"""serve/test_mcp.py - tools from MCP servers (serve/mcp.py) and the web app's tool loop, against the mock engine and
the fake MCP server in serve/mcp_fake_server.py (no GPU, no pack, no MCP SDK).

    python -m unittest serve.test_mcp -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from serve import mcp_fake_server as fake  # noqa: E402
from serve.frontend import ChatTemplate  # noqa: E402
from serve.mcp import MAX_RESULT_IMAGES, McpCancelled, McpHub, hub_from_config, result_parts, result_text  # noqa: E402
from serve.server import ByteTokenizer, MockEngine, Service, _answer_from_command, serve, without_content_tools  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FAKE = str(ROOT / "serve" / "mcp_fake_server.py")
CTX = 8192


def stdio(*args, **extra):
    return {"command": sys.executable, "args": [FAKE, *args], **extra}


def call_script(name, **params):
    """The model's text for one tool call, as Qwen's template asks for it."""
    body = "".join(f"<parameter={k}>\n{v}\n</parameter>\n" for k, v in params.items())
    return f"</think>\n\nLet me check.\n\n<tool_call>\n<function={name}>\n{body}</function>\n</tool_call>"


class ScriptedEngine(MockEngine):
    """A mock engine with one script per call (the last one repeats): a tool call first, then the answer."""

    def __init__(self, tok, scripts, max_context=CTX, delay_s=0.0):
        super().__init__(tok, list(scripts), max_context=max_context, delay_s=delay_s)
        self.prompts = []

    def generate(self, ids, max_new, sampling, cancel, embeddings=None):
        self.prompts.append(list(ids))
        yield from super().generate(ids, max_new, sampling, cancel, embeddings)

    def prompt_text(self, i):
        return bytes(t for t in self.prompts[i] if t < 256).decode("utf-8", "replace")


# ------------------------------------------------------------------------------------------------ the client
class Client(unittest.TestCase):
    """The stdio client against the fake server: start, pagination, calls, errors, crashes, timeouts, the cap."""

    @classmethod
    def setUpClass(cls):
        cls.log = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl")
        cls.log.close()
        os.environ["FAKE_MCP_LOG"] = cls.log.name
        cls.hub = McpHub({"fake": stdio(), "paged": stdio("--page", "4"), "broken": stdio("--crash-at-start"),
                          "missing": {"command": "strata-no-such-program"}},
                         {"timeout_s": 1.5, "max_result_chars": 1000})
        cls.hub.start(wait=True)

    @classmethod
    def tearDownClass(cls):
        cls.hub.close()
        del os.environ["FAKE_MCP_LOG"]
        os.unlink(cls.log.name)

    def test_initialize_and_list_every_page(self):
        s = self.hub.servers["fake"]
        self.assertEqual(s.status, "ready")
        self.assertEqual(s.info["name"], "fake")
        self.assertEqual(s.info["protocol"], "2025-06-18")
        want = [t["name"] for t in fake.TOOLS]
        self.assertEqual([t["name"] for t in s.tools], want)         # 3 pages of 2
        self.assertEqual([t["name"] for t in self.hub.servers["paged"].tools], want)   # 2 pages of 4

    def test_namespaced_openai_tools(self):
        tools = self.hub.openai_tools()
        names = [t["function"]["name"] for t in tools]
        self.assertIn("fake__echo", names)
        self.assertIn("paged__echo", names)
        echo = next(t for t in tools if t["function"]["name"] == "fake__echo")
        self.assertEqual(echo["type"], "function")
        self.assertEqual(echo["function"]["parameters"]["properties"]["text"]["type"], "string")

    def test_a_server_that_fails_is_left_out(self):
        for name, why in (("broken", "missing configuration"), ("missing", "could not start")):
            with self.subTest(name=name):
                s = self.hub.servers[name]
                self.assertEqual(s.status, "failed")
                self.assertIn(why, s.error)
                self.assertFalse([t for t in self.hub.template_tools() if t["name"].startswith(name + "__")])
        st = {s["name"]: s for s in self.hub.status()["servers"]}
        self.assertEqual(st["broken"]["status"], "failed")
        self.assertEqual(st["fake"]["status"], "ready")

    def test_call(self):
        self.hub.routes()
        r = self.hub.call("fake__echo", {"text": "hello wörld"})
        self.assertEqual((r["ok"], r["text"], r["server"], r["tool"]), (True, "hello wörld", "fake", "echo"))
        self.assertEqual(self.hub.call("fake__add", {"a": 2, "b": 40})["text"], "42")

    def test_an_exec_command_that_carries_the_answer_content_is_refused(self):
        """Local guard (2026-11-10): the webchat's HTML prompt wrote the page through exec under the
        2000-character bound; the shell mangled the quoting and the model retried until the round limit."""
        class Stub:
            name = "image"

            def call(self, tool, arguments, timeout, cancel):
                return {"content": [{"type": "text", "text": "ran"}]}

        hub = McpHub({})
        hub._routes["image__exec"] = (Stub(), "exec")
        for command in ("node -e \"const h = `<!DOCTYPE html><html>`\"",
                        "Set-Content D:\\x.html '<html><body></body></html>'"):
            r = hub.call("image__exec", {"command": command})
            self.assertFalse(r["ok"], command)
            self.assertIn("answer's content", r["text"])
            self.assertEqual(r["refused_text"], command)   # the chat shows the page without a second write
        r = hub.call("image__exec", {"command": "echo hi"})
        self.assertTrue(r["ok"])
        self.assertEqual(r["text"], "ran")

    def test_the_page_in_a_refused_command_is_the_answer(self):
        """Local guard (2026-11-10): the page was already written inside the refused call.  The chat shows it
        directly, so the model does not write the same 10K tokens again in a second round."""
        self.assertEqual(_answer_from_command("Set-Content D:\\x.html '<!doctype html><html><body>hi</body></html>'"),
                         "<!doctype html><html><body>hi</body></html>")
        self.assertEqual(_answer_from_command('node -e "const h = `<html>\\n<body>hi</body>\\n</html>`"'),
                         "<html>\n<body>hi</body>\n</html>")
        self.assertEqual(_answer_from_command("echo hi"), "")

    def test_the_webchat_is_not_offered_exec(self):
        """Local guard (2026-11-10): without exec in the list the model cannot try to write the page through a
        shell command, which is what looped at max_tokens 4000."""
        tools = [{"name": "image__exec"}, {"name": "image__generate_image"},
                 {"name": "image__write_file"}, {"name": "image__attach_file"}]
        self.assertEqual([t["name"] for t in without_content_tools(tools)],
                         ["image__generate_image", "image__attach_file"])

    def test_errors_become_text(self):
        self.hub.routes()
        r = self.hub.call("fake__fail", {})                         # the tool's own error (isError)
        self.assertFalse(r["ok"])
        self.assertEqual(r["text"], "error: it failed on purpose")
        r = self.hub.call("nobody__nothing", {})                    # not a tool at all
        self.assertTrue(r["text"].startswith("error: there is no tool"))
        # a JSON-RPC error from the server
        s = self.hub.servers["fake"]
        with self.assertRaises(Exception) as ctx:
            s.call("no-such-tool", {}, 5)
        self.assertIn("unknown tool", str(ctx.exception))

    def test_timeout(self):
        self.hub.routes()
        t0 = time.monotonic()
        r = self.hub.call("fake__sleep", {"seconds": 5})
        self.assertLess(time.monotonic() - t0, 4)
        self.assertFalse(r["ok"])
        self.assertIn("timed out after 1.5 s", r["text"])
        self.assertEqual(self.hub.call("fake__echo", {"text": "still here"})["text"], "still here")

    def test_truncation(self):
        self.hub.routes()
        r = self.hub.call("fake__big", {"n": 50000})
        self.assertTrue(r["ok"])
        self.assertTrue(r["truncated"])
        self.assertEqual(r["chars"], 50000)
        self.assertTrue(r["text"].startswith("y" * 1000 + "\n\n[... truncated"))
        self.assertIn("50,000 characters", r["text"])
        self.assertLess(len(r["text"]), 1200)

    def test_crash_mid_call_then_restart(self):
        hub = McpHub({"solo": stdio()}, {"timeout_s": 5})
        hub.start(wait=True)
        try:
            hub.routes()
            r = hub.call("solo__die", {})
            self.assertFalse(r["ok"])
            self.assertIn("the server stopped", r["text"])
            self.assertIn("dying on purpose", r["text"])
            self.assertEqual(hub.servers["solo"].status, "stopped")
            self.assertIn("solo__echo", hub.routes())                # its tools stay: the next call restarts it
            self.assertEqual(hub.call("solo__echo", {"text": "back"})["text"], "back")
            self.assertEqual(hub.servers["solo"].status, "ready")
        finally:
            hub.close()

    def test_cancel(self):
        self.hub.routes()
        cancel = threading.Event()
        threading.Timer(0.3, cancel.set).start()
        t0 = time.monotonic()
        with self.assertRaises(McpCancelled):
            self.hub.call("fake__sleep", {"seconds": 1.2}, cancel)
        self.assertLess(time.monotonic() - t0, 1.0)
        time.sleep(0.3)
        seen = [json.loads(line) for line in Path(self.log.name).read_text().splitlines()]
        self.assertTrue(any("cancelled" in e for e in seen), seen)   # notifications/cancelled reached the server


class HttpClient(unittest.TestCase):
    """Streamable HTTP: JSON answers, an event-stream answer, the session id."""

    @classmethod
    def setUpClass(cls):
        cls.httpd = fake.http_server(0)
        url = f"http://127.0.0.1:{cls.httpd.server_address[1]}/mcp"
        cls.hub = McpHub({"web": {"url": url}, "down": {"url": "http://127.0.0.1:9/mcp"}}, {"timeout_s": 1.5})
        cls.hub.start(wait=True)

    @classmethod
    def tearDownClass(cls):
        cls.hub.close()
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_list_and_call(self):
        s = self.hub.servers["web"]
        self.assertEqual(s.status, "ready", s.error)
        self.assertEqual(len(s.tools), len(fake.TOOLS))             # pages, with the session id on each request
        self.assertEqual(s.transport.session, "s-1")
        self.hub.routes()
        self.assertEqual(self.hub.call("web__echo", {"text": "over http"})["text"], "over http")   # event stream
        self.assertEqual(self.hub.call("web__fail", {})["text"], "error: it failed on purpose")

    def test_timeout_and_unreachable(self):
        self.hub.routes()
        r = self.hub.call("web__sleep", {"seconds": 4})
        self.assertIn("timed out", r["text"])
        self.assertEqual(self.hub.servers["down"].status, "failed")
        self.assertIn("could not reach", self.hub.servers["down"].error)


class HttpSessionRestart(unittest.TestCase):
    """#6014: an HTTP server restarted under a running engine (UE5's editor) forgets the session.  The next call starts
    a new session (initialize + initialized) and runs once, whether the server says so with a 404 or with a JSON-RPC
    "-32600 Unknown session id ...; client should reinitialize" in a 400 or a 200.  Nothing runs twice."""

    def setUp(self):
        self.log = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl")
        self.log.close()
        self.old_log = os.environ.get("FAKE_MCP_LOG")
        os.environ["FAKE_MCP_LOG"] = self.log.name

    def tearDown(self):
        if self.old_log is None:
            os.environ.pop("FAKE_MCP_LOG", None)
        else:
            os.environ["FAKE_MCP_LOG"] = self.old_log
        os.unlink(self.log.name)

    def events(self):
        return [json.loads(line) for line in Path(self.log.name).read_text().splitlines()]

    def hub_for(self, mode, timeout_s=5.0):
        httpd = fake.http_server(0, unknown_session=mode)
        hub = McpHub({"web": {"url": f"http://127.0.0.1:{httpd.server_address[1]}/mcp"}}, {"timeout_s": timeout_s})
        hub.start(wait=True)
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        self.addCleanup(hub.close)
        hub.routes()
        return httpd, hub

    def test_a_restarted_server_gets_a_new_session_and_the_call_runs_once(self):
        for mode in ("404", "jsonrpc-400", "jsonrpc-200"):
            with self.subTest(mode=mode):
                httpd, hub = self.hub_for(mode)
                self.assertEqual(hub.call("web__echo", {"text": "before"})["text"], "before")
                first = hub.servers["web"].transport.session
                httpd.restart()
                open(self.log.name, "w").close()
                r = hub.call("web__echo", {"text": "after"})
                self.assertTrue(r["ok"], r["text"])
                self.assertEqual(r["text"], "after")
                self.assertNotEqual(hub.servers["web"].transport.session, first)
                self.assertEqual(hub.servers["web"].status, "ready")
                seen = self.events()
                self.assertEqual(sum(1 for e in seen if e.get("call") == "echo"), 1, seen)
                self.assertEqual(sum(1 for e in seen if "initialize" in e), 1, seen)

    def test_two_callers_at_once_start_one_session(self):
        httpd, hub = self.hub_for("jsonrpc-200")
        httpd.restart()
        open(self.log.name, "w").close()
        out = {}
        threads = [threading.Thread(target=lambda k=k: out.__setitem__(k, hub.call("web__echo", {"text": k})))
                   for k in ("a", "b")]
        for t in threads:
            t.start()
        for t in threads:
            t.join(20)
        self.assertEqual({k: v["text"] for k, v in out.items()}, {"a": "a", "b": "b"})
        seen = self.events()
        self.assertEqual(sum(1 for e in seen if "initialize" in e), 1, seen)
        self.assertEqual(sum(1 for e in seen if e.get("call") == "echo"), 2, seen)

    def test_a_server_that_keeps_forgetting_is_not_retried_for_ever(self):
        httpd, hub = self.hub_for("jsonrpc-200")
        httpd.restart()
        httpd.forget_sessions = True
        open(self.log.name, "w").close()
        r = hub.call("web__echo", {"text": "x"})
        self.assertFalse(r["ok"])
        seen = self.events()
        self.assertEqual(sum(1 for e in seen if e.get("call") == "echo"), 0, seen)
        self.assertLessEqual(sum(1 for e in seen if "initialize" in e), 1, seen)

    def test_other_errors_do_not_start_a_new_session_or_run_again(self):
        httpd, hub = self.hub_for("jsonrpc-200", timeout_s=1.0)
        first = hub.servers["web"].transport.session
        open(self.log.name, "w").close()
        self.assertEqual(hub.call("web__fail", {})["text"], "error: it failed on purpose")
        self.assertIn("timed out", hub.call("web__sleep", {"seconds": 2})["text"])     # an answer lost after the work
        time.sleep(1.2)                                                                # let the slow call finish
        seen = self.events()
        self.assertEqual([e.get("call") for e in seen if "call" in e], ["fail", "sleep"], seen)
        self.assertFalse(any("initialize" in e for e in seen), seen)
        self.assertEqual(hub.servers["web"].transport.session, first)


class Config(unittest.TestCase):
    def test_both_spellings_and_the_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "claude_desktop_config.json")
            Path(path).write_text(json.dumps({"mcpServers": {"b": {"url": "http://x/mcp"}, "a": stdio()}}),
                                  encoding="utf-8")
            hub = hub_from_config({"mcp_servers": {"a": {"command": "old"}},
                                   "mcpServers": {"c": stdio(), "off": {"command": "x", "disabled": True}},
                                   "mcp": {"timeout_s": 5, "max_result_chars": 100, "max_rounds": 3}}, path)
            self.assertEqual(sorted(hub.servers), ["a", "b", "c"])
            self.assertEqual(hub.servers["a"].cfg["command"], sys.executable)   # the file wins a name clash
            self.assertEqual(hub.servers["b"].kind, "http")
            self.assertEqual((hub.settings["timeout_s"], hub.settings["max_result_chars"], hub.settings["max_rounds"]),
                             (5.0, 100, 3))
        self.assertIsNone(hub_from_config({}))
        self.assertEqual(McpHub({}).settings["max_result_chars"], 20000)

    def test_bad_entries_stop_the_start(self):
        for cfg in ({"mcp_servers": {"x": {}}}, {"mcp_servers": {"x": {"command": "a", "args": "b"}}},
                    {"mcp_servers": ["x"]}, {"mcpServers": {"x": {"url": "http://a", "type": "sse"}}},
                    {"mcp_servers": {"x": {"command": "a"}}, "mcp": {"timeout_s": 0}},
                    {"mcp_servers": {"x": {"command": "a"}}, "mcp": {"max_rounds": 1.5}}):
            with self.subTest(cfg=cfg), self.assertRaises(SystemExit):
                hub_from_config(cfg)
        with self.assertRaises(SystemExit):
            hub_from_config({}, os.path.join(tempfile.gettempdir(), "strata-no-such-mcp.json"))


# ------------------------------------------------------------------------------------------------ the tool loop
class ToolLoop(unittest.TestCase):
    """The web app's chat (`"strata_mcp": true`): the model calls an MCP tool, the server runs it and the model
    answers with its result; plain API requests never see the MCP tools."""

    def setUp(self):
        self.log = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl")
        self.log.close()
        os.environ["FAKE_MCP_LOG"] = self.log.name
        self.hub = McpHub({"fake": stdio(), "broken": stdio("--crash-at-start")},
                          {"timeout_s": 10, "max_result_chars": 500, "max_rounds": 2})
        self.hub.start(wait=True)
        self.httpd = None

    def tearDown(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
        self.hub.close()
        del os.environ["FAKE_MCP_LOG"]
        os.unlink(self.log.name)

    def start(self, *scripts, delay_s=0.0):
        tok = ByteTokenizer()
        self.engine = ScriptedEngine(tok, list(scripts), delay_s=delay_s)
        self.svc = Service(self.engine, tok, ChatTemplate(ROOT / "serve/chat_template.jinja"))
        self.svc.mcp = self.hub
        self.svc.trusted_origins = ["http://127.0.0.1:8081"]       # the webchat's origin, as production trusts it
        self.webchat = {"Origin": "http://127.0.0.1:8081"}        # the empty-answer retry is webchat-only
        self.httpd = serve(self.svc, port=0)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def post(self, body, headers=None, stream=True):
        body = {"model": "m", "messages": [{"role": "user", "content": "check it"}], "stream": stream, **body}
        req = urllib.request.Request(self.base + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                text = r.read().decode()
                return r.status, text
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.read().decode()

    @staticmethod
    def chunks(text):
        return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: {")]

    def test_tool_call_then_answer(self):
        self.start(call_script("fake__echo", text="hello from the tool"), "</think>\n\nThe tool said hello.")
        code, text = self.post({"strata_mcp": True})
        self.assertEqual(code, 200, text)
        cs = self.chunks(text)
        mcp = [c["strata_mcp"] for c in cs if "strata_mcp" in c]
        self.assertEqual([m["event"] for m in mcp], ["start", "call", "result"])
        self.assertEqual(mcp[1]["arguments"], {"text": "hello from the tool"})
        self.assertEqual((mcp[1]["server"], mcp[1]["tool"]), ("fake", "echo"))
        self.assertEqual((mcp[2]["ok"], mcp[2]["text"]), (True, "hello from the tool"))
        self.assertEqual(len({m["id"] for m in mcp}), 1)
        content = "".join((c["choices"][0]["delta"].get("content") or "") for c in cs)
        self.assertEqual(content, "Let me check.The tool said hello.")
        self.assertFalse([c for c in cs if c["choices"][0]["delta"].get("tool_calls")])   # nothing for the client to run
        self.assertEqual(cs[-1]["choices"][0]["finish_reason"], "stop")
        self.assertEqual(len(self.engine.prompts), 2)
        first, second = self.engine.prompt_text(0), self.engine.prompt_text(1)
        self.assertIn('"name": "fake__echo"', first)                 # the MCP tools are in the prompt
        self.assertNotIn("broken__", first)                          # the server that failed is left out
        self.assertIn("<function=fake__echo>\n<parameter=text>\nhello from the tool\n</parameter>", second)
        self.assertIn("<tool_response>\nhello from the tool\n</tool_response>", second)
        self.assertEqual(cs[-1]["usage"]["prompt_tokens"], len(self.engine.prompts[1]))

    def test_a_call_the_output_ends_inside_is_not_run(self):
        """#211: the model's turn ends inside an MCP call: nothing runs (it used to run with no arguments)."""
        script = call_script("fake__echo", text="hello from the tool")
        self.start(script[:script.index("from the tool")], "</think>\n\nnever")
        code, text = self.post({"strata_mcp": True})
        self.assertEqual(code, 200, text)
        cs = self.chunks(text)
        mcp = [c["strata_mcp"] for c in cs if "strata_mcp" in c]
        self.assertEqual([m["event"] for m in mcp], ["start"])        # the web app shows it as "Not run" at the end
        self.assertEqual(len(self.engine.prompts), 1)
        self.assertNotIn('"call"', Path(self.log.name).read_text())    # nothing ran
        self.assertEqual(cs[-1]["choices"][0]["finish_reason"], "stop")

    def test_non_stream(self):
        self.start(call_script("fake__add", a=2, b=3), "</think>\n\n5.")
        code, text = self.post({"strata_mcp": True}, stream=False)
        self.assertEqual(code, 200, text)
        msg = json.loads(text)["choices"][0]["message"]
        self.assertEqual(msg["content"], "Let me check.5.")
        self.assertEqual(msg["strata_mcp"][-1]["text"], "5")

    def test_plain_requests_get_no_mcp_tools(self):
        self.start(call_script("fake__echo", text="x"), "</think>\n\nnever")
        code, text = self.post({})
        self.assertEqual(code, 200, text)
        self.assertNotIn("fake__echo", self.engine.prompt_text(0))
        cs = self.chunks(text)
        self.assertFalse([c for c in cs if "strata_mcp" in c])
        # #3075: a request that declared no tools gets no tool call back; the call is the text it was written as
        self.assertEqual(cs[-1]["choices"][0]["finish_reason"], "stop")
        self.assertFalse([tc for c in cs for tc in c["choices"][0]["delta"].get("tool_calls") or []])
        self.assertIn("<function=fake__echo>", "".join(c["choices"][0]["delta"].get("content") or "" for c in cs))
        self.assertEqual(len(self.engine.prompts), 1)
        self.assertNotIn('"call"', Path(self.log.name).read_text())    # nothing ran
        for req in ({"strata_mcp": "yes"}, {"strata_mcp": 1}):         # only a real true opts in
            self.post(req)
            self.assertNotIn("fake__echo", self.engine.prompt_text(-1))

    def test_the_header_opts_in(self):
        """X-Strata-MCP: 1 - for a client that cannot add a body field (Codex's http_headers)."""
        self.start(call_script("fake__echo", text="hi"), "</think>\n\nIt said hi.")
        code, text = self.post({}, {"X-Strata-MCP": "1"})
        self.assertEqual(code, 200, text)
        mcp = [c["strata_mcp"] for c in self.chunks(text) if "strata_mcp" in c]
        self.assertEqual([m["event"] for m in mcp], ["start", "call", "result"])

    def test_another_header_value_does_not(self):
        self.start(call_script("fake__echo", text="x"), "</think>\n\nnever")
        self.post({}, {"X-Strata-MCP": "0"})
        self.assertNotIn("fake__echo", self.engine.prompt_text(0))

    # Claude Code: /v1/messages, opted in by the header (ANTHROPIC_CUSTOM_HEADERS)
    def post_anthropic(self, body, headers=None, stream=True):
        body = {"model": "m", "max_tokens": 256, "messages": [{"role": "user", "content": "check it"}],
                "stream": stream, **body}
        req = urllib.request.Request(self.base + "/v1/messages", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.read().decode()

    def test_anthropic_tool_call_then_answer(self):
        self.start(call_script("fake__echo", text="hello from the tool"), "</think>\n\nThe tool said hello.")
        code, text = self.post_anthropic({}, {"X-Strata-MCP": "1"})
        self.assertEqual(code, 200, text)
        events = self.chunks(text)
        blocks = [e["content_block"]["type"] for e in events if e["type"] == "content_block_start"]
        self.assertNotIn("tool_use", blocks)                          # nothing for the client to run
        thinking = "".join(e["delta"].get("thinking", "") for e in events if e["type"] == "content_block_delta")
        self.assertIn('[fake__echo {"text": "hello from the tool"}]', thinking)   # the user sees what ran
        self.assertIn("[ok: 19 characters in", thinking)
        text_out = "".join(e["delta"].get("text", "") for e in events if e["type"] == "content_block_delta")
        self.assertEqual(text_out, "Let me check.The tool said hello.")
        starts = [e["index"] for e in events if e["type"] == "content_block_start"]
        stops = [e["index"] for e in events if e["type"] == "content_block_stop"]
        self.assertEqual(starts, stops)                               # every block opened is closed, in order
        self.assertEqual(starts, list(range(len(starts))))
        self.assertEqual([e for e in events if e["type"] == "message_delta"][0]["delta"]["stop_reason"], "end_turn")
        self.assertEqual(len(self.engine.prompts), 2)
        self.assertIn("<tool_response>\nhello from the tool\n</tool_response>", self.engine.prompt_text(1))

    def test_anthropic_non_stream(self):
        self.start(call_script("fake__add", a=2, b=3), "</think>\n\n5.")
        code, text = self.post_anthropic({"strata_mcp": True}, stream=False)
        self.assertEqual(code, 200, text)
        msg = json.loads(text)
        self.assertEqual("".join(b.get("text", "") for b in msg["content"] if b["type"] == "text"), "Let me check.5.")
        self.assertEqual(msg["stop_reason"], "end_turn")

    def test_anthropic_own_tools_still_go_to_the_client(self):
        own = [{"name": "Read", "input_schema": {"type": "object", "properties": {"file_path": {"type": "string"}}}}]
        self.start(call_script("Read", file_path="a.py"), "</think>\n\nnever")
        code, text = self.post_anthropic({"tools": own}, {"X-Strata-MCP": "1"})
        self.assertEqual(code, 200, text)
        events = self.chunks(text)
        uses = [e["content_block"] for e in events if e["type"] == "content_block_start"
                and e["content_block"]["type"] == "tool_use"]
        self.assertEqual([u["name"] for u in uses], ["Read"])
        self.assertEqual([e for e in events if e["type"] == "message_delta"][0]["delta"]["stop_reason"], "tool_use")
        self.assertIn('"name": "fake__echo"', self.engine.prompt_text(0))
        self.assertEqual(len(self.engine.prompts), 1)

    def test_anthropic_plain_requests_get_no_mcp_tools(self):
        self.start(call_script("fake__echo", text="x"), "</think>\n\nnever")
        code, text = self.post_anthropic({})
        self.assertEqual(code, 200, text)
        self.assertNotIn("fake__echo", self.engine.prompt_text(0))
        self.assertNotIn('"call"', Path(self.log.name).read_text())    # nothing ran

    def test_own_tools_still_go_to_the_client(self):
        own = [{"type": "function", "function": {"name": "lookup", "parameters": {"type": "object", "properties": {
            "q": {"type": "string"}}}}}]
        self.start(call_script("lookup", q="x"), "</think>\n\nnever")
        code, text = self.post({"strata_mcp": True, "tools": own})
        cs = self.chunks(text)
        calls = [tc for c in cs for tc in c["choices"][0]["delta"].get("tool_calls") or []]
        self.assertEqual(calls[0]["function"]["name"], "lookup")
        self.assertEqual(cs[-1]["choices"][0]["finish_reason"], "tool_calls")
        self.assertIn('"name": "lookup"', self.engine.prompt_text(0))
        self.assertIn('"name": "fake__echo"', self.engine.prompt_text(0))
        self.assertEqual(len(self.engine.prompts), 1)

    # --- the model sees `fake__echo` but often writes the tool's own name, `echo`
    def test_an_unprefixed_name_runs_the_one_tool_it_names(self):
        """A name that matches exactly one offered MCP tool runs it; the events, the call and the history carry the
        full name, and the tool's schema still types the arguments (the string "42" stays a string)."""
        self.start(call_script("echo", text="42"), "</think>\n\nThe tool said 42.")
        code, text = self.post({"strata_mcp": True})
        self.assertEqual(code, 200, text)
        cs = self.chunks(text)
        mcp = [c["strata_mcp"] for c in cs if "strata_mcp" in c]
        self.assertEqual([m["event"] for m in mcp], ["start", "call", "result"])
        self.assertEqual((mcp[0]["name"], mcp[1]["name"]), ("fake__echo", "fake__echo"))
        self.assertEqual(mcp[1]["arguments"], {"text": "42"})
        self.assertEqual((mcp[2]["ok"], mcp[2]["text"]), (True, "42"))
        self.assertFalse([c for c in cs if c["choices"][0]["delta"].get("tool_calls")])   # nothing for the client to run
        self.assertEqual(cs[-1]["choices"][0]["finish_reason"], "stop")
        self.assertIn("<function=fake__echo>\n<parameter=text>\n42\n</parameter>", self.engine.prompt_text(1))

    def test_an_ambiguous_unprefixed_name_goes_to_the_client(self):
        """Two servers offer `echo`: the bare name names neither of them, so it is not guessed."""
        self.hub.close()
        self.hub = McpHub({"fake": stdio(), "other": stdio()}, {"timeout_s": 10, "max_result_chars": 500, "max_rounds": 2})
        self.hub.start(wait=True)
        self.start(call_script("echo", text="x"), "</think>\n\nnever")
        code, text = self.post({"strata_mcp": True})
        cs = self.chunks(text)
        calls = [tc for c in cs for tc in c["choices"][0]["delta"].get("tool_calls") or []]
        self.assertEqual(calls[0]["function"]["name"], "echo")
        self.assertEqual(cs[-1]["choices"][0]["finish_reason"], "tool_calls")
        self.assertEqual(len(self.engine.prompts), 1)
        self.assertNotIn('"call"', Path(self.log.name).read_text())    # nothing ran

    def test_an_unprefixed_name_the_client_owns_stays_the_clients(self):
        own = [{"type": "function", "function": {"name": "echo", "parameters": {"type": "object", "properties": {
            "text": {"type": "string"}}}}}]
        self.start(call_script("echo", text="x"), "</think>\n\nnever")
        code, text = self.post({"strata_mcp": True, "tools": own})
        cs = self.chunks(text)
        calls = [tc for c in cs for tc in c["choices"][0]["delta"].get("tool_calls") or []]
        self.assertEqual(calls[0]["function"]["name"], "echo")
        self.assertEqual(cs[-1]["choices"][0]["finish_reason"], "tool_calls")
        self.assertEqual(len(self.engine.prompts), 1)
        self.assertNotIn('"call"', Path(self.log.name).read_text())

    def test_a_name_that_matches_no_offered_tool_goes_to_the_client(self):
        self.start(call_script("nosuch", text="x"), "</think>\n\nnever")
        code, text = self.post({"strata_mcp": True})
        cs = self.chunks(text)
        calls = [tc for c in cs for tc in c["choices"][0]["delta"].get("tool_calls") or []]
        self.assertEqual(calls[0]["function"]["name"], "nosuch")
        self.assertEqual(cs[-1]["choices"][0]["finish_reason"], "tool_calls")
        self.assertNotIn('"call"', Path(self.log.name).read_text())

    def test_tool_error_is_a_result(self):
        self.start(call_script("fake__fail"), "</think>\n\nIt failed.")
        code, text = self.post({"strata_mcp": True})
        mcp = [c["strata_mcp"] for c in self.chunks(text) if "strata_mcp" in c]
        self.assertEqual((mcp[-1]["ok"], mcp[-1]["text"]), (False, "error: it failed on purpose"))
        self.assertIn("<tool_response>\nerror: it failed on purpose\n</tool_response>", self.engine.prompt_text(1))
        self.assertEqual(self.chunks(text)[-1]["choices"][0]["finish_reason"], "stop")

    def test_truncated_for_the_model(self):
        self.start(call_script("fake__big", n=3000), "</think>\n\nLong.")
        self.post({"strata_mcp": True})
        second = self.engine.prompt_text(1)
        self.assertIn("y" * 500 + "\n\n[... truncated: the tool returned 3,000 characters", second)
        self.assertNotIn("y" * 501, second)

    def test_max_rounds(self):
        self.start(call_script("fake__echo", text="first result"),
                   call_script("fake__echo", text="second result"), "</think>\n\nSummary of both results.")
        code, text = self.post({"strata_mcp": True})
        self.assertEqual(code, 200, text)
        chunks = self.chunks(text)
        mcp = [chunk["strata_mcp"] for chunk in chunks if "strata_mcp" in chunk]
        self.assertEqual(len(self.engine.prompts), 3)
        self.assertEqual(sum(m["event"] == "call" for m in mcp), 2)
        self.assertIn({"event": "limit", "max_rounds": 2}, mcp)
        self.assertFalse(any(m.get("skipped") for m in mcp))
        self.assertIn("Summary of both results.", "".join(chunk["choices"][0]["delta"].get("content", "")
                                                        for chunk in chunks))
        final_prompt = self.engine.prompt_text(2)
        self.assertIn("<tool_response>\nfirst result\n</tool_response>", final_prompt)
        self.assertIn("<tool_response>\nsecond result\n</tool_response>", final_prompt)
        self.assertIn("No tools are available for this final reply", final_prompt)
        self.assertNotIn("<tools>", final_prompt)
        self.assertEqual(chunks[-1]["choices"][0]["finish_reason"], "stop")
        self.assertEqual(chunks[-1]["usage"]["prompt_tokens"], len(self.engine.prompts[2]))

    def test_max_rounds_non_stream_with_existing_system(self):
        self.hub.settings["max_rounds"] = 1
        self.start(call_script("fake__add", a=2, b=3), "</think>\n\nThe result is 5.")
        code, text = self.post({"strata_mcp": True, "messages": [
            {"role": "system", "content": "Keep answers concise."},
            {"role": "developer", "content": "Use the provided evidence."},
            {"role": "user", "content": "Add 2 and 3."}]}, stream=False)
        self.assertEqual(code, 200, text)
        response = json.loads(text)
        self.assertIn("The result is 5.", response["choices"][0]["message"]["content"])
        final_prompt = self.engine.prompt_text(1)
        self.assertIn("Keep answers concise.", final_prompt)
        self.assertIn("Use the provided evidence.", final_prompt)
        self.assertIn("<tool_response>\n5\n</tool_response>", final_prompt)
        self.assertNotIn("<tools>", final_prompt)

    def test_max_rounds_counts_rounds_with_multiple_calls(self):
        self.hub.settings["max_rounds"] = 1
        self.start(call_script("fake__echo", text="source A") + "\n" +
                   call_script("fake__echo", text="source B"), "</think>\n\nBoth sources agree.")
        code, text = self.post({"strata_mcp": True})
        self.assertEqual(code, 200, text)
        chunks = self.chunks(text)
        mcp = [chunk["strata_mcp"] for chunk in chunks if "strata_mcp" in chunk]
        calls = [event for event in mcp if event["event"] == "call"]
        self.assertEqual([event["round"] for event in calls], [1, 1])
        self.assertEqual(len(self.engine.prompts), 2)
        self.assertIn("<tool_response>\nsource A\n</tool_response>", self.engine.prompt_text(1))
        self.assertIn("<tool_response>\nsource B\n</tool_response>", self.engine.prompt_text(1))
        self.assertIn("Both sources agree.", "".join(chunk["choices"][0]["delta"].get("content", "")
                                                  for chunk in chunks))

    def test_sixteen_rounds_then_final_answer(self):
        self.hub.settings["max_rounds"] = 16
        scripts = [call_script("fake__echo", text=f"source {index}") for index in range(16)]
        self.start(*scripts, "</think>\n\nSummary after sixteen rounds.")
        code, text = self.post({"strata_mcp": True})
        self.assertEqual(code, 200, text)
        chunks = self.chunks(text)
        mcp = [chunk["strata_mcp"] for chunk in chunks if "strata_mcp" in chunk]
        self.assertEqual(sum(event["event"] == "call" for event in mcp), 16)
        self.assertIn({"event": "limit", "max_rounds": 16}, mcp)
        self.assertEqual(len(self.engine.prompts), 17)
        final_prompt = self.engine.prompt_text(16)
        self.assertIn("<tool_response>\nsource 0\n</tool_response>", final_prompt)
        self.assertIn("<tool_response>\nsource 15\n</tool_response>", final_prompt)
        self.assertNotIn("<tools>", final_prompt)
        self.assertIn("Summary after sixteen rounds.", "".join(chunk["choices"][0]["delta"].get("content", "")
                                                              for chunk in chunks))

    def test_max_rounds_preserves_errors_and_disables_client_tools(self):
        self.hub.settings["max_rounds"] = 1
        own = [{"type": "function", "function": {"name": "lookup", "parameters": {"type": "object"}}}]
        self.start(call_script("fake__fail"), "</think>\n\nThe source failed; here is what is known.")
        code, text = self.post({"strata_mcp": True, "tools": own})
        self.assertEqual(code, 200, text)
        chunks = self.chunks(text)
        self.assertFalse(any(chunk["choices"][0]["delta"].get("tool_calls") for chunk in chunks))
        self.assertIn("error: it failed on purpose", self.engine.prompt_text(1))
        self.assertNotIn("<tools>", self.engine.prompt_text(1))
        self.assertIn("here is what is known", "".join(chunk["choices"][0]["delta"].get("content", "")
                                                     for chunk in chunks))

    def test_max_rounds_does_not_execute_more_calls(self):
        self.hub.settings["max_rounds"] = 1
        self.start(call_script("fake__echo", text="known"), call_script("fake__echo", text="must not run"))
        code, text = self.post({"strata_mcp": True})
        self.assertEqual(code, 200, text)
        self.assertEqual(len(self.engine.prompts), 2)
        mcp = [chunk["strata_mcp"] for chunk in self.chunks(text) if "strata_mcp" in chunk]
        self.assertEqual(sum(event["event"] == "call" for event in mcp), 1)
        self.assertNotIn("must not run", Path(self.log.name).read_text())

    def test_the_last_round_is_told_to_answer(self):
        """15 research prompts ended with an EMPTY answer when the tool loop reached max_rounds: the last pass was a
        thinking-plus-call turn.  The last tool result now carries a note to answer; nothing earlier in the prompt
        changes (the tools block at its start must stay byte-identical, or the engine's conversation cache is lost)."""
        from serve.server import TOOL_LIMIT_NOTE
        self.start(call_script("fake__echo", text="again"))          # max_rounds is 2; the model never stops calling
        self.post({"strata_mcp": True})
        self.assertEqual(len(self.engine.prompts), 3)
        p0, p1, p2 = (self.engine.prompt_text(i) for i in range(3))
        self.assertNotIn(TOOL_LIMIT_NOTE, p0)
        self.assertNotIn(TOOL_LIMIT_NOTE, p1)                        # a round is still left: no note yet
        self.assertIn(TOOL_LIMIT_NOTE, p2)
        last = p2.rindex("<tool_response>")
        block = p2[last:p2.index("</tool_response>", last)]
        self.assertIn(TOOL_LIMIT_NOTE, block)                        # inside the LAST tool result ...
        self.assertIn("again", block)                                # ... which keeps what the tool returned
        base = p1[:p1.rindex("</tool_response>") + len("</tool_response>")]
        self.assertTrue(p2.startswith(base))                         # everything before it is unchanged

    def test_an_answer_after_the_note_is_delivered(self):
        from serve.server import TOOL_LIMIT_NOTE
        self.start(call_script("fake__echo", text="a"), call_script("fake__echo", text="b"), "</think>\n\nHere is the answer.")
        code, text = self.post({"strata_mcp": True})
        cs = self.chunks(text)
        self.assertEqual(code, 200)
        self.assertIn("Here is the answer.", "".join((c["choices"][0]["delta"].get("content") or "") for c in cs))
        self.assertIn(TOOL_LIMIT_NOTE, self.engine.prompt_text(2))
        self.assertEqual(cs[-1]["choices"][0]["finish_reason"], "stop")

    def test_a_reasoning_only_stop_is_asked_again_without_thinking(self):
        """Local guard (2026-11-10): a "fix the page" request with the page in the prompt ended after 2K tokens of
        thinking with no answer and no call, so the webchat showed the thought and then nothing.  One retry with
        thinking off must answer, with the reasoning kept in the prompt (the 24K prefix is unchanged for the cache)."""
        self.start("I see the page and the fix.</think" + ">", "Here is the fixed page.")
        self.svc.effort_end = True                                   # the production config's effort_position "end"
        code, text = self.post({"strata_mcp": True, "reasoning_effort": "low"}, self.webchat)
        self.assertEqual(code, 200, text)
        cs = self.chunks(text)
        content = "".join((c["choices"][0]["delta"].get("content") or "") for c in cs)
        self.assertIn("Here is the fixed page.", content)
        self.assertEqual(cs[-1]["choices"][0]["finish_reason"], "stop")
        self.assertEqual(len(self.engine.prompts), 2)
        p0, p1 = self.engine.prompt_text(0), self.engine.prompt_text(1)
        note = "Your previous reply was thinking only and wrote no answer."
        self.assertNotIn(note, p0)
        self.assertIn(note, p1)
        self.assertIn("I see the page and the fix.", p1)             # the thinking is not thrown away
        self.assertEqual(p1.count("</think" + ">"), 1)              # thinking off's empty block; no empty turn (#843)
        base = p0[:p0.index("check it") + len("check it")]          # control tokens are not in prompt_text
        self.assertTrue(p1.startswith(base))                         # the page's prefix is unchanged

    def test_a_reasoning_only_stop_without_mcp_is_asked_again(self):
        """The webchat's chat can have no MCP tools; that path stopped silently too (2026-11-10), so it gets the
        same one retry with thinking off."""
        self.start("I thought about the page.</think" + ">", "Here is the answer.")
        self.svc.effort_end = True
        code, text = self.post({"reasoning_effort": "low"}, self.webchat)          # no strata_mcp: Service.run, not run_with_mcp
        self.assertEqual(code, 200, text)
        cs = self.chunks(text)
        content = "".join((c["choices"][0]["delta"].get("content") or "") for c in cs)
        self.assertIn("Here is the answer.", content)
        self.assertEqual(len(self.engine.prompts), 2)
        self.assertIn("thinking only", self.engine.prompt_text(1))

    def test_a_rejected_call_only_is_asked_again(self):
        """A call to a tool this chat does not offer stays text; when it is the whole reply, the chat must still
        answer instead of showing only the refused call (the live webchat did this on 2026-11-10)."""
        self.start("I will run a check.</think" + ">\n\n<tool_call>\n<function=image__exec>\n</function>\n"
                   "</tool_call>", "Here is the answer.")
        self.svc.effort_end = True
        code, text = self.post({"reasoning_effort": "low"}, self.webchat)
        self.assertEqual(code, 200, text)
        cs = self.chunks(text)
        content = "".join((c["choices"][0]["delta"].get("content") or "") for c in cs)
        self.assertIn("Here is the answer.", content)
        self.assertEqual(len(self.engine.prompts), 2)
        self.assertIn("thinking only", self.engine.prompt_text(1))

    def test_a_rejected_call_inside_the_thinking_is_asked_again(self):
        """The live 17:35 reply wrote an image__exec call inside the thinking and then stopped; no answer reached
        the chat.  The retry must see it as thinking only, not as a client tool call."""
        self.start("I will check.\n<tool_call>\n<function=image__exec>\n</function>\n</tool_call>\n"
                   "Now I know.</think" + ">", "Here is the answer.")
        self.svc.effort_end = True
        code, text = self.post({"reasoning_effort": "low"}, self.webchat)
        self.assertEqual(code, 200, text)
        cs = self.chunks(text)
        content = "".join((c["choices"][0]["delta"].get("content") or "") for c in cs)
        self.assertIn("Here is the answer.", content)
        self.assertEqual(len(self.engine.prompts), 2)
        self.assertIn("thinking only", self.engine.prompt_text(1))

    def test_stop_during_a_tool(self):
        """Closing the connection while a slow tool runs stops the tool (notifications/cancelled) and the loop."""
        self.start(call_script("fake__sleep", seconds=8), "</think>\n\nnever")
        body = {"model": "m", "messages": [{"role": "user", "content": "x"}], "stream": True, "strata_mcp": True}
        req = urllib.request.Request(self.base + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        r = urllib.request.urlopen(req, timeout=30)
        for raw in r:
            if b'"event": "call"' in raw:
                break
        r.close()                                                    # the web app's Stop aborts the fetch
        t0 = time.monotonic()
        while time.monotonic() - t0 < 6 and "cancelled" not in Path(self.log.name).read_text():
            time.sleep(0.1)
        self.assertIn("cancelled", Path(self.log.name).read_text())
        self.assertLess(time.monotonic() - t0, 6)
        time.sleep(0.5)
        self.assertEqual(len(self.engine.prompts), 1)                # no second round
        self.assertFalse(self.svc.status["busy"])

    def test_only_from_the_app_s_own_page(self):
        self.start("</think>\n\nhi")
        req = urllib.request.Request(self.base + "/v1/chat/completions", data=json.dumps(
            {"model": "m", "messages": [{"role": "user", "content": "x"}], "strata_mcp": True}).encode(),
            headers={"Content-Type": "text/plain"})                  # a cross-site "simple" request
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, 415)
        code, _ = self.post({"strata_mcp": True}, {"Origin": "http://evil.example"})
        self.assertEqual(code, 403)
        self.assertEqual(self.engine.prompts, [])
        host = self.base.split("://", 1)[1]
        code, _ = self.post({"strata_mcp": True}, {"Origin": "http://" + host})
        self.assertEqual(code, 200)

    def test_get_mcp(self):
        self.start("</think>\n\nhi")
        with urllib.request.urlopen(self.base + "/mcp", timeout=10) as r:
            st = json.loads(r.read())
        servers = {s["name"]: s for s in st["servers"]}
        self.assertEqual(servers["fake"]["status"], "ready")
        self.assertEqual(servers["fake"]["transport"], "stdio")
        self.assertIn("fake__echo", [t["name"] for t in servers["fake"]["tools"]])
        self.assertEqual(servers["broken"]["status"], "failed")
        self.assertIn("missing configuration", servers["broken"]["error"])
        self.assertEqual(st["tools"], len(fake.TOOLS))
        self.assertEqual(st["settings"]["max_rounds"], 2)
        self.svc.api_key = "k"
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(self.base + "/mcp", timeout=10)
        self.svc.api_key = ""


class NoServers(unittest.TestCase):
    def test_opt_in_without_servers_is_a_plain_chat(self):
        tok = ByteTokenizer()
        svc = Service(ScriptedEngine(tok, ["</think>\n\nhi"]), tok, ChatTemplate(ROOT / "serve/chat_template.jinja"))
        httpd = serve(svc, port=0)
        try:
            base = f"http://127.0.0.1:{httpd.server_address[1]}"
            with urllib.request.urlopen(base + "/mcp", timeout=10) as r:
                self.assertEqual(json.loads(r.read()), {"servers": [], "tools": 0})
            req = urllib.request.Request(base + "/v1/chat/completions", data=json.dumps(
                {"model": "m", "messages": [{"role": "user", "content": "x"}], "strata_mcp": True}).encode(),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                self.assertEqual(json.loads(r.read())["choices"][0]["message"]["content"], "hi")
        finally:
            httpd.shutdown()
            httpd.server_close()


class BareToolNames(unittest.TestCase):
    """The model is shown `<server>__<tool>` but often writes `<tool>`: which bare names count (mcp_aliases) and that
    the parser applies them to the whole call."""
    ROUTES = {"fake__echo": (None, "echo"), "fake__add": (None, "add"), "other__echo": (None, "echo"),
              "other__ping": (None, "ping")}

    def test_only_a_name_that_is_exactly_one_offered_tool(self):
        from serve.server import mcp_aliases
        offered = set(self.ROUTES)
        self.assertEqual(mcp_aliases(self.ROUTES, offered, set()), {"add": "fake__add", "ping": "other__ping"})

    def test_the_clients_own_tools_win(self):
        from serve.server import mcp_aliases
        self.assertEqual(mcp_aliases(self.ROUTES, set(self.ROUTES), {"add"}), {"ping": "other__ping"})

    def test_a_tool_that_is_not_offered_is_not_an_alias(self):
        from serve.server import mcp_aliases
        offered = {"fake__echo", "fake__add"}                           # `other` is not offered: `echo` is unique now
        self.assertEqual(mcp_aliases(self.ROUTES, offered, set()), {"echo": "fake__echo", "add": "fake__add"})

    def test_a_bare_name_is_never_a_full_name(self):
        from serve.server import mcp_aliases
        # "c" is an offered tool's full name: the other tool's own name, also "c", must not take it over
        routes = {"a__b": (None, "c"), "c": (None, "zzz")}
        self.assertEqual(mcp_aliases(routes, set(routes), set()), {"zzz": "c"})

    def test_the_parser_resolves_it_in_both_events(self):
        from serve.frontend import OutputParser
        schema = [{"name": "fake__echo", "parameters": {"type": "object", "properties": {"text": {"type": "string"}}}}]
        text = "</think>\n\n<tool_call>\n<function=echo>\n<parameter=text>\n42\n</parameter>\n</function>\n</tool_call>"
        for step in (1, 7, 10_000):
            with self.subTest(step=step):
                p = OutputParser(thinking=True, tools=schema, stream_tools=True, aliases={"echo": "fake__echo"})
                evs = []
                for i in range(0, len(text), step):
                    evs += p.feed(text[i:i + step])
                evs += p.finish()
                self.assertEqual([e.call.name for e in evs if e.kind == "tool_start"], ["fake__echo"])
                calls = [e.call for e in evs if e.kind == "tool_call"]
                self.assertEqual([(c.name, c.arguments) for c in calls], [("fake__echo", {"text": "42"})])
                streamed = "".join(e.text for e in evs if e.kind == "tool_args")
                self.assertEqual(json.loads(streamed), {"text": "42"})

    def test_without_aliases_the_parser_is_unchanged(self):
        from serve.frontend import OutputParser
        text = "</think>\n\n<tool_call>\n<function=echo>\n<parameter=text>\nhi\n</parameter>\n</function>\n</tool_call>"
        p = OutputParser(thinking=True, tools=None, stream_tools=True)
        evs = p.feed(text) + p.finish()
        self.assertEqual([e.call.name for e in evs if e.kind == "tool_call"], ["echo"])


# --------------------------------------------------------------------------- image parts in tool results
class ToolImages(unittest.TestCase):
    """A tool result that carries a picture: an image block with a string `source` (a local path or a URL - the
    shape the prompt's image pass already handles) becomes a part attached to the tool message; data blocks stay
    named in the text.  The fake server's `picture` tool supplies them."""

    @classmethod
    def setUpClass(cls):
        cls.hub = McpHub({"fake": stdio()}, {"timeout_s": 5})
        cls.hub.start(wait=True)

    @classmethod
    def tearDownClass(cls):
        cls.hub.close()

    def test_a_source_image_becomes_a_part_the_text_names_attached(self):
        r = self.hub.call("fake__picture", {"sources": ["D:\\graphs\\arch.png"]})
        self.assertTrue(r["ok"])
        self.assertEqual(r["images"], [{"type": "image", "source": "D:\\graphs\\arch.png"}])
        self.assertIn("here it is", r["text"])
        self.assertIn("arch.png", r["text"])

    def test_parts_keep_their_order_after_the_text(self):
        r = self.hub.call("fake__picture", {"sources": ["a.png", "b.png"]})
        self.assertEqual(r["images"], [{"type": "image", "source": "a.png"}, {"type": "image", "source": "b.png"}])

    def test_more_than_the_cap_is_left_out_with_a_note(self):
        r = self.hub.call("fake__picture", {"sources": ["a.png", "b.png", "c.png"]})
        self.assertEqual(len(r["images"]), MAX_RESULT_IMAGES)
        self.assertIn("left out", r["text"])

    def test_text_only_results_keep_the_default_path_exactly(self):
        r = self.hub.call("fake__echo", {"text": "plain"})
        self.assertEqual((r["ok"], r["text"], r["images"]), (True, "plain", []))

    def test_a_data_block_is_named_not_shown(self):
        self.assertEqual(result_text({"content": [{"type": "image", "data": "abcdefgh", "mimeType": "image/png"},
                                                  {"type": "text", "text": "word"}]}),
                         "[image (image/png, 6 bytes): not shown to the model]\nword")
        self.assertEqual(result_parts({"content": [{"type": "image", "data": "abcdefgh",
                                                    "mimeType": "image/png"}]}),
                         ("[image (image/png, 6 bytes): not shown to the model]", []))


if __name__ == "__main__":
    unittest.main()
