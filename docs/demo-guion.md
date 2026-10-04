# Guion de la demo en vivo — Seguridad IoT/IIoT

**Grupo 18 · SSI** · Duración objetivo: 8–12 min.
Todo corre en laboratorio propio (equipo y red del grupo), con fines
educativos.

## 0. Antes de empezar (checklist)

- [ ] PC-A y PC-B en la **misma red** de laboratorio (idealmente un
      router/AP propio, no la red de la facultad).
- [ ] Anotar la **IP del broker** (PC-A): `ipconfig` / `ip a` / `ifconfig`.
- [ ] Docker corriendo en PC-A.
- [ ] Python 3 + `pip install -r poc/attacker/requirements.txt` en ambas PC.
- [ ] ESP32 flasheado con `WIFI_*` y `MQTT_HOST` correctos
      (o tener listo `simulate_esp32.py` como plan B).
- [ ] Terminales grandes y con buena tipografía para proyectar.

**Disposición de pantallas sugerida (para que se vea el impacto):**

| Pantalla | Qué muestra |
|---|---|
| SCADA (PC-A) | `scada.py` — panel en vivo del proceso |
| Atacante (PC-B) | la terminal donde lanzamos sniff/spoof/inject |
| ESP32 físico | la válvula/LED/buzzer sobre la mesa |

---

## 1. El sistema funcionando (línea base) — 2 min

En PC-A:

```bash
cd poc/broker && docker compose up -d       # broker INSEGURO
cd ../dashboard && python scada.py --host <IP_BROKER>
```

Encender el ESP32 (o `python poc/firmware/simulate_esp32.py --host <IP_BROKER>`).

**Mostrar:** el panel del SCADA actualizando el nivel del tanque; la
válvula abriendo/cerrando sola según el nivel; el LED acompañando.

> *Narrativa:* "Esto es un nodo industrial típico: un sensor reporta,
> un controlador decide, un actuador ejecuta. Hablan por MQTT, que es
> el protocolo de facto en IoT. Ahora veamos qué pasa si alguien más
> está en la misma red."

---

## 2. Reconocimiento / Sniffing (confidencialidad) — 2 min

En PC-B (atacante):

```bash
cd poc/attacker
python sniff.py --host <IP_BROKER>
```

**Mostrar:** sin ninguna credencial, el atacante ve **todos** los topics
y payloads: niveles, comandos, estados. El broker es anónimo y abierto.

Opcional (impacto fuerte) — captura a nivel de red:

```bash
sudo tshark -i <iface> -Y mqtt -O mqtt
```

Se leen los `PUBLISH` con topic y payload **en texto plano**.

> *Narrativa:* "Primera lección: MQTT por defecto no cifra ni autentica.
> Cualquiera en la red lee el proceso completo. Pero leer es lo de menos."

---

## 3. Inyección de datos falsos (integridad) — 2 min

Dejar el SCADA a la vista. En PC-B:

```bash
python spoof_sensor.py --host <IP_BROKER> --mode fixed --value 80
```

**Mostrar:** el panel del SCADA queda "clavado" en 80% aunque el tanque
real se esté vaciando (o aunque movamos la mano frente al sensor). El
operador ve un proceso que no existe.

> *Narrativa:* "Esto es *false data injection*. El controlador toma
> decisiones sobre datos mentira: puede no reponer a tiempo, o frenar
> una línea sin motivo. Daño económico y de producción sin tocar nada
> físico."

---

## 4. Control del actuador (seguridad operacional) — 2 min

En PC-B:

```bash
python inject_command.py --host <IP_BROKER> --cmd ABRIR
python inject_command.py --host <IP_BROKER> --cmd ALARMA
```

**Mostrar:** la válvula del ESP32 se mueve y el buzzer suena **sin que
el SCADA lo haya ordenado**. El atacante controla el mundo físico.

> *Narrativa:* "Acá cruzamos de lo digital a lo físico. Un comando no
> autenticado y el actuador obedece. Esta es la clase de debilidad —
> acceso no autenticado, credenciales por defecto — que encadenan
> botnets como **Mirai** para tomar millones de dispositivos."

---

## 5. Mitigación: los mismos ataques, ahora fallan — 2–3 min

Seguir `poc/mitigations/README.md`:

1. `./gen-certs.sh <IP_BROKER>` y crear usuarios (`mosquitto_passwd`).
2. Cambiar el compose a `mosquitto-secure.conf` + `passwd` + `acl` + `certs`.
3. `docker compose up -d`.
4. Reconfigurar SCADA/ESP32 con TLS (8883) + credenciales.

Volver a correr el atacante **sin cambiar nada de su lado**:

```bash
python sniff.py --host <IP_BROKER> --port 1883   # ya no hay puerto plano
python sniff.py --host <IP_BROKER> --port 8883   # rechazado: sin credenciales
python inject_command.py --host <IP_BROKER> --port 1883   # falla
sudo tshark -i <iface> -Y mqtt                   # solo handshake TLS, payloads cifrados
```

**Mostrar:** conexiones rechazadas y tráfico ilegible.

> *Narrativa:* "Tres cambios —TLS, autenticación y ACL— y el mismo
> atacante en la misma red se queda afuera. La inseguridad de IoT casi
> nunca es inevitable: es configuración por defecto y falta de
> mantenimiento."

---

## 6. Cierre — 1 min

- IoT/IIoT amplía la superficie de ataque: cada objeto conectado es una
  puerta (el acertijo).
- Las causas raíz son mundanas: credenciales por defecto, sin cifrado,
  sin updates, redes planas.
- Las defensas son conocidas y aplicables: cifrado, identidad por
  dispositivo, mínimo privilegio, segmentación, monitoreo y OTA seguro.

---

## Troubleshooting rápido

| Síntoma | Causa probable | Fix |
|---|---|---|
| El atacante no conecta | IP/puerto o red distinta | verificar `<IP_BROKER>` y que ambas PC estén en la misma LAN |
| El SCADA no muestra nada | ESP32/sim no publica, o topic mal | revisar Serial del ESP32 / logs del broker |
| El spoof "no gana" | el sensor real publica más seguido | bajar `--rate` en `spoof_sensor.py` |
| `tshark` no ve MQTT | interfaz equivocada | listar con `tshark -D` y elegir la de la LAN |
| Firewall bloquea 1883 | regla local | permitir el puerto en PC-A solo para la LAN de lab |
