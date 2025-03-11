#!/usr/bin/env python3
"""
GPT Client Application
Connects to the GPT file transfer server and allows sending commands
"""

import os
import socket
import json
import base64
import threading
import time
import platform
import sys
from pathlib import Path
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("GPTClient")

class GPTClientApp:
    """Client application to connect to the GPT file transfer network"""
    
    def _init_(self, server_ip, server_port=9999):
        """
        Initialize the client application
        
        Args:
            server_ip (str): IP address of the server
            server_port (int): Port of the server (default: 9999)
        """
        logger.info(f"Initializing client with server: {server_ip}:{server_port}")
        self.server_ip = server_ip
        self.server_port = server_port
        self.socket = None
        self.connected = False
        self.device_name = platform.node()  # Use computer name as device name
        
        # Get system info
        self.device_info = {
            "os": platform.system(),
            "os_version": platform.version(),
            "architecture": platform.machine(),
            "username": os.getlogin()
        }
        
        # Define download directory
        if platform.system() == "Windows":
            self.download_dir = Path(os.path.expanduser("~")) / "Downloads"
        else:
            self.download_dir = Path(os.path.expanduser("~")) / "Downloads"
        
        # Create downloads directory if it doesn't exist
        self.download_dir.mkdir(exist_ok=True)
        logger.info(f"Download directory set to: {self.download_dir}")
    
    def connect(self):
        """
        Connect to the server and register this device
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        logger.info(f"Attempting to connect to {self.server_ip}:{self.server_port}")
        try:
            # Create socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)  # Add timeout for connection
            self.socket.connect((self.server_ip, self.server_port))
            logger.info("Socket connection established")
            
            # Send registration information
            registration = {
                "device_name": self.device_name,
                "device_info": self.device_info
            }
            logger.info(f"Sending registration as: {self.device_name}")
            self.socket.send(json.dumps(registration).encode('utf-8'))
            
            # Get acknowledgment
            response_data = self.socket.recv(1024).decode('utf-8')
            logger.info(f"Registration response: {response_data}")
            response = json.loads(response_data)
            
            if response.get("status") == "registered":
                self.connected = True
                logger.info(f"Successfully registered with server as {self.device_name}")
                
                # Start heartbeat thread
                heartbeat_thread = threading.Thread(target=self._heartbeat, daemon=True)
                heartbeat_thread.start()
                logger.info("Heartbeat thread started")
                
                # Start listener thread
                listener_thread = threading.Thread(target=self._listen_for_commands, daemon=True)
                listener_thread.start()
                logger.info("Command listener thread started")
                
                return True
            else:
                logger.error(f"Registration failed: {response}")
                self.socket.close()
                return False
                
        except socket.timeout:
            logger.error("Connection timed out")
            if self.socket:
                self.socket.close()
            return False
        except ConnectionRefusedError:
            logger.error(f"Connection refused. Is the server running at {self.server_ip}:{self.server_port}?")
            if self.socket:
                self.socket.close()
            return False
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            if self.socket:
                self.socket.close()
            return False
    
    def _heartbeat(self):
        """Send periodic heartbeats to keep connection alive"""
        logger.info("Starting heartbeat thread")
        while self.connected:
            try:
                heartbeat = {
                    "type": "heartbeat",
                    "timestamp": time.time()
                }
                self.socket.send(json.dumps(heartbeat).encode('utf-8'))
                response_data = self.socket.recv(1024).decode('utf-8')
                response = json.loads(response_data)
                
                if response.get("status") != "ok":
                    logger.warning(f"Heartbeat failed: {response}")
                    self.connected = False
                    break
                else:
                    logger.debug("Heartbeat acknowledged")
            except Exception as e:
                logger.error(f"Heartbeat error: {str(e)}")
                self.connected = False
                break
                
            time.sleep(30)  # Send heartbeat every 30 seconds
        
        logger.info("Heartbeat thread terminated")
    
    def _listen_for_commands(self):
        """Listen for commands from the server"""
        logger.info("Starting command listener thread")
        while self.connected:
            try:
                data = self.socket.recv(8192).decode('utf-8')
                if not data:
                    logger.warning("Server closed connection")
                    self.connected = False
                    break
                
                logger.info(f"Received command from server: {data[:100]}...")
                message = json.loads(data)
                
                # Handle different command types
                if message.get("action") == "send_file":
                    self._handle_send_file(message)
                elif message.get("action") == "receive_file":
                    self._handle_receive_file(message)
                elif message.get("action") == "search_files":
                    self._handle_search_files(message)
                else:
                    logger.warning(f"Unknown command: {message}")
                    
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON received: {e}")
            except Exception as e:
                logger.error(f"Error handling command: {str(e)}")
                self.connected = False
                break
        
        logger.info("Command listener thread terminated")
    
    def _handle_send_file(self, message):
        """
        Handle request to send a file to the server
        
        Args:
            message (dict): Command message with file path
        """
        file_path = message.get("path")
        logger.info(f"Server requested file: {file_path}")
        
        try:
            path = Path(file_path)
            if not path.exists():
                logger.warning(f"File not found: {file_path}")
                response = {"status": "error", "message": f"File not found: {file_path}"}
            else:
                logger.info(f"Reading file: {path}")
                with open(path, 'rb') as f:
                    # For simplicity, we're sending the whole file at once
                    # In a real implementation, you'd chunk large files
                    file_data = base64.b64encode(f.read()).decode('utf-8')
                
                logger.info(f"Sending file data: {path.name} ({path.stat().st_size} bytes)")
                response = {
                    "status": "success",
                    "file_name": path.name,
                    "file_size": path.stat().st_size,
                    "file_data": file_data
                }
        except Exception as e:
            logger.error(f"Error preparing file: {str(e)}")
            response = {"status": "error", "message": str(e)}
            
        self.socket.send(json.dumps(response).encode('utf-8'))
    
    def _handle_receive_file(self, message):
        """
        Handle incoming file from the server
        
        Args:
            message (dict): Command message with file path and data
        """
        file_path = message.get("path")
        file_data = message.get("file_data")
        logger.info(f"Receiving file: {file_path}")
        
        try:
            # Save to downloads directory with original filename
            target_path = self.download_dir / Path(file_path).name
            
            logger.info(f"Saving file to: {target_path}")
            with open(target_path, 'wb') as f:
                f.write(base64.b64decode(file_data))
                
            response = {
                "status": "success",
                "message": f"File saved to {target_path}"
            }
            logger.info(f"File saved successfully: {target_path}")
            
        except Exception as e:
            logger.error(f"Error saving file: {str(e)}")
            response = {"status": "error", "message": str(e)}
            
        self.socket.send(json.dumps(response).encode('utf-8'))
    
    def _handle_search_files(self, message):
        """
        Search for files matching search terms
        
        Args:
            message (dict): Command message with search terms
        """
        search_terms = message.get("terms", "")
        logger.info(f"Searching for files matching: {search_terms}")
        
        try:
            results = []
            
            # Simple file search in home directory
            home_dir = Path.home()
            logger.info(f"Searching in home directory: {home_dir}")
            
            for root, dirs, files in os.walk(str(home_dir)):
                for file in files:
                    if all(term.lower() in file.lower() for term in search_terms.split()):
                        full_path = Path(root) / file
                        results.append({
                            "path": str(full_path),
                            "name": file,
                            "size": full_path.stat().st_size,
                            "modified": full_path.stat().st_mtime
                        })
                        # Limit results to prevent huge responses
                        if len(results) >= 50:
                            break
                            
                if len(results) >= 50:
                    break
            
            logger.info(f"Found {len(results)} matching files")
            response = {
                "status": "success",
                "files": results
            }
            
        except Exception as e:
            logger.error(f"Error searching files: {str(e)}")
            response = {"status": "error", "message": str(e)}
            
        self.socket.send(json.dumps(response).encode('utf-8'))
    
    def send_command(self, command):
        """
        Send a natural language command to the server
        
        Args:
            command (str): The natural language command
            
        Returns:
            dict: Server response
        """
        if not self.connected:
            logger.warning("Not connected to server")
            return {"status": "error", "message": "Not connected to server"}
            
        message = {
            "type": "command",
            "command": command
        }
        
        try:
            logger.info(f"Sending command: {command}")
            self.socket.send(json.dumps(message).encode('utf-8'))
            
            logger.info("Waiting for response...")
            response_data = self.socket.recv(8192).decode('utf-8')
            response = json.loads(response_data)
            logger.info(f"Received response with status: {response.get('status', 'unknown')}")
            
            return response
            
        except Exception as e:
            logger.error(f"Error sending command: {str(e)}")
            self.connected = False
            return {"status": "error", "message": f"Connection error: {str(e)}"}
    
    def disconnect(self):
        """Disconnect from the server"""
        logger.info("Disconnecting from server")
        self.connected = False
        if self.socket:
            try:
                self.socket.close()
                logger.info("Socket closed")
            except Exception as e:
                logger.error(f"Error closing socket: {str(e)}")

def main():
    """Main client application entry point"""
    print("\n=== GPT File Transfer Client ===\n")
    
    if len(sys.argv) < 2:
        print("Usage: python client_app.py <server_ip>")
        print("Example: python client_app.py 192.168.1.100")
        return
    
    # Get server IP from command line arguments
    server_ip = sys.argv[1]
    
    # Create client application
    print(f"Connecting to server at {server_ip}...")
    client = GPTClientApp(server_ip)
    
    # Try to connect
    if not client.connect():
        print("Failed to connect to server. Please check the server address and ensure the server is running.")
        return
    
    print("\n=== Connected to GPT network ===")
    print("Type 'exit' to quit.")
    print("\nExample commands:")
    print("- Send my document.txt to my laptop")
    print("- Find photos in my Downloads folder")
    print("- Move my presentation.pptx from my desktop to my tablet")
    
    try:
        while True:
            command = input("\nEnter command: ")
            if command.lower() in ('exit', 'quit'):
                break
            
            if command.strip():
                response = client.send_command(command)
                print("\nResponse:")
                print(json.dumps(response, indent=2))
            
    except KeyboardInterrupt:
        print("\nExiting client application")
    finally:
        client.disconnect()
        print("Disconnected from server")

if _name_ == "_main_":
    main()
