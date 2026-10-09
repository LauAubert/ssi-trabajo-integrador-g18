/*
 * SSI - TP Seguridad en IoT/IIoT - Grupo 18
 * ------------------------------------------------------------
 * Firmware ESP32 que simula un nodo industrial (IIoT):
 *
 *   - SENSOR: mide distancia con un HC-SR04 (ultrasonido) y la
 *     reporta como "nivel de un tanque" (ej: materia prima en una
 *     linea de produccion). Publica por MQTT cada SAMPLE_MS.
 *
 *   - ACTUADOR: se suscribe a un topic de comandos y acciona
 *     una valvula simulada con un servo, un LED de estado y un
 *     buzzer de alarma segun el comando recibido.
 *
 * Objetivo didactico (TP de seguridad):
 *   Este firmware usa MQTT EN TEXTO PLANO, SIN TLS Y SIN
 *   AUTENTICACION, a proposito, para poder demostrar en un
 *   laboratorio cerrado y propio como un atacante en la misma
 *   red puede leer e inyectar mensajes. La version endurecida
 *   (TLS + usuario/password + validacion) se documenta en
 *   ../mitigations/.
 *
 * Hardware:
 *   - ESP32 DevKit
 *   Pines elegidos todos sobre la MISMA hilera libre de la protoboard
 *   (la que trae VIN y GND), evitando los pines de flash (CMD/SD2/SD3),
 *   los strapping y EN. Alimentacion por USB: 5V se toma del pin VIN.
 *
 *   - HC-SR04  : TRIG -> GPIO 13, ECHO -> GPIO 34 (via divisor 5V->3.3V)
 *                (GPIO34 es solo-entrada: ideal para el Echo)
 *   - Servo    : signal -> GPIO 14
 *   - LED      : GPIO 27 (+ resistencia 220 ohm)
 *   - Buzzer   : GPIO 26
 *
 * Librerias (Library Manager):
 *   - PubSubClient (Nick O'Leary)
 *   - ESP32Servo
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ESP32Servo.h>

// ----------------------------------------------------------------
// Configuracion - ajustar a tu laboratorio
// ----------------------------------------------------------------
const char* WIFI_SSID     = "TU_RED_DE_LAB";
const char* WIFI_PASS     = "TU_PASSWORD";

// IP de la PC que corre el broker Mosquitto (ver ../broker/)
const char* MQTT_HOST     = "192.168.1.100";
const int   MQTT_PORT     = 1883;            // 1883 = sin TLS (inseguro, a proposito)
const char* MQTT_CLIENT   = "esp32-linea-A";

// Topics (convencion planta/linea/dispositivo/medida)
const char* TOPIC_NIVEL   = "planta/lineaA/tanque1/nivel";     // sensor -> broker
const char* TOPIC_CMD     = "planta/lineaA/valvula1/cmd";      // broker -> actuador
const char* TOPIC_ESTADO  = "planta/lineaA/valvula1/estado";   // actuador -> broker

// Pines
const int PIN_TRIG   = 13;
const int PIN_ECHO   = 34;   // solo-entrada (sin pull interno; lo maneja el sensor)
const int PIN_SERVO  = 14;
const int PIN_LED    = 27;
const int PIN_BUZZER = 26;

// Logica de proceso simulado
const float NIVEL_MIN_CM = 5.0;    // tanque lleno (sensor cerca de la superficie)
const float NIVEL_MAX_CM = 40.0;   // tanque vacio
const unsigned long SAMPLE_MS = 2000;

WiFiClient    net;
PubSubClient  mqtt(net);
Servo         valvula;

unsigned long lastSample = 0;

// ----------------------------------------------------------------
// WiFi
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

// ----------------------------------------------------------------
// Actuador: aplica un comando recibido por MQTT
//   "ABRIR"  -> valvula 90deg, LED on
//   "CERRAR" -> valvula 0deg,  LED off
//   "ALARMA" -> buzzer 3 pitidos
// ----------------------------------------------------------------
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
    // Buzzer ACTIVO (trae oscilador propio): basta con dar/quitar
    // tension. Evitamos tone(), que en el ESP32 puede competir por el
    // timer/LEDC que usa el servo. Si tu buzzer es PASIVO, reemplazar
    // digitalWrite por: tone(PIN_BUZZER, 2000, 200);
    for (int i = 0; i < 3; i++) {
      digitalWrite(PIN_BUZZER, HIGH);
      delay(200);
      digitalWrite(PIN_BUZZER, LOW);
      delay(200);
    }
    mqtt.publish(TOPIC_ESTADO, "ALARMA", true);
  } else {
    Serial.println("[CMD] Comando desconocido (ignorado)");
  }
}

// ----------------------------------------------------------------
// Callback MQTT: llega un mensaje a un topic suscripto.
//
// NOTA DIDACTICA: aqui NO se valida origen ni integridad del
// mensaje. Cualquiera que pueda publicar en TOPIC_CMD puede mover
// el actuador. Esa es, justamente, la vulnerabilidad que la demo
// muestra y que la version endurecida corrige (auth + ACL + TLS).
// ----------------------------------------------------------------
void onMessage(char* topic, byte* payload, unsigned int len) {
  String msg;
  for (unsigned int i = 0; i < len; i++) msg += (char)payload[i];
  if (String(topic) == TOPIC_CMD) {
    aplicarComando(msg);
  }
}

void conectarMQTT() {
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMessage);
  while (!mqtt.connected()) {
    Serial.print("[MQTT] Conectando... ");
    // Sin usuario/password: broker abierto (inseguro, a proposito)
    if (mqtt.connect(MQTT_CLIENT)) {
      Serial.println("OK");
      mqtt.subscribe(TOPIC_CMD);
      mqtt.publish(TOPIC_ESTADO, "ONLINE", true);
    } else {
      Serial.printf("fallo rc=%d, reintento en 2s\n", mqtt.state());
      delay(2000);
    }
  }
}

// ----------------------------------------------------------------
// Sensor: lectura HC-SR04 -> distancia en cm
// ----------------------------------------------------------------
float leerDistanciaCruda() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);

  long dur = pulseIn(PIN_ECHO, HIGH, 30000UL); // timeout 30ms (~5m)
  if (dur == 0) return NIVEL_MAX_CM;           // sin eco -> asumimos vacio
  return dur * 0.0343 / 2.0;
}

// Mediana de N lecturas: filtra picos espurios (una lectura mala no
// mueve el resultado). Clave para que el HC-SR04 no haga saltar el nivel.
float leerDistanciaCm() {
  const int N = 5;
  float m[N];
  for (int i = 0; i < N; i++) { m[i] = leerDistanciaCruda(); delay(40); }
  for (int i = 1; i < N; i++) {                // insertion sort (N chico)
    float k = m[i]; int j = i - 1;
    while (j >= 0 && m[j] > k) { m[j + 1] = m[j]; j--; }
    m[j + 1] = k;
  }
  return m[N / 2];
}

// Convierte distancia a porcentaje de llenado (0-100%)
int nivelPorcentaje(float cm) {
  if (cm <= NIVEL_MIN_CM) return 100;
  if (cm >= NIVEL_MAX_CM) return 0;
  float pct = (NIVEL_MAX_CM - cm) / (NIVEL_MAX_CM - NIVEL_MIN_CM) * 100.0;
  return (int)pct;
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

    // Payload JSON simple: { "nivel": 72, "cm": 14.8, "ts": 123456 }
    char payload[96];
    snprintf(payload, sizeof(payload),
             "{\"nivel\":%d,\"cm\":%.1f,\"ts\":%lu}", pct, cm, now);
    mqtt.publish(TOPIC_NIVEL, payload);
    Serial.printf("[PUB] %s -> %s\n", TOPIC_NIVEL, payload);
  }
}
