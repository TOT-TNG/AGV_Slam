#pragma once

#include "esp_err.h"

/**
 * Gửi 1 mẫu RSSI liên tục lên "<host>/api/wifi/report".
 * Đây là nguồn dữ liệu cho biểu đồ phổ tín hiệu trên dashboard.
 */
esp_err_t wifi_report_post_sample(const char *device_id, int rssi,
                                   const char *ssid, int channel);

/**
 * Gửi 1 sự kiện (weak_signal / outage_start / recovered / disconnected /
 * reconnected) lên "<host>/api/wifi/alert". Các tham số optional truyền
 * NULL nếu không áp dụng.
 */
esp_err_t wifi_report_post_event(const char *device_id, const char *event_type,
                                  const int *rssi, const int *consecutive_count,
                                  const int *outage_seconds);
