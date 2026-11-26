#!/usr/bin/env python3
"""model-router v1.3: one OpenAI/Anthropic endpoint in front of two local engines.

The chain is OpenCode (or any client) -> this router -> the model named in the request:
  - qwen3.8-flash-next-ud-q2_0  -> the Qwen engine on 18080 (strata.exe)
  - inkling-2-mini-sq-10        -> the Inkling engine on 8000 (strata-inkling.exe, stock weights)
  - inkling-2-mini-sq-10-unc    -> the same Inkling server, switched to its abliterated profile
One model is loaded at a time on a 12 GB card: before a backend serves, the other one is unloaded
(/v1/unload), so a request that names a model switches by itself. A request that still asks for
DeepSeek ("deepseek", "ds41") gets the same clear 404 as before.

The web page (served from the checkout by this router) lists the models from /v1/models; POST
/v1/load answers at once and switches in the background. Logs to
%LOCALAPPDATA%\\strata-stack\\model-router.log
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
# 0.2.16 moved serve/ under terminal/: keep one rule for the server and the page it serves.
SERVE_DIR = HOME / "terminal" / "serve"
if not SERVE_DIR.is_dir():
    SERVE_DIR = HOME / "serve"                   # the layout before 0.2.16
WEB_DIR = SERVE_DIR / "web"
LOG = STACK / "model-router.log"
VENV_PY = HOME / ".venv" / "Scripts" / "python.exe"

QWEN_CFG = HOME / "terminal" / "strata-ud-q2_0-tuned.json"
if not QWEN_CFG.is_file():                       # the layout before the 0.2.22 adoption moved it into terminal/
    QWEN_CFG = HOME / "strata-ud-q2_0-tuned.json"
QWEN_PORT = 18080
QWEN_ID = "qwen3.8-flash-next-ud-q2_0"

INK_CFG = HOME / "terminal" / "strata-inkling-sq10-stock.json"
INK_PORT = 8000
INK_ID = "inkling-2-mini-sq-10"
INK_FAST_ID = "inkling-2-mini-sq-10-fast"
INK_UNC_ID = "inkling-2-mini-sq-10-unc"

PORT = int(os.environ.get("MODEL_ROUTER_PORT", "8081"))
NO_WINDOW = 0x08000000

BACKENDS = {
    "qwen": {"port": QWEN_PORT, "cfg": QWEN_CFG, "id": QWEN_ID,
             "log": STACK / "qwen-serve.log", "ids": [QWEN_ID]},
    "inkling": {"port": INK_PORT, "cfg": INK_CFG, "id": INK_ID,
                "log": STACK / "inkling-serve.log", "ids": [INK_ID, INK_FAST_ID, INK_UNC_ID]},
}

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


def key_of(name):
    try:
        return json.loads(BACKENDS[name]["cfg"].read_text(encoding="utf-8-sig")).get("api_key") or None
    except Exception:
        return None


def port_of(name):
    return BACKENDS[name]["port"]


def id_of(name):
    return BACKENDS[name]["id"]


def listening(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


def fetch_json(port, key, path, method="GET", body=None, timeout=60, origin=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    h = {"Authorization": "Bearer " + key} if key else {}
    if origin:
        h["Origin"] = origin
    if body is not None:
        h["Content-Type"] = "application/json"
        h["Content-Length"] = str(len(body))
    c.request(method, path, body=body, headers=h)
    r = c.getresponse()
    raw = r.read().decode("utf-8", "replace")
    return r.status, (json.loads(raw) if raw else {})


def backend_status(name):
    try:
        code, st = fetch_json(port_of(name), key_of(name), "/v1/status", timeout=5)
        if code == 200:
            _last_status[port_of(name)] = st
            return st
    except Exception:
        pass
    return None


def model_available(st):
    m = (st or {}).get("models") or {}
    cur, avail = m.get("current"), m.get("available")
    out = [n for n in (avail or []) if isinstance(n, str)]
    if isinstance(cur, str) and cur not in out:
        out.insert(0, cur)
    return out


def ready_of(name):
    st = backend_status(name)
    return bool(st and st.get("loaded"))


def any_ready():
    for name in BACKENDS:
        if listening(port_of(name)) and ready_of(name):
            return name
    return None


def detect_active():
    """The router can be restarted while an engine stays up."""
    return any_ready()


def active_port():
    global _active
    if _active is None:
        _active = detect_active()
    return port_of(_active) if _active else QWEN_PORT


def active_key():
    return key_of(_active) if _active else key_of("qwen")


def current_id():
    if _active:
        st = _last_status.get(port_of(_active)) or backend_status(_active) or {}
        cur = ((st.get("models") or {}).get("current"))
        if isinstance(cur, str) and cur:
            return cur
        return id_of(_active)
    return None


def known_ids():
    out = []
    for name in ("qwen", "inkling"):
        st = backend_status(name) if listening(port_of(name)) else None
        ids = model_available(st) or BACKENDS[name]["ids"]
        for n in ids:
            if n not in out:
                out.append(n)
    if QWEN_ID not in out:
        out.insert(0, QWEN_ID)
    return out


def merged_models(backend=None):
    bm = dict(backend or {})
    avail = known_ids()
    cur = current_id() or bm.get("current")
    return {"current": cur, "available": avail,
            "switching": _switching if _switching else bm.get("switching"),
            "last_error": bm.get("last_error")}


def cached_metrics():
    port = port_of(_active) if _active else QWEN_PORT
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


def start_backend(name):
    be = BACKENDS[name]
    out = open(be["log"], "ab")
    subprocess.Popen([str(VENV_PY), str(SERVE_DIR / "server.py"), "--engine", "strata",
                      "--config", str(be["cfg"]), "--port", str(be["port"])],
                     cwd=str(HOME), stdin=subprocess.DEVNULL, stdout=out, stderr=out,
                     creationflags=NO_WINDOW)
    log("started %s on %d" % (name, be["port"]))


def wait_ready(name, seconds=420):
    t0 = time.time()
    while time.time() - t0 < seconds:
        if ready_of(name):
            return True
        time.sleep(2)
    return False


def unload(name):
    """Free the card: the other backend's model goes (the process stays, auto-load on the next request)."""
    if not listening(port_of(name)):
        return
    if not ready_of(name):
        return
    try:
        fetch_json(port_of(name), key_of(name), "/v1/unload", method="POST", body=b"{}",
                   timeout=120, origin="http://127.0.0.1:%d" % PORT)
        t0 = time.time()
        while time.time() - t0 < 60 and ready_of(name):
            time.sleep(1)
    except Exception as e:
        log("unload %s: %s" % (name, e))
    log("unloaded %s" % name)


