#!/usr/bin/env python3
"""model-router v1.2: one OpenAI/Anthropic endpoint in front of the local qwen engine.

A request's `model` field must name the qwen family ("qwen" or "ornith"); anything
that still asks for DeepSeek ("deepseek", "ds41") gets a clear 404 - the model and
its preset were removed from this machine on 2026-10-29, they must not silently
route to the wrong engine. Empty or placeholder names stay on the active engine
(the page sends its current model once /health has answered).

The web page (served from the checkout by this router) lists its models from
/metrics; POST /v1/load answers with {"restart": true} to bounce the engine after
a config change without a second model to switch through.
Logs to %LOCALAPPDATA%\\strata-stack\\model-router.log
"""
import http.client
import http.server
import json
import mimetypes
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

HOME = Path(r"D:\GitHub\Strata")
STACK = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\ADMIN\AppData\Local")) / "strata-stack"
WEB_DIR = HOME / "serve" / "web"
LOG = STACK / "model-router.log"
VENV_PY = HOME / ".venv" / "Scripts" / "python.exe"
QWEN_CFG = HOME / "strata-q2_0-v144-refusal.json"
QWEN_PORT = 18080
QWEN_ID = "qwen38-q2_0-refusal"
PORT = int(os.environ.get("MODEL_ROUTER_PORT", "8081"))
NO_WINDOW = 0x08000000

_lock = threading.Lock()
_switch_lock = threading.Lock()
_active = None
_switching = None            # {"phase": ..., "from": ..., "to": ...} while a /v1/load runs
_last_metrics = {}           # port -> last good /metrics JSON (served while switching)
_last_status = {}            # port -> last good /v1/status JSON


def log(msg):
    STACK.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))


def qwen_key():
    try:
        return json.loads(QWEN_CFG.read_text(encoding="utf-8")).get("api_key")
    except Exception:
        return None


def listening(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


def fetch_json(port, key, path, method="GET", body=None, timeout=60):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    h = {"Authorization": "Bearer " + key} if key else {}
    if body is not None:
        h["Content-Type"] = "application/json"
        h["Content-Length"] = str(len(body))
    c.request(method, path, body=body, headers=h)
    r = c.getresponse()
    raw = r.read().decode("utf-8", "replace")
    return r.status, (json.loads(raw) if raw else {})


def backend_status(port, key=None):
    try:
        code, st = fetch_json(port, key, "/v1/status", timeout=5)
        return st if code == 200 else None
    except Exception:
        return None


def ready():
    st = backend_status(QWEN_PORT, qwen_key())
    return bool(st and st.get("loaded"))


def detect_active():
    """The router can be restarted while an engine stays up."""
    return "qwen" if (listening(QWEN_PORT) and ready()) else None


def active_port():
    global _active
    if _active is None:
        _active = detect_active()
    return QWEN_PORT


def current_id():
    st = _last_status.get(QWEN_PORT) or {}
    return ((st.get("models") or {}).get("current")) or (QWEN_ID if _active else None)


def known_ids():
    avail = []
    for n in ((((_last_status.get(QWEN_PORT) or {}).get("models") or {}).get("available")) or []):
        if isinstance(n, str) and n not in avail:
            avail.append(n)
    if QWEN_ID not in avail:
        avail.append(QWEN_ID)
    return avail


def merged_models(backend=None):
    bm = dict(backend or {})
    avail = [n for n in (bm.get("available") or []) if isinstance(n, str)]
    if QWEN_ID not in avail:
        avail.append(QWEN_ID)
    cur = bm.get("current")
    if _active == "qwen" and not cur:
        cur = QWEN_ID
    return {"current": cur, "available": avail,
            "switching": _switching if _switching else bm.get("switching"),
            "last_error": bm.get("last_error")}


def cached_metrics():
    if QWEN_PORT in _last_metrics:
        return json.loads(json.dumps(_last_metrics[QWEN_PORT]))
    return {"live": {"state": "idle"}, "models": {}}


def kill_port(port):
    """Stop whatever listens on `port` (its cmd/python/powershell tree)."""
    ps = (
        "$c=(Get-NetTCPConnection -State Listen -LocalPort %d -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess;"
        "if($c){$p=Get-CimInstance Win32_Process -Filter \"ProcessId=$c\";"
        "while($true){$q=Get-CimInstance Win32_Process -Filter \"ProcessId=$($p.ParentProcessId)\";"
        "if($q -and $q.Name -in 'python.exe','cmd.exe','powershell.exe' -and $q.ProcessId -ne %d){$p=$q}else{break}};"
        "taskkill /PID $p.ProcessId /T /F 2>$null | Out-Null}" % (port, os.getpid())
    )
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                   capture_output=True, timeout=180)
    t0 = time.time()
    while listening(port) and time.time() - t0 < 90:
        time.sleep(1)


