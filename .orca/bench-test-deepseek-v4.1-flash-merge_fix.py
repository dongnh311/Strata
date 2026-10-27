import importlib.util, traceback
spec = importlib.util.spec_from_file_location("sol", r"D:\\GitHub\\Strata\\.orca\\bench-sol-deepseek-v4.1-flash-merge_fix.py"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
ok = t = 0
def chk(name, fn):
    global ok, t
    t += 1
    try:
        if fn(): ok += 1; print("PASS", name)
        else: print("FAIL", name)
    except Exception as e:
        print("FAIL", name, type(e).__name__, e)
chk("basic", lambda: m.merge([1,3],[2,4]) == [1,2,3,4])
chk("left-empty", lambda: m.merge([], [1,2]) == [1,2])
chk("right-empty", lambda: m.merge([1,2], []) == [1,2])
chk("tail", lambda: m.merge([1,5,9], [2]) == [1,2,5,9])
chk("dups", lambda: m.merge([1,1],[1,2]) == [1,1,1,2])
print("RESULT %d/%d" % (ok, t))