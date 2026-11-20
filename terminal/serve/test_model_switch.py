"""POST /v1/load {"model": <another of the config's "models">}: one model at a time, switched in the running server."""
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import serve.server as server
from serve.frontend import ChatTemplate
from serve.server import ByteTokenizer, MockEngine, Service, StrataEngine, model_profiles, serve


class SwitchEngine(StrataEngine):
    """The engine as a switch sees it: restart() starts what `spawn` says; args with --fail do not start."""

    def __init__(self, tok, spawn):
        self.reply = MockEngine(tok, "Hello.", max_context=4096)
        self.spawn = spawn
        self.max_context, self.info, self.last = 4096, {}, {}
        self.running, self.unloaded, self.progress = False, True, None
        self.started = []                               # the args of every start

    def alive(self):
        return self.running

    def exit_code(self):
        return None

    def restart(self):
        self.started.append(list(self.spawn[1]))
        if "--fail" in self.spawn[1]:
            raise RuntimeError("the engine exited before READY")
        self.running, self.unloaded = True, False
        self.info = {"version": "test"}

    def close(self):
        self.running = False

    def unload(self):
        self.close()
        self.unloaded = True

    def generate(self, *args, **kwargs):
        yield from self.reply.generate(*args, **kwargs)


def write(path: Path, cfg: dict) -> str:
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return str(path)