def start_qwen():
    out = open(STACK / "qwen-serve.log", "ab")
    subprocess.Popen([str(VENV_PY), str(HOME / "serve" / "server.py"), "--engine", "strata",
                      "--config", str(QWEN_CFG), "--port", str(QWEN_PORT)],
                     cwd=str(HOME), stdin=subprocess.DEVNULL, stdout=out, stderr=out,
                     creationflags=NO_WINDOW)
    log("started qwen on %d" % QWEN_PORT)


def wait_ready(seconds=420):
    t0 = time.time()
    while time.time() - t0 < seconds:
        if ready():
            return True
        time.sleep(2)
    return False


def ensure(restart=False):
    """Make qwen the one loaded model. Serialized; `restart` bounces the engine."""
    global _active
    with _lock:
        if ready():
            if not restart and _active == "qwen":
                return True
            log("restart: stopping qwen on %d" % QWEN_PORT)
            kill_port(QWEN_PORT)
            _active = None
        elif listening(QWEN_PORT):
            log("qwen listens but is not loaded: restarting it")
            kill_port(QWEN_PORT)
        log("starting qwen (cold start)")
        start_qwen()
        ok = wait_ready()
        if ok:
            _active = "qwen"
            log("qwen ready")
        else:
            log("qwen FAILED to become ready")
        return ok


def pick(model_name):
    """None means this name is gone from the machine (answer 404)."""
    m = (model_name or "").lower()
    if "deepseek" in m or "ds41" in m or "dsv41" in m:
        return None
    if "qwen" in m or "ornith" in m or not m:
        return "qwen"
    return "qwen"


