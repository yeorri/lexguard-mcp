<#
.SYNOPSIS
    LexGuard MCP 로컬(stdio) 설치 스크립트 — Windows.

.DESCRIPTION
    가상환경 생성 → 의존성 설치 → .env 작성 → 서버 동작 검증 →
    Claude Desktop(일반 대화창)과 Claude Code 설정에 등록까지 한 번에 수행한다.
    여러 번 실행해도 안전하다(기존 .env는 덮어쓰지 않고, 설정 파일은 백업 후 갱신).

.PARAMETER ApiKey
    국가법령정보센터 OPEN API 키(OC). .env가 이미 있으면 생략 가능.
    발급: https://open.law.go.kr

.PARAMETER SkipConfig
    Claude 설정 파일을 건드리지 않고 설치·검증만 수행한다.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\setup_local.ps1 -ApiKey 발급받은키
#>
param(
    [string]$ApiKey,
    [switch]$SkipConfig
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$Launcher = Join-Path $Root "run_stdio.py"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "    OK  $msg" -ForegroundColor Green }
function Write-Warn2($msg) { Write-Host "    !   $msg" -ForegroundColor Yellow }

# ---------------------------------------------------------------- 1. Python
Write-Step "Python 확인"
$py = $null
foreach ($cand in @("py", "python")) {
    try {
        $v = & $cand -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $v) { $py = $cand; break }
    } catch {}
}
if (-not $py) {
    throw "Python을 찾을 수 없습니다. https://www.python.org/downloads/ 에서 3.10 이상을 설치하고 'Add to PATH'를 체크하세요."
}
Write-Ok "$py (버전 $v)"

# ---------------------------------------------------------------- 2. venv
Write-Step "가상환경 준비"
if (-not (Test-Path $VenvPython)) {
    & $py -m venv (Join-Path $Root ".venv")
    if (-not (Test-Path $VenvPython)) { throw "가상환경 생성 실패" }
    Write-Ok "생성됨: .venv"
} else {
    Write-Ok "이미 존재함: .venv"
}

Write-Step "의존성 설치 (몇 분 걸릴 수 있음)"
& $VenvPython -m pip install --quiet --upgrade pip
& $VenvPython -m pip install --quiet -r (Join-Path $Root "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "의존성 설치 실패" }
Write-Ok "requirements.txt 설치 완료"

# ---------------------------------------------------------------- 3. .env
Write-Step "API 키 설정"
$EnvFile = Join-Path $Root ".env"
if (Test-Path $EnvFile) {
    Write-Ok ".env 이미 존재 (덮어쓰지 않음)"
} else {
    if (-not $ApiKey) {
        throw ".env가 없습니다. -ApiKey 옵션으로 국가법령정보센터 인증키(OC)를 지정하세요. 발급: https://open.law.go.kr"
    }
    @(
        "LAW_API_KEY=$ApiKey",
        "LAW_GO_KR_DRF_SCHEME=https",
        "PORT=9099",
        "LOG_LEVEL=INFO",
        "RELOAD=false"
    ) | Set-Content -Path $EnvFile -Encoding utf8
    Write-Ok ".env 생성됨"
}

# ---------------------------------------------------------------- 4. 검증
Write-Step "서버 동작 검증"
$reqFile = Join-Path $env:TEMP "lexguard_probe.jsonl"
$outFile = Join-Path $env:TEMP "lexguard_probe.out"
$errFile = Join-Path $env:TEMP "lexguard_probe.err"

# JSON-RPC 입력에 BOM이 섞이면 첫 줄 파싱이 깨지므로 BOM 없이 기록한다.
$noBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($reqFile, @(
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"setup","version":"1"}}}',
    '{"jsonrpc":"2.0","id":2,"method":"tools/list"}',
    '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"law_article_tool","arguments":{"law_name":"근로기준법","article_number":"23"}}}'
), $noBom)

# cwd 무관 동작을 확인하기 위해 일부러 다른 폴더에서 실행한다.
# (PowerShell 5.1에서 native exe의 stderr를 파이프로 받으면 NativeCommandError가 나므로 파일로 리다이렉트)
$proc = Start-Process -FilePath $VenvPython `
    -ArgumentList @("-X", "utf8", $Launcher) `
    -WorkingDirectory $env:TEMP `
    -RedirectStandardInput $reqFile `
    -RedirectStandardOutput $outFile `
    -RedirectStandardError $errFile `
    -NoNewWindow -Wait -PassThru