def ensure_backend(name, restart=False):
    """Start it if needed. A serve that is up but unloaded loads on the request that follows."""
    global _active
    with _lock:
        if restart and listening(port_of(name)):
            log("restart: stopping %s on %d" % (name, port_of(name)))
            kill_port(port_of(name))
            _active = None
        if listening(port_of(name)):
            if not ready_of(name):
                log("%s listens but is unloaded: the request will load it" % name)
            _active = name
            return True
        log("starting %s (cold start)" % name)
        start_backend(name)
        ok = wait_ready(name)
        if ok:
            _active = name
            log("%s ready" % name)
        else:
            log("%s FAILED to become ready" % name)
        return ok


def switch_to(name, model="", restart=False):
    """Serve `model` from backend `name`: unload the other model, start this one, switch its profile."""
    global _active
    other = "inkling" if name == "qwen" else "qwen"
    with _switch_lock:
        if other != name and listening(port_of(other)) and ready_of(other):
            unload(other)
        if not ensure_backend(name, restart):
            return False
        # the abliterated pack is a profile of the same Inkling engine: switch inside it.
        # This includes a request for the stock name while the unc profile is loaded.
        if name == "inkling" and model:
            st = backend_status("inkling") or {}
            cur = ((st.get("models") or {}).get("current") or "").lower()
            if cur != model.lower():
                log("switching the Inkling profile -> %s" % model)
                try:
                    fetch_json(port_of("inkling"), key_of("inkling"), "/v1/load", method="POST",
                               body=json.dumps({"model": model}).encode(), timeout=420,
                               origin="http://127.0.0.1:%d" % PORT)
                    t0 = time.time()
                    while time.time() - t0 < 420:
                        st = backend_status("inkling") or {}
                        m = st.get("models") or {}
                        if not m.get("switching") and (m.get("current") or "").lower() == model.lower():
                            break
                        time.sleep(2)
                except Exception as e:
                    log("Inkling profile %s: %s" % (model, e))
        _active = name
        return True


