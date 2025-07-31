// ✅ 측정 가능 릴레이: R1 (A0,A1), R2 (A2,A3)
// ✅ 릴레이 명령은 기존과 동일하게 처리함

#include <SoftwareSerial.h>
#include <WiFiEsp.h>
#include <WiFiEspClient.h>
#include <ArduinoHttpClient.h>
#include <ArduinoJson.h>

char ssid[] = "spreatics_eungam_cctv";
char password[] = "spreatics*";
char server[] = "52.63.106.255";
int port = 5001;

SoftwareSerial espSerial(2, 3); // RX, TX
WiFiEspClient client;
HttpClient http(client, server, port);

const int relayPins[5] = {4, 5, 6, 7, 8}; // 릴레이 핀

#define LED1_V1 A0
#define LED1_V2 A1
#define LED2_V1 A2
#define LED2_V2 A3
float resistance1 = 330.0;
float resistance2 = 330.0;

unsigned long lastPostTime = 0;

void setup() {
  Serial.begin(9600);
  espSerial.begin(9600);
  WiFi.init(&espSerial);

  for (int i = 0; i < 5; i++) {
    pinMode(relayPins[i], OUTPUT);
    digitalWrite(relayPins[i], LOW);
  }

  while (WiFi.status() != WL_CONNECTED) {
    Serial.println("📡 WiFi 연결 시도 중...");
    WiFi.begin(ssid, password);
    delay(3000);
  }
  Serial.println("✅ WiFi 연결 완료");
}

void loop() {
  unsigned long now = millis();
  fetchRelayStatus();

  float i1 = measureCurrent(LED1_V1, LED1_V2, resistance1);
  float i2 = measureCurrent(LED2_V1, LED2_V2, resistance2);
  float p1 = (i1 / 1000.0) * 5.0;
  float p2 = (i2 / 1000.0) * 5.0;

  Serial.print("LED1 전력: "); Serial.print(p1, 3); Serial.println(" W");
  Serial.print("LED2 전력: "); Serial.print(p2, 3); Serial.println(" W");

  if (now - lastPostTime >= 20000) {
    lastPostTime = now;
    sendStatus(1, p1, nullptr); 
    sendStatus(2, p2, nullptr);
  }

  delay(500);
}

void fetchRelayStatus() {
  Serial.println("서버에서 명령어 받아오는 중...");
  http.get("/serv_ardu/command");

  int statusCode = http.responseStatusCode();
  if (statusCode != 200) {
    Serial.print("응답 오류: ");
    Serial.println(statusCode);
    http.stop(); client.stop();
    return;
  }

  http.skipResponseHeaders();
  DynamicJsonDocument doc(768);
  DeserializationError error = deserializeJson(doc, http);
  if (error) {
    Serial.print("JSON 파싱 실패: ");
    Serial.println(error.c_str());
    http.stop(); client.stop();
    return;
  }

  JsonArray commands = doc["commands"];
  for (JsonObject cmd : commands) {
    int id = cmd["relay_id"];
    int status = cmd["status"];

    if (id >= 1 && id <= 5) {
      digitalWrite(relayPins[id - 1], status == 1 ? LOW : HIGH);
      Serial.print("릴레이 ");
      Serial.print(id);
      Serial.print(" → ");
      Serial.println(status == 1 ? "ON" : "OFF");
    }
  }
  http.stop(); client.stop();
}

float measureCurrent(int pinV1, int pinV2, float R) {
  float V1 = analogRead(pinV1) * (5.0 / 1023.0);
  float V2 = analogRead(pinV2) * (5.0 / 1023.0);
  float Vdiff = V1 - V2;
  return (Vdiff / R) * 1000.0;  // mA
}

void sendStatus(int relay_id, float power_kw, float* soc) {
  DynamicJsonDocument doc(256);
  doc["relay_id"] = relay_id;
  doc["power_kw"] = power_kw;
  if (soc != nullptr) doc["soc"] = *soc;
  else doc["soc"] = nullptr;

  String requestBody;
  serializeJson(doc, requestBody);

  http.beginRequest();
  http.post("/ardu_serv/node_status");
  http.sendHeader("Content-Type", "application/json");
  http.sendHeader("Content-Length", requestBody.length());
  http.beginBody();
  http.print(requestBody);
  http.endRequest();

  int statusCode = http.responseStatusCode();
  Serial.print("📤 POST status code: ");
  Serial.println(statusCode);
  http.skipResponseHeaders();
  http.stop(); client.stop();
}

