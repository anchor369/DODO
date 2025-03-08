from fastapi import FastAPI, WebSocket
import json

app = FastAPI()

# Store connected clients
connected_clients = []

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            print(f"Received command: {data}")

            # Broadcast command to all clients
            for client in connected_clients:
                if client != websocket:
                    await client.send_text(data)
    except Exception as e:
        print(f"Connection closed: {e}")
    finally:
        connected_clients.remove(websocket)
