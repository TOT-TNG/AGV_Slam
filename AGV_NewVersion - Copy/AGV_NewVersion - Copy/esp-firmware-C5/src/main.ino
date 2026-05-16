/*
  ESP32-C5 Firmware — AGV MQTT Bridge (VDA5050 v2.0.0)
  =====================================================
  Platform : ESP32-C5 (RISC-V) — pioarduino / ESP-IDF 5.5.x
  Role     : Bridge MQTT ↔ UART1 (Arduino Mega)

  Topics (VDA5050 §5.2):
    PUB  uagv/v2/{FACTORY}/{AGV_ID}/state          — Arduino → FMS
    PUB  uagv/v2/{FACTORY}/{AGV_ID}/connection     — Last Will / ONLINE
    PUB  uagv/v2/{FACTORY}/{AGV_ID}/factsheet      — retain=true
    SUB  uagv/v2/{FACTORY}/{AGV_ID}/order          — FMS → Arduino (plan)
    SUB  uagv/v2/{FACTORY}/{AGV_ID}/instantActions — FMS → Arduino (cmd)

  KHÔNG dùng:
    - WebServer / ESPmDNS / HTTPUpdateServer  (crash trên C5)
    - configTime() / SNTP  (tạo UDP socket từ sai FreeRTOS task
      → assert crash ESP-IDF 5.x: udp_new_ip_type thiếu TCPIP lock)
  Timestamp dùng millis() thay thế (NTP không cần thiết cho bridge).

  TLS (port 8883): dùng WiFiClientSecure + setInsecure().
  Root cause crash trước = configTime() chứ không phải TLS.
*/

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>  // TLS port 8883 — OK khi không dùng configTime()
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <HardwareSerial.h>

// ============================================================
// Cấu hình WiFi
// ============================================================
const char* WIFI_SSID = "TNG";
const char* WIFI_PASS = "BK#204078";

IPAddress STATIC_IP(192, 168, 0, 191);
IPAddress GATEWAY  (192, 168, 0,   1);
IPAddress SUBNET   (255, 255, 255, 0);
IPAddress DNS1     (192, 168, 0,   1);   // Primary: router
IPAddress DNS2     (  8,   8, 8,   8);   // Fallback: Google DNS — cần cho hostname public

// ============================================================
// Cấu hình MQTT — TLS port 8883
// ============================================================
const char* MQTT_HOST = "iot.tot360.com.vn";
const int   MQTT_PORT = 8883;
const char* MQTT_USER = "iot_user";
const char* MQTT_PASS = "d7xvk5pKkqsKKMd";

// ============================================================
// Cấu hình AGV (VDA5050)
// ============================================================
#define AGV_ID      "AGV01"
#define FACTORY     "VietDuc"
#define VDA_VERSION "2.0.0"

// ============================================================
// UART tới Arduino Mega — ESP32-C5: UART1, GPIO4=RX, GPIO5=TX
// ============================================================
HardwareSerial ArduinoUART(1);
#define UART_RX   4
#define UART_TX   5
#define UART_BAUD 115200

// ============================================================
// Biến toàn cục
// ============================================================
WiFiClientSecure tlsClient;
PubSubClient     mqttClient(tlsClient);

char topicState  [80];
char topicOrder  [80];
char topicInstant[80];
char topicConn   [80];
char topicFact   [80];

String   macStr;
uint32_t headerSeq = 0;

// UART non-blocking accumulator
String uartBuf = "";

// MQTT reconnect timer
static unsigned long lastReconnectMs  = 0;
static const unsigned long RECONNECT_MS = 8000;

// ============================================================
// Timestamp bằng millis() — không dùng NTP/configTime()
// configTime() gọi SNTP → tạo UDP socket từ Arduino task
// → assert crash trên ESP-IDF 5.x (thiếu TCPIP core lock)
// ============================================================
void buildTimestamp(char* buf, size_t len) {
  unsigned long ms = millis();
  unsigned long s  = ms / 1000;
  unsigned long h  = s / 3600;
  unsigned long m  = (s % 3600) / 60;
  unsigned long ss = s % 60;
  snprintf(buf, len, "1970-01-01T%02lu:%02lu:%02lu.%03luZ",
           h % 24, m, ss, ms % 1000);
}

// ============================================================
// VDA5050 header
// ============================================================
void addVdaHeader(JsonDocument& doc) {
  char ts[32];
  buildTimestamp(ts, sizeof(ts));
  doc["headerId"]     = headerSeq++;
  doc["timestamp"]    = ts;
  doc["version"]      = VDA_VERSION;
  doc["manufacturer"] = FACTORY;
  doc["serialNumber"] = AGV_ID;
}

