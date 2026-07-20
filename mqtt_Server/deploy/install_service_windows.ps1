# install_service_windows.ps1 - Dang ky AGVmqtt server chay nen nhu 1 Windows
# Service, tu khoi dong cung Windows va tu restart neu crash. Dung NSSM
# (Non-Sucking Service Manager) de wrap main.py thanh service that.
#
# Chay (can quyen Administrator):
#   powershell -ExecutionPolicy Bypass -File deploy\install_service_windows.ps1
#
# Go bo service:
#   nssm remove AGVmqttServer confirm
#   (hoac: & "$RootDir\deploy\nssm.exe" remove AGVmqttServer confirm)

$ErrorActionPreference = "Stop"

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir     = Split-Path -Parent $ScriptDir            # mqtt_Server/
$VenvPython  = Join-Path $RootDir ".venv\Scripts\python.exe"
$MainPy      = Join-Path $RootDir "main.py"
$ServiceName = "AGVmqttServer"
$NssmExe     = Join-Path $ScriptDir "nssm.exe"
$LocalPort   = 8000
$NssmVersion = "2.24"

if (-not (Test-Path $VenvPython)) {
    Write-Host "[SERVICE] Chua thay venv tai $VenvPython - chay deploy\setup.py truoc" -ForegroundColor Red
    exit 1
}

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "Script nay CAN chay voi quyen Administrator (chuot phai PowerShell > Run as Administrator)."
    exit 1
}

# -- Tai NSSM truc tiep tu nssm.cc neu chua co --------------------------------
# KHONG dung 'winget install NSSM.NSSM' - nhieu may nha may (Windows cu/Server,
# bi IT khoa app store) khong co winget, khien buoc cai that bai kho hieu.
# Tai thang tu nssm.cc giong het cach dung cho frpc (cloud_gateway/factory/) -
# khong phu thuoc winget, hoat dong dong nhat tren moi may Windows.
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
& $NssmExe set $ServiceName AppDirectory $RootDir | Out-Null
& $NssmExe set $ServiceName DisplayName "AGVmqtt Server" | Out-Null
& $NssmExe set $ServiceName Description "AGV Fleet Management Server (FastAPI + MQTT)" | Out-Null
& $NssmExe set $ServiceName Start SERVICE_AUTO_START | Out-Null
# Tu restart neu crash - NSSM mac dinh da restart khi process thoat bat thuong,
# dat rieng them de chac chan luon bat (khong phu thuoc default cua ban NSSM).
& $NssmExe set $ServiceName AppExit Default Restart | Out-Null
& $NssmExe set $ServiceName AppRestartDelay 3000 | Out-Null
& $NssmExe set $ServiceName AppStdout (Join-Path $RootDir "deploy\service_stdout.log") | Out-Null
& $NssmExe set $ServiceName AppStderr (Join-Path $RootDir "deploy\service_stderr.log") | Out-Null

Write-Host "[SERVICE] Khoi dong service ..."
Start-Service -Name $ServiceName

# -- Tu kiem tra ket qua NGAY TAI MAY NAY -------------------------------------
Start-Sleep -Seconds 5
$svc = Get-Service -Name $ServiceName
Write-Host ""
Write-Host "[SERVICE] Trang thai: $($svc.Status)"

$portOk = Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue
if ($svc.Status -eq "Running" -and $portOk) {
    Write-Host "[SERVICE] OK: server da chay thanh cong va dang lang nghe port $LocalPort." -ForegroundColor Green
    Write-Host "[SERVICE] Se tu chay cung Windows va tu restart neu crash."
} elseif ($svc.Status -eq "Running") {
    Write-Host "[SERVICE] CANH BAO: service dang Running nhung CHUA thay lang nghe port $LocalPort." -ForegroundColor Yellow
    Write-Host "  Co the server dang khoi dong cham (DB/MQTT) - doi vai giay roi kiem tra lai:"
    Write-Host "  Get-NetTCPConnection -LocalPort $LocalPort -State Listen"
    Write-Host "  Neu van khong co, xem log loi:"
    Write-Host "  Get-Content `"$RootDir\deploy\service_stderr.log`" -Tail 30"
} else {
    Write-Error "Service khong khoi dong duoc. Xem log: $RootDir\deploy\service_stderr.log"
}

Write-Host ""
Write-Host "[SERVICE] Log: $RootDir\deploy\service_stdout.log / service_stderr.log"
