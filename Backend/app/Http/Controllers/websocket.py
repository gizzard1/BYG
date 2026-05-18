import asyncio
from websockets.asyncio.client import connect

import sys
import json


def obtener_comando() -> str:
    if len(sys.argv) > 1 and sys.argv[1]:
        return sys.argv[1]

    stdin_content = sys.stdin.read().strip()
    if not stdin_content:
        raise ValueError("No se recibió comando para websocket")

    try:
        data = json.loads(stdin_content)
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            return data.get("command") or data.get("msg")
    except json.JSONDecodeError:
        return stdin_content

    raise ValueError("No se pudo obtener el comando para websocket")

async def send_message(msg):
    # Connect to a WebSocket server
    async with connect("ws://192.168.100.17:81") as websocket:
        await websocket.send(msg)


if __name__ == "__main__":
    command = obtener_comando()
    asyncio.run(send_message(command))