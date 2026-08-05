param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8001,
    [switch]$Reload = $false,
    [switch]$InstallRequirements = $true,
    [switch]$ForceKillPort = $true
)

$ErrorActionPreference = "Stop"

# 以脚本所在目录为 backend 根（和你原脚本一致）
$BackendDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoDir = Split-Path -Parent $BackendDir
$Requirements = Join-Path $BackendDir "requirements.txt"

# 找到系统上的 python 可执行（尝试 python, py, python3）
$pythonCmd = (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
if (-not $pythonCmd) { $pythonCmd = (Get-Command py -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue) }
if (-not $pythonCmd) { $pythonCmd = (Get-Command python3 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue) }

if (-not $pythonCmd) {
    Write-Error "未在 PATH 中找到 python。请安装 Python 或将其加入 PATH。"
    exit 1
}

Write-Host "Using Python: $pythonCmd"

# Stop all existing listeners on the target port, then wait until it is free.
if ($ForceKillPort) {
    try {
        $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    } catch {
        # On non-Windows/old PowerShell, Get-NetTCPConnection may not exist; warn but continue
        Write-Warning "无法使用 Get-NetTCPConnection 检查端口（Get-NetTCPConnection 不可用），跳过自动强杀端口步骤。"
        $listener = $null
    }

    if ($listener) {
        $pidsToStop = $listener | Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($pidToStop in $pidsToStop) {
            Write-Host "Stopping existing process on port $Port (PID=$pidToStop)..."
            Stop-Process -Id $pidToStop -Force -ErrorAction SilentlyContinue
        }

        $deadline = (Get-Date).AddSeconds(10)
        while ((Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {
            Start-Sleep -Milliseconds 200
        }

        $stillListening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($stillListening) {
            $stillPids = $stillListening | Select-Object -ExpandProperty OwningProcess -Unique
            Write-Error "Port $Port is still in use by PID(s): $($stillPids -join ', ')"
            exit 1
        }
    }
}

# 切换到 backend 目录（确保相对导入、模块路径正确）
Push-Location $BackendDir
try {
    # 如果用户要求安装依赖，则用 python -m pip 安装；使用 --user 以避免需要管理员权限
    if ($InstallRequirements) {
        if (Test-Path $Requirements) {
            Write-Host "Installing backend requirements (per-user) from: $Requirements ..."
            & $pythonCmd -m pip install --user -r $Requirements
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "pip install 返回非零状态，依赖安装可能失败。请手动检查或以管理员身份运行。"
            }
        } else {
            Write-Warning "找不到 requirements.txt: $Requirements — 跳过安装依赖。"
        }
    }

    # 启动 uvicorn：通过 python -m uvicorn 指定 app（不依赖 venv）
    $uvicornTarget = "src.api.document_qa_api:app"
    $uvicornArgs = @($uvicornTarget, "--host", $BindHost, "--port", $Port.ToString())
    if ($Reload) { $uvicornArgs += "--reload" }

    Write-Host "Starting backend with: $pythonCmd -m uvicorn $($uvicornArgs -join ' ')"
    & $pythonCmd -m uvicorn @uvicornArgs
}
catch {
    Write-Error "启动后端时发生错误: $_"
    throw
}
finally {
    Pop-Location
}