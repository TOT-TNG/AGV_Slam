# install.ps1 - Cai dat AGVmqtt server tren Windows.
# Chay (PowerShell, quyen Administrator khuyen nghi de cai goi he thong):
#   powershell -ExecutionPolicy Bypass -File deploy\install.ps1
#   powershell -ExecutionPolicy Bypass -File deploy\install.ps1 -NoSeed
#
# Dung winget de cai Python/PostgreSQL/Mosquitto neu chua co san tren may.
# Neu may da co san 3 phan nay (nhu may hien tai), script se tu bo qua.

param(
    [switch]$NoSeed
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir   = Split-Path -Parent $ScriptDir   # mqtt_Server/

Write-Host "=== AGVmqtt install (Windows) ===" -ForegroundColor Cyan

function Test-Cmd($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

if (-not (Test-Cmd "winget")) {
    Write-Host "[INSTALL] Khong tim thay 'winget'. Tu cai Python/PostgreSQL/Mosquitto thu cong roi chay lai script." -ForegroundColor Yellow
} else {
    if (-not (Test-Cmd "python")) {
        Write-Host "[INSTALL] Cai Python..."
        winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    } else {
        Write-Host "[INSTALL] Python da co san, bo qua"
    }

    $pgService = Get-Service | Where-Object { $_.Name -like "postgresql*" }
    if (-not $pgService) {
        Write-Host "[INSTALL] Cai PostgreSQL (se can dat password superuser trong luc cai)..."
        winget install -e --id PostgreSQL.PostgreSQL.16 --accept-source-agreements --accept-package-agreements
    } else {
        Write-Host "[INSTALL] PostgreSQL da co san (service: $($pgService.Name)), bo qua"
    }

    $mosqService = Get-Service | Where-Object { $_.Name -like "mosquitto*" }
    if (-not $mosqService) {
        Write-Host "[INSTALL] Cai Mosquitto..."
        winget install -e --id EclipseFoundation.Mosquitto --accept-source-agreements --accept-package-agreements
    } else {
        Write-Host "[INSTALL] Mosquitto da co san (service: $($mosqService.Name)), bo qua"
    }
}

# ── Ap dung mosquitto.conf mac dinh (listener 1883 + anonymous) ──────────────
$mosqConf = "C:\Program Files\mosquitto\mosquitto.conf"
if (Test-Path (Split-Path $mosqConf)) {
    Write-Host "[INSTALL] Ghi cau hinh mac dinh vao $mosqConf ..."
    Copy-Item "$ScriptDir\mosquitto.conf.template" $mosqConf -Force
    try {
        Restart-Service mosquitto -ErrorAction Stop
        Write-Host "[INSTALL] Da restart dich vu Mosquitto"
    } catch {
        Write-Host "[INSTALL] Khong tu restart duoc dich vu Mosquitto - tu restart thu cong (services.msc)" -ForegroundColor Yellow
    }
} else {
    Write-Host "[INSTALL] Khong tim thay thu muc cai Mosquitto mac dinh - tu copy $ScriptDir\mosquitto.conf.template vao dung vi tri" -ForegroundColor Yellow
}

# ── Chay setup.py (tao venv + cai package + khoi tao database) ──────────────
Write-Host ""
Write-Host "[INSTALL] Chay setup.py ..."
$setupArgs = @("$ScriptDir\setup.py")
if ($NoSeed) { $setupArgs += "--no-seed" }
python @setupArgs