// ============================================================
// Build topic strings
// ============================================================
void buildTopics() {
  snprintf(topicState,   sizeof(topicState),   "uagv/v2/%s/%s/state",          FACTORY, AGV_ID);
  snprintf(topicOrder,   sizeof(topicOrder),   "uagv/v2/%s/%s/order",          FACTORY, AGV_ID);
  snprintf(topicInstant, sizeof(topicInstant), "uagv/v2/%s/%s/instantActions", FACTORY, AGV_ID);
  snprintf(topicConn,    sizeof(topicConn),    "uagv/v2/%s/%s/connection",      FACTORY, AGV_ID);
  snprintf(topicFact,    sizeof(topicFact),    "uagv/v2/%s/%s/factsheet",       FACTORY, AGV_ID);

  Serial.println(F("[Topics]"));
  Serial.print(F("  state:   ")); Serial.println(topicState);
  Serial.print(F("  order:   ")); Serial.println(topicOrder);
  Serial.print(F("  instant: ")); Serial.println(topicInstant);
  Serial.print(F("  conn:    ")); Serial.println(topicConn);
}

// ============================================================
// Publish factsheet (retain=true)
// ============================================================
void publishFactsheet() {
  StaticJsonDocument<512> doc;
  addVdaHeader(doc);
  doc["agvClass"]              = "CARRIER";
  doc["maxLoadMass"]           = 500;
  doc["maxSpeed"]              = 1.5;
  doc["localizationType"]      = "RFID";
  doc["navigationMode"]        = "GUIDED";
  doc["batteryStateAvailable"] = true;
  doc["positionControlMode"]   = "NONE";
  char buf[512];
  serializeJson(doc, buf);
  mqttClient.publish(topicFact, buf, true);
  Serial.println(F("[MQTT] Factsheet published"));
}

// ============================================================
// Publish ONLINE (retain=true)
// ============================================================
void publishOnline() {
  StaticJsonDocument<256> doc;
  addVdaHeader(doc);
  doc["connectionState"] = "ONLINE";
  char buf[256];
  serializeJson(doc, buf);
  mqttClient.publish(topicConn, buf, true);
  Serial.println(F("[MQTT] Connection ONLINE"));
}

// ============================================================
// MQTT callback: FMS → Arduino UART
// ============================================================
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  Serial.print(F("[MQTT→UART] ")); Serial.print(topic);
  Serial.print(F(" len=")); Serial.println(length);

  DynamicJsonDocument doc(2048);
  String msg;
  msg.reserve(length);
  for (unsigned int i = 0; i < length; i++) msg += (char)payload[i];

  DeserializationError err = deserializeJson(doc, msg);
  if (!err) {
    serializeJson(doc, ArduinoUART);
    ArduinoUART.println();
  } else {
    Serial.print(F("[MQTT] JSON err: ")); Serial.println(err.c_str());
    ArduinoUART.println(msg);  // Forward raw — Arduino tự xử lý
  }
}

// ============================================================
// WiFi: kết nối blocking (chỉ gọi trong setup + mất WiFi)
// ============================================================
void connectWifi() {
  Serial.print(F("\n[WiFi] Connecting: ")); Serial.println(WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.config(STATIC_IP, GATEWAY, SUBNET, DNS1, DNS2);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print('.');
    if (millis() - t0 > 20000) {
      Serial.println(F("\n[WiFi] Timeout, retry..."));
      WiFi.disconnect(true);
      delay(500);
      WiFi.begin(WIFI_SSID, WIFI_PASS);
      t0 = millis();
    }
  }

  macStr = WiFi.macAddress();
  macStr.replace(":", "");
  Serial.println();
  Serial.print(F("[WiFi] OK  IP=")); Serial.print(WiFi.localIP());
  Serial.print(F("  MAC=")); Serial.println(macStr);
  // KHÔNG gọi configTime() — gây crash assert lwIP trên ESP-IDF 5.x
}

