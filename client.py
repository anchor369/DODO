import asyncio
import websockets
import pyautogui

SERVER_IP = "192.168.84.138"  # 🔹 Replace with your main PC's local IP
SERVER_PORT = 8000
WEBSOCKET_URL = f"ws://{SERVER_IP}:{SERVER_PORT}/ws"

async def listen():
    async with websockets.connect(WEBSOCKET_URL) as websocket:
        print("Connected to server. Waiting for commands...")

        while True:
            command = await websocket.recv()
            print(f"Received command: {command}")

            # Process the command
            if command == "copy":
                pyautogui.hotkey("ctrl", "c")
            elif command == "paste":
                pyautogui.hotkey("ctrl", "v")
            elif command == "left":
                pyautogui.moveRel(-50, 0)
            elif command == "right":
                pyautogui.moveRel(50, 0)
            elif command == "up":
                pyautogui.moveRel(0, -50)
            elif command == "down":
                pyautogui.moveRel(0, 50)
            elif command.startswith("type:"):
                text = command.split("type:")[1]
                pyautogui.write(text)

asyncio.run(listen())