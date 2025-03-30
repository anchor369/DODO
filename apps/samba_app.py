import os
import sys
import time
import socket
import subprocess
import threading
import platform
import pystray
from PIL import Image, ImageDraw
import ctypes
import pythoncom
import win32com.client
import tkinter as tk
from tkinter import messagebox

class SambaConnector:
    def __init__(self):
        self.server_ip = "192.168.9.63" #FIB-By-Server
        self.share_name = "Shared"
        self.username = "aadish" #FIB
        self.password = "1234" #FIB
        self.mapped_drive_letter = "S:"
        self.check_interval = 30

        self.is_connected = False
        self.stop_event = threading.Event()
        self.icon = self.create_tray_icon()

        self.monitor_thread = threading.Thread(target=self.connection_monitor, daemon=True)
        self.monitor_thread.start()

    def create_tray_icon(self):
        icon_image = self.create_icon_image(connected=False)

        menu = (
            pystray.MenuItem('Status', lambda: self.show_status(self.icon, None)),
            pystray.MenuItem('Open Shared Folder', lambda: self.open_folder(self.icon, None)),
            pystray.MenuItem('Connect', lambda: self.connect_share(self.icon, None)),
            pystray.MenuItem('Disconnect', lambda: self.disconnect_share(self.icon, None)),
            pystray.MenuItem('Exit', lambda: self.exit_app(self.icon, None))
        )

        icon = pystray.Icon("SambaConnector", icon_image, "Samba Auto-Connector", menu)
        icon.on_click = self.on_icon_click
        return icon

    def create_icon_image(self, connected=False):
        width, height = 64, 64
        color = (0, 128, 0) if connected else (200, 0, 0)

        image = Image.new('RGB', (width, height), (255, 255, 255))
        dc = ImageDraw.Draw(image)
        dc.ellipse((10, 10, width-10, height-10), fill=color)
        return image

    def update_icon(self, connected=False):
        self.icon.icon = self.create_icon_image(connected)
        self.icon.title = f"Samba Auto-Connector ({'Connected' if connected else 'Disconnected'})"

    def on_icon_click(self, icon, button):
        if button == 1:
            if self.is_connected:
                self.open_folder()
            else:
                self.connect_share()

    def show_status(self, icon, item):
        status = "Connected" if self.is_connected else "Disconnected"
        message = f"Status: {status}\nServer: {self.server_ip}\nShare: {self.share_name}"
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("Samba Connector Status", message)
        root.destroy()

    def open_folder(self, icon=None, item=None):
        if self.is_connected:
            os.system(f'explorer {self.mapped_drive_letter}\\')
        else:
            self.show_notification("Not connected. Attempting to connect...")
            self.connect_share()

    def connect_share(self, icon=None, item=None):
        try:
            self.disconnect_share(quiet=True)
            share_path = f"\\\\{self.server_ip}\\{self.share_name}"
            cmd = f'net use {self.mapped_drive_letter} {share_path} /user:{self.username} {self.password} /persistent:no'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            if result.returncode == 0:
                self.is_connected = True
                self.update_icon(connected=True)
                self.show_notification(f"Connected to {self.share_name} on {self.server_ip}")
            else:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                self.show_notification(f"Failed to connect: {error_msg}")
        except Exception as e:
            self.show_notification(f"Connection error: {str(e)}")

    def disconnect_share(self, icon=None, item=None, quiet=False):
        try:
            subprocess.run(f'net use {self.mapped_drive_letter} /delete /y', shell=True, capture_output=True)
            self.is_connected = False
            self.update_icon(connected=False)
            if not quiet:
                self.show_notification("Disconnected from Samba share")
        except Exception as e:
            if not quiet:
                self.show_notification(f"Error during disconnect: {str(e)}")

    def connection_monitor(self):
        while not self.stop_event.is_set():
            if self.is_server_reachable() and not self.is_connected:
                self.connect_share()
            elif not self.is_server_reachable() and self.is_connected:
                self.disconnect_share()
            time.sleep(self.check_interval)

    def is_server_reachable(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((self.server_ip, 445))
            sock.close()
            return result == 0
        except:
            return False

    def show_notification(self, message):
        try:
            pythoncom.CoInitialize()
            wshell = win32com.client.Dispatch("WScript.Shell")
            wshell.Popup(message, 0, "Samba Connector", 0)
        except:
            print(message)

    def exit_app(self, icon=None, item=None):
        self.disconnect_share(quiet=True)
        self.stop_event.set()
        self.icon.stop()

def create_mutex():
    try:
        mutex = ctypes.windll.kernel32.CreateMutexA(None, False, b"SambaConnectorPythonApp")
        if ctypes.windll.kernel32.GetLastError() == 183:
            messagebox.showinfo("Samba Connector", "Application is already running.")
            sys.exit(0)
        return mutex
    except:
        return None

def main():
    if platform.system() != "Windows":
        print("This application is designed for Windows only.")
        sys.exit(1)

    create_mutex()
    app = SambaConnector()
    app.icon.run()

if __name__ == "__main__":
    main()