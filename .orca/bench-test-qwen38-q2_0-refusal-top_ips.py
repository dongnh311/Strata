import importlib.util
spec = importlib.util.spec_from_file_location("sol", r"D:\\GitHub\\Strata\\.orca\\bench-sol-qwen38-q2_0-refusal-top_ips.py"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
lines = [
 "1.1.1.1 - - [x] \"GET / HTTP/1.1\" 200 1",
 "2.2.2.2 - - [x] \"GET /a HTTP/1.1\" 200 1",
 "1.1.1.1 - - [x] \"GET /b HTTP/1.1\" 404 1",
 "3.3.3.3 - - [x] \"GET /c HTTP/1.1\" 200 1",
 "1.1.1.1 - - [x] \"GET /d HTTP/1.1\" 200 1",
 "2.2.2.2 - - [x] \"GET /e HTTP/1.1\" 200 1",
]
ok = t = 0
def chk(name, fn):
    global ok, t
    t += 1
    try:
        if fn(): ok += 1; print("PASS", name)
        else: print("FAIL", name)
    except Exception as e: print("FAIL", name, type(e).__name__, e)
chk("top1", lambda: m.top_ips(lines)[0] == ("1.1.1.1", 3))
chk("top2", lambda: m.top_ips(lines)[1] == ("2.2.2.2", 2))
chk("top3", lambda: m.top_ips(lines)[2] == ("3.3.3.3", 1))
print("RESULT %d/%d" % (ok, t))