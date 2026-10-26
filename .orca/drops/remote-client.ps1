<#
  remote-client.ps1 — CHẠY TRÊN MÁY KHÁCH WINDOWS (máy khác).

  Mở Claude Code, Codex, OpenCode, hoặc Chat REPL, tất cả trỏ về các model MLX đang chạy
  trên máy Mac (AI Gateway :8090), qua Tailscale hoặc LAN. Máy khách KHÔNG chạy
  inference — Mac lo hết.

  Cài trên máy khách: copy 2 file này (remote-client.ps1 + remote-client.cmd).
  Cần: PowerShell (có sẵn trên Windows), curl không cần; và CLI muốn dùng —
    claude → Claude Code   (npm install -g @anthropic-ai/claude-code)
    codex  → Codex CLI
    opencode → OpenCode CLI (đã cài OpenCode)
    chat   → không cần gì thêm (PowerShell tự gọi).

  Dùng:
    Double-click remote-client.cmd            → menu
    .\remote-client.ps1                       → menu
    .\remote-client.ps1 claude                → hoặc codex / opencode / chat

  Mặc định gửi model "local" (model box đang phục vụ). Đặt REMOTE_MODEL thành một id đích danh
  trong /v1/models chỉ khi thật sự muốn đổi model cho CẢ box (mất 1-4 phút).

  Đổi địa chỉ máy chủ mà không cần sửa file (đặt biến môi trường):
    $env:REMOTE_HOSTS = "100.82.116.73 my-mac.tailnet.ts.net 192.168.1.92"
    .\remote-client.ps1 claude
