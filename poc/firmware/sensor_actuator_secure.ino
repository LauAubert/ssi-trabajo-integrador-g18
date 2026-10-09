/*
 * SSI - TP Seguridad en IoT/IIoT - Grupo 18
 * ------------------------------------------------------------
 * VERSION ENDURECIDA del nodo ESP32 (fase de MITIGACION).
 *
 * Es igual que sensor_actuator.ino pero se conecta al broker de forma
 * segura, cerrando las vulnerabilidades que mostramos en la demo:
 *
 *   1. TLS (puerto 8883)        -> el trafico deja de viajar en claro;
 *                                  el sniffer ya no lee los payloads.
 *   2. Autenticacion usuario/pass -> el broker rechaza anonimos; un
 *                                  atacante sin credenciales no entra.
 *   3. Validacion del broker con la CA -> el ESP32 verifica que habla
 *                                  con NUESTRO broker (no un impostor).
 *
 * Requisitos nuevos respecto de la version insegura:
 *   - Broker levantado con mosquitto-secure.conf (TLS + passwd + ACL).
 *   - Usuario "esp32" creado con mosquitto_passwd (ver mitigations/).
 *   - Pegar el contenido de broker/certs/ca.crt en CA_CERT (abajo).
 *   - Hora valida por NTP: TLS valida la vigencia del certificado, y
 *     sin hora correcta la conexion FALLA. Por eso sincronizamos NTP
 *     antes de conectar (necesita salida a internet en la red de lab).
 *
 * El pinout, los topics y la logica de sensor/actuador son identicos
 * a la version insegura.
 */

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ESP32Servo.h>
#include <time.h>

// ----------------------------------------------------------------
// Configuracion
// ----------------------------------------------------------------
const char* WIFI_SSID = "TU_RED_DE_LAB";
const char* WIFI_PASS = "TU_PASSWORD";

const char* MQTT_HOST = "192.168.1.100";   // IP/host del broker (igual al CN/SAN del cert)
const int   MQTT_PORT = 8883;              // 8883 = MQTT sobre TLS
const char* MQTT_CLIENT = "esp32-linea-A";

// Credenciales creadas con mosquitto_passwd (ver mitigations/README.md)
const char* MQTT_USER = "esp32";
const char* MQTT_PASS = "CAMBIAR_POR_TU_PASSWORD";

// Topics
const char* TOPIC_NIVEL  = "planta/lineaA/tanque1/nivel";
const char* TOPIC_CMD    = "planta/lineaA/valvula1/cmd";
const char* TOPIC_ESTADO = "planta/lineaA/valvula1/estado";

// Pines (misma hilera libre que la version insegura)
const int PIN_TRIG   = 13;
const int PIN_ECHO   = 34;   // solo-entrada
const int PIN_SERVO  = 14;
const int PIN_LED    = 27;
const int PIN_BUZZER = 26;

const float NIVEL_MIN_CM = 5.0;
const float NIVEL_MAX_CM = 40.0;
const unsigned long SAMPLE_MS = 2000;

// ----------------------------------------------------------------
// Certificado de la CA de laboratorio.
// Pegar aca el contenido COMPLETO de broker/certs/ca.crt, incluidas
// las lineas -----BEGIN CERTIFICATE----- / -----END CERTIFICATE-----
// (lo genera mitigations/gen-certs.sh).
// ----------------------------------------------------------------
const char* CA_CERT = R"EOF(
-----BEGIN CERTIFICATE-----
PEGAR_AQUI_EL_CONTENIDO_DE_ca.crt
-----END CERTIFICATE-----
)EOF";

WiFiClientSecure net;
PubSubClient     mqtt(net);
Servo            valvula;

unsigned long lastSample = 0;

