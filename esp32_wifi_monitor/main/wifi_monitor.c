#include "wifi_monitor.h"

#include <string.h>

#include "esp_wifi.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sdkconfig.h"

#include "http_report.h"

static const char *TAG = "wifi_monitor";

// Ngưỡng/chu kỳ lấy từ Kconfig (menuconfig > "WiFi Signal Monitor
// Configuration") — không hardcode để dễ tinh chỉnh theo thực tế nhà máy
// mà không phải sửa code.
#define GOOD_THRESHOLD   CONFIG_WIFI_MON_RSSI_GOOD
#define WEAK_THRESHOLD   CONFIG_WIFI_MON_RSSI_WEAK
#define SAMPLE_INTERVAL_US  ((int64_t)CONFIG_WIFI_MON_SAMPLE_INTERVAL_S * 1000000LL)
#define ALERT_INTERVAL_US   ((int64_t)CONFIG_WIFI_MON_ALERT_INTERVAL_S * 1000000LL)
#define OUTAGE_ALERT_COUNT  CONFIG_WIFI_MON_OUTAGE_ALERT_COUNT
#define DEVICE_ID        CONFIG_WIFI_MON_DEVICE_ID

typedef enum {
    STATE_GOOD = 0,
    STATE_WEAK,
    STATE_OUTAGE,
} mon_state_t;

static mon_state_t s_state = STATE_GOOD;
static int s_weak_count = 0;
static int64_t s_last_alert_us = 0;
static int64_t s_outage_start_us = 0;
// Theo dõi cạnh lên/xuống của kết nối để chỉ báo disconnected/reconnected
// đúng 1 lần mỗi lần đổi trạng thái, không spam mỗi chu kỳ đo.
static bool s_was_connected = false;
// BSSID (MAC AP) của lần đo trước — so sánh để phát hiện roaming, phục vụ
// quản lý roaming AGV. Rỗng nghĩa là chưa có dữ liệu để so sánh.
static char s_last_bssid[18] = "";

static void _format_bssid(const uint8_t *mac, char *out, size_t out_len) {
    snprintf(out, out_len, "%02x:%02x:%02x:%02x:%02x:%02x",
              mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

static void _handle_disconnected(void) {
    if (s_was_connected) {
        ESP_LOGW(TAG, "Mat ket noi WiFi");
        wifi_report_post_event(DEVICE_ID, "disconnected", NULL, NULL, NULL);
        s_was_connected = false;
    }
}

static void _handle_sample(int rssi, const char *ssid, int channel, const char *bssid) {
    if (!s_was_connected) {
        ESP_LOGI(TAG, "Da ket noi lai WiFi");
        wifi_report_post_event(DEVICE_ID, "reconnected", &rssi, NULL, NULL);
        s_was_connected = true;
        // Không tự ý đưa về GOOD ở đây — vòng máy trạng thái bên dưới sẽ tự
        // đánh giá lại theo đúng RSSI vừa đo được của lần kết nối mới.
    }

    if (s_last_bssid[0] != '\0' && strcmp(s_last_bssid, bssid) != 0) {
        ESP_LOGW(TAG, "Roaming: %s -> %s (rssi=%d)", s_last_bssid, bssid, rssi);
        wifi_report_post_roam(DEVICE_ID, s_last_bssid, bssid, rssi);
    }
    strlcpy(s_last_bssid, bssid, sizeof(s_last_bssid));

    ESP_LOGI(TAG, "Mau: rssi=%d bssid=%s ssid=%s kenh=%d", rssi, bssid, ssid, channel);
    wifi_report_post_sample(DEVICE_ID, rssi, ssid, channel, bssid);

    int64_t now_us = esp_timer_get_time();

    switch (s_state) {
    case STATE_GOOD:
        if (rssi < WEAK_THRESHOLD) {
            s_state = STATE_WEAK;
            s_weak_count = 1;
            s_last_alert_us = now_us;
            ESP_LOGW(TAG, "Tin hieu yeu: rssi=%d (canh bao 1/%d)", rssi, OUTAGE_ALERT_COUNT);
            wifi_report_post_event(DEVICE_ID, "weak_signal", &rssi, &s_weak_count, NULL);
        }
        break;

    case STATE_WEAK:
        if (rssi >= GOOD_THRESHOLD) {
            ESP_LOGI(TAG, "Tin hieu da phuc hoi (chua toi nguong outage): rssi=%d", rssi);
            wifi_report_post_event(DEVICE_ID, "recovered", &rssi, NULL, NULL);
            s_state = STATE_GOOD;
            s_weak_count = 0;
        } else if (now_us - s_last_alert_us >= ALERT_INTERVAL_US) {
            s_weak_count++;
            s_last_alert_us = now_us;
            if (s_weak_count >= OUTAGE_ALERT_COUNT) {
                s_state = STATE_OUTAGE;
                s_outage_start_us = now_us;
                ESP_LOGE(TAG, "Bat dau outage sau %d canh bao lien tiep: rssi=%d", s_weak_count, rssi);
                wifi_report_post_event(DEVICE_ID, "outage_start", &rssi, &s_weak_count, NULL);
            } else {
                ESP_LOGW(TAG, "Tin hieu yeu: rssi=%d (canh bao %d/%d)", rssi, s_weak_count, OUTAGE_ALERT_COUNT);
                wifi_report_post_event(DEVICE_ID, "weak_signal", &rssi, &s_weak_count, NULL);
            }
        }
        break;

    case STATE_OUTAGE:
        if (rssi >= GOOD_THRESHOLD) {
            int outage_seconds = (int)((now_us - s_outage_start_us) / 1000000LL);
            ESP_LOGI(TAG, "Tin hieu da phuc hoi sau outage %d giay: rssi=%d", outage_seconds, rssi);
            wifi_report_post_event(DEVICE_ID, "recovered", &rssi, NULL, &outage_seconds);
            s_state = STATE_GOOD;
            s_weak_count = 0;
        }
        // Còn outage: mẫu RSSI liên tục ở trên đã đủ để dựng lại dòng thời
        // gian trên dashboard, không cần spam thêm cảnh báo ở đây.
        break;
    }
}

static void _monitor_task(void *arg) {
    (void)arg;
    for (;;) {
        wifi_ap_record_t ap_info;
        esp_err_t err = esp_wifi_sta_get_ap_info(&ap_info);
        if (err == ESP_OK) {
            char bssid_str[18];
            _format_bssid(ap_info.bssid, bssid_str, sizeof(bssid_str));
            _handle_sample((int8_t)ap_info.rssi, (const char *)ap_info.ssid, ap_info.primary, bssid_str);
        } else {
            _handle_disconnected();
        }
        vTaskDelay(pdMS_TO_TICKS(SAMPLE_INTERVAL_US / 1000));
    }
}

void wifi_monitor_start(void) {
    xTaskCreate(_monitor_task, "wifi_monitor", 4096, NULL, tskIDLE_PRIORITY + 3, NULL);
}
