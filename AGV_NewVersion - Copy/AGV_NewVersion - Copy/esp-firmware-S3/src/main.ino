/*
  ESP32-S3 Firmware for AGV System — VDA5050 v2.0.0 Compliant MQTT Bridge
  Hardware: ESP32-S3 DevKitC-1
  Role   : Bridge MQTT ↔ UART (Arduino Mega)

  So sánh S3 vs C5:
    S3: Serial2 (RX=GPIO18, TX=GPIO17), không dùng HardwareSerial(1)
    C5: HardwareSerial(1) (RX=GPIO4,  TX=GPIO5)

  Topic Structure (VDA5050 §5.2):
    PUB  uagv/v2/{FACTORY}/{AGV_ID}/state           — AGV → FMS (trạng thái)
    PUB  uagv/v2/{FACTORY}/{AGV_ID}/connection       — AGV → FMS (kết nối, Last Will)
    PUB  uagv/v2/{FACTORY}/{AGV_ID}/factsheet        — AGV → FMS (thông số, retain)
    SUB  uagv/v2/{FACTORY}/{AGV_ID}/order            — FMS → AGV (lộ trình plan)
    SUB  uagv/v2/{FACTORY}/{AGV_ID}/instantActions   — FMS → AGV (lệnh tức thì)
*/

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <WebServer.h>
#include <ESPmDNS.h>
#include <HTTPUpdateServer.h>
#include <time.h>

// ============================================================
// --- Cấu hình WiFi ---
// ============================================================
const char* ssid     = "TNG";
const char* password = "BK#204078";

// IP tĩnh (xóa WiFi.config() nếu muốn dùng DHCP)
// IPAddress staticIP(192, 168, 0, 191);
// IPAddress gateway (192, 168, 0,   1);
// IPAddress subnet  (255, 255, 255, 0);
// IPAddress dns1    (192, 168, 0,   1);

// ============================================================
// --- Cấu hình MQTT Broker ---
// ============================================================
const char* mqtt_server = "iot.tot360.com.vn";
const int   mqtt_port   = 8883;
const char* mqtt_user   = "iot_user";
const char* mqtt_pass   = "d7xvk5pKkqsKKMd";

// ============================================================
// --- Cấu hình AGV & Nhà máy (VDA5050: manufacturer / serialNumber) ---
// ============================================================
#define AGV_ID      "AGV01"          // serialNumber VDA5050
#define FACTORY     "VietDuc"        // manufacturer  VDA5050
#define HARDWARE    "hardware2603"   // Nội bộ (không dùng trong topic VDA5050)
#define VDA_VERSION "2.0.0"

// ============================================================
// --- Topic VDA5050 (xây dựng trong build_topics()) ---
// ============================================================
char topic_state  [128];  // uagv/v2/{FACTORY}/{AGV_ID}/state
char topic_order  [128];  // uagv/v2/{FACTORY}/{AGV_ID}/order
char topic_instant[128];  // uagv/v2/{FACTORY}/{AGV_ID}/instantActions
char topic_conn   [128];  // uagv/v2/{FACTORY}/{AGV_ID}/connection
char topic_fact   [128];  // uagv/v2/{FACTORY}/{AGV_ID}/factsheet
String mac_str;

// ============================================================
// --- Biến đếm header VDA5050 ---
// ============================================================
uint32_t stateHeaderId = 0;

// ============================================================
// --- Cấu hình UART giao tiếp Arduino Mega ---
// ESP32-S3: Serial2 (RX=GPIO18, TX=GPIO17)
// ============================================================
#define UART_MEGA  Serial2
#define RX_PIN     18
#define TX_PIN     17
#define BAUD_RATE  115200

WiFiClientSecure espClient;
PubSubClient     client(espClient);
WebServer        webServer(80);
HTTPUpdateServer httpUpdater;

// ============================================================
// --- Lấy timestamp ISO8601 từ NTP (VDA5050 §5.3) ---
// ============================================================
void getTimestamp(char* buf, size_t len) {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo, 100)) {
    unsigned long ms = millis();
    snprintf(buf, len, "1970-01-01T00:00:%02lu.%03luZ", (ms / 1000) % 60, ms % 1000);
    return;
  }
  snprintf(buf, len, "%04d-%02d-%02dT%02d:%02d:%02d.000Z",
           timeinfo.tm_year + 1900, timeinfo.tm_mon + 1, timeinfo.tm_mday,
           timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec);
}

