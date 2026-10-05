#!/usr/bin/env python3
"""
SSI - TP IoT/IIoT - Grupo 18
Mini-SCADA / operador legitimo.

Representa el sistema de control normal de la planta. Suscribe al
nivel del tanque y al estado de la valvula, muestra un panel en vivo
(con un grafico temporal del nivel) y ejecuta un lazo de control
simple:

  - nivel < LOW   -> ABRIR valvula (reponer)
  - nivel > HIGH  -> CERRAR valvula

En la demo, este panel es el "cliente de buena fe": primero se lo ve
operar normal; despues se lanza el atacante (spoof_sensor / inject_
command) y se observa como el grafico reacciona a datos falsos o como
el actuador cambia de estado sin que el SCADA lo haya ordenado.

Ejecutar:
  python scada.py --host 192.168.1.100
  python scada.py --host 192.168.1.100 --no-control   # solo monitoreo
"""
import argparse
import json
import threading
import time
from collections import deque

import paho.mqtt.client as mqtt
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

TOPIC_NIVEL  = "planta/lineaA/tanque1/nivel"
TOPIC_CMD    = "planta/lineaA/valvula1/cmd"
TOPIC_ESTADO = "planta/lineaA/valvula1/estado"

LOW, HIGH = 30, 90
HIST_MAX = 60               # muestras guardadas (~2 min a 2s c/u)
BLOCKS = "▁▂▃▄▅▆▇█"         # 8 niveles para el sparkline

console = Console()
state = {"nivel": None, "cm": None, "estado": "?", "ultimo_cmd": "-",
         "ultimo_msg": "-"}
history = deque(maxlen=HIST_MAX)
lock = threading.Lock()


def sparkline(vals):
    """Convierte una lista de niveles (0-100) en una linea de bloques."""
    if not vals:
        return "(sin datos aun...)"
    return "".join(
        BLOCKS[min(len(BLOCKS) - 1, int(v / 100 * len(BLOCKS)))] for v in vals
    )


def chart():
    with lock:
        vals = list(history)
    linea = sparkline(vals)
    if vals:
        actual, mn, mx = vals[-1], min(vals), max(vals)
        pie = (f"actual: [bold]{actual}%[/bold]   min: {mn}%   max: {mx}%"
               f"   ({len(vals)} muestras · ~2s c/u)")
    else:
        pie = "esperando datos del sensor..."
    cuerpo = f"100% ┤\n[green]{linea}[/green]\n  0% ┤   {pie}"
    return Panel(cuerpo, title="Nivel del tanque — histórico",
                 border_style="cyan")


def tabla():
    t = Table(title="SCADA - Linea A / Tanque 1", expand=True)
    t.add_column("Variable"); t.add_column("Valor", justify="right")
    with lock:
        nivel = state["nivel"]
        barra = ""
        if nivel is not None:
            llenos = int(nivel / 5)
            barra = "█" * llenos + "·" * (20 - llenos)
        t.add_row("Nivel tanque", f"{nivel}%  {barra}" if nivel is not None else "-")
        t.add_row("Distancia", f'{state["cm"]} cm' if state["cm"] else "-")
        t.add_row("Estado valvula", str(state["estado"]))
        t.add_row("Ultimo comando enviado", str(state["ultimo_cmd"]))
        t.add_row("Ultimo update", str(state["ultimo_msg"]))
    return t


def render():
    return Group(tabla(), chart())


def on_message(client, userdata, msg):
    control = userdata["control"]
    with lock:
        if msg.topic == TOPIC_NIVEL:
            try:
                data = json.loads(msg.payload.decode())
                state["nivel"] = data.get("nivel")
                state["cm"] = data.get("cm")
                state["ultimo_msg"] = time.strftime("%H:%M:%S")
                if state["nivel"] is not None:
                    history.append(int(state["nivel"]))
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        elif msg.topic == TOPIC_ESTADO:
            state["estado"] = msg.payload.decode()

    if control and state["nivel"] is not None:
        if state["nivel"] < LOW and state["estado"] != "ABIERTA":
            client.publish(TOPIC_CMD, "ABRIR")
            with lock: state["ultimo_cmd"] = "ABRIR (auto)"
        elif state["nivel"] > HIGH and state["estado"] != "CERRADA":
            client.publish(TOPIC_CMD, "CERRAR")
            with lock: state["ultimo_cmd"] = "CERRAR (auto)"


def main():
    ap = argparse.ArgumentParser(description="Mini-SCADA (lab IoT)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--no-control", action="store_true",
                    help="solo monitorear, no enviar comandos")
    args = ap.parse_args()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="scada",
                         userdata={"control": not args.no_control})
    client.on_message = on_message
    client.connect(args.host, args.port, keepalive=60)
    client.subscribe([(TOPIC_NIVEL, 0), (TOPIC_ESTADO, 0)])
    client.loop_start()

    with Live(render(), refresh_per_second=4, console=console) as live:
        try:
            while True:
                live.update(render())
                time.sleep(0.25)
        except KeyboardInterrupt:
            pass
    client.loop_stop()


if __name__ == "__main__":
    main()
