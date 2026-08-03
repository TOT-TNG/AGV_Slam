/**
 * ESP32-C5 WiFi 5GHz Signal Monitor
 *
 * Kết nối vào mạng 5GHz cần kiểm tra, đo RSSI định kỳ, đẩy liên tục về
 * backend (biểu đồ phổ tín hiệu) và cảnh báo khi tín hiệu yếu kéo dài theo
 * máy trạng thái trong wifi_monitor.c. Cấu hình (SSID/mật khẩu, gateway
 * key, ngưỡng RSSI...) đặt qua `idf.py menuconfig`, xem Kconfig.projbuild.
 *
 * Phạm vi v1: chỉ xử lý "tín hiệu yếu trong khi vẫn kết nối AP". Khi mất
 * kết nối hoàn toàn, thiết bị không có đường nào để báo real-time — chỉ tự
 * reconnect và báo "disconnected"/"reconnected" khi có thể (best-effort),
 * không lưu-và-gửi-lại (store-and-forward) dữ liệu trong lúc offline.
 */
#include <string.h>

#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "nvs_flash.h"
#include "sdkconfig.h"

#include "wifi_monitor.h"

static const char *TAG = "wifi_mon_main";

static void _wifi_event_handler(void *arg, esp_event_base_t base, int32_t id, void *data) {
    (void)arg; (void)data;
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        ESP_LOGW(TAG, "WiFi disconnected, dang thu ket noi lai...");
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ESP_LOGI(TAG, "Da co IP, bat dau giam sat tin hieu");
    }
}

static void _wifi_init_sta(void) {
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &_wifi_event_handler, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &_wifi_event_handler, NULL));

    wifi_config_t wifi_config = { 0 };
    strlcpy((char *)wifi_config.sta.ssid, CONFIG_WIFI_MON_SSID, sizeof(wifi_config.sta.ssid));
    strlcpy((char *)wifi_config.sta.password, CONFIG_WIFI_MON_PASSWORD, sizeof(wifi_config.sta.password));

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));

    // Ép kết nối băng tần 5GHz — ESP32-C5 hỗ trợ dual-band (2.4/5GHz), nếu
    // không ép band thiết bị có thể tự rớt xuống 2.4GHz trên AP phát cả 2
    // băng tần, làm sai mục đích kiểm tra 5GHz. API `esp_wifi_set_band_mode`
    // dành riêng cho chip dual-band (ESP-IDF 5.3+) — kiểm tra lại tên
    // enum/API này khớp với version ESP-IDF thực tế cài đặt khi build.
    ESP_ERROR_CHECK(esp_wifi_set_band_mode(WIFI_BAND_MODE_5G_ONLY));

    ESP_ERROR_CHECK(esp_wifi_start());
}

void app_main(void) {
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    ESP_LOGI(TAG, "Device ID: %s | Server: %s", CONFIG_WIFI_MON_DEVICE_ID, CONFIG_WIFI_MON_SERVER_HOST);
    ESP_LOGI(TAG, "Nguong RSSI: tot >= %d dBm, yeu < %d dBm", CONFIG_WIFI_MON_RSSI_GOOD, CONFIG_WIFI_MON_RSSI_WEAK);

    _wifi_init_sta();
    wifi_monitor_start();
}