def pick(name):
    """Which backend serves this model name (None: removed from the machine)."""
    m = (name or "").lower()
    if "deepseek" in m or "ds41" in m or "dsv41" in m:
        return None
    if "inkling" in m:
        return "inkling"
    return "qwen"


def do_load(name, restart=False):
    """POST /v1/load in the page: switch to the named model."""
    global _switching
    try:
        be = pick(name)
        if be is None:
            log("load %s refused: removed from this machine" % name)
            return
        ok = switch_to(be, name, restart)
        log("load %s: %s" % (name, "ok" if ok else "FAILED"))
    finally:
        _switching = None


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "model-router/1.3"
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
        be = pick(name)
        if be is None:
            self._json(404, {"error": {"type": "router", "code": "model_removed",
                                       "message": "%s was removed from this machine (2026-10-29); "
                                                  "use %s or %s" % (name, QWEN_ID, INK_ID)}})
            return
        if not switch_to(be, name):
            self._json(503, {"error": {"type": "router",
                                       "message": "%s did not start; see model-router.log" % be}})
            return
        self._proxy(port_of(be), key_of(be), body)

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
            if _switching or not (_active and listening(port_of(_active))):
                self._json(200, {"status": "ok", "service": "strata",
                                 "model": (_switching or {}).get("to") or current_id() or QWEN_ID,
                                 "loaded": False, "images": False, "max_context": 262144,
                                 "router": True, "active": _active})
                return
            self._proxy(port_of(_active), key_of(_active), b"")
            return
        if path == "/v1/models":
            self._json(200, {"object": "list", "data": [
                {"id": n, "object": "model", "owned_by": "local", "created": 0}
                for n in known_ids()
            ]})
            return
        if path in ("/v1/status", "/status"):
            if _switching:
                st = {"service": "strata", "loaded": True, "model": (_switching or {}).get("to"),
                      "active": _active,
                      "models": {"current": _switching.get("from"), "available": known_ids(),
                                 "switching": _switching, "last_error": None}}
                self._json(200, st)
                return
            if not (_active and listening(port_of(_active))):
                self._json(200, {"service": "model-router", "loaded": False, "active": _active,
                                 "models": {"current": None, "available": known_ids(),
                                            "switching": None, "last_error": None}})
                return
            try:
                code, st = fetch_json(port_of(_active), key_of(_active), self.path)
                st["models"] = merged_models(st.get("models"))
                _last_status[port_of(_active)] = st
                self._json(code, st)
            except Exception as e:
                log("status error on %d: %s" % (port_of(_active), e))
                self._json(502, {"error": {"type": "router", "message": str(e)}})
            return
        if path == "/metrics":
            if _switching:
                m = cached_metrics()
                m["models"] = {"current": _switching.get("from"), "available": known_ids(),
                               "switching": _switching, "last_error": None}
                self._json(200, m)
                return
            if not (_active and listening(port_of(_active))):
                self._json(503, {"error": {"type": "router", "message": "no model loaded yet"}})
                return
            try:
                code, m = fetch_json(port_of(_active), key_of(_active), self.path)
                m["models"] = merged_models(m.get("models"))
                _last_metrics[port_of(_active)] = m
                self._json(code, m)
            except Exception as e:
                log("metrics error on %d: %s" % (port_of(_active), e))
                self._json(502, {"error": {"type": "router", "message": str(e)}})
            return
        if path == "/mcp":
            if not (_active and listening(port_of(_active))):
                self._json(200, {"servers": []})
                return
            self._proxy(port_of(_active), key_of(_active), b"")
            return
        # the web page and everything else: serve from the active model
        port = active_port()
        if not listening(port):
            self._json(503, {"error": {"type": "router", "message": "no model loaded yet: send a request with a model name"}})
            return
        self._proxy(port, active_key(), b"")

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
    log("router starting on %d (qwen %d, inkling %d; active %s)" % (PORT, QWEN_PORT, INK_PORT, _active))
    ThreadingServer(("0.0.0.0", PORT), Handler).serve_forever()
