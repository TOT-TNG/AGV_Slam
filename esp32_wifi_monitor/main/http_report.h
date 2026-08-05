#pragma once

#include "esp_err.h"

/**
 * Gửi 1 mẫu RSSI liên tục lên "<host>/api/wifi/report".
 * Đây là nguồn dữ liệu cho biểu đồ phổ tín hiệu trên dashboard.
 * `bssid` (MAC của AP đang kết nối, dạng "aa:bb:cc:dd:ee:ff") truyền NULL
 * nếu không có. `noise_floor` (dBm, đo qua promiscuous mode, thưa hơn RSSI
 * nhiều) truyền NULL ở các chu kỳ không đo nhiễu.
 */
esp_err_t wifi_report_post_sample(const char *device_id, int rssi,
                                   const char *ssid, int channel,
                                   const char *bssid, const int *noise_floor);

/**
 * Gửi 1 sự kiện (weak_signal / outage_start / recovered / disconnected /
 * reconnected) lên "<host>/api/wifi/alert". Các tham số optional truyền
 * NULL nếu không áp dụng.
 */
esp_err_t wifi_report_post_event(const char *device_id, const char *event_type,
                                  const int *rssi, const int *consecutive_count,
                                  const int *outage_seconds);

/**
 * Gửi sự kiện 'roamed' (AGV/thiết bị đổi sang AP khác) lên
 * "<host>/api/wifi/alert" — phục vụ quản lý roaming.
 */
esp_err_t wifi_report_post_roam(const char *device_id, const char *old_bssid,
                                 const char *new_bssid, int rssi);
