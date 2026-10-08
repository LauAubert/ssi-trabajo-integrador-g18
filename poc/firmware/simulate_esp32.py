#!/usr/bin/env python3
"""
SSI - TP IoT/IIoT - Grupo 18
Simulador del nodo ESP32 (plan B sin hardware).

Emite en los MISMOS topics que el firmware real y obedece comandos,
de modo que el broker, el SCADA y los scripts del atacante funcionan
igual tengan o no el ESP32 fisico delante. Util para ensayar la demo.

El nivel del tanque baja solo (consumo) y sube cuando la valvula esta
ABIERTA, para que el lazo de control del SCADA tenga algo que hacer.

Ejecutar:
  python simulate_esp32.py --host 192.168.1.100
"""
import argparse
import json
import time

import paho.mqtt.client as mqtt

TOPIC_NIVEL  = "planta/lineaA/tanque1/nivel"
TOPIC_CMD    = "planta/lineaA/valvula1/cmd"
TOPIC_ESTADO = "planta/lineaA/valvula1/estado"

estado = {"nivel": 60.0, "valvula": "CERRADA"}


def on_message(client, userdata, msg):
    if msg.topic == TOPIC_CMD:
        cmd = msg.payload.decode()
        if cmd == "ABRIR":
            estado["valvula"] = "ABIERTA"
        elif cmd == "CERRAR":
            estado["valvula"] = "CERRADA"
        elif cmd == "ALARMA":
            print("    [ESP32-sim] *** BUZZER ALARMA ***")
        client.publish(TOPIC_ESTADO, estado["valvula"], retain=True)
        print(f"    [ESP32-sim] cmd={cmd} -> valvula={estado['valvula']}")


def main():
    ap = argparse.ArgumentParser(description="Simulador ESP32 (lab IoT)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1883)
    # Fase de mitigacion: TLS + credenciales (broker endurecido, puerto 8883)
    ap.add_argument("--tls", action="store_true", help="conectar por TLS")
    ap.add_argument("--ca", help="ruta al ca.crt para validar el broker")
    ap.add_argument("--user", help="usuario MQTT")
    ap.add_argument("--password", help="password MQTT")
    ap.add_argument("--insecure-tls", action="store_true",
                    help="no validar el certificado (sigue cifrando)")
    args = ap.parse_args()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id="esp32-sim")
    client.on_message = on_message
    if args.user:
        client.username_pw_set(args.user, args.password)
    if args.tls:
        client.tls_set(ca_certs=args.ca)
        if args.insecure_tls:
            client.tls_insecure_set(True)
    client.connect(args.host, args.port, keepalive=60)
    client.subscribe(TOPIC_CMD)
    client.publish(TOPIC_ESTADO, estado["valvula"], retain=True)
    client.loop_start()

    print("[+] Nodo ESP32 simulado en marcha. Ctrl-C para salir.")
    try:
        while True:
            # dinamica del tanque
            if estado["valvula"] == "ABIERTA":
                estado["nivel"] = min(100.0, estado["nivel"] + 4)
            else:
                estado["nivel"] = max(0.0, estado["nivel"] - 2)

            nivel = int(estado["nivel"])
            cm = round(40 - (nivel / 100.0) * 35, 1)
            payload = json.dumps({"nivel": nivel, "cm": cm,
                                  "ts": int(time.time() * 1000)})
            client.publish(TOPIC_NIVEL, payload)
            print(f"[PUB] {TOPIC_NIVEL} -> {payload}  (valvula={estado['valvula']})")
            time.sleep(2)
    except KeyboardInterrupt:
        client.loop_stop()


if __name__ == "__main__":
    main()