// ----------------------------------------------------------------
void conectarWiFi() {
  Serial.printf("[WiFi] Conectando a %s ...\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }
  Serial.printf("\n[WiFi] OK - IP: %s\n", WiFi.localIP().toString().c_str());
}

// TLS valida la vigencia del certificado -> necesitamos hora real.
void sincronizarHora() {
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  Serial.print("[TLS] Sincronizando hora por NTP");
  time_t now = time(nullptr);
  while (now < 1700000000) {        // ~nov 2023; esperamos hora valida
    delay(300);
    Serial.print(".");
    now = time(nullptr);
  }
  Serial.printf("\n[TLS] Hora OK (%ld)\n", (long)now);
}

void aplicarComando(const String& cmd) {
  Serial.printf("[CMD] Recibido: %s\n", cmd.c_str());
  if (cmd == "ABRIR") {
    valvula.write(90);
    digitalWrite(PIN_LED, HIGH);
    mqtt.publish(TOPIC_ESTADO, "ABIERTA", true);
  } else if (cmd == "CERRAR") {
    valvula.write(0);
    digitalWrite(PIN_LED, LOW);
    mqtt.publish(TOPIC_ESTADO, "CERRADA", true);
  } else if (cmd == "ALARMA") {
    for (int i = 0; i < 3; i++) {
      digitalWrite(PIN_BUZZER, HIGH); delay(200);
      digitalWrite(PIN_BUZZER, LOW);  delay(200);
    }
    mqtt.publish(TOPIC_ESTADO, "ALARMA", true);
  } else {
    Serial.println("[CMD] Comando desconocido (ignorado)");
  }
}

void onMessage(char* topic, byte* payload, unsigned int len) {
  String msg;
  for (unsigned int i = 0; i < len; i++) msg += (char)payload[i];
  if (String(topic) == TOPIC_CMD) aplicarComando(msg);
}

void conectarMQTT() {
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMessage);
  while (!mqtt.connected()) {
    Serial.print("[MQTT] Conectando (TLS)... ");
    // Ahora con usuario y password: el broker ya no acepta anonimos.
    if (mqtt.connect(MQTT_CLIENT, MQTT_USER, MQTT_PASS)) {
      Serial.println("OK");
      mqtt.subscribe(TOPIC_CMD);
      mqtt.publish(TOPIC_ESTADO, "ONLINE", true);
    } else {
      Serial.printf("fallo rc=%d, reintento en 2s\n", mqtt.state());
      delay(2000);
    }
  }
}

float leerDistanciaCruda() {
  digitalWrite(PIN_TRIG, LOW);  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  long dur = pulseIn(PIN_ECHO, HIGH, 30000UL);
  if (dur == 0) return NIVEL_MAX_CM;
  return dur * 0.0343 / 2.0;
}

// Mediana de N lecturas: filtra picos espurios del HC-SR04.
float leerDistanciaCm() {
  const int N = 5;
  float m[N];
  for (int i = 0; i < N; i++) { m[i] = leerDistanciaCruda(); delay(40); }
  for (int i = 1; i < N; i++) {
    float k = m[i]; int j = i - 1;
    while (j >= 0 && m[j] > k) { m[j + 1] = m[j]; j--; }
    m[j + 1] = k;
  }
  return m[N / 2];
}

int nivelPorcentaje(float cm) {
  if (cm <= NIVEL_MIN_CM) return 100;
  if (cm >= NIVEL_MAX_CM) return 0;
  return (int)((NIVEL_MAX_CM - cm) / (NIVEL_MAX_CM - NIVEL_MIN_CM) * 100.0);
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  pinMode(PIN_LED, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  valvula.attach(PIN_SERVO);
  valvula.write(0);

  conectarWiFi();
  sincronizarHora();          // imprescindible para validar el cert TLS
  net.setCACert(CA_CERT);     // confiar solo en NUESTRA CA
  conectarMQTT();
}

void loop() {
  if (!mqtt.connected()) conectarMQTT();
  mqtt.loop();

  unsigned long now = millis();
  if (now - lastSample >= SAMPLE_MS) {
    lastSample = now;
    float cm = leerDistanciaCm();
    int pct = nivelPorcentaje(cm);
    char payload[96];
    snprintf(payload, sizeof(payload),
             "{\"nivel\":%d,\"cm\":%.1f,\"ts\":%lu}", pct, cm, now);
    mqtt.publish(TOPIC_NIVEL, payload);
    Serial.printf("[PUB] %s -> %s\n", TOPIC_NIVEL, payload);
  }
}
