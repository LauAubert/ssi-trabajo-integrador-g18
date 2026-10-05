# POC — Setup paso a paso

Guía práctica para montar el laboratorio de la demo de seguridad
IoT/IIoT. Seguí las secciones en orden. Para el guion de la
presentación en vivo, ver [`../docs/demo-guion.md`](../docs/demo-guion.md).

> ⚠️ **Ámbito.** Todo corre sobre equipo y red propios del grupo, con
> fines educativos. No usar contra sistemas de terceros.

## Topología

```
[ ESP32 sensor/actuador ] --MQTT--> [ PC-A: broker + SCADA ] <-- [ PC-B: atacante ]
                                         (misma red de laboratorio)
```

| Rol | Equipo | Qué corre |
|---|---|---|
| Nodo IIoT | ESP32 | `firmware/sensor_actuator.ino` |
| Servidor + operador | PC-A | broker Mosquitto (Docker) + `dashboard/scada.py` |
| Atacante | PC-B | Wireshark + scripts de `attacker/` |

**Requisitos:** Docker en PC-A · Python 3.10+ en PC-A y PC-B · Arduino
IDE · Wireshark en PC-B · un router/AP del grupo (no la red del aula).

Instalar dependencias Python (en PC-A y PC-B):

```bash
pip install -r attacker/requirements.txt
```

---

## 1. Subir el código al ESP32

