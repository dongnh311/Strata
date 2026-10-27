import importlib.util
spec = importlib.util.spec_from_file_location("sol", r"D:\\GitHub\\Strata\\.orca\\bench-sol-qwen38-q2_0-refusal-lis.py"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
ok = t = 0
def chk(name, fn):
    global ok, t
    t += 1
    try:
        if fn(): ok += 1; print("PASS", name)
        else: print("FAIL", name)
    except Exception as e: print("FAIL", name, type(e).__name__, e)
chk("classic", lambda: m.lis([10,9,2,5,3,7,101,18]) == 4)
chk("empty", lambda: m.lis([]) == 0)
chk("increasing", lambda: m.lis([1,2,3]) == 3)
chk("equal", lambda: m.lis([3,3,3]) == 1)
chk("decreasing", lambda: m.lis([5,4,3,2,1]) == 1)
print("RESULT %d/%d" % (ok, t))