param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$Reload = $false,
    [switch]$ForceKillPort = $true
)

$ErrorActionPreference = "Stop"

$BackendDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# 找到 Python
$pythonCmd = (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
if (-not $pythonCmd) { $pythonCmd = (Get-Command py -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source) }
if (-not $pythonCmd) { $pythonCmd = (Get-Command python3 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source) }

if (-not $pythonCmd) {
    Write-Error "未在 PATH 中找到 python。请安装 Python 或将其加入 PATH。"
    exit 1
}

Write-Host "Using Python: $pythonCmd"

# 强杀占用端口的进程
if ($ForceKillPort) {
    try {
        $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($listener) {
            $pids = $listener | Select-Object -ExpandProperty OwningProcess -Unique
            foreach ($pid in $pids) {
                Write-Host "Stopping process on port $Port (PID=$pid)..."
                Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            }
            $deadline = (Get-Date).AddSeconds(10)
            while ((Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {
                Start-Sleep -Milliseconds 200
            }
        }
    } catch {
        Write-Warning "无法检查端口占用（非 Windows 或权限不足），跳过。"
    }
}

Push-Location $BackendDir
try {
    $uvicornArgs = @("src.api.server:app", "--host", $BindHost, "--port", $Port.ToString())
    if ($Reload) { $uvicornArgs += "--reload" }

    Write-Host "Starting backend (full app) on ${BindHost}:${Port} ..."
    & $pythonCmd -m uvicorn @uvicornArgs
}
finally {
    Pop-Location
}