def do_load(name, restart=False):
    """POST /v1/load in the page: (re)start the engine and, for a qwen config
    such as ornith, let the qwen server switch inside its own engine."""
    global _switching
    try:
        if pick(name) is None:
            log("load %s refused: removed from this machine" % name)
            return
        ok = ensure(restart)
        if ok:
            cur = current_id() or ""
            if name and name.lower() not in (cur.lower(), "qwen"):
                try:
                    body = json.dumps({"model": name}).encode()
                    key = qwen_key()
                    fetch_json(QWEN_PORT, key, "/v1/load", method="POST", body=body, timeout=420)
                    t0 = time.time()
                    while time.time() - t0 < 420:
                        st = backend_status(QWEN_PORT, key)
                        m = ((st or {}).get("models") or {})
                        if not m.get("switching") and (m.get("current") or "").lower() == name.lower():
                            break
                        time.sleep(2)
                except Exception as e:
                    log("load %s inside qwen: %s" % (name, e))
        log("load %s: %s" % (name, "ok" if ok else "FAILED"))
    finally:
        _switching = None


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "model-router/1.2"
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt, *args):
        pass

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _json(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)

    def _proxy(self, port, key, body):
        try:
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=3600)
            headers = {k: v for k, v in self.headers.items()
                       if k.lower() not in ("host", "connection", "content-length", "keep-alive")}
            if key:
                headers["Authorization"] = "Bearer " + key
            if body:
                headers["Content-Length"] = str(len(body))
            c.request(self.command, self.path, body=body if body else None, headers=headers)
            r = c.getresponse()
            self.send_response(r.status)
            for k, v in r.getheaders():
                if k.lower() in ("transfer-encoding", "connection", "content-length", "keep-alive"):
                    continue
                self.send_header(k, v)
            self.send_header("Connection", "close")
            self.end_headers()
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except Exception as e:
            log("proxy error on %d: %s" % (port, e))
            try:
                self._json(502, {"error": {"type": "router", "message": "backend on %d: %s" % (port, e)}})
            except Exception:
                pass

    def _static(self, path):
        """Serve the UI from the checkout so the page does not change when the active engine does."""
        rel = "index.html" if path in ("/", "/index.html") else path.lstrip("/")
        if rel.startswith("web/"):
            rel = rel[4:]
        base = WEB_DIR.resolve()
        try:
            file = (base / rel).resolve()
            file.relative_to(base)
        except (OSError, ValueError):
            self.send_error(404)
            return
        if not file.is_file():
            self.send_error(404)
            return
        data = file.read_bytes()
        ctype = mimetypes.guess_type(str(file))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache" if rel == "index.html" else "public, max-age=300")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)

    def _route(self, body):
        try:
            name = json.loads(body.decode("utf-8", "replace") or "{}").get("model", "")
        except Exception:
            name = ""
        if pick(name) is None:
            self._json(404, {"error": {"type": "router", "code": "model_removed",
                                       "message": "%s was removed from this machine (2026-10-29); "
                                                  "use %s" % (name, QWEN_ID)}})
            return
        if not ensure():
            self._json(503, {"error": {"type": "router",
                                       "message": "qwen did not start; see model-router.log"}})
            return
        self._proxy(QWEN_PORT, qwen_key(), body)

    def do_OPTIONS(self):
        self.send_response(204)
        for h in ("Access-Control-Allow-Origin", "Access-Control-Allow-Headers",
                  "Access-Control-Allow-Methods"):
            self.send_header(h, "*")
        self.send_header("Connection", "close")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html") or path.startswith("/web/"):
            self._static(path)
            return
        if path in ("/health", "/healthz"):
            if _switching or not listening(active_port()):
                self._json(200, {"status": "ok", "service": "strata",
                                 "model": (_switching or {}).get("to") or QWEN_ID,
                                 "loaded": False, "images": False, "max_context": 262144,
                                 "router": True, "active": _active})
                return
            self._proxy(QWEN_PORT, qwen_key(), b"")
            return
        if path == "/v1/models":
            self._json(200, {"object": "list", "data": [
                {"id": n, "object": "model", "owned_by": "local", "created": 0}
                for n in known_ids()
            ]})
            return
        if path == "/v1/status":
            if _switching:
                st = {"service": "strata", "loaded": True, "model": (_switching or {}).get("to"),
                      "active": _active,
                      "models": {"current": _switching.get("from"), "available": known_ids(),
                                 "switching": _switching, "last_error": None}}
                self._json(200, st)
                return
            if not listening(QWEN_PORT):
                self._json(200, {"service": "model-router", "loaded": False, "active": _active,
                                 "models": {"current": None, "available": known_ids(),
                                            "switching": None, "last_error": None}})
                return
            try:
                code, st = fetch_json(QWEN_PORT, qwen_key(), self.path)
                st["models"] = merged_models(st.get("models"))
                _last_status[QWEN_PORT] = st
                self._json(code, st)
            except Exception as e:
                log("status error on %d: %s" % (QWEN_PORT, e))
                self._json(502, {"error": {"type": "router", "message": str(e)}})
            return
        if path == "/metrics":
            if _switching:
                m = cached_metrics()
                m["models"] = {"current": _switching.get("from"), "available": known_ids(),
                               "switching": _switching, "last_error": None}
                self._json(200, m)
                return
            if not listening(QWEN_PORT):
                self._json(503, {"error": {"type": "router", "message": "no model loaded yet"}})
                return
            try:
                code, m = fetch_json(QWEN_PORT, qwen_key(), self.path)
                m["models"] = merged_models(m.get("models"))
                _last_metrics[QWEN_PORT] = m
                self._json(code, m)
            except Exception as e:
                log("metrics error on %d: %s" % (QWEN_PORT, e))
                self._json(502, {"error": {"type": "router", "message": str(e)}})
            return
        if path == "/mcp":
            if _active is None and not listening(QWEN_PORT):
                self._json(200, {"servers": []})
                return
            self._proxy(QWEN_PORT, qwen_key(), b"")
            return
        # the web page and everything else: serve from the active model
        port = active_port()
        if not listening(port):
            self._json(503, {"error": {"type": "router", "message": "no model loaded yet: send a request with a model name"}})
            return
        self._proxy(port, qwen_key(), b"")

    def do_POST(self):
        global _switching
        path = self.path.split("?")[0]
        body = self._body()
        if path in ("/v1/load", "/load"):
            try:
                req = json.loads(body.decode("utf-8", "replace") or "{}")
            except Exception:
                req = {}
            name = req.get("model", "")
            restart = bool(req.get("restart"))
            if not name:
                self._json(400, {"error": {"type": "router", "message": "no model name"}})
                return
            with _switch_lock:
                if _switching:
                    self._json(409, {"error": {"type": "router", "message": "a switch is already running"}})
                    return
                _switching = {"phase": "switching", "from": current_id() or _active, "to": name}
            log("web load -> %s%s" % (name, " (restart)" if restart else ""))
            threading.Thread(target=do_load, args=(name, restart), daemon=True).start()
            self._json(202, {"ok": True, "model": name})
            return
        self._route(body)

    def do_PUT(self):
        self._route(self._body())


class ThreadingServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    _active = detect_active()
    log("router starting on %d (qwen %d; active %s)" % (PORT, QWEN_PORT, _active))
    ThreadingServer(("0.0.0.0", PORT), Handler).serve_forever()
