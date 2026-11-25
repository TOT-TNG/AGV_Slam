@echo off
REM start_mosquitto_sim.bat — Khoi 1 Mosquitto RIENG cho mo phong fleet (port
REM 1884), KHAC broker san xuat that (1883) — xem mosquitto_sim.conf canh file
REM nay. GIU CUA SO NAY MO trong luc dung trang "Mo phong Fleet" tren Web_UI;
REM dong cua so (hoac Ctrl+C) de dung Mosquitto mo phong khi xong.

set MOSQUITTO_EXE="C:\Program Files\mosquitto\mosquitto.exe"

if not exist %MOSQUITTO_EXE% (
    echo [LOI] Khong tim thay Mosquitto tai %MOSQUITTO_EXE%
    echo Sua lai duong dan trong file nay cho dung may ban, hoac cai Mosquitto tu https://mosquitto.org/download/
    pause
    exit /b 1
)

echo Dang khoi Mosquitto MO PHONG tai port 1884 (Ctrl+C de dung)...
%MOSQUITTO_EXE% -c "%~dp0mosquitto_sim.conf" -v
pause
