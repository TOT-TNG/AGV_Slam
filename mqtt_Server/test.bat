@echo off
"C:\Program Files\mosquitto\mosquitto_pub.exe" -h localhost -t "vda5050/agv/AGV001/state" -f "state.json"
pause



