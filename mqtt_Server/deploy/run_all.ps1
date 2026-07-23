# run_all.ps1 - Chay song song mqtt_Server (FastAPI, port 8000) va Web_UI (Dash, port 8050).
# Chay tu bat ky dau:  powershell -ExecutionPolicy Bypass -File mqtt_Server\deploy\run_all.ps1

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$MqttDir   = Split-Path -Parent $ScriptDir          # mqtt_Server/
$RootDir   = Split-Path -Parent $MqttDir            # thu muc goc project
$WebUiDir  = Join-Path $RootDir "Web_UI"
$VenvPython = Join-Path $MqttDir ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "[RUN_ALL] Khong tim thay venv tai $VenvPython - chay deploy\install.bat truoc." -ForegroundColor Yellow
    exit 1
}

Write-Host "[RUN_ALL] Mo cua so rieng cho mqtt_Server (port 8000) ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$MqttDir'; & '$VenvPython' main.py"

Write-Host "[RUN_ALL] Mo cua so rieng cho Web_UI (port 8050) ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$WebUiDir'; & '$VenvPython' main.py"

Write-Host "[RUN_ALL] Da mo 2 cua so - kiem tra log tung cua so de xac nhan khoi dong thanh cong." -ForegroundColor Green
