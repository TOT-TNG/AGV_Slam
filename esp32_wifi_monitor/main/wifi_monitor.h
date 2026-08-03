#pragma once

/**
 * Khởi động task đo RSSI định kỳ + máy trạng thái GOOD/WEAK/OUTAGE.
 * Gọi 1 lần sau khi đã esp_wifi_start()/esp_wifi_connect() — task tự chờ
 * và tự phát hiện mất/khôi phục kết nối ở mỗi chu kỳ đo, không cần đăng ký
 * thêm event handler nào từ bên ngoài.
 */
void wifi_monitor_start(void);