#>
param(
  [Parameter(Position = 0)][string]$Mode = "menu",
  [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest
)

$ErrorActionPreference = "Stop"
# Cho phép hiển thị tiếng Việt + ký hiệu trong console.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$OutputEncoding = [System.Text.Encoding]::UTF8

# ── Nơi AI truy cập được. Mặc định domain HTTPS công khai — chạy mọi nơi, không
#    cần Tailscale/LAN. Override bằng REMOTE_BASES ("https://api.dongnh.dev 192.168.1.92"). ──
$DefaultBases = @("https://api.dongnh.dev")
$srcList = if ($env:REMOTE_BASES) { $env:REMOTE_BASES } elseif ($env:REMOTE_HOSTS) { $env:REMOTE_HOSTS } else { $null }
$BaseList = if ($srcList) { $srcList -split '\s+' | Where-Object { $_ } } else { $DefaultBases }
$Port  = if ($env:REMOTE_PORT)  { $env:REMOTE_PORT }  else { "8090" }
# API key: from env, else ~/.airkey. Never hard-coded (keeps secrets out of git).
$Key   = if ($env:REMOTE_KEY) { $env:REMOTE_KEY } else { (Get-Content "$HOME/.airkey" -ErrorAction SilentlyContinue | Select-Object -First 1) }
$Model = if ($env:REMOTE_MODEL) { $env:REMOTE_MODEL } else { "local" }
# Resolve the client compact threshold from the gateway's versioned /status
# contract after a host is selected. The fallback is only for an older gateway
# that does not publish the contract, and is reported explicitly.
$CtxWindow = if ($env:REMOTE_CTX) { $env:REMOTE_CTX } else { $null }
$ContextFallback = 57344
# Optional Claude Code local-evaluation mode. Keep this opt-in: --bare skips automatic
# customizations (including CLAUDE.md discovery), so the task prompt must explicitly tell Claude
# which repository rules/files to read when this is enabled.
$MinimalClaude = if ($env:REMOTE_CLAUDE_MINIMAL) { $env:REMOTE_CLAUDE_MINIMAL } else { "0" }

# entry → base URL: full URL kept as-is, bare host → http://host:8090 (the ai-gateway)
function To-Base($h) { if ($h -match '^https?://') { $h } else { "http://${h}:${Port}" } }

function Write-Ok  ($m) { Write-Host "✓ $m" -ForegroundColor Green }
function Write-Warn2($m) { Write-Host "! $m" -ForegroundColor Yellow }
function Write-Err2 ($m) { Write-Host "✗ $m" -ForegroundColor Red }
function Write-Dim ($m) { Write-Host $m -ForegroundColor DarkGray }
function Have($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function Pause-Exit($code) { Read-Host "Nhấn Enter để đóng" | Out-Null; exit $code }
function Validate-Ctx($value) {
  if (-not $value -or $value -notmatch '^[1-9][0-9]*$') {
    Write-Err2 "REMOTE_CTX phải là số nguyên dương."; Pause-Exit 2
  }
}
if ($CtxWindow) { Validate-Ctx $CtxWindow }
if ($MinimalClaude -notmatch '^[01]$') { Write-Err2 "REMOTE_CLAUDE_MINIMAL phải là 0 hoặc 1."; Pause-Exit 2 }

# ── Chọn host đầu tiên truy cập được, báo RÕ lý do từng host nếu hỏng. ──
if (-not $Key) {
  Write-Err2 "Chưa có API key. Làm 1 trong 2 cách rồi chạy lại:"
  Write-Host '   1) Lưu key 1 lần:  "sk-live-XXXX" | Out-File -NoNewline -Encoding ascii $HOME\.airkey'
  Write-Host '                      .\remote-client.ps1'
  Write-Host '   2) Hoặc mỗi lần:   $env:REMOTE_KEY="sk-live-XXXX"; .\remote-client.ps1'
  Write-Host '   (Lấy key trên MÁY CHỦ:  cat ~/.local/go-llm-proxy/api-key )'
  Pause-Exit 1
}

$Base = $null
Write-Host ""
Write-Dim "Đang tìm AI local (thử: $($BaseList -join ', ')) …"
foreach ($h in $BaseList) {
  $b = To-Base $h
  $url = "$b/v1/models"
  $code = 0
  try {
    $r = Invoke-WebRequest -Uri $url -Headers @{ Authorization = "Bearer $Key" } `
           -TimeoutSec 8 -UseBasicParsing -ErrorAction Stop
    $code = [int]$r.StatusCode
  } catch {
    if ($_.Exception.Response) { try { $code = [int]$_.Exception.Response.StatusCode } catch { $code = 0 } }
    else { $code = 0 }
  }
  if ($code -eq 200) { Write-Ok "$b → 200"; $Base = $b; break }
  elseif ($code -eq 0) { Write-Warn2 "$b → không tới được (timeout / mạng / firewall)" }
  elseif ($code -in 401, 403, 429) { Write-Warn2 "$b → $code (key sai, hoặc proxy throttle IP này)" }
  elseif ($code -eq 404) { Write-Warn2 "$b → 404 (không phải go-llm-proxy)" }
  else { Write-Warn2 "$b → HTTP $code" }
}

if (-not $Base) {
  Write-Err2 "Không kết nối được AI local. Xử lý theo mã lỗi ở trên:"
  Write-Host "  • không tới được : kiểm tra internet; Mac chủ đang bật + cloudflared tunnel chạy."
  Write-Host '                     Địa chỉ khác → $env:REMOTE_BASES = "https://api.dongnh.dev" rồi chạy lại.'
  Write-Host "  • 401/403/429    : sai REMOTE_KEY (key mạnh), hoặc bị throttle — chờ ~1 phút."
  Write-Host "  • 404            : URL không phải go-llm-proxy (xem REMOTE_BASES)."
  Pause-Exit 1
}

# The gateway owns the context contract. An explicit REMOTE_CTX may only lower
# the advertised client threshold; a larger value would consume the headroom
# reserved for system/tool/output tokens.
$contractCompact = $null
$contractGuard = $null
try {
  $statusPayload = Invoke-RestMethod -Uri "$Base/status" `
    -Headers @{ Authorization = "Bearer $Key" } -TimeoutSec 4 -ErrorAction Stop
  $contract = $statusPayload.context_contract
  if ($contract -and "$($contract.client_compact_threshold)" -match '^[1-9][0-9]*$') {
    $contractCompact = [int64]$contract.client_compact_threshold
  }
  if ($contract -and "$($contract.guard_tokens)" -match '^[1-9][0-9]*$') {
    $contractGuard = [int64]$contract.guard_tokens
  }
} catch {}
# /status is loopback-only: over the tunnel it answers 403 and every Windows session compacted at the
# 57344 fallback. The key-protected /v1/models `local` entry carries the same contract (2026-09-29).
if (-not ($contractCompact -and $contractGuard)) {
  try {
    $models = Invoke-RestMethod -Uri "$Base/v1/models" `
      -Headers @{ Authorization = "Bearer $Key" } -TimeoutSec 6 -ErrorAction Stop
    $localEntry = $models.data | Where-Object { $_.id -eq "local" } | Select-Object -First 1
    $contract = $localEntry.context_contract
    if ($contract -and "$($contract.client_compact_threshold)" -match '^[1-9][0-9]*$') {
      $contractCompact = [int64]$contract.client_compact_threshold
    }
    if ($contract -and "$($contract.guard_tokens)" -match '^[1-9][0-9]*$') {
      $contractGuard = [int64]$contract.guard_tokens
    }
  } catch {}
}
if ($contractCompact -and $contractGuard -and $contractGuard -ge $contractCompact) {
  if (-not $CtxWindow) {
    $CtxWindow = "$contractCompact"
    Write-Ok "Context contract: client compact $CtxWindow / gateway guard $contractGuard"
  } elseif ([int64]$CtxWindow -gt $contractCompact) {
    Write-Err2 "REMOTE_CTX=$CtxWindow vượt client_compact_threshold=$contractCompact của gateway."
    Pause-Exit 2
  }
} elseif (-not $CtxWindow) {
  $CtxWindow = "$ContextFallback"
  Write-Warn2 "Gateway không công bố context_contract; dùng fallback $CtxWindow và không coi là contract-verified."
} else {
  Write-Warn2 "Không đọc được context_contract; giữ REMOTE_CTX=$CtxWindow theo explicit override."
}
Validate-Ctx $CtxWindow
Write-Ok "Kết nối AI local qua $Base  ·  model: $Model"

# Map the picked LOCAL alias to Claude Code's --effort so the client sends the effort the alias asks
# for (an 8-minute think on 2026-09-08 started this). Default medium; -nothink sends none. Same table
# as remote-client.sh. Since 2026-10-04 the gateway forwards Claude Code's effort with precedence
# alias > client effort > MLX_AGENT_REASONING_EFFORT, so this setting really reaches the model.
function Effort-Of-Model($m) {
  if ($m -like "*-nothink") { return "" }
  if ($m -like "*-think-xhigh") { return "xhigh" }
  if ($m -like "*-think-high") { return "high" }
  if ($m -like "*-think-medium") { return "medium" }
  if ($m -like "*-think-low") { return "low" }
  return "medium"
}

function Run-Claude {
  if (-not (Have claude)) { Write-Err2 "Chưa cài Claude Code: npm install -g @anthropic-ai/claude-code"; Pause-Exit 1 }
  $env:ANTHROPIC_BASE_URL = $Base            # KHÔNG có /v1 — Claude Code tự nối /v1/messages
  $env:ANTHROPIC_API_KEY = $Key
  $env:ANTHROPIC_AUTH_TOKEN = $Key
  $env:DISABLE_LOGIN_COMMAND = "1"
  $env:CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"
  $env:DISABLE_AUTOUPDATER = "1"
  $env:CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL = "1"
  $env:CLAUDE_CODE_DISABLE_BACKGROUND_TASKS = "1"
  $env:CLAUDE_CODE_MAX_CONTEXT_TOKENS = $CtxWindow
  # Both windows: MAX_CONTEXT_TOKENS alone is a no-op while auto-compaction is on, and the client keeps
  # its 200K assumption and thrashes (2026-09-09) — so NORMAL mode sets the compact window too.
  $env:CLAUDE_CODE_AUTO_COMPACT_WINDOW = $CtxWindow
  $env:CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT = "1"
  Write-Host ""; Write-Ok "Mở Claude Code (→ $Base)"
  # Mặc định bỏ hỏi quyền từng tool — client nội bộ trỏ AI nhà. Muốn hỏi
  # quyền lại như gốc: đặt env REMOTE_SAFE=1 trước khi chạy.
  $claudeArgs = @("--model", $Model)
  if (-not $env:REMOTE_SAFE) { $claudeArgs += "--dangerously-skip-permissions" }
  # Same rule as is_local_model in remote-client.sh: the alias and its variants, a -think/-nothink/
  # -think-<effort> suffix, or an exact local id (org--name) that is not an OpenRouter-style org/name.
  $isLocal = ($Model -eq "local") -or ($Model -like "local-*") -or ($Model -like "*-think") -or ($Model -like "*-nothink") -or ($Model -like "*-think-*") -or (($Model -like "*--*") -and ($Model -notlike "*/*"))
  if ($isLocal -and $MinimalClaude -ne "1") {
    $eff = Effort-Of-Model $Model
    if ($eff) { $claudeArgs += @("--effort", $eff) }
    # A LOCAL gateway serves ONE decode slot; Claude Code's Task subagent tool fans parallel calls out at
    # it -> 429 storms + a crawl (measured 2026-09-10; remote-client.sh has disallowed it since). Override
    # with REMOTE_CLAUDE_DISALLOW: "none" keeps subagents (Windows deletes an env var set to ""), a comma
    # list such as "Task,WebFetch" removes more. Minimal mode already excludes Task via --tools.
    $dis = if ($null -eq $env:REMOTE_CLAUDE_DISALLOW) { "Task" } else { "$env:REMOTE_CLAUDE_DISALLOW" }
    if ($dis -and $dis -ne "none") { $claudeArgs += @("--disallowedTools", $dis) }
  }
  if ($MinimalClaude -eq "1") {
    Write-Dim "Claude local minimal mode: automatic memory/customizations disabled; prompt must provide CLAUDE.md context."
    $minimalSystemPrompt = "You are Claude Code in a trusted local coding worktree. First inspect and obey CLAUDE.md and repository instructions. Use only the available Read, Edit, Bash, Glob, and Grep tools. Keep changes focused, run targeted tests, and report exact commands and results. Never claim success without evidence."
    $env:CLAUDE_CODE_DISABLE_AUTO_MEMORY = "1"
    $env:CLAUDE_CODE_DISABLE_ATTACHMENTS = "1"
    $env:CLAUDE_CODE_DISABLE_CLAUDE_MDS = "1"
    $env:CLAUDE_CODE_DISABLE_BUNDLED_SKILLS = "1"
    $env:CLAUDE_CODE_DISABLE_CLAUDE_CODE_SKILL = "1"
    $env:CLAUDE_CODE_DISABLE_CLAUDE_API_SKILL = "1"
    $env:CLAUDE_CODE_SKIP_PROJECT_BACKFILL = "1"
    $env:CLAUDE_CODE_SKIP_PROMPT_HISTORY = "1"
    $env:CLAUDE_CODE_AUTO_COMPACT_WINDOW = $CtxWindow
    # Keep the first local request below the gateway ceiling: the default Claude tool catalog is
    # large enough to exceed a 57k local context before the first compaction can run.
    $claudeArgs += @("--bare", "--no-session-persistence", "--disable-slash-commands",
                     "--tools", "Bash,Read,Edit,Glob,Grep",
                     "--system-prompt", $minimalSystemPrompt)
  }
  & claude @claudeArgs @Rest
}

function Run-Codex {
  if (-not (Have codex)) { Write-Err2 "Chưa cài Codex CLI."; Pause-Exit 1 }
  # Config riêng để KHÔNG đụng ~/.codex sẵn có của máy khách (login cloud).
  $ch = Join-Path $HOME ".cache\claude-local-remote\codex"
  New-Item -ItemType Directory -Force -Path $ch | Out-Null
  # approval/sandbox là key TOP-LEVEL — phải đứng TRƯỚC [model_providers]
  # (TOML: key sau một bảng là chui vào bảng đó). REMOTE_SAFE=1 → hỏi như gốc.
  $skipKeys = "approval_policy = `"never`"`nsandbox_mode = `"danger-full-access`"`n"
  if ($env:REMOTE_SAFE) { $skipKeys = "" }
  $codexWindow = if ($contractGuard) { $contractGuard } else { $CtxWindow }
  $cfg = @"
# Auto-generated by remote-client.ps1 — Codex → remote go-llm-proxy.
model_provider = "glp"
model = "$Model"
# Window = the gateway guard (the real ceiling); auto-compact BELOW it so Codex compacts before a 400
# instead of after overflow (codex#16068). Same form as remote-client.sh run_codex.
model_context_window = $codexWindow
model_auto_compact_token_limit = $CtxWindow
model_max_output_tokens = 16384
$skipKeys
[model_providers.glp]
name = "go-llm-proxy (remote MLX)"
base_url = "$Base/v1"
env_key = "GLP_KEY"
wire_api = "responses"
"@
  Set-Content -Path (Join-Path $ch "config.toml") -Value $cfg -Encoding UTF8
  # Kỷ luật toàn cục cho model local: Codex đọc AGENTS.md trong CODEX_HOME cho
  # MỌI repo — khỏi tạo tay từng repo. Regenerate mỗi lần chạy (như config.toml).
  $agents = @'
# Global agent rules — local LLM via home gateway

These rules apply whenever the model is `local` (home MLX gateway, context
**57,344 tokens**). A repo's own AGENTS.md adds to / overrides this file.

## Before starting in any repo
- If the repo root has **CLAUDE.md**, read it FIRST — repo map, build/verify
  commands, and conventions live there.

## Context discipline (hard limits)
- The context window is 57,344 tokens. One oversized request gets a hard 400 —
  measured: batch-reading ~50 files ≈ 477K tokens = instant failure.
- Read files in SMALL batches (5 or fewer per turn). List directories before
  reading. Never re-read a file already read this session.
- Never read generated/vendored files wholesale (lock files, target/,
  node_modules/, generated protocol files) — grep for the symbol you need.

## Big tasks (whole-repo review, audit, migration)
- Divide and conquer: one module per session; write findings to
  docs/reviews/<module>.md as each part finishes; synthesize at the end.

## Turn discipline
- Never end a turn with an intent announcement ("I'll continue reading…").
  Either call a tool, deliver the result, or ask the user a real question.
'@
  $agents = $agents.Replace("57,344", $CtxWindow)
  Set-Content -Path (Join-Path $ch "AGENTS.md") -Value $agents -Encoding UTF8
  $env:CODEX_HOME = $ch
  $env:GLP_KEY = $Key
  Write-Host ""; Write-Ok "Mở Codex (→ $Base/v1)"
  & codex -m $Model @Rest
}

function Run-OpenCode {
  if (-not (Have opencode)) { Write-Err2 "Chưa cài OpenCode: xem https://opencode.ai/docs/ hoặc cài opencode trước"; Pause-Exit 1 }
  # OpenCode runs against the gateway through an isolated custom OpenAI-compatible provider.
  # Use the same model selected for Claude and Codex. `local` remains the default alias, while
  # REMOTE_MODEL may name an exact registered gateway route.
  $ocConfig = @{
    '$schema' = "https://opencode.ai/config.json"
    model = "ai-gateway/$Model"
    provider = @{
      "ai-gateway" = @{
        npm = "@ai-sdk/openai-compatible"
        name = "AI Gateway Local"
        options = @{
          baseURL = "$Base/v1"
          apiKey = "{env:OPENCODE_API_KEY}"
        }
        # The model key must match the selected model, not only the default alias. OpenCode
        # otherwise receives ai-gateway/<exact-id> on the CLI while its provider catalog only
        # declares local, so a remote model choice can be rejected before the first request.
        # limit.context = the resolved window: without it OpenCode uses the SDK default, never
        # compacts a local model, and walks into the gateway's 400 (same as remote-client.sh).
        models = @{ $Model = @{ name = "AI Gateway Local"; limit = @{ context = [int64]$CtxWindow; output = 16384 } } }
      }
    }
  } | ConvertTo-Json -Depth 10 -Compress
  $env:OPENCODE_API_KEY = $Key
  $env:OPENCODE_CONFIG_CONTENT = $ocConfig
  Write-Host ""; Write-Ok "Mở OpenCode (→ $Base/v1, model $Model, --auto)"
  & opencode --auto --model "ai-gateway/$Model" @Rest
}

function Run-Chat {
  Add-Type -AssemblyName System.Net.Http -ErrorAction SilentlyContinue
  $client = [System.Net.Http.HttpClient]::new()
  $client.Timeout = [TimeSpan]::FromMinutes(10)
  $url = "$Base/v1/chat/completions"
  $msgs = New-Object System.Collections.Generic.List[object]
  Write-Host ""; Write-Ok "Chat REPL (→ $url)"
  Write-Host ("Chat với AI local ({0}). Gõ nội dung, Ctrl-C để thoát.`n" -f $Model)
  while ($true) {
    [Console]::Write("you › ")
    $u = [Console]::ReadLine()
    if ($null -eq $u) { Write-Host ""; break }
    $u = $u.Trim()
    if (-not $u) { continue }
    $msgs.Add(@{ role = "user"; content = $u }) | Out-Null

    # messages LUÔN là mảng (PowerShell 5.1 hay bỏ [] khi chỉ 1 phần tử).
    $msgsJson = ($msgs | ForEach-Object { $_ | ConvertTo-Json -Depth 5 -Compress }) -join ","
    $body = '{"model":"' + $Model + '","stream":true,"max_tokens":6000,"messages":[' + $msgsJson + ']}'

    $req = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Post, $url)
    $req.Headers.TryAddWithoutValidation("Authorization", "Bearer $Key") | Out-Null
    $req.Content = [System.Net.Http.StringContent]::new($body, [System.Text.Encoding]::UTF8, "application/json")

    $acc = ""; $started = $false; $think = 0
    try {
      $resp = $client.SendAsync($req, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).Result
      $stream = $resp.Content.ReadAsStreamAsync().Result
      $reader = [System.IO.StreamReader]::new($stream)
      while (-not $reader.EndOfStream) {
        $line = $reader.ReadLine()
        if (-not $line -or -not $line.StartsWith("data:")) { continue }
        $data = $line.Substring(5).Trim()
        if ($data -eq "[DONE]") { break }
        try { $delta = ($data | ConvertFrom-Json).choices[0].delta } catch { continue }
        $chunk = $delta.content
        if ($chunk) {
          if (-not $started) {
            [Console]::Write("`r" + (" " * 24) + "`r")
            Write-Host -NoNewline "ai  › " -ForegroundColor Green
            $started = $true
            $chunk = $chunk.TrimStart("`n")
          }
          $acc += $chunk
          [Console]::Write($chunk)
        }
        elseif (-not $started) {
          $think++
          Write-Host -NoNewline ("`r(đang nghĩ… $think)") -ForegroundColor DarkGray
        }
      }
      $reader.Dispose()
    } catch {
      [Console]::Write("`r" + (" " * 24) + "`r")
      Write-Err2 ("lỗi: " + $_.Exception.Message)
      $msgs.RemoveAt($msgs.Count - 1)
      continue
    }
    if (-not $started) {
      [Console]::Write("`r" + (" " * 24) + "`r")
      Write-Host "ai  › (không có nội dung — thử lại)" -ForegroundColor Green
      $msgs.RemoveAt($msgs.Count - 1)
      continue
    }
    Write-Host "`n"
    $msgs.Add(@{ role = "assistant"; content = $acc }) | Out-Null
  }
}

switch ($Mode.ToLower()) {
  "claude" { Run-Claude }
  "codex"  { Run-Codex }
  "opencode" { Run-OpenCode }
  "chat"   { Run-Chat }
  "menu"   {
    Write-Host ""
    Write-Host "Chọn chế độ:" -ForegroundColor White
    Write-Host "  1) Claude Code"
    Write-Host "  2) Codex"
    Write-Host "  3) OpenCode (--auto)"
    Write-Host "  4) Chat"
    $choice = Read-Host "›"
    switch ($choice.Trim()) {
      "1" { Run-Claude }
      "2" { Run-Codex }
      "3" { Run-OpenCode }
      "4" { Run-Chat }
      default { Write-Err2 "Lựa chọn không hợp lệ."; Pause-Exit 1 }
    }
  }
  default { Write-Err2 "Lệnh không rõ: $Mode  (dùng: claude | codex | opencode | chat)"; Pause-Exit 1 }
}
