# --- Cai frpc thanh Windows Service bang NSSM (chay voi quyen Administrator) -
# Cach dung:
#   1. Dat frpc.exe va frpc.toml vao cung 1 thu muc (vi du: C:\frp\)
#   2. Sua frpc.toml cho dung nha may
#   3. Mo PowerShell voi quyen Administrator, chay script nay
#
# TAI SAO DUNG NSSM thay vi "sc.exe create" truc tiep:
# frpc.exe la 1 chuong trinh console binh thuong, KHONG tu goi
# StartServiceCtrlDispatcher de bao cao trang thai voi Windows Service Control
# Manager (SCM). "sc.exe create" van TAO duoc dinh nghia service (khong bao
# loi), nhung khi Start-Service goi vao thi Windows cho SCM callback va
# KHONG BAO GIO nhan duoc -> loi "Cannot start service". NSSM (Non-Sucking
# Service Manager) la cong cu chuan de boc bat ky .exe console nao thanh
# Windows Service that, tu quan ly restart/logging.
#
# Ghi chu: file nay CHI dung ky tu ASCII (khong dau) de tranh loi encoding
# tren Windows PowerShell 5.1 khi doc file .ps1 khong co BOM UTF-8.

param(
    [string]$FrpcDir = "C:\frp"
)

$ErrorActionPreference = "Stop"

$frpcExe  = Join-Path $FrpcDir "frpc.exe"
$frpcConf = Join-Path $FrpcDir "frpc.toml"
$nssmExe  = Join-Path $FrpcDir "nssm.exe"
$svcName  = "frpc-agv"
$svcDesc  = "frp Client - AGV Cloud Tunnel (chay bang NSSM)"

# Kiem tra file can thiet
if (-not (Test-Path $frpcExe)) {
    Write-Error "Khong tim thay $frpcExe - hay dat frpc.exe vao $FrpcDir"
    exit 1
}
if (-not (Test-Path $frpcConf)) {
    Write-Error "Khong tim thay $frpcConf - hay dat frpc.toml vao $FrpcDir"
    exit 1
}

# Tai NSSM neu chua co
if (-not (Test-Path $nssmExe)) {
    Write-Host "Dang tai nssm.exe..."
    $nssmZipUrl = "https://nssm.cc/release/nssm-2.24.zip"
    $tmpZip = Join-Path $FrpcDir "_setup_nssm.zip"
    $tmpDir = Join-Path $FrpcDir "_setup_nssm_extract"

    Invoke-WebRequest -Uri $nssmZipUrl -OutFile $tmpZip
    if (Test-Path $tmpDir) { Remove-Item $tmpDir -Recurse -Force }
    Expand-Archive -Path $tmpZip -DestinationPath $tmpDir -Force

    $arch = if ([Environment]::Is64BitOperatingSystem) { "win64" } else { "win32" }
    $found = Get-ChildItem -Path $tmpDir -Filter "nssm.exe" -Recurse |
        Where-Object { $_.FullName -match $arch } | Select-Object -First 1
    if (-not $found) {
        Write-Error "Khong tim thay nssm.exe (kien truc $arch) sau khi giai nen"
        exit 1
    }
    Copy-Item $found.FullName -Destination $nssmExe -Force
    Remove-Item $tmpZip, $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  OK: da tai nssm.exe"
} else {
    Write-Host "  nssm.exe da co san tai $nssmExe - bo qua tai lai."
}

# Xoa service cu neu co (co the tao boi sc.exe truoc day - khong hoat dong -
# hoac NSSM lan chay truoc)
$existing = Get-Service -Name $svcName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Dung va xoa service cu '$svcName'..."
    Stop-Service -Name $svcName -Force -ErrorAction SilentlyContinue
    # Thu xoa bang NSSM truoc (neu la service cu do NSSM tao), fallback sc.exe
    # (neu la service cu do sc.exe tao truoc day, NSSM se khong nhan dien duoc)
    & $nssmExe remove $svcName confirm 2>$null | Out-Null
    sc.exe delete $svcName 2>$null | Out-Null
    Start-Sleep -Seconds 2
}

# Tao service moi bang NSSM
Write-Host "Tao Windows Service '$svcName' bang NSSM..."
& $nssmExe install $svcName $frpcExe "-c `"$frpcConf`""
& $nssmExe set $svcName DisplayName $svcDesc | Out-Null
& $nssmExe set $svcName Description $svcDesc | Out-Null
& $nssmExe set $svcName Start SERVICE_AUTO_START | Out-Null
& $nssmExe set $svcName AppDirectory $FrpcDir | Out-Null
& $nssmExe set $svcName AppExit Default Restart | Out-Null
& $nssmExe set $svcName AppRestartDelay 5000 | Out-Null
& $nssmExe set $svcName AppStdout (Join-Path $FrpcDir "frpc-service.log") | Out-Null
& $nssmExe set $svcName AppStderr (Join-Path $FrpcDir "frpc-service-error.log") | Out-Null

# Khoi dong ngay
Write-Host "Khoi dong service..."
Start-Service -Name $svcName

Start-Sleep -Seconds 3
$svc = Get-Service -Name $svcName
Write-Host "Trang thai: $($svc.Status)"

if ($svc.Status -eq "Running") {
    Write-Host "OK: frpc service da chay thanh cong!" -ForegroundColor Green
    Write-Host "  Tunnel se tu ket noi lai sau moi lan khoi dong may."
    Write-Host "  Log: $FrpcDir\frpc-service.log"
} else {
    Write-Error "Service khong khoi dong duoc. Xem log tai $FrpcDir\frpc-service-error.log"
}
