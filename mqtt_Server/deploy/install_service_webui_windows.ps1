# install_service_webui_windows.ps1 - Dang ky Web_UI (Dash dashboard, port 8050)
# chay nen nhu 1 Windows Service, tu khoi dong cung Windows va tu restart neu
# crash. Dung chung nssm.exe da tai san (hoac tu tai neu chua co) - giong het
# co che cua install_service_windows.ps1 (mqtt_Server, port 8000).
#
# Chay (can quyen Administrator), SAU KHI da cai xong mqtt_Server (can chung
# venv tai mqtt_Server\.venv de co san goi dash/dash-bootstrap-components):
#   powershell -ExecutionPolicy Bypass -File deploy\install_service_webui_windows.ps1
#
# Go bo service:
#   nssm remove AGVWebUI confirm
#   (hoac: & "$ScriptDir\nssm.exe" remove AGVWebUI confirm)

$ErrorActionPreference = "Stop"

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$MqttDir     = Split-Path -Parent $ScriptDir            # mqtt_Server/
$RootDir     = Split-Path -Parent $MqttDir              # thu muc goc project
$WebUiDir    = Join-Path $RootDir "Web_UI"
$VenvPython  = Join-Path $MqttDir ".venv\Scripts\python.exe"
$MainPy      = Join-Path $WebUiDir "main.py"
$ServiceName = "AGVWebUI"
$NssmExe     = Join-Path $ScriptDir "nssm.exe"
$LocalPort   = 8050
$NssmVersion = "2.24"

if (-not (Test-Path $VenvPython)) {
    Write-Host "[SERVICE] Chua thay venv tai $VenvPython - chay deploy\install.bat (mqtt_Server) truoc." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $MainPy)) {
    Write-Host "[SERVICE] Khong tim thay $MainPy" -ForegroundColor Red
    exit 1
}

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "Script nay CAN chay voi quyen Administrator (chuot phai PowerShell > Run as Administrator)."
    exit 1
}

# -- Tai NSSM truc tiep tu nssm.cc neu chua co (dung chung file voi service kia) --
if (-not (Test-Path $NssmExe)) {
    Write-Host "[SERVICE] Dang tai nssm.exe v$NssmVersion..."
    try {
        Add-MpPreference -ExclusionPath $ScriptDir -ErrorAction Stop
    } catch {
        Write-Host "[SERVICE] Khong them duoc Defender exclusion tu dong - bo qua (khong bat buoc cho NSSM)." -ForegroundColor Yellow
    }
    $nssmZipUrl = "https://nssm.cc/release/nssm-$NssmVersion.zip"
    $tmpZip = Join-Path $ScriptDir "_setup_nssm.zip"
    $tmpDir = Join-Path $ScriptDir "_setup_nssm_extract"

    Invoke-WebRequest -Uri $nssmZipUrl -OutFile $tmpZip
    if (Test-Path $tmpDir) { Remove-Item $tmpDir -Recurse -Force }
    Expand-Archive -Path $tmpZip -DestinationPath $tmpDir -Force

    $arch = if ([Environment]::Is64BitOperatingSystem) { "win64" } else { "win32" }
    $found = Get-ChildItem -Path $tmpDir -Filter "nssm.exe" -Recurse |
        Where-Object { $_.FullName -match $arch } | Select-Object -First 1
    if (-not $found) {
        Write-Error "Khong tim thay nssm.exe (kien truc $arch) sau khi giai nen."
        exit 1
    }
    Copy-Item $found.FullName -Destination $NssmExe -Force
    Remove-Item $tmpZip, $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "[SERVICE] OK: da tai nssm.exe"
} else {
    Write-Host "[SERVICE] nssm.exe da co san tai $NssmExe - bo qua tai lai."
}

$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "[SERVICE] Service '$ServiceName' da ton tai - xoa de tao lai..."
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    & $NssmExe remove $ServiceName confirm 2>$null | Out-Null
    sc.exe delete $ServiceName 2>$null | Out-Null
    Start-Sleep -Seconds 2
}

Write-Host "[SERVICE] Tao service '$ServiceName' ..."
& $NssmExe install $ServiceName $VenvPython $MainPy
& $NssmExe set $ServiceName AppDirectory $WebUiDir | Out-Null
& $NssmExe set $ServiceName DisplayName "AGV Web UI (Dash)" | Out-Null
& $NssmExe set $ServiceName Description "AGV Fleet Management Web Dashboard (Dash, port $LocalPort)" | Out-Null
& $NssmExe set $ServiceName Start SERVICE_AUTO_START | Out-Null
# Phu thuoc AGVmqttServer (DB/MQTT) - khoi dong sau, nhung khong bat buoc
# (Web_UI tu ket noi lai neu chua san sang).
& $NssmExe set $ServiceName DependOnService AGVmqttServer | Out-Null
& $NssmExe set $ServiceName AppExit Default Restart | Out-Null
& $NssmExe set $ServiceName AppRestartDelay 3000 | Out-Null
& $NssmExe set $ServiceName AppStdout (Join-Path $ScriptDir "service_webui_stdout.log") | Out-Null
& $NssmExe set $ServiceName AppStderr (Join-Path $ScriptDir "service_webui_stderr.log") | Out-Null
# File tho du phong cua NSSM (khong co timestamp tung dong) - bat rotate de
# khong phinh vo han, xem giai thich day du o install_service_windows.ps1.
& $NssmExe set $ServiceName AppRotateFiles 1 | Out-Null
& $NssmExe set $ServiceName AppRotateOnline 1 | Out-Null
& $NssmExe set $ServiceName AppRotateSeconds 86400 | Out-Null
& $NssmExe set $ServiceName AppRotateBytes 52428800 | Out-Null

Write-Host "[SERVICE] Khoi dong service ..."
Start-Service -Name $ServiceName

# -- Tu kiem tra ket qua NGAY TAI MAY NAY -------------------------------------
Start-Sleep -Seconds 5
$svc = Get-Service -Name $ServiceName
Write-Host ""
Write-Host "[SERVICE] Trang thai: $($svc.Status)"

$portOk = Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue
if ($svc.Status -eq "Running" -and $portOk) {
    Write-Host "[SERVICE] OK: Web UI da chay thanh cong va dang lang nghe port $LocalPort." -ForegroundColor Green
    Write-Host "[SERVICE] Se tu chay cung Windows va tu restart neu crash."
} elseif ($svc.Status -eq "Running") {
    Write-Host "[SERVICE] CANH BAO: service dang Running nhung CHUA thay lang nghe port $LocalPort." -ForegroundColor Yellow
    Write-Host "  Doi vai giay roi kiem tra lai:"
    Write-Host "  Get-NetTCPConnection -LocalPort $LocalPort -State Listen"
    Write-Host "  Neu van khong co, xem log loi:"
    Write-Host "  Get-Content `"$ScriptDir\service_webui_stderr.log`" -Tail 30"
} else {
    Write-Error "Service khong khoi dong duoc. Xem log: $ScriptDir\service_webui_stderr.log"
}

Write-Host ""
Write-Host "[SERVICE] Log: $ScriptDir\service_webui_stdout.log / service_webui_stderr.log"
