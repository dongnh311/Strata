# code-bench.ps1 - coding benchmark: DeepSeek 1.75 vs Qwen3.8 (local, via router 8081).
# Each task's answer is extracted and run against unit tests; wall time and tok/s recorded.
$log = 'D:\GitHub\Strata\.orca\code-bench-log.txt'
function Log($m) { Add-Content -Path $log -Value ("{0} {1}" -f (Get-Date -Format 'HH:mm:ss'), $m) }

$tasks = @(
  @{ name = 'merge_fix'; prompt = @'
Fix this Python function so it returns a correctly merged sorted list of two sorted lists. Return only the fixed function in one python code block, no explanation.
def merge(a, b):
    out = []
    i = j = 0
    while i < len(a) and j < len(b):
        if a[i] <= b[j]:
            out.append(a[i]); i += 1
        else:
            out.append(b[j]); j += 1
    return out
'@; test = @'
import importlib.util, traceback
spec = importlib.util.spec_from_file_location("sol", r"__SOL__"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
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
'@ },
  @{ name = 'lis'; prompt = @'
Write a Python function lis(seq) that returns the length of the longest strictly increasing subsequence, O(n log n) preferred. Return only code in one python code block.
'@; test = @'
import importlib.util
spec = importlib.util.spec_from_file_location("sol", r"__SOL__"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
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
'@ },
  @{ name = 'csv_parser'; prompt = @'
Write a Python class CSVParser with exactly this interface: CSVParser().parse(path) -> list[dict], stdlib only. It must handle a header row, commas inside double-quoted fields, a UTF-8 BOM, and blank lines (skipped). Return only code in one python code block.
'@; test = @'
import importlib.util, tempfile, os
spec = importlib.util.spec_from_file_location("sol", r"__SOL__"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
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
'@ },
  @{ name = 'top_ips'; prompt = @'
Write a Python function top_ips(lines: list[str]) -> list[tuple[str, int]] that reads Apache-style access log lines, counts client IPs (the first space-separated token), and returns the 3 most frequent as (ip, count), ties broken by ip ascending. Return only code in one python code block.
'@; test = @'
import importlib.util
spec = importlib.util.spec_from_file_location("sol", r"__SOL__"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
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
'@ }
)

function Ask-Once($model, $prompt) {
    $b = @{ model = $model; max_tokens = 900; temperature = 0.0;
            messages = @(@{ role = 'user'; content = $prompt }) } | ConvertTo-Json -Depth 4
    $t0 = Get-Date
    $r = Invoke-RestMethod 'http://127.0.0.1:8081/v1/chat/completions' -Method Post `
         -Body ([System.Text.Encoding]::UTF8.GetBytes($b)) -ContentType 'application/json' -TimeoutSec 1800
    $dt = ((Get-Date) - $t0).TotalSeconds
    return @{ text = [string]$r.choices[0].message.content; wall = $dt
              prompt_tok = $r.usage.prompt_tokens; comp_tok = $r.usage.completion_tokens }
}

function Extract-Code($text) {
    $m = [regex]::Match($text, '(?s)```(?:python|py)?\s*\r?\n(.*?)```')
    if ($m.Success) { return $m.Groups[1].Value } else { return $text }
}

$results = @()
foreach ($model in @('deepseek-v4.1-flash', 'qwen38-q2_0-refusal')) {
    Log ("=== model " + $model + " ===")
    foreach ($task in $tasks) {
        $ans = Ask-Once $model $task.prompt
        $code = Extract-Code $ans.text
        $sol = "D:\GitHub\Strata\.orca\bench-sol-$model-$($task.name).py"
        [IO.File]::WriteAllText($sol, $code, (New-Object Text.UTF8Encoding($false)))
        $harness = $task.test.Replace('__SOL__', $sol.Replace('\', '\\'))
        $hp = "D:\GitHub\Strata\.orca\bench-test-$model-$($task.name).py"
        [IO.File]::WriteAllText($hp, $harness, (New-Object Text.UTF8Encoding($false)))
        $out = & 'C:\Users\ADMIN\AppData\Local\Programs\Python\Python312\python.exe' $hp 2>&1 | Out-String
        $res = [regex]::Match($out, 'RESULT (\d+)/(\d+)')
        if ($res.Success) { $pass = [int]$res.Groups[1].Value; $total = [int]$res.Groups[2].Value }
        else { $pass = 0; $total = 0 }
        $tokps = if ($ans.wall -gt 0) { [math]::Round($ans.comp_tok / $ans.wall, 2) } else { 0 }
        Log ("{0,-12} {1,-12} pass {2}/{3}  wall {4,6:N1}s  comp {5,4} tok  {6,5:N2} tok/s  prompt {7}" -f $model, $task.name, $pass, $total, $ans.wall, $ans.comp_tok, $tokps, $ans.prompt_tok)
        $results += [pscustomobject]@{ model = $model; task = $task.name; pass = $pass; total = $total; wall = [math]::Round($ans.wall,1); comp = $ans.comp_tok; tokps = $tokps }
    }
}
Log '=== summary ==='
foreach ($g in ($results | Group-Object model)) {
    $p = ($g.Group | Measure-Object pass -Sum).Sum; $t = ($g.Group | Measure-Object total -Sum).Sum
    $w = ($g.Group | Measure-Object wall -Sum).Sum; $c = ($g.Group | Measure-Object comp -Sum).Sum
    Log ("{0,-24} tests {1}/{2}  wall {3:N1}s  tokens {4}  avg {5:N2} tok/s" -f $g.Name, $p, $t, $w, $c, ($c / $w))
}
Log '=== done ==='