class ModelProfiles(unittest.TestCase):
    def test_the_config_first_then_its_models(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write(d / "b.json", {"exe": "strata", "args": [], "model_name": "model-b"})
            write(d / "same.json", {"exe": "strata", "args": [], "model_name": "model-b"})   # a name already taken
            (d / "broken.json").write_text("{", encoding="utf-8")
            write(d / "no-exe.json", {"args": []})
            cfg = {"exe": "strata", "args": [], "model_name": "model-a",
                   "models": ["b.json", "same.json", "broken.json", "no-exe.json", "missing.json", "b.json"]}
            a = write(d / "a.json", cfg)
            with mock.patch("builtins.print"):
                got = model_profiles(a, cfg)
            self.assertEqual(list(got), ["model-a", "model-b", "same"])
            self.assertEqual(got["model-a"], str((d / "a.json").resolve()))
            self.assertEqual(got["model-b"], str((d / "b.json").resolve()))
            self.assertEqual(model_profiles(a, {"exe": "strata", "args": []}), {"qwen3.8-flash-next": str(Path(a).resolve())})
            for bad in ("b.json", [1], [""]):
                with self.assertRaises(ValueError):
                    model_profiles(a, {**cfg, "models": bad})


class Switch(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        d = Path(self.dir.name)
        exe = d / "strata.exe"
        exe.write_bytes(b"")
        for f in ("a.gguf", "b.gguf", "c.gguf", "mmproj.gguf"):
            (d / f).write_bytes(b"")
        vision = {"exe": str(exe), "mmproj": str(d / "mmproj.gguf"), "model": str(d / "a.gguf"), "threads": 4}
        self.a = write(d / "a.json", {"exe": str(exe), "args": ["--native", str(d / "a.gguf"), "--max-context", "4096"],
                                      "model_name": "model-a", "vision": vision, "models": ["b.json", "c.json"]})
        write(d / "b.json", {"exe": str(exe), "args": ["--native", str(d / "b.gguf"), "--max-context", "8192"],
                             "model_name": "model-b", "sampling": {"temperature": 0.6}, "aliases": ["b-alias"],
                             "fit_max_tokens": True})
        write(d / "c.json", {"exe": str(exe), "args": ["--native", str(d / "c.gguf"), "--fail"], "model_name": "model-c"})
        def encoder_up(vision):                         # the image encoder "runs" without a process
            vision.proc, vision.stopped = mock.Mock(**{"poll.return_value": None}), False
        for patch in (mock.patch.object(server, "load_tokenizer", lambda p: ByteTokenizer()),
                      mock.patch.object(server.Vision, "_start", encoder_up)):
            patch.start()
            self.addCleanup(patch.stop)
        quiet = mock.patch("builtins.print")
        quiet.start()
        self.addCleanup(quiet.stop)
        tok = ByteTokenizer()
        self.engine = SwitchEngine(tok, ("strata", [], None, None, None, False, None))
        self.svc = Service(self.engine, tok, ChatTemplate(Path(server.__file__).parent / "chat_template.jinja"),
                           model_name="model-a")
        self.svc.profiles = model_profiles(self.a, json.loads(Path(self.a).read_text(encoding="utf-8")))
        self.svc._apply_profile(self.svc.profile_state("model-a", self.svc.profiles["model-a"]))
        self.svc.ensure_loaded()
        self.httpd = serve(self.svc, port=0)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        if self.svc.vision is not None:
            self.svc.vision.shutdown()
        self.dir.cleanup()

    def request(self, path, body=None, headers=None):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", **(headers or {})})
        try:
            response = urllib.request.urlopen(req, timeout=20)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read().decode())

    CHAT = {"messages": [{"role": "user", "content": "Hello"}], "max_tokens": 16, "reasoning_effort": "none"}

    def test_switch_and_back(self):
        first_vision = self.svc.vision
        self.assertTrue(first_vision.alive())            # started with model-a
        code, body = self.request("/v1/load?wait=1", {"model": "model-b"})
        self.assertEqual(code, 200, body)
        self.assertEqual(body["model"], "model-b")
        self.assertEqual(body["models"]["current"], "model-b")
        self.assertTrue(self.engine.started[-1][1].endswith("b.gguf"))
        self.assertTrue(self.svc.config_path.endswith("b.json"))
        self.assertEqual(self.svc.sampling_defaults, {"temperature": 0.6})
        self.assertEqual(self.svc.aliases, ["b-alias"])
        self.assertIsNone(self.svc.vision)               # model-b has no image encoder
        self.assertTrue(self.svc.fit_max_tokens)         # model-b's small window clamps a client's 32K cap
        self.assertTrue(first_vision.stopped)            # model-a's was stopped
        self.assertEqual(self.engine.info, {"version": "test"})
        code, answer = self.request("/v1/chat/completions", self.CHAT)
        self.assertEqual(code, 200)
        self.assertEqual(answer["model"], "model-b")
        self.assertEqual(answer["choices"][0]["message"]["content"], "Hello.")
        code, body = self.request("/v1/load?wait=1", {"model": "model-a"})
        self.assertEqual(code, 200, body)
        self.assertTrue(self.engine.started[-1][1].endswith("a.gguf"))
        self.assertEqual(self.svc.sampling_defaults, {})
        self.assertFalse(self.svc.fit_max_tokens)
        self.assertTrue(self.svc.vision.alive())         # model-a's encoder is back, a new one
        self.assertIsNot(self.svc.vision, first_vision)
        self.assertEqual(self.svc.models_view()["available"], ["model-a", "model-b", "model-c"])

    def test_answers_at_once_and_says_when_done(self):
        code, body = self.request("/v1/load", {"model": "model-b"})
        self.assertEqual(code, 202, body)
        self.assertEqual((body["status"], body["from"]), ("switching", "model-a"))
        deadline = time.time() + 10
        while (self.svc.switching is not None or self.svc.model != "model-b") and time.time() < deadline:
            time.sleep(0.05)
        self.assertEqual(self.svc.model, "model-b")
        metrics = self.request("/metrics")[1]
        self.assertEqual(metrics["models"]["current"], "model-b")
        self.assertIsNone(metrics["models"]["switching"])

    def test_a_model_that_does_not_start_brings_the_previous_one_back(self):
        code, body = self.request("/v1/load?wait=1", {"model": "model-c"})
        self.assertEqual(code, 503, body)
        self.assertIn("model-c did not start", body["error"]["message"])
        self.assertEqual(self.svc.model, "model-a")
        self.assertTrue(self.engine.running)
        self.assertTrue(self.engine.started[-1][1].endswith("a.gguf"))
        err = self.request("/metrics")[1]["models"]["last_error"]
        self.assertEqual(err["model"], "model-c")
        self.assertEqual(self.request("/v1/chat/completions", self.CHAT)[0], 200)

    def test_new_requests_wait_for_the_new_model(self):
        self.svc.switching = {"from": "model-a", "to": "model-b", "since": time.time(), "phase": "loading"}
        out = {}
        t = threading.Thread(target=lambda: out.update(r=self.request("/v1/chat/completions", self.CHAT)))
        try:
            t.start()
            time.sleep(0.6)
            self.assertTrue(t.is_alive(), "a request went on while the model switched")
            self.assertEqual(self.svc.status["queued"], 0)   # not counted: the switch does not wait for it
            self.assertEqual(self.request("/metrics")[1]["live"]["state"], "switching")
            with self.assertRaisesRegex(server.EngineStarting, "being switched to model-b"):
                self.svc.prepare([{"role": "user", "content": "Hello"}], None, {})   # one that skipped load()
        finally:
            self.svc.switching = None
        t.join(10)
        self.assertEqual(out["r"][0], 200)

    def test_a_running_request_is_waited_for(self):
        self.svc.SWITCH_WAIT_S = 0.3
        self.svc.status["busy"] = True
        try:
            code, body = self.request("/v1/load?wait=1", {"model": "model-b"})
        finally:
            self.svc.status["busy"] = False
        self.assertEqual(code, 409, body)
        self.assertEqual(self.svc.model, "model-a")
        self.assertTrue(self.engine.running)            # not unloaded
        self.assertIsNone(self.svc.switching)
        self.assertEqual(self.request("/v1/load?wait=1", {"model": "model-b"})[0], 200)

    def test_another_switch_or_a_foreign_page_is_refused(self):
        with self.svc.switch_lock:
            self.assertEqual(self.request("/v1/load", {"model": "model-b"})[0], 409)
        self.assertEqual(self.request("/v1/load", {"model": "model-b"}, {"Origin": "https://other.example"})[0], 403)
        self.assertEqual(self.request("/v1/load", {"model": "no-such-model"})[0], 404)
        self.svc.api_key = "local-secret"
        self.assertEqual(self.request("/v1/load", {"model": "model-b"})[0], 401)
        self.assertEqual(self.svc.model, "model-a")

    def test_a_broken_config_is_said_before_anything_stops(self):
        Path(self.svc.profiles["model-b"]).write_text(json.dumps({"exe": "missing.exe", "args": []}), encoding="utf-8")
        code, body = self.request("/v1/load", {"model": "model-b"})
        self.assertEqual(code, 400)
        self.assertIn("missing", body["error"]["message"])
        self.assertEqual(self.svc.model, "model-a")
        self.assertTrue(self.engine.running)
        cfg = {"exe": str(Path(self.dir.name) / "strata.exe"), "args": ["--native", "not-downloaded.gguf"]}
        Path(self.svc.profiles["model-b"]).write_text(json.dumps(cfg), encoding="utf-8")
        code, body = self.request("/v1/load", {"model": "model-b"})
        self.assertEqual(code, 400)
        self.assertIn("not-downloaded.gguf is missing", body["error"]["message"])
        self.assertTrue(self.engine.running)


if __name__ == "__main__":
    unittest.main()
