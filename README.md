# SSI — Seguridad en Internet de las Cosas (IoT e IIoT)

**Materia:** Seguridad en Sistemas de Información · **Grupo 18**
**Tema (Acertijo 19):** *«Cada objeto conectado es una puerta; desde el
hogar hasta la industria.»* → Seguridad en IoT/IIoT: credenciales por
defecto, falta de actualizaciones y casos como la botnet **Mirai**.

## De qué trata este trabajo

Demostramos, en un **laboratorio cerrado y propio**, por qué un
despliegue IoT/IIoT típico es inseguro cuando usa MQTT sin cifrado ni
autenticación — y cómo se corrige. El entregable tiene tres partes:

1. **POC ejecutable** (`poc/`) — lo que se muestra en vivo.
2. **Informe / monografía** (`docs/informe.md`).
3. **Guion de la demo** (`docs/demo-guion.md`) — paso a paso reproducible.

> ⚠️ **Ámbito y ética.** Todo el ejercicio corre sobre equipo propio
> (nuestro ESP32, nuestro broker, nuestra red de laboratorio) y con
> fines educativos. Las técnicas de sniffing e inyección se usan para
> *entender y mitigar* el riesgo, nunca contra sistemas de terceros.
> Atacar infraestructura ajena sin autorización es ilegal.

## Arquitectura del laboratorio

```
   [ ESP32 + sensores/actuadores ]        <- nodo industrial simulado
        | MQTT (1883, texto plano)
        v
   [ PC-A: broker Mosquitto ]  <----  [ PC-A: mini-SCADA/dashboard ]
        ^                                      (operador legítimo)
        | misma red de laboratorio
        |
   [ PC-B: atacante ]   sniff.py / spoof_sensor.py / inject_command.py
```

- **ESP32** mide "nivel de un tanque" (HC-SR04) y acciona una "válvula"
  (servo) + LED + buzzer, hablando MQTT con el broker.
- **Mini-SCADA** monitorea y controla el proceso (lazo automático).
- **Atacante** (segunda PC en la misma red) primero **lee** el tráfico
  y luego **inyecta** datos/comandos falsos.
- La fase final **endurece** el broker (TLS + auth + ACL) y muestra que
  los mismos ataques dejan de funcionar.

## Estructura

```
SSI/
├─ README.md                 (este archivo)
├─ docs/
│  ├─ informe.md             (monografía)
│  └─ demo-guion.md          (runbook de la demo en vivo)
└─ poc/
   ├─ firmware/
   │  └─ sensor_actuator.ino (ESP32: sensor + actuador por MQTT)
   ├─ broker/
   │  ├─ docker-compose.yml
   │  ├─ mosquitto-insecure.conf   (demo del ataque)
   │  ├─ mosquitto-secure.conf     (demo de la mitigación)
   │  └─ acl
   ├─ dashboard/
   │  └─ scada.py            (operador legítimo + panel en vivo)
   ├─ attacker/
   │  ├─ sniff.py            (lectura pasiva del tráfico)
   │  ├─ spoof_sensor.py     (inyección de lecturas falsas)
   │  └─ inject_command.py   (comandos no autorizados al actuador)
   └─ mitigations/
      ├─ README.md           (contramedidas + buenas prácticas)
      └─ gen-certs.sh        (CA + cert del broker para TLS)
```

## Quickstart (resumen — detalle en `docs/demo-guion.md`)

```bash
# 1) Broker (PC-A)
cd poc/broker && docker compose up -d

# 2) SCADA / operador (PC-A)
cd ../dashboard && pip install -r ../attacker/requirements.txt
python scada.py --host <IP_BROKER>

# 3) ESP32: abrir poc/firmware/sensor_actuator.ino en Arduino IDE,
#    configurar WIFI_* y MQTT_HOST, y flashear.

# 4) Atacante (PC-B)
cd poc/attacker && pip install -r requirements.txt
python sniff.py --host <IP_BROKER>
python spoof_sensor.py --host <IP_BROKER> --mode fixed --value 80
python inject_command.py --host <IP_BROKER> --cmd ABRIR

# 5) Mitigación: ver poc/mitigations/README.md
```

## Si no hay hardware a mano

La demo es idéntica sin ESP32: usar el firmware real cuando esté, o un
**publicador simulado** en Python que emita en los mismos topics. El
broker, el SCADA y el atacante no distinguen el origen (ese es, de
hecho, el punto del trabajo). Ver la nota en `docs/demo-guion.md`.
