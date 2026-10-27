#!/usr/bin/env python3
"""model-router: one OpenAI/Anthropic endpoint in front of two local models.

A request's `model` field selects the engine:
  * contains "qwen" or "ornith"     -> qwen serve  (port 18080, config strata-q2_0-v144-refusal.json)
  * contains "deepseek" or "ds41"   -> DeepSeek    (port 8080, terminal preset "ds41f")
Default: DeepSeek. Before starting one model the other is stopped, so only one
engine ever holds the 12 GB card. Logs to %LOCALAPPDATA%\\strata-stack\\model-router.log

The web page (served by the active engine) lists its models from /metrics.  This
router rewrites that list to include the other engine too, and answers
POST /v1/load by starting/switching the engine in the background, so the model
picker in the page can reach both models.
"""
import http.client
import http.server
import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

HOME = Path(r"D:\GitHub\Strata")
STACK = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\ADMIN\AppData\Local")) / "strata-stack"
LOG = STACK / "model-router.log"
VENV_PY = HOME / ".venv" / "Scripts" / "python.exe"
QWEN_CFG = HOME / "strata-q2_0-v144-refusal.json"
QWEN_PORT, DS_PORT = 18080, 8080
QWEN_ID, DS_ID = "qwen38-q2_0-refusal", "deepseek-v4.1-flash"
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


def ready(model):
    port = QWEN_PORT if model == "qwen" else DS_PORT
    st = backend_status(port, qwen_key() if model == "qwen" else None)
    return bool(st and st.get("loaded"))


def active_port():
    return QWEN_PORT if _active == "qwen" else DS_PORT


def current_id(model=None):
    m = model or _active
    if m == "ds":
        return DS_ID
    if m == "qwen":
        st = _last_status.get(QWEN_PORT) or {}
        return ((st.get("models") or {}).get("current")) or QWEN_ID
    return None


def known_ids():
    avail = []
    for port in (QWEN_PORT, DS_PORT):
        for n in ((((_last_status.get(port) or {}).get("models") or {}).get("available")) or []):
            if isinstance(n, str) and n not in avail:
                avail.append(n)
    for n in (QWEN_ID, DS_ID):
        if n not in avail:
            avail.append(n)
    return avail


def merged_models(backend=None):
    bm = dict(backend or {})
    avail = [n for n in (bm.get("available") or []) if isinstance(n, str)]
    for n in (QWEN_ID, DS_ID):
        if n not in avail:
            avail.append(n)
    cur = bm.get("current")
    if _active == "ds":
        cur = DS_ID
    elif _active == "qwen" and not cur:
        cur = QWEN_ID
    return {"current": cur, "available": avail,
            "switching": _switching if _switching else bm.get("switching"),
            "last_error": bm.get("last_error")}


def cached_metrics():
    for port in (active_port(), QWEN_PORT, DS_PORT):
        if port in _last_metrics:
            return json.loads(json.dumps(_last_metrics[port]))
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


def start_ds():
    env = dict(os.environ)
    env["STRATA_ALLOWED_HOSTS"] = "pc-dik-win.tail1b3f7b.ts.net"
    out = open(STACK / "ds41-serve.log", "ab")
    cmd = r"C:\Users\ADMIN\AppData\Local\Strata\terminal\current\bin\strata.cmd"
    subprocess.Popen([cmd, "launch", "--preset", "ds41f", "--yes", "--no-tui"],
                     cwd=str(HOME), env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=out,
                     creationflags=NO_WINDOW)
    log("started ds41f on %d" % DS_PORT)


def wait_ready(model, seconds=420):
    t0 = time.time()
    while time.time() - t0 < seconds:
        if ready(model):
            return True
        time.sleep(2)
    return False


def ensure(model):
    """Make `model` the one loaded model. Serialized; stops the other engine first."""
    global _active
    with _lock:
        port, other = (QWEN_PORT, DS_PORT) if model == "qwen" else (DS_PORT, QWEN_PORT)
        other_name = "deepseek" if model == "qwen" else "qwen"
        if ready(model) and _active == model:
            return True
        if listening(other):
            log("switch %s -> %s: stopping %s" % (_active, model, other_name))
            kill_port(other)
            _active = None
        if ready(model):
            _active = model
            return True
        if listening(port):
            log("%s listens but is not loaded: restarting it" % model)
            kill_port(port)
        log("starting %s (cold start; VRAM %s)" % (model, "free" if not listening(other) else "busy"))
        (start_qwen if model == "qwen" else start_ds)()
        ok = wait_ready(model)
        if ok:
            _active = model
            log("%s ready" % model)
        else:
            log("%s FAILED to become ready" % model)
        return ok


