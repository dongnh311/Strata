import importlib.util, tempfile, os
spec = importlib.util.spec_from_file_location("sol", r"D:\\GitHub\\Strata\\.orca\\bench-sol-deepseek-v4.1-flash-csv_parser.py"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
text = "\ufeffname,note\r\nalice,\"likes, commas\"\r\n\r\nbob,plain\r\n"
p = os.path.join(tempfile.gettempdir(), "bench_csv_test.csv")
open(p, "w", encoding="utf-8", newline="").write(text)
ok = t = 0
def chk(name, fn):
    global ok, t
    t += 1
    try:
        if fn(): ok += 1; print("PASS", name)
        else: print("FAIL", name)
    except Exception as e: print("FAIL", name, type(e).__name__, e)
rows_holder = {}
def parse():
    rows_holder["rows"] = m.CSVParser().parse(p); return True
chk("runs", parse)
chk("count", lambda: len(rows_holder["rows"]) == 2)
chk("columns", lambda: rows_holder["rows"][0].get("name") == "alice" and rows_holder["rows"][0].get("note") == "likes, commas")
chk("last", lambda: rows_holder["rows"][1].get("name") == "bob" and rows_holder["rows"][1].get("note") == "plain")
print("RESULT %d/%d" % (ok, t))