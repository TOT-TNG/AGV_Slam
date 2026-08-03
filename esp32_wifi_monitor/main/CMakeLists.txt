idf_component_register(
    SRCS "main.c" "wifi_monitor.c" "http_report.c"
    INCLUDE_DIRS "."
    REQUIRES esp_wifi esp_event esp_netif nvs_flash esp_http_client esp-tls json
)
