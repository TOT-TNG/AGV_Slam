# --- Cai dat frpc cho 1 nha may - DUNG LAI DUOC CHO MOI NHA MAY MOI ---------
# Chay 1 lenh duy nhat, khong can sua file nao trong repo, khong can hoi lai.
# Script tu tai frpc.exe (neu chua co dung version), tu sinh frpc.toml (khong
# commit, chi nam tren may nay), roi goi install_service.ps1 de cai Windows
# Service tu khoi dong cung may.
#
# Cach dung (PowerShell VOI QUYEN ADMINISTRATOR):
#   cd cloud_gateway\factory
#   .\deploy_frpc.ps1 -Subdomain "vietduc" -Token "<token that>"
#
# Them nha may moi sau nay - CHI CAN:
#   1. Tren VPS: them 1 entry vao /etc/agv-gateway/factories.json (khong can restart)
#   2. Tren may nha may moi: chay lenh tren voi dung -Subdomain cua nha may do
#      (Token dung lai y het - auth.token la chung cho toan he thong, khong
#      phai theo tung nha may)
#
# Tham so:
#   -Subdomain   BAT BUOC - phai khop "frp_host" da khai trong factories.json tren VPS
#   -Token       BAT BUOC - auth.token that cua frps (lay tu /etc/frp/frps.toml tren VPS,
#                KHONG luu trong repo - luon truyen tay hoac qua secret store rieng)
#   -ServerAddr  Mac dinh "iot.tot360.com.vn"
#   -ServerPort  Mac dinh 7500 - PHAI khop bindPort trong frps.toml tren VPS
#   -LocalPort   Mac dinh 8000 - port FastAPI local (mqtt_Server)
#   -FrpVersion  Mac dinh 0.62.1 - PHAI khop version frps tren VPS
#                (kiem tra tren VPS: /usr/local/bin/frps --version)
#   -FrpcDir     Mac dinh C:\frp - noi dat frpc.exe + frpc.toml + cai service

param(
    [Parameter(Mandatory=$true)][string]$Subdomain,
    [Parameter(Mandatory=$true)][string]$Token,
    [string]$ServerAddr = "iot.tot360.com.vn",
    [int]$ServerPort    = 7500,
    [int]$LocalPort     = 8000,
    [string]$FrpVersion = "0.62.1",
    [string]$FrpcDir    = "C:\frp"
)

$ErrorActionPreference = "Stop"

Write-Host "=== Cai dat frpc cho nha may (subdomain=$Subdomain) ===" -ForegroundColor Cyan

# -- 0a. Kiem tra dang chay voi quyen Administrator ---------------------------
# Add-MpPreference (Defender exclusion) va cai Windows Service (NSSM) deu can
# quyen Admin - neu thieu, script se that bai giua chung voi loi kho hieu.
# Bao loi ro rang ngay tu dau thay vi de nguoi cai dat tu doan lung tung.
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "Script nay CAN chay voi quyen Administrator (chuot phai PowerShell > Run as Administrator)."
    exit 1
}

# -- 0b. Kiem tra mqtt_Server (FastAPI local) da chay chua --------------------
# Tunnel chi huu ich neu server local dang lang nghe dung $LocalPort. Thieu
# buoc nay se cai xong tunnel roi moi phat hien server local chua chay, gay
# nham lan (tunnel "thanh cong" nhung goi API van 502/504 tu xa).
$portCheck = Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue
if (-not $portCheck) {
    Write-Host ""
    Write-Host "CANH BAO: khong thay gi dang lang nghe tren port $LocalPort tren may nay." -ForegroundColor Yellow
    Write-Host "  mqtt_Server (main.py) co the CHUA CHAY - tunnel se cai duoc binh thuong"
    Write-Host "  nhung moi request qua cloud se bi loi (khong ket noi duoc toi FastAPI local)."
    Write-Host "  Hay chac chan main.py dang chay (port $LocalPort) truoc khi dung he thong that."
    Write-Host ""
} else {
    Write-Host "  OK: da thay dich vu dang lang nghe tren port $LocalPort (mqtt_Server co ve dang chay)"
}

# -- 1. Tao thu muc dich ------------------------------------------------------
New-Item -ItemType Directory -Force -Path $FrpcDir | Out-Null

# -- 1b. Loai tru Windows Defender cho thu muc nay ----------------------------
# frp (frpc.exe) rat hay bi Defender/AV nham la PUA (dual-use tunneling tool)
# va xoa/chan ngay luc giai nen. Them exclusion TRUOC khi tai - can quyen
# Administrator (script nay von da yeu cau chay Admin de cai Windows Service).
try {
    Add-MpPreference -ExclusionPath $FrpcDir -ErrorAction Stop
    Write-Host "  OK: da them Windows Defender exclusion cho $FrpcDir"
} catch {
    Write-Host "  CANH BAO: khong them duoc Defender exclusion tu dong ($($_.Exception.Message))" -ForegroundColor Yellow
    Write-Host "  Neu buoc tai frpc.exe bi loi 'virus or potentially unwanted software',"
    Write-Host "  vao Windows Security > Virus & threat protection > Exclusions > them thu muc $FrpcDir thu cong."
}

# -- 2. Tai frpc.exe neu chua co dung version ---------------------------------
# Tai + giai nen NGAY TRONG $FrpcDir (khong dung %TEMP%) - de exclusion o
# Buoc 1b bao phu ca luc tai/giai nen, khong chi luc dat file frpc.exe cuoi cung.
$frpcExe       = Join-Path $FrpcDir "frpc.exe"
$versionMarker = Join-Path $FrpcDir ".frp_version"
$needDownload  = $true
if ((Test-Path $frpcExe) -and (Test-Path $versionMarker)) {
    $existingVer = (Get-Content $versionMarker -Raw).Trim()
    if ($existingVer -eq $FrpVersion) { $needDownload = $false }
}

