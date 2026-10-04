# Mitigaciones — del broker vulnerable al broker endurecido

Esta carpeta cierra la demo: después de mostrar el ataque sobre el
broker inseguro, aplicamos contramedidas y repetimos los mismos
scripts del atacante para evidenciar que **ya no funcionan**. Ese
contraste es la parte que demuestra aprendizaje, no solo el ataque.

## Mapa vulnerabilidad → contramedida

| Lo que explotamos en la demo | Contramedida | Efecto |
|---|---|---|
| Tráfico en texto plano (sniff lee payloads) | **TLS** (puerto 8883) | El sniffer y `tshark` ya no ven el contenido |
| Acceso anónimo (`allow_anonymous true`) | **Autenticación** usuario/password | El atacante sin credenciales no se conecta |
| Cualquier cliente publica en cualquier topic | **ACL** por usuario/topic | Aunque robe una credencial, su alcance es mínimo |
| ESP32 ejecuta cualquier comando recibido | **Validación + credenciales por dispositivo** | El actuador no obedece a un emisor no autorizado |
| Credenciales por defecto / reutilizadas | **Password única por dispositivo** | Evita el vector tipo Mirai |
| Red plana (IoT junto a IT) | **Segmentación / VLAN + firewall** | Reduce quién puede siquiera hablar con el broker |

## Pasos para la demo de mitigación

1. **Generar certificados** (CA de laboratorio + cert del broker):

   ```bash
   cd poc/mitigations
   ./gen-certs.sh 192.168.1.100     # IP del broker
   ```

2. **Crear usuarios** (dentro del contenedor o con mosquitto en local):

   ```bash
   cd poc/broker
   docker run --rm -it -v "$PWD:/m" eclipse-mosquitto:2 \
     mosquitto_passwd -c /m/passwd esp32
   docker run --rm -it -v "$PWD:/m" eclipse-mosquitto:2 \
     mosquitto_passwd /m/passwd scada
   ```

3. **Cambiar la config** montada en `docker-compose.yml`: comentar la
   línea de `mosquitto-insecure.conf` y descomentar el bloque
   `mosquitto-secure.conf` + `passwd` + `acl` + `certs`. Luego:

   ```bash
   docker compose up -d
   ```

4. **Actualizar los clientes** para usar TLS + credenciales:
   - ESP32: usar `WiFiClientSecure`, cargar `ca.crt`, `mqtt.connect(id, "esp32", "<pass>")`, puerto 8883.
   - SCADA: `client.tls_set("ca.crt")`, `client.username_pw_set("scada", "<pass>")`, puerto 8883.

5. **Re-ejecutar el atacante** y mostrar los fallos:
   - `sniff.py --port 1883` → ya no hay puerto plano / no conecta.
   - `sniff.py --port 8883` sin credenciales → **conexión rechazada**.
   - `tshark -Y mqtt` → solo se ve el handshake TLS, los payloads van cifrados.
   - `inject_command.py` → **rechazado** (no autenticado / fuera de ACL).

## Buenas prácticas IIoT (para el informe)

- **Secure by default**: nunca desplegar con credenciales de fábrica;
  forzar cambio en el primer arranque.
- **Actualizaciones firmadas (secure OTA)**: poder parchear el firmware;
  la falta de updates es una de las causas raíz del problema IoT.
- **Mínimo privilegio** en broker y dispositivos (ACL, scopes).
- **Monitoreo/IDS**: alertar ante publicaciones anómalas (p. ej. dos
  "sensores" publicando en el mismo topic, o comandos fuera de horario).
- **Segmentación de red** OT/IT y exposición mínima (no publicar el
  broker a Internet; si hace falta acceso remoto, VPN).
- **Gestión de identidad por dispositivo** (idealmente certificados de
  cliente, no una password compartida).
