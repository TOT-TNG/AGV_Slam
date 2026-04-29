@echo off
setlocal enabledelayedexpansion

REM Xoa log cu
del wifi_debug.log 2>nul
echo === BAT STARTED === >> wifi_debug.log

echo Dang ket noi den WiFi TOT...
netsh wlan connect name="TOT" >> wifi_debug.log 2>&1

echo Sau lenh connect, errorlevel = %errorlevel% >> wifi_debug.log

REM Neu ket noi WiFi loi -> thoat luon
if %errorlevel% neq 0 (
    echo Loi ket noi WiFi. >> wifi_debug.log
    exit /b
)

REM Cho WiFi on IP
timeout /t 10 >nul

REM Lay IP tu interface Wi-Fi
for /f "tokens=2 delims=:" %%A in ('netsh interface ip show address name^="Wi-Fi" ^| findstr "IP Address"') do (
    set rawip=%%A
)
set ip=%rawip: =%

echo IP tim duoc: %ip% >> wifi_debug.log

REM Neu IP dung thi mo phan mem
if "%ip%"=="192.168.0.200" (
    echo Mo phan mem... >> wifi_debug.log
    start "" "C:\Users\admin\Desktop\WindowsService1.exe"
) else (
    echo Sai IP. Khong mo phan mem. >> wifi_debug.log
)

REM Auto close console
exit