def pick(model_name):
    m = (model_name or "").lower()
    if "deepseek" in m or "ds41" in m:
        return "ds"
    if "qwen" in m or "ornith" in m:
        return "qwen"
    return "ds"


def do_load(name):
    """POST /v1/load in the page: start the engine (and, for a qwen config such as
    ornith, let the qwen server switch inside its own engine)."""
    global _switching
    try:
        target = pick(name)
        ok = ensure(target)
        if ok and target == "qwen":
            cur = current_id("qwen") or ""
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
    server_version = "model-router/1.1"
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

    def _route(self, body):
        try:
            name = json.loads(body.decode("utf-8", "replace") or "{}").get("model", "")
        except Exception:
            name = ""
        model = pick(name)
        if not ensure(model):
            self._json(503, {"error": {"type": "router",
                                       "message": "%s did not start; see model-router.log" % model}})
            return
        if model == "qwen":
            self._proxy(QWEN_PORT, qwen_key(), body)
        else:
            self._proxy(DS_PORT, None, body)

    def do_OPTIONS(self):
        self.send_response(204)
        for h in ("Access-Control-Allow-Origin", "Access-Control-Allow-Headers",
                  "Access-Control-Allow-Methods"):
            self.send_header(h, "*" if h != "Access-Control-Allow-Headers" else "*")
        self.send_header("Connection", "close")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/health", "/healthz"):
            if _switching or not listening(active_port()):
                target = (_switching or {}).get("to") or (QWEN_ID if _active == "qwen" else DS_ID)
                self._json(200, {"status": "ok", "service": "strata", "model": target,
                                 "loaded": False, "images": False, "max_context": 262144,
                                 "router": True, "active": _active})
                return
            self._proxy(active_port(), qwen_key() if _active == "qwen" else None, b"")
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
            port = active_port()
            if not listening(port):
                self._json(200, {"service": "model-router", "loaded": False, "active": _active,
                                 "models": {"current": None, "available": known_ids(),
                                            "switching": None, "last_error": None}})
                return
            try:
                code, st = fetch_json(port, qwen_key() if _active == "qwen" else None, self.path)
                st["models"] = merged_models(st.get("models"))
                _last_status[port] = st
                self._json(code, st)
            except Exception as e:
                log("status error on %d: %s" % (port, e))
                self._json(502, {"error": {"type": "router", "message": str(e)}})
            return
        if path == "/metrics":
            if _switching:
                m = cached_metrics()
                m["models"] = {"current": _switching.get("from"), "available": known_ids(),
                               "switching": _switching, "last_error": None}
                self._json(200, m)
                return
            port = active_port()
            if not listening(port):
                self._json(503, {"error": {"type": "router", "message": "no model loaded yet"}})
                return
            try:
                code, m = fetch_json(port, qwen_key() if _active == "qwen" else None, self.path)
                m["models"] = merged_models(m.get("models"))
                _last_metrics[port] = m
                self._json(code, m)
            except Exception as e:
                log("metrics error on %d: %s" % (port, e))
                self._json(502, {"error": {"type": "router", "message": str(e)}})
            return
        if path == "/mcp":
            if _active is None and not listening(QWEN_PORT) and not listening(DS_PORT):
                self._json(200, {"servers": []})
                return
            port = active_port()
            self._proxy(port, qwen_key() if _active == "qwen" else None, b"")
            return
        # the web page and everything else: serve from the active model, default DeepSeek
        if path in ("/", "/index.html") and _active is None:
            ensure("ds")
        port = active_port()
        if not listening(port):
            self._json(503, {"error": {"type": "router", "message": "no model loaded yet: send a request with a model name"}})
            return
        self._proxy(port, qwen_key() if _active == "qwen" else None, b"")

    def do_POST(self):
        global _switching
        path = self.path.split("?")[0]
        body = self._body()
        if path in ("/v1/load", "/load"):
            try:
                name = json.loads(body.decode("utf-8", "replace") or "{}").get("model", "")
            except Exception:
                name = ""
            if not name:
                self._json(400, {"error": {"type": "router", "message": "no model name"}})
                return
            with _switch_lock:
                if _switching:
                    self._json(409, {"error": {"type": "router", "message": "a switch is already running"}})
                    return
                _switching = {"phase": "switching", "from": current_id() or _active, "to": name}
            log("web load -> %s" % name)
            threading.Thread(target=do_load, args=(name,), daemon=True).start()
            self._json(202, {"ok": True, "model": name})
            return
        self._route(body)

    def do_PUT(self):
        self._route(self._body())


class ThreadingServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    log("router starting on %d (qwen %d, deepseek %d)" % (PORT, QWEN_PORT, DS_PORT))
    ThreadingServer(("0.0.0.0", PORT), Handler).serve_forever()