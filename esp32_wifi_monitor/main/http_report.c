#include "http_report.h"

#include <string.h>

#include "esp_http_client.h"
#include "esp_crt_bundle.h"
#include "esp_log.h"
#include "cJSON.h"
#include "sdkconfig.h"

static const char *TAG = "wifi_http_report";

// Chuỗi băng tần gửi lên backend — tự chọn theo khả năng thật của chip
// (project build chung code cho cả ESP32-C5 5GHz lẫn ESP32-S3 2.4GHz).
#if CONFIG_SOC_WIFI_SUPPORT_5G
#define WIFI_MON_BAND_STR "5GHz"
#else
#define WIFI_MON_BAND_STR "2.4GHz"
#endif

// Lỗi POST chỉ log cảnh báo, không bao giờ chặn vòng lặp đo RSSI của
// wifi_monitor.c — mạng chập chờn tạm thời không được làm rớt phép đo.
static esp_err_t _post_json(const char *path, const char *json_body) {
    char url[256];
    snprintf(url, sizeof(url), "%s%s", CONFIG_WIFI_MON_SERVER_HOST, path);

    esp_http_client_config_t config = {
        .url = url,
        .method = HTTP_METHOD_POST,
        .crt_bundle_attach = esp_crt_bundle_attach,
        .timeout_ms = 8000,
    };
    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) {
        ESP_LOGW(TAG, "Khong tao duoc http client cho %s", url);
        return ESP_FAIL;
    }

    esp_http_client_set_header(client, "Content-Type", "application/json");
    esp_http_client_set_header(client, "X-Gateway-Key", CONFIG_WIFI_MON_GATEWAY_KEY);
    esp_http_client_set_post_field(client, json_body, strlen(json_body));

    esp_err_t err = esp_http_client_perform(client);
    if (err == ESP_OK) {
        int status = esp_http_client_get_status_code(client);
        if (status < 200 || status >= 300) {
            ESP_LOGW(TAG, "POST %s -> HTTP %d", path, status);
        } else {
            ESP_LOGD(TAG, "POST %s -> HTTP %d", path, status);
        }
    } else {
        ESP_LOGW(TAG, "POST %s that bai: %s", path, esp_err_to_name(err));
    }

    esp_http_client_cleanup(client);
    return err;
}

esp_err_t wifi_report_post_sample(const char *device_id, int rssi,
                                   const char *ssid, int channel,
                                   const char *bssid, const int *noise_floor) {
    cJSON *root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "device_id", device_id);
    cJSON_AddNumberToObject(root, "rssi", rssi);
    if (ssid && ssid[0]) {
        cJSON_AddStringToObject(root, "ssid", ssid);
    }
    if (channel > 0) {
        cJSON_AddNumberToObject(root, "channel", channel);
    }
    cJSON_AddStringToObject(root, "band", WIFI_MON_BAND_STR);
    if (bssid && bssid[0]) {
        cJSON_AddStringToObject(root, "bssid", bssid);
    }
    if (noise_floor) {
        cJSON_AddNumberToObject(root, "noise_floor", *noise_floor);
    }

    char *body = cJSON_PrintUnformatted(root);
    esp_err_t err = _post_json("/api/wifi/report", body);

    cJSON_free(body);
    cJSON_Delete(root);
    return err;
}

esp_err_t wifi_report_post_event(const char *device_id, const char *event_type,
                                  const int *rssi, const int *consecutive_count,
                                  const int *outage_seconds) {
    cJSON *root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "device_id", device_id);
    cJSON_AddStringToObject(root, "event_type", event_type);
    if (rssi) {
        cJSON_AddNumberToObject(root, "rssi", *rssi);
    }
    if (consecutive_count) {
        cJSON_AddNumberToObject(root, "consecutive_count", *consecutive_count);
    }
    if (outage_seconds) {
        cJSON_AddNumberToObject(root, "outage_seconds", *outage_seconds);
    }

    char *body = cJSON_PrintUnformatted(root);
    ESP_LOGI(TAG, "Event %s: %s", event_type, body);
    esp_err_t err = _post_json("/api/wifi/alert", body);

    cJSON_free(body);
    cJSON_Delete(root);
    return err;
}

esp_err_t wifi_report_post_roam(const char *device_id, const char *old_bssid,
                                 const char *new_bssid, int rssi) {
    cJSON *root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "device_id", device_id);
    cJSON_AddStringToObject(root, "event_type", "roamed");
    cJSON_AddNumberToObject(root, "rssi", rssi);
    cJSON_AddStringToObject(root, "old_bssid", old_bssid);
    cJSON_AddStringToObject(root, "new_bssid", new_bssid);

    char *body = cJSON_PrintUnformatted(root);
    ESP_LOGI(TAG, "Event roamed: %s", body);
    esp_err_t err = _post_json("/api/wifi/alert", body);

    cJSON_free(body);
    cJSON_Delete(root);
    return err;
}
