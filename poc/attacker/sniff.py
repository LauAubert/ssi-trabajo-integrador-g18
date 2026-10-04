#!/usr/bin/env python3
"""
SSI - TP IoT/IIoT - Grupo 18
Sniffer MQTT (observacion pasiva a nivel de aplicacion).

Uso previsto: laboratorio cerrado y propio, con autorizacion, para
demostrar que un broker MQTT sin TLS ni autenticacion expone todo
el trafico a cualquiera en la red.

Que hace:
  Se conecta al broker como cliente anonimo y se suscribe a '#'
  (todos los topics). Imprime cada mensaje con timestamp. Como el
  broker es abierto, no hace falta ninguna credencial: eso es,
  precisamente, el hallazgo a mostrar.

Complemento a nivel de red (captura en el cable/aire):
  El sniff a nivel de aplicacion de arriba funciona porque el broker
  es abierto. Para mostrar que ADEMAS viaja en texto plano, capturar
  el trafico con tshark/Wireshark en la red de lab:

      sudo tshark -i <iface> -Y mqtt -O mqtt

  Se ven los PUBLISH con el topic y el payload legibles. Con TLS
  (version endurecida) esto queda cifrado.

Ejecutar:
  python sniff.py --host 192.168.1.100
"""
import argparse
import datetime as dt

import paho.mqtt.client as mqtt
from rich.console import Console

console = Console()


def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        console.print("[green]\\[+] Conectado al broker (anonimo). "
                      "Suscribiendo a '#'[/green]")
        client.subscribe("#", qos=0)
        # $SYS expone metadatos del broker: tambien util para recon.
        client.subscribe("$SYS/#", qos=0)
    else:
        console.print(f"[red]\\[!] Conexion rechazada: rc={reason_code}[/red]")


def on_message(client, userdata, msg):
    ts = dt.datetime.now().strftime("%H:%M:%S")
    payload = msg.payload.decode("utf-8", errors="replace")
    console.print(f"[dim]{ts}[/dim] [cyan]{msg.topic}[/cyan]  {payload}")


def main():
    ap = argparse.ArgumentParser(description="Sniffer MQTT (lab IoT)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1883)
    args = ap.parse_args()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id="sniffer-lab")
    client.on_connect = on_connect
    client.on_message = on_message

    console.rule("[bold]Sniffer MQTT - laboratorio SSI[/bold]")
    console.print(f"Broker: {args.host}:{args.port}  (Ctrl-C para salir)")
    client.connect(args.host, args.port, keepalive=60)
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        console.print("\n[yellow]Fin.[/yellow]")


if __name__ == "__main__":
    main()