if ($needDownload) {
    Write-Host "Dang tai frpc.exe v$FrpVersion..."
    $zipUrl = "https://github.com/fatedier/frp/releases/download/v$FrpVersion/frp_${FrpVersion}_windows_amd64.zip"
    $tmpZip = Join-Path $FrpcDir "_setup_frp.zip"
    $tmpDir = Join-Path $FrpcDir "_setup_extract"

    Invoke-WebRequest -Uri $zipUrl -OutFile $tmpZip
    if (Test-Path $tmpDir) { Remove-Item $tmpDir -Recurse -Force }
    Expand-Archive -Path $tmpZip -DestinationPath $tmpDir -Force

    $extractedExe = Join-Path $tmpDir "frp_${FrpVersion}_windows_amd64\frpc.exe"
    if (-not (Test-Path $extractedExe)) {
        Write-Error "Khong tim thay frpc.exe sau khi giai nen - kiem tra lai FrpVersion ($FrpVersion) co dung khong."
        exit 1
    }
    Copy-Item $extractedExe -Destination $frpcExe -Force
    Set-Content -Path $versionMarker -Value $FrpVersion
    Remove-Item $tmpZip, $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  OK: da tai va dat frpc.exe v$FrpVersion"
} else {
    Write-Host "  frpc.exe v$FrpVersion da co san tai $frpcExe - bo qua tai lai."
}

# -- 3. Sinh frpc.toml (khong commit - chi nam tren may nay) -----------------
$tomlContent = @"
# Tu dong sinh boi deploy_frpc.ps1 luc $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
# KHONG commit file nay len git - chua token that.
serverAddr = "$ServerAddr"
serverPort = $ServerPort
auth.token = "$Token"

transport.heartbeatInterval = 10
transport.heartbeatTimeout  = 30

[[proxies]]
name      = "agv-local"
type      = "http"
localIP   = "127.0.0.1"
localPort = $LocalPort
subdomain = "$Subdomain"
"@
$tomlPath = Join-Path $FrpcDir "frpc.toml"
# QUAN TRONG: KHONG dung "-Encoding utf8" (Windows PowerShell 5.1 tu them BOM
# EF BB BF vao dau file voi option nay) - trinh doc TOML cua frpc.exe (Go) doc
# phai byte BOM nay se loi "cannot unmarshal string into Go value of type
# v1.ClientConfig" ngay tu dong dau. Noi dung toan ASCII nen dung -Encoding
# ASCII de dam bao khong co BOM.
[System.IO.File]::WriteAllText($tomlPath, $tomlContent, (New-Object System.Text.UTF8Encoding $false))
Write-Host "  OK: da sinh $tomlPath (subdomain=$Subdomain, serverPort=$ServerPort)"

# -- 4. Cai / cap nhat Windows Service (dung lai install_service.ps1 co san) --
$installScript = Join-Path $PSScriptRoot "install_service.ps1"
if (-not (Test-Path $installScript)) {
    Write-Error "Khong tim thay install_service.ps1 trong $PSScriptRoot"
    exit 1
}
& $installScript -FrpcDir $FrpcDir

# -- 5. Tu kiem tra ket qua NGAY TAI MAY NAY -----------------------------------
# Khong phai ai cai dat cung co quyen SSH vao VPS de kiem tra - doc log cua
# chinh service vua khoi dong de bao PASS/FAIL ro rang tai cho.
Write-Host ""
Write-Host "=== Tu kiem tra ket qua tunnel (doc log local) ===" -ForegroundColor Cyan
Start-Sleep -Seconds 2
$logPath = Join-Path $FrpcDir "frpc-service.log"
$tunnelOk = $false
if (Test-Path $logPath) {
    $recentLog = Get-Content $logPath -Tail 15
    if ($recentLog -match "login to server success" -and $recentLog -match "start proxy success") {
        $tunnelOk = $true
    }
    Write-Host "--- 15 dong log gan nhat ($logPath) ---"
    $recentLog | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Host "  Khong tim thay $logPath - service co the chua kip ghi log."
}

Write-Host ""
if ($tunnelOk) {
    Write-Host "=== KET QUA: TUNNEL DA KET NOI THANH CONG ===" -ForegroundColor Green
} else {
    Write-Host "=== KET QUA: CHUA XAC NHAN DUOC TUNNEL DA KET NOI ===" -ForegroundColor Yellow
    Write-Host "  Xem lai log o tren - loi thuong gap:"
    Write-Host "  - 'token in login doesnt match'  -> Token sai, kiem tra lai -Token vs auth.token tren VPS"
    Write-Host "  - 'connect to server error'      -> Sai ServerAddr/ServerPort, hoac firewall chan outbound"
    Write-Host "  - Khong co dong nao ca            -> Service co the chua kip khoi dong, doi vai giay roi xem lai:"
    Write-Host "      Get-Content `"$logPath`" -Tail 20"
}

Write-Host ""
Write-Host "=== Kiem tra THEM tu phia VPS (neu co quyen SSH) ===" -ForegroundColor Cyan
Write-Host "curl -s -H `"Host: $Subdomain.tot360.internal`" http://127.0.0.1:8090/api/maps/list"
Write-Host ""
Write-Host "Hoac qua gateway (can Gateway Key khop factories.json):"
Write-Host "curl -s -H `"X-Gateway-Key: <KEY_CUA_NHA_MAY_NAY>`" https://$ServerAddr/acs/api/maps/list"