1. **Soporte ESP32 en Arduino IDE:** *Preferencias → URLs adicionales de
   gestor de placas* →
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`.
   Luego *Herramientas → Placa → Gestor de placas* → instalar **esp32**.
2. **Librerías** (*Herramientas → Gestionar bibliotecas*): `PubSubClient`
   (Nick O'Leary) y `ESP32Servo`.
3. **Configurar** las credenciales y el broker en
   [`firmware/sensor_actuator.ino`](firmware/sensor_actuator.ino):

   ```cpp
   const char* WIFI_SSID = "TU_RED_DE_LAB";
   const char* WIFI_PASS = "TU_PASSWORD";
   const char* MQTT_HOST = "192.168.1.100";  // IP de PC-A (ver paso 3)
   ```

4. **Placa y puerto:** *Placa* = "ESP32 Dev Module", elegí el *Puerto*.
5. **Subir** (botón →) y abrir el **Monitor Serie a 115200**. Deberías ver
   `[WiFi] OK`, `[MQTT] OK` y mensajes `[PUB] .../nivel -> {...}`.

> **¿No tenés el ESP32 a mano?** Saltá este paso y usá el nodo simulado en
> el paso 4 ([`firmware/simulate_esp32.py`](firmware/simulate_esp32.py)):
> publica en los mismos topics y la demo es idéntica.

---

## 2. Conexión del circuito

Diagrama completo: [`../docs/diagrama-conexion.svg`](../docs/diagrama-conexion.svg).

| Componente | Conexión al ESP32 |
|---|---|
| **HC-SR04** (ultrasonido) | `Vcc→5V (VIN)`, `Gnd→GND`, `Trig→GPIO13`, `Echo→`divisor`→GPIO34` |
| **Servo SG90** (válvula) | `Rojo→5V (VIN)`, `Marrón→GND`, `Naranja(señal)→GPIO14` |
| **LED** de estado | `GPIO27 → 220Ω → ánodo(+)`; `cátodo(−) → GND` |
| **Buzzer** activo | `GPIO26 → (+)`; `(−) → GND` |

> Todos los pines están sobre la **misma hilera libre** de la protoboard
> (el lado de `VIN`/`GND`), para poder usar el ESP32 con una sola
> protoboard. Se evitan `CMD`/`SD2`/`SD3` (flash interna) y `EN` (reset).
> `GPIO34` es solo-entrada: ideal para el Echo. Alimentación por **USB**:
> el pin `VIN` entrega los 5V.

**Dos cuidados clave:**

- **Divisor de tensión en ECHO** (el HC-SR04 saca 5V y el ESP32 tolera
  3.3V): `Echo → R1(1kΩ) → GPIO34`, y `GPIO34 → R2(2kΩ) → GND`.
- **Alimentación del servo:** si al mover la válvula el ESP32 se resetea,
  alimentá el servo con una fuente 5V aparte y **uní los GND**.

---

## 3. Levantar el broker (PC-A)

El `docker-compose.yml` arranca por defecto con la config **insegura**
(sin TLS, acceso anónimo), que es la que permite la demo del ataque.

```bash
cd broker
docker compose up -d        # levanta Mosquitto en el puerto 1883
docker compose logs -f      # (opcional) ver conexiones y mensajes
```

Averiguá la **IP de PC-A** (es la que va en `MQTT_HOST` del ESP32 y en
`--host` de los scripts):

```bash
# macOS
ipconfig getifaddr en0
# Linux
hostname -I | awk '{print $1}'
```

Probá que responde (opcional, desde PC-A):

```bash
docker exec -it ssi-broker mosquitto_sub -h localhost -t '#' -v
```

---

## 4. Usar el laboratorio (verificar que todo funciona)

En **PC-A**, levantá el operador/SCADA:

```bash
cd dashboard
python scada.py --host <IP_PC-A>
```

Encendé el ESP32 (o, sin hardware, en otra terminal:
`python firmware/simulate_esp32.py --host <IP_PC-A>`).

Deberías ver el panel del SCADA actualizando el **nivel del tanque** y la
**válvula** abriendo/cerrando sola según el nivel. Ese es el sistema
"sano" que vamos a atacar.

---

## 5. Sniffear con Wireshark (confidencialidad)

Desde **PC-B**, en la misma red:

1. Abrí **Wireshark** y elegí la interfaz de la red del lab (Wi-Fi o
   Ethernet). Si dudás, en terminal: `tshark -D` lista las interfaces.
2. En el campo de **filtro de visualización** escribí:

   ```
   mqtt
   ```

3. Vas a ver paquetes **MQTT PUBLISH** con el *topic* y el *payload*
   **en texto plano**: niveles del sensor, comandos, estados. Clic
   derecho en un paquete → *Follow → TCP Stream* para leer el flujo.

> **Por qué funciona:** MQTT sin TLS no cifra nada; cualquiera en la red
> lee el proceso completo. (En redes conmutadas, para ver tráfico entre
> *otros* dos equipos hace falta estar en el camino —p. ej. ARP
> spoofing—; para la demo alcanza con capturar el tráfico desde/hacia
> PC-B o escuchar el broadcast de la Wi-Fi del lab.)

**Equivalente por línea de comandos** (muestra topic + payload):

```bash
sudo tshark -i <iface> -Y mqtt -O mqtt
```

**A nivel de aplicación** (como el broker es anónimo, nos suscribimos a
todo sin credenciales — útil para mapear los topics rápido):

```bash
cd attacker
python sniff.py --host <IP_PC-A>
```

---

## 6. Inyectar peticiones maliciosas (integridad + control físico)

Con el sniffing ya sabemos los *topics* y el formato. Ahora reproducimos
e inyectamos tráfico desde **PC-B**. Dejá el SCADA (paso 4) a la vista
para ver el impacto en vivo.

**a) Falsear el sensor** (*false data injection*): el SCADA pasa a ver
datos mentira.

```bash
cd attacker
python spoof_sensor.py --host <IP_PC-A> --mode fixed --value 80
```

El panel queda "clavado" en 80% aunque el tanque real se vacíe. Si el
sensor real le gana la carrera, bajá `--rate` (publica más seguido):
`--rate 0.5`.

**b) Comandar el actuador sin autorización** (salto al mundo físico):

```bash
python inject_command.py --host <IP_PC-A> --cmd ABRIR
python inject_command.py --host <IP_PC-A> --cmd ALARMA
```

La válvula del ESP32 se mueve y el buzzer suena **sin que el operador lo
haya pedido**. Esta es la clase de debilidad —acceso no autenticado,
credenciales por defecto— que encadenan botnets como **Mirai**.

---

## 7. Mitigar (y mostrar que los ataques dejan de funcionar)

Endurecemos el broker con **TLS + autenticación + ACL** y re-ejecutamos
los mismos ataques, que ahora fallan. Detalle completo en
[`mitigations/README.md`](mitigations/README.md).

1. **Generar certificados** de laboratorio (CA + cert del broker):

   ```bash
   cd mitigations
   ./gen-certs.sh <IP_PC-A>
   ```

2. **Crear usuarios** (password única por identidad):

   ```bash
   cd ../broker
   docker run --rm -it -v "$PWD:/m" eclipse-mosquitto:2 \
     mosquitto_passwd -c /m/passwd esp32
   docker run --rm -it -v "$PWD:/m" eclipse-mosquitto:2 \
     mosquitto_passwd /m/passwd scada
   ```

3. **Cambiar a la config segura** en `broker/docker-compose.yml`:
   comentar el montaje de `mosquitto-insecure.conf` y descomentar el
   bloque de `mosquitto-secure.conf` + `passwd` + `acl` + `certs`. Luego:

   ```bash
   docker compose up -d
   ```

4. **Actualizar los clientes** a TLS (puerto **8883**) + credenciales
   (ESP32 con `WiFiClientSecure` + `ca.crt`; SCADA con `tls_set()` y
   `username_pw_set()`).

5. **Re-correr el atacante** y mostrar los fallos:

   ```bash
   python sniff.py --host <IP_PC-A> --port 1883   # ya no hay puerto plano
   python sniff.py --host <IP_PC-A> --port 8883   # rechazado: sin credenciales
   python inject_command.py --host <IP_PC-A> --port 1883   # falla
   sudo tshark -i <iface> -Y mqtt                 # solo handshake TLS; payloads cifrados
   ```

**Resultado:** mismo atacante, misma red, pero el tráfico es ilegible y
las conexiones/inyecciones son rechazadas. La inseguridad de IoT casi
nunca es inevitable: es configuración por defecto y falta de
mantenimiento.

---

## Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| El ESP32 no conecta | SSID/clave o IP del broker mal | revisá las 3 líneas del paso 1 y el Monitor Serie |
| El atacante no conecta | PC-B en otra red | verificá que ambas PC estén en la LAN del lab |
| El SCADA no muestra nada | el nodo no publica | revisá el Monitor Serie / `docker compose logs` |
| El spoof "no gana" | el sensor real publica más seguido | `spoof_sensor.py --rate 0.5` |
| Wireshark no ve MQTT | interfaz equivocada | `tshark -D` y elegí la de la LAN |