// ============================================================
// --- Thêm VDA5050 mandatory header vào JSON doc ---
// ============================================================
void addVdaHeader(JsonDocument& doc) {
  char ts[32];
  getTimestamp(ts, sizeof(ts));
  doc["headerId"]     = stateHeaderId++;
  doc["timestamp"]    = ts;
  doc["version"]      = VDA_VERSION;
  doc["manufacturer"] = FACTORY;
  doc["serialNumber"] = AGV_ID;
}

// ============================================================
// --- Callback: nhận lệnh MQTT (order / instantActions) → UART Arduino ---
// ============================================================
void callback(char* topic, byte* payload, unsigned int length) {
  Serial.print(F("[MQTT→UART] topic=")); Serial.print(topic);
  Serial.print(F("  len=")); Serial.println(length);

  // Parse để validate, rồi forward xuống Arduino
  StaticJsonDocument<1024> doc;
  DeserializationError err = deserializeJson(doc, payload, length);
  if (!err) {
    serializeJson(doc, UART_MEGA);
    UART_MEGA.println();
  } else {
    Serial.print(F("[MQTT] JSON parse error: ")); Serial.println(err.c_str());
  }
}

// ============================================================
// --- Kết nối WiFi ---
// ============================================================
void setup_wifi() {
  Serial.print(F("Connecting to WiFi: ")); Serial.println(ssid);
  // WiFi.config(staticIP, gateway, subnet, dns1);  // Bỏ comment để dùng IP tĩnh
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println();
  Serial.print(F("WiFi connected. IP: ")); Serial.println(WiFi.localIP());
  mac_str = WiFi.macAddress();
  mac_str.replace(":", "");
  Serial.print(F("MAC: ")); Serial.println(mac_str);
  // Đồng bộ thời gian NTP (UTC+7)
  configTime(7 * 3600, 0, "pool.ntp.org", "time.nist.gov");
  Serial.println(F("NTP sync requested..."));
}

// ============================================================
// --- Xây dựng topic VDA5050 ---
// ============================================================
void build_topics() {
  snprintf(topic_state,   sizeof(topic_state),   "uagv/v2/%s/%s/state",          FACTORY, AGV_ID);
  snprintf(topic_order,   sizeof(topic_order),   "uagv/v2/%s/%s/order",          FACTORY, AGV_ID);
  snprintf(topic_instant, sizeof(topic_instant), "uagv/v2/%s/%s/instantActions", FACTORY, AGV_ID);
  snprintf(topic_conn,    sizeof(topic_conn),    "uagv/v2/%s/%s/connection",      FACTORY, AGV_ID);
  snprintf(topic_fact,    sizeof(topic_fact),    "uagv/v2/%s/%s/factsheet",       FACTORY, AGV_ID);
  Serial.print(F("[Topic] state:   ")); Serial.println(topic_state);
  Serial.print(F("[Topic] order:   ")); Serial.println(topic_order);
  Serial.print(F("[Topic] instant: ")); Serial.println(topic_instant);
  Serial.print(F("[Topic] conn:    ")); Serial.println(topic_conn);
  Serial.print(F("[Topic] fact:    ")); Serial.println(topic_fact);
}

// ============================================================
// --- Publish Factsheet (VDA5050 §6.10) — retain=true ---
// ============================================================
void publishFactsheet() {
  StaticJsonDocument<512> fsDoc;
  addVdaHeader(fsDoc);
  fsDoc["agvClass"]              = "CARRIER";
  fsDoc["maxLoadMass"]           = 500;
  fsDoc["maxSpeed"]              = 1.5;
  fsDoc["maxRotationSpeed"]      = 0.5;
  fsDoc["localizationType"]      = "RFID";
  fsDoc["navigationMode"]        = "GUIDED";
  fsDoc["batteryStateAvailable"] = false;
  fsDoc["positionControlMode"]   = "NONE";
  JsonObject dims = fsDoc.createNestedObject("agvGeometry");
  dims["width"]  = 0.6;
  dims["length"] = 1.2;
  char fsBuf[512];
  serializeJson(fsDoc, fsBuf);
  client.publish(topic_fact, fsBuf, true);
  Serial.println(F("[VDA] Factsheet published."));
}

