"""Testa o chat novo da Kick (Centrifugo) sem token: conecta, assina e mostra o que chega por ~20 s."""
import json
import sys
import time

import websocket

URL = "wss://realtime.us-east-1.platform.kick.com/connection/websocket"
sala = sys.argv[1] if len(sys.argv) > 1 else "16543790"

ws = websocket.create_connection(URL, timeout=15, header=["Origin: https://kick.com"])
ws.send(json.dumps({"connect": {"name": "js"}, "id": 1}) + "\n" +
        json.dumps({"subscribe": {"channel": f"chatrooms.{sala}.v2", "flag": 1}, "id": 2}))
fim = time.time() + 20
n = 0
while time.time() < fim:
    try:
        raw = ws.recv()
    except Exception as e:  # noqa: BLE001
        print("recv:", e)
        break
    for linha in raw.splitlines():
        if linha.strip() in ("", "{}"):
            ws.send("{}")  # pong
            continue
        n += 1
        if n <= 6:
            print(linha[:600])
print("total de frames:", n)
ws.close()
