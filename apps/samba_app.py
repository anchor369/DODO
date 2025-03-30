import os
import sys
import time
import socket
import subprocess
import threading
import platform
import pystray
import shutil
from PIL import Image, ImageDraw
import ctypes
import pythoncom
import win32com.client
import tkinter as tk
from tkinter import messagebox, simpledialog, filedialog

class SambaConnector:
    def __init__(self):
        self.server_ip = "192.168.9.63" #FIB-By-Server
        self.share_name = "Shared"
        self.username = "aadish" #FIB
        self.password = "1234" #FIB
        self.mapped_drive_letter = "S:"
        self.check_interval = 30
        self.user_directory = None
        self.local_sync_path = None
        self.sync_enabled = False
        self.last_sync_time = None
        self.sync_interval = 300  # 5 minutes

        self.is_connected = False
        self.stop_event = threading.Event()
        
        # Ask for username directory and local sync path on startup
        self.prompt_for_user_directory()
        self.prompt_for_local_sync_path()
        
        self.icon = self.create_tray_icon()
        
        self.monitor_thread = threading.Thread(target=self.connection_monitor, daemon=True)
        self.sync_thread = threading.Thread(target=self.sync_monitor, daemon=True)
        self.monitor_thread.start()
        self.sync_thread.start()

    def prompt_for_user_directory(self):
        root = tk.Tk()
        root.withdraw()
        self.user_directory = simpledialog.askstring("User Directory", "Enter username for directory:", initialvalue=self.username)
        root.destroy()
        if not self.user_directory:
            self.user_directory = self.username  # Use default if none provided

    def prompt_for_local_sync_path(self):
        root = tk.Tk()
        root.withdraw()
        
        # Default path is username folder on D: drive, fallback to E:
        default_path = f"D:\\{self.user_directory}"
        if not os.path.exists("D:\\"):
            default_path = f"E:\\{self.user_directory}"
        
        message = "Select local folder for syncing files\n(Cancel to disable auto-sync)"
        self.local_sync_path = filedialog.askdirectory(title=message)
        
        if not self.local_sync_path:
            # If no directory selected, suggest default path
            result = messagebox.askyesno("Sync Location", 
                                       f"No directory selected. Use {default_path}?")
            if result:
                self.local_sync_path = default_path
                # Create default directory if it doesn't exist
                if not os.path.exists(self.local_sync_path):
                    try:
                        os.makedirs(self.local_sync_path)
                    except Exception as e:
                        messagebox.showerror("Error", f"Could not create directory: {e}")
                        self.local_sync_path = None
                self.sync_enabled = True
            else:
                self.sync_enabled = False
                self.local_sync_path = None
        else:
            self.sync_enabled = True
            
        root.destroy()

    def create_tray_icon(self):
        icon_image = self.create_icon_image(connected=False)

        menu = (
            pystray.MenuItem('Status', lambda: self.show_status(self.icon, None)),
            pystray.MenuItem('Open Shared Folder', lambda: self.open_folder(self.icon, None)),
            pystray.MenuItem('Open User Directory', lambda: self.open_user_directory(self.icon, None)),
            pystray.MenuItem('Open Local Sync Folder', lambda: self.open_local_folder(self.icon, None)),
            pystray.MenuItem('Change User Directory', lambda: self.change_user_directory(self.icon, None)),
            pystray.MenuItem('Change Local Sync Folder', lambda: self.change_local_sync_path(self.icon, None)),
            pystray.MenuItem('Sync Now', lambda: self.sync_files_now(self.icon, None)),
            pystray.MenuItem('Toggle Auto-Sync', lambda: self.toggle_sync(self.icon, None)),
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
        sync_status = "Sync ON" if self.sync_enabled else "Sync OFF"
        self.icon.title = f"Samba Auto-Connector ({'Connected' if connected else 'Disconnected'}) - {sync_status}"

    def on_icon_click(self, icon, button):
        if button == 1:
            if self.is_connected:
                self.open_folder()
            else:
                self.connect_share()

    def show_status(self, icon, item):
        status = "Connected" if self.is_connected else "Disconnected"
        sync_status = "Enabled" if self.sync_enabled else "Disabled"
        last_sync = self.last_sync_time.strftime("%Y-%m-%d %H:%M:%S") if self.last_sync_time else "Never"
        
        message = (f"Status: {status}\n"
                  f"Server: {self.server_ip}\n"
                  f"Share: {self.share_name}\n"
                  f"User Directory: {self.user_directory}\n"
                  f"Local Sync Folder: {self.local_sync_path or 'Not Set'}\n"
                  f"Auto-Sync: {sync_status}\n"
                  f"Last Sync: {last_sync}")
        
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

    def open_user_directory(self, icon=None, item=None):
        if self.is_connected:
            user_dir_path = os.path.join(self.mapped_drive_letter + "\\", self.user_directory)
            if os.path.exists(user_dir_path):
                os.system(f'explorer "{user_dir_path}"')
            else:
                self.show_notification(f"User directory does not exist. Creating it now...")
                self.create_user_directory()
                os.system(f'explorer "{user_dir_path}"')
        else:
            self.show_notification("Not connected. Attempting to connect...")
            self.connect_share()

    def open_local_folder(self, icon=None, item=None):
        if self.local_sync_path and os.path.exists(self.local_sync_path):
            os.system(f'explorer "{self.local_sync_path}"')
        else:
            self.show_notification("Local sync folder not set or doesn't exist")
            self.change_local_sync_path()

    def change_user_directory(self, icon=None, item=None):
        root = tk.Tk()
        root.withdraw()
        new_dir = simpledialog.askstring("Change User Directory", 
                                         "Enter new username for directory:", 
                                         initialvalue=self.user_directory)
        root.destroy()
        
        if new_dir and new_dir != self.user_directory:
            self.user_directory = new_dir
            self.show_notification(f"User directory changed to: {self.user_directory}")
            if self.is_connected:
                self.create_user_directory()
                
            # Ask if local path should be updated too
            root = tk.Tk()
            root.withdraw()
            update_local = messagebox.askyesno("Update Local Path", 
                                             f"Update local sync path to match new username?\nCurrent: {self.local_sync_path}")
            root.destroy()
            
            if update_local:
                # Create path with same drive but new username
                if self.local_sync_path:
                    drive = os.path.splitdrive(self.local_sync_path)[0]
                    new_path = os.path.join(drive + "\\", self.user_directory)
                    self.local_sync_path = new_path
                    
                    # Create directory if it doesn't exist
                    if not os.path.exists(self.local_sync_path):
                        try:
                            os.makedirs(self.local_sync_path)
                            self.show_notification(f"Created local directory: {self.local_sync_path}")
                        except Exception as e:
                            self.show_notification(f"Failed to create local directory: {str(e)}")

    def change_local_sync_path(self, icon=None, item=None):
        root = tk.Tk()
        root.withdraw()
        new_path = filedialog.askdirectory(title="Select new local sync folder", 
                                           initialdir=self.local_sync_path)
        root.destroy()
        
        if new_path:
            self.local_sync_path = new_path
            self.sync_enabled = True
            self.show_notification(f"Local sync path changed to: {self.local_sync_path}")
        elif new_path == "":  # Empty string when dialog is cancelled
            if messagebox.askyesno("Disable Sync", "Do you want to disable auto-sync?"):
                self.sync_enabled = False
                self.show_notification("Auto-sync disabled")
            
        self.update_icon(self.is_connected)

    def toggle_sync(self, icon=None, item=None):
        if not self.local_sync_path:
            self.show_notification("Please set a local sync folder first")
            self.change_local_sync_path()
            return
            
        self.sync_enabled = not self.sync_enabled
        self.update_icon(self.is_connected)
        status = "enabled" if self.sync_enabled else "disabled"
        self.show_notification(f"Auto-sync {status}")

    def sync_files_now(self, icon=None, item=None):
        if not self.is_connected:
            self.show_notification("Not connected. Attempting to connect...")
            self.connect_share()
            return
            
        if not self.local_sync_path:
            self.show_notification("Local sync folder not set")
            self.change_local_sync_path()
            return
            
        self.show_notification("Starting file synchronization...")
        self.sync_files()

    def sync_monitor(self):
        while not self.stop_event.is_set():
            if self.sync_enabled and self.is_connected:
                self.sync_files()
            time.sleep(self.sync_interval)

    def sync_files(self):
        try:
            if not self.is_connected or not self.sync_enabled or not self.local_sync_path:
                return False
                
            source_dir = os.path.join(self.mapped_drive_letter + "\\", self.user_directory)
            if not os.path.exists(source_dir):
                self.create_user_directory()
                if not os.path.exists(source_dir):
                    return False
            
            # Create local directory if it doesn't exist
            if not os.path.exists(self.local_sync_path):
                os.makedirs(self.local_sync_path)
            
            # Count files before sync
            files_before = len([f for f in os.listdir(self.local_sync_path) 
                              if os.path.isfile(os.path.join(self.local_sync_path, f))])
            
            # Copy all files from network to local
            copied_count = 0
            for item in os.listdir(source_dir):
                source_item = os.path.join(source_dir, item)
                dest_item = os.path.join(self.local_sync_path, item)
                
                # Only copy files, not directories
                if os.path.isfile(source_item):
                    # Check if file exists and is newer on the server
                    copy_file = False
                    if not os.path.exists(dest_item):
                        copy_file = True
                    else:
                        src_mtime = os.path.getmtime(source_item)
                        dest_mtime = os.path.getmtime(dest_item)
                        if src_mtime > dest_mtime:
                            copy_file = True
                    
                    if copy_file:
                        shutil.copy2(source_item, dest_item)
                        copied_count += 1
            
            self.last_sync_time = time.localtime()
            
            # Only notify if files were copied
            if copied_count > 0:
                self.show_notification(f"Synchronized {copied_count} files to local folder")
            
            return True
            
        except Exception as e:
            self.show_notification(f"Sync error: {str(e)}")
            return False

    def create_user_directory(self):
        if not self.is_connected:
            return False
            
        try:
            user_dir_path = os.path.join(self.mapped_drive_letter + "\\", self.user_directory)
            if not os.path.exists(user_dir_path):
                os.makedirs(user_dir_path)
                self.show_notification(f"Created directory: {self.user_directory}")
                return True
            return True  # Directory already exists
        except Exception as e:
            self.show_notification(f"Failed to create directory: {str(e)}")
            return False

    def connect_share(self, icon=None, item=None):
        try:
            self.disconnect_share(quiet=True)
            share_path = f"\\\\{self.server_ip}\\{self.share_name}"
            cmd = f'net use {self.mapped_drive_letter} {share_path} /user:{self.username} {self.password} /persistent:no'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            if result.returncode == 0:
                self.is_connected = True
                self.update_icon(connected=True)
                self.create_user_directory()  # Create user directory after connection
                
                # Sync files immediately after connect
                if self.sync_enabled and self.local_sync_path:
                    self.sync_files()
                    
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