// ============================================================
// --- Kết nối lại MQTT (với Last Will VDA5050) ---
// ============================================================
void reconnect() {
  while (!client.connected()) {
    String cid = "AGV_S3_" + String(AGV_ID) + "_" + String(random(0xffff), HEX);

    // Last Will: connectionState = CONNECTIONBROKEN (VDA5050 §6.11)
    StaticJsonDocument<256> lwDoc;
    char lwTs[32]; getTimestamp(lwTs, sizeof(lwTs));
    lwDoc["headerId"]        = 0;
    lwDoc["timestamp"]       = lwTs;
    lwDoc["version"]         = VDA_VERSION;
    lwDoc["manufacturer"]    = FACTORY;
    lwDoc["serialNumber"]    = AGV_ID;
    lwDoc["connectionState"] = "CONNECTIONBROKEN";
    char lwBuf[256];
    serializeJson(lwDoc, lwBuf);

    Serial.print(F("Attempting MQTT connection..."));
    bool ok = (strlen(mqtt_user) > 0)
              ? client.connect(cid.c_str(), mqtt_user, mqtt_pass,
                               topic_conn, 1, true, lwBuf)
              : client.connect(cid.c_str(), nullptr, nullptr,
                               topic_conn, 1, true, lwBuf);

    if (ok) {
      Serial.println(F("connected"));

      // Publish ONLINE — retain=true
      StaticJsonDocument<256> connDoc;
      addVdaHeader(connDoc);
      connDoc["connectionState"] = "ONLINE";
      char connBuf[256];
      serializeJson(connDoc, connBuf);
      client.publish(topic_conn, connBuf, true);
      Serial.println(F("[VDA] Connection ONLINE published."));

      client.subscribe(topic_order);
      client.subscribe(topic_instant);
      Serial.print(F("Subscribed: ")); Serial.println(topic_order);
      Serial.print(F("Subscribed: ")); Serial.println(topic_instant);

      publishFactsheet();
    } else {
      Serial.print(F("failed, rc="));
      Serial.print(client.state());
      Serial.println(F(" — retry in 5s"));
      delay(5000);
    }
  }
}

// ============================================================
// --- Setup ---
// ============================================================
void setup() {
  Serial.begin(115200);
  UART_MEGA.begin(BAUD_RATE, SERIAL_8N1, RX_PIN, TX_PIN);

  setup_wifi();
  build_topics();

  espClient.setInsecure();
  espClient.setTimeout(15);

  MDNS.begin("esp32s3-" AGV_ID);
  httpUpdater.setup(&webServer, "/update", "admin", "admin");
  webServer.begin();

  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
  client.setBufferSize(1200);
  client.setKeepAlive(60);
}

// ============================================================
// --- Loop ---
// ============================================================
void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    setup_wifi();
    build_topics();
  }
  if (!client.connected()) reconnect();
  client.loop();
  webServer.handleClient();

  // Đọc trạng thái từ Arduino → thêm VDA5050 headers + RSSI/MAC → publish state
  if (UART_MEGA.available()) {
    String line = UART_MEGA.readStringUntil('\n');
    line.trim();
    if (line.length() > 0) {
      StaticJsonDocument<1200> doc;
      DeserializationError err = deserializeJson(doc, line);
      if (!err) {
        addVdaHeader(doc);
        doc["rssi"] = WiFi.RSSI();
        doc["mac"]  = mac_str;
        char buffer[1200];
        serializeJson(doc, buffer);
        bool ok = client.publish(topic_state, buffer);
        Serial.print(F("[MQTT] state publish ")); Serial.println(ok ? "OK" : "FAILED");
      } else {
        Serial.print(F("[JSON] parse error: ")); Serial.println(err.c_str());
      }
    }
  }
}
