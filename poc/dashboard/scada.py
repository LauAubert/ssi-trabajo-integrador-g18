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
CHART_H = 8                 # alto del grafico, en filas de texto
PARTS = " ▁▂▃▄▅▆▇█"         # 0..8 octavos de bloque (relleno desde abajo)

console = Console()
state = {"nivel": None, "cm": None, "estado": "?", "ultimo_cmd": "-",
         "ultimo_msg": "-"}
history = deque(maxlen=HIST_MAX)
lock = threading.Lock()


def chart():
    """Grafico de columnas (alto CHART_H filas) del nivel historico."""
    with lock:
        vals = list(history)
    if not vals:
        return Panel("esperando datos del sensor...",
                     title="Nivel del tanque — histórico", border_style="cyan")

    # nivel de cada muestra expresado en octavos de celda (resolucion CHART_H*8)
    levels = [min(CHART_H * 8, max(0, round(v / 100 * CHART_H * 8))) for v in vals]
    filas = []
    for r in range(CHART_H - 1, -1, -1):        # de arriba (100%) hacia abajo (0%)
        base = r * 8
        linea = ""
        for lv in levels:
            f = lv - base
            linea += "█" if f >= 8 else (" " if f <= 0 else PARTS[f])
        lbl = "100" if r == CHART_H - 1 else ("  0" if r == 0 else "   ")
        filas.append(f"{lbl} ┤[green]{linea}[/green]")

    eje = "    └" + "─" * len(vals)
    actual, mn, mx = vals[-1], min(vals), max(vals)
    pie = (f"       actual: [bold]{actual}%[/bold]   min: {mn}%   max: {mx}%"
           f"   ({len(vals)} muestras · ~2s c/u)")
    cuerpo = "\n".join(filas) + "\n" + eje + "\n" + pie
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
    # Fase de mitigacion: TLS + credenciales (broker endurecido, puerto 8883)
    ap.add_argument("--tls", action="store_true", help="conectar por TLS")
    ap.add_argument("--ca", help="ruta al ca.crt para validar el broker")
    ap.add_argument("--user", help="usuario MQTT")
    ap.add_argument("--password", help="password MQTT")
    ap.add_argument("--insecure-tls", action="store_true",
                    help="no validar el certificado (solo si hay problemas "
                         "de hostname; sigue cifrando)")
    args = ap.parse_args()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="scada",
                         userdata={"control": not args.no_control})
    client.on_message = on_message
    if args.user:
        client.username_pw_set(args.user, args.password)
    if args.tls:
        client.tls_set(ca_certs=args.ca)      # ca_certs=None usa el store del SO
        if args.insecure_tls:
            client.tls_insecure_set(True)
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