$out = @()
# 기본 인코딩(ANSI)으로 읽으면 한글이 깨져 ConvertFrom-Json이 실패한다.
if (Test-Path $outFile) { $out = Get-Content $outFile -Encoding UTF8 }
if ($out.Count -eq 0 -and (Test-Path $errFile)) {
    Write-Warn2 "서버 stderr 마지막 줄:"
    Get-Content $errFile | Select-Object -Last 5 | ForEach-Object { Write-Host "        $_" }
}
Remove-Item $reqFile, $outFile, $errFile -ErrorAction SilentlyContinue

$toolCount = 0
$articleOk = $false
foreach ($line in $out) {
    if (-not $line.Trim()) { continue }
    try { $msg = $line | ConvertFrom-Json } catch { continue }
    if ($msg.result.tools) { $toolCount = $msg.result.tools.Count }
    if ($msg.id -eq 3 -and $msg.result.content) {
        $text = $msg.result.content[0].text
        if ($text -match '"success":\s*true') { $articleOk = $true }
    }
}

if ($toolCount -eq 0) { throw "서버가 도구 목록을 반환하지 못했습니다. 위 오류를 확인하세요." }
Write-Ok "도구 $($toolCount)개 로드됨"
if ($articleOk) {
    Write-Ok "국가법령정보센터 조회 성공 (근로기준법 제23조)"
} else {
    Write-Warn2 "서버는 뜨지만 법령 조회에 실패했습니다. API 키(OC)가 잘못됐거나,"
    Write-Warn2 "open.law.go.kr에 이 PC의 IP/도메인이 등록되지 않았을 수 있습니다."
}

# ---------------------------------------------------------------- 5. 설정 등록
function Update-McpConfig {
    param([string]$Path, [bool]$IncludeType)

    if (-not (Test-Path $Path)) {
        $dir = Split-Path -Parent $Path
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
        '{}' | Set-Content -Path $Path -Encoding utf8
    } else {
        Copy-Item $Path "$Path.bak" -Force
    }

    $json = Get-Content $Path -Raw
    if (-not $json.Trim()) { $json = '{}' }
    $cfg = $json | ConvertFrom-Json

    $entry = [ordered]@{}
    if ($IncludeType) { $entry["type"] = "stdio" }
    $entry["command"] = $VenvPython
    $entry["args"] = @("-X", "utf8", $Launcher)
    $entry["cwd"] = $Root
    $entry["env"] = [ordered]@{ PYTHONIOENCODING = "utf-8"; PYTHONUNBUFFERED = "1" }

    if (-not $cfg.PSObject.Properties["mcpServers"]) {
        $cfg | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([PSCustomObject]@{})
    }
    if ($cfg.mcpServers -eq $null) { $cfg.mcpServers = [PSCustomObject]@{} }

    $servers = $cfg.mcpServers
    if ($servers.PSObject.Properties["lexguard"]) {
        $servers.lexguard = [PSCustomObject]$entry
    } else {
        $servers | Add-Member -NotePropertyName lexguard -NotePropertyValue ([PSCustomObject]$entry)
    }

    $cfg | ConvertTo-Json -Depth 20 | Set-Content -Path $Path -Encoding utf8
}

if ($SkipConfig) {
    Write-Step "설정 등록 건너뜀 (-SkipConfig)"
} else {
    Write-Step "Claude 설정에 등록"
    $desktopCfg = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
    Update-McpConfig -Path $desktopCfg -IncludeType $false
    Write-Ok "Claude Desktop (일반 대화창): $desktopCfg"

    $codeCfg = Join-Path $env:USERPROFILE ".claude.json"
    Update-McpConfig -Path $codeCfg -IncludeType $true
    Write-Ok "Claude Code: $codeCfg"
    Write-Warn2 "기존 파일은 .bak으로 백업했습니다."
}

Write-Host "`n설치 완료." -ForegroundColor Green
Write-Host "Claude를 완전히 종료(트레이 아이콘까지)한 뒤 다시 실행하세요." -ForegroundColor Green
Write-Host "확인: 일반 대화창에서 '근로기준법 23조 알려줘' 라고 물어보세요.`n"