// ============================================================
// MQTT reconnect non-blocking (không delay)
// ============================================================
bool mqttReconnect() {
  if (mqttClient.connected()) return false;

  unsigned long now = millis();
  if (now - lastReconnectMs < RECONNECT_MS) return false;
  lastReconnectMs = now;

  Serial.print(F("[MQTT] Connecting ")); Serial.print(MQTT_HOST);
  Serial.print(':'); Serial.println(MQTT_PORT);

  // Last Will payload
  StaticJsonDocument<256> lwDoc;
  char lwTs[32]; buildTimestamp(lwTs, sizeof(lwTs));
  lwDoc["headerId"]        = 0;
  lwDoc["timestamp"]       = lwTs;
  lwDoc["version"]         = VDA_VERSION;
  lwDoc["manufacturer"]    = FACTORY;
  lwDoc["serialNumber"]    = AGV_ID;
  lwDoc["connectionState"] = "CONNECTIONBROKEN";
  char lwBuf[256];
  serializeJson(lwDoc, lwBuf);

  String cid = String("AGV_") + AGV_ID + "_" + String(millis(), HEX);
  bool ok = mqttClient.connect(cid.c_str(), MQTT_USER, MQTT_PASS,
                                topicConn, 1, true, lwBuf);
  if (ok) {
    Serial.println(F("[MQTT] Connected!"));
    publishOnline();
    mqttClient.subscribe(topicOrder);
    mqttClient.subscribe(topicInstant);
    Serial.print(F("[MQTT] SUB: ")); Serial.println(topicOrder);
    Serial.print(F("[MQTT] SUB: ")); Serial.println(topicInstant);
    publishFactsheet();
  } else {
    Serial.print(F("[MQTT] Failed rc=")); Serial.println(mqttClient.state());
  }
  return ok;
}

// ============================================================
// Xử lý 1 dòng hoàn chỉnh từ Arduino
// ============================================================
void handleUartLine(const String& line) {
  if (line.length() == 0) return;
  if (line[0] != '{') {
    Serial.print(F("[UART] skip: ")); Serial.println(line.substring(0, 32));
    return;
  }

  DynamicJsonDocument doc(1500);
  DeserializationError err = deserializeJson(doc, line);
  if (err) {
    Serial.print(F("[UART] JSON err: ")); Serial.println(err.c_str());
    return;
  }

  // ── Ping/pong handshake ────────────────────────────────────────────────────
  // Arduino gửi {"c":"ping"} lúc khởi động để kiểm tra UART
  const char* cmd = doc["c"] | "";
  if (strcmp(cmd, "ping") == 0) {
    ArduinoUART.println(F("{\"c\":\"pong\"}"));
    Serial.println(F("[UART] Ping ← Arduino | Pong → Arduino (UART OK)"));
    return;  // Không forward lên MQTT
  }

  addVdaHeader(doc);
  doc["rssi"] = WiFi.RSSI();
  doc["mac"]  = macStr;

  char buf[1500];
  size_t n = serializeJson(doc, buf);
  if (mqttClient.connected()) {
    if (!mqttClient.publish(topicState, buf, n)) {
      Serial.println(F("[MQTT] publish fail"));
    }
  }
}

// ============================================================
// SETUP
// ============================================================
void setup() {
  Serial.begin(115200);
  delay(1500);
  Serial.println(F("\n====== ESP32-C5 AGV Bridge ======"));
  Serial.print(F("Chip: ")); Serial.print(ESP.getChipModel());
  Serial.print(F("  CPU: ")); Serial.print(ESP.getCpuFreqMHz());
  Serial.print(F("MHz  Heap: ")); Serial.println(ESP.getFreeHeap());

  ArduinoUART.begin(UART_BAUD, SERIAL_8N1, UART_RX, UART_TX);
  uartBuf.reserve(1600);
  Serial.print(F("[UART] RX=")); Serial.print(UART_RX);
  Serial.print(F(" TX=")); Serial.println(UART_TX);

  buildTopics();
  connectWifi();

  tlsClient.setInsecure();   // Bỏ qua cert validation (broker nội bộ)
  mqttClient.setServer(MQTT_HOST, MQTT_PORT);
  mqttClient.setCallback(mqttCallback);
  mqttClient.setBufferSize(2048);
  mqttClient.setKeepAlive(60);

  Serial.println(F("[Setup] Done"));
}

// ============================================================
// LOOP
// ============================================================
void loop() {
  // WiFi watchdog
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println(F("[WiFi] Lost!"));
    connectWifi();
    lastReconnectMs = 0;
    return;
  }

  // MQTT
  if (mqttClient.connected()) {
    mqttClient.loop();
  } else {
    mqttReconnect();
  }

  // UART non-blocking accumulator
  while (ArduinoUART.available()) {
    char c = (char)ArduinoUART.read();
    if (c == '\n') {
      uartBuf.trim();
      handleUartLine(uartBuf);
      uartBuf = "";
    } else if (c != '\r') {
      uartBuf += c;
      if (uartBuf.length() > 1550) {
        Serial.println(F("[UART] overflow"));
        uartBuf = "";
      }
    }
  }
}
