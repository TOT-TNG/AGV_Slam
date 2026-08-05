# update_windows.ps1 - Cap nhat AGVmqtt server sau khi da cai dat lan dau
# (khong can lam lai buoc winget/tao venv/tao database tu dau). Dung khi code
# co thay doi (git pull ve) va can nap len 2 service dang chay san.
#
# Chay (PowerShell, quyen Administrator - can de restart Windows Service):
#   powershell -ExecutionPolicy Bypass -File deploy\update_windows.ps1
#
# Viec script nay lam:
#   1. git pull code moi nhat (neu thu muc goc la 1 git repo)
#   2. Cai lai requirements.txt vao venv da co san (chi cai goi thay doi/moi)
#   3. Ap dung lai schema_core.sql (an toan - CREATE TABLE IF NOT EXISTS, khong
#      mat du lieu) phong truong hop schema co them thay doi
#   4. Restart 2 Windows Service AGVmqttServer + AGVWebUI (neu da cai)
#
# KHONG dong bo du lieu backup - neu can cap nhat du lieu (AGV/ban do moi...)
# tu may khac, dung rieng buoc "Phuc hoi tu backup" trong INSTALL_GUIDE.md.

$ErrorActionPreference = "Stop"

# -- 0. Kiem tra quyen Administrator -------------------------------------------
# Restart-Service/Stop-Service can quyen admin de mo handle dieu khien service.
# Neu khong co quyen nay, Get-Service van chay binh thuong (chi doc) nhung
# Restart-Service se bao loi kho hieu "Cannot open ... service on computer '.'".
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "[UPDATE] LOI: Ban dang chay PowerShell KHONG co quyen Administrator." -ForegroundColor Red
    Write-Host "[UPDATE] Buoc restart Windows Service can quyen admin de thuc hien." -ForegroundColor Red
    Write-Host "[UPDATE] Hay dong cua so nay, mo lai PowerShell bang 'Run as Administrator' roi chay lai script." -ForegroundColor Yellow
    exit 1
}

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$MqttDir    = Split-Path -Parent $ScriptDir            # mqtt_Server/
$RootDir    = Split-Path -Parent $MqttDir              # thu muc goc project
$VenvPython = Join-Path $MqttDir ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "[UPDATE] Chua thay venv tai $VenvPython - day la lan cai dat dau tien, chay deploy\install.bat truoc (khong dung script nay)." -ForegroundColor Red
    exit 1
}

# -- 1. git pull (neu la git repo) --------------------------------------------
Push-Location $RootDir
try {
    if (Test-Path (Join-Path $RootDir ".git")) {
        Write-Host "[UPDATE] git pull code moi nhat..." -ForegroundColor Cyan
        git pull
    } else {
        Write-Host "[UPDATE] Thu muc goc khong phai git repo - bo qua git pull. Neu ban cap nhat code bang cach copy file thu cong, hay copy truoc khi chay script nay." -ForegroundColor Yellow
    }
} finally {
    Pop-Location
}

# -- 2. Cai lai requirements.txt vao venv co san ------------------------------
Write-Host "[UPDATE] Cap nhat package trong venv..." -ForegroundColor Cyan
& $VenvPython -m pip install -r (Join-Path $MqttDir "requirements.txt")

# -- 3. Ap dung lai schema_core.sql (an toan, khong mat du lieu) --------------
Write-Host "[UPDATE] Ap dung lai schema_core.sql (CREATE TABLE IF NOT EXISTS - an toan)..." -ForegroundColor Cyan
$pgHost = if ($env:PGHOST) { $env:PGHOST } else { "localhost" }
$pgPort = if ($env:PGPORT) { $env:PGPORT } else { "5432" }
$pgUser = if ($env:PGUSER) { $env:PGUSER } else { "postgres" }
$pgDb   = if ($env:PGDATABASE) { $env:PGDATABASE } else { "TOT_AGV" }
$pgBin  = Get-ChildItem "C:\Program Files\PostgreSQL" -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending | Select-Object -First 1
if ($pgBin) {
    $psqlExe = Join-Path $pgBin.FullName "bin\psql.exe"
    if ($env:PGPASSWORD) {
        & $psqlExe -h $pgHost -p $pgPort -U $pgUser -d $pgDb -f (Join-Path $ScriptDir "schema_core.sql")
    } else {
        Write-Host "[UPDATE] Bo qua - can bien moi truong PGPASSWORD de chay khong hoi mat khau. Tu chay tay neu can:" -ForegroundColor Yellow
        Write-Host "  & `"$psqlExe`" -U $pgUser -d $pgDb -f `"$ScriptDir\schema_core.sql`""
    }
} else {
    Write-Host "[UPDATE] Khong tim thay PostgreSQL tai C:\Program Files\PostgreSQL - bo qua buoc schema." -ForegroundColor Yellow
}

# -- 4. Restart 2 Windows Service (neu da cai) --------------------------------
$restartFailed = $false
foreach ($svcName in @("AGVmqttServer", "AGVWebUI")) {
    $svc = Get-Service -Name $svcName -ErrorAction SilentlyContinue
    if ($svc) {
        Write-Host "[UPDATE] Restart service '$svcName' ..." -ForegroundColor Cyan
        try {
            Restart-Service -Name $svcName -Force -ErrorAction Stop
            Start-Sleep -Seconds 3
            $svc = Get-Service -Name $svcName
            Write-Host "[UPDATE] $svcName -> $($svc.Status)"
        } catch {
            $restartFailed = $true
            Write-Host "[UPDATE] LOI khi restart '$svcName': $($_.Exception.Message)" -ForegroundColor Red
            Write-Host "[UPDATE] Thu restart tay bang Services.msc (chay voi quyen Administrator) hoac lenh: Restart-Service -Name $svcName -Force" -ForegroundColor Yellow
        }
    } else {
        Write-Host "[UPDATE] Service '$svcName' chua duoc cai - bo qua restart (chay deploy\install_service_windows.ps1 / install_service_webui_windows.ps1 neu muon cai service)." -ForegroundColor Yellow
    }
}
if ($restartFailed) {
    Write-Host ""
    Write-Host "[UPDATE] Code/schema da cap nhat xong, nhung co it nhat 1 service restart LOI (xem chi tiet o tren)." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[UPDATE] HOAN TAT." -ForegroundColor Green
