import socket
import threading
import json
import time
import os
import subprocess
import sys

# Configuration
SERVER_IP = '192.168.1.100'  # Update with your Raspberry Pi's IP
SERVER_PORT = 8765
CLIENT_ID = None  # Will be set during startup

# Command execution handling
def execute_command(command, source_id):
    """Execute a command received from another client"""
    print(f"\nReceived command from {source_id}: {command}")
    
    # Parse the command
    cmd_parts = command.strip().split()
    if not cmd_parts:
        return "Empty command"
    
    main_cmd = cmd_parts[0].lower()
    
    # Handle different commands
    if main_cmd == "close":
        print("Received close command. Exiting...")
        # You might want to add confirmation here in a real implementation
        os._exit(0)
        
    elif main_cmd == "shutdown":
        print("Received shutdown command. Shutting down system...")
        # System shutdown - uncomment in actual use
        # if sys.platform == "win32":
        #     os.system("shutdown /s /t 10")
        # else:  # Linux/Mac
        #     os.system("sudo shutdown -h +1")
        return "Shutdown initiated"
        
    elif main_cmd == "restart":
        print("Received restart command. Restarting system...")
        # System restart - uncomment in actual use
        # if sys.platform == "win32":
        #     os.system("shutdown /r /t 10")
        # else:  # Linux/Mac
        #     os.system("sudo reboot")
        return "Restart initiated"
        
    elif main_cmd == "exec" and len(cmd_parts) > 1:
        # Execute arbitrary command - BE CAREFUL WITH THIS!
        # This can be a security risk if not properly secured
        cmd_to_run = " ".join(cmd_parts[1:])
        print(f"Executing: {cmd_to_run}")
        try:
            result = subprocess.check_output(
                cmd_to_run, 
                shell=True, 
                stderr=subprocess.STDOUT,
                timeout=10
            ).decode('utf-8')
            return f"Command executed:\n{result[:500]}" # Limit output size
        except subprocess.CalledProcessError as e:
            return f"Command failed with code {e.returncode}: {e.output.decode('utf-8')[:500]}"
        except subprocess.TimeoutExpired:
            return "Command timed out after 10 seconds"
            
    elif main_cmd == "echo":
        # Simple echo command
        echo_text = " ".join(cmd_parts[1:]) if len(cmd_parts) > 1 else ""
        return f"Echo: {echo_text}"
        
    elif main_cmd == "status":
        # Return system status
        import platform
        status = {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": platform.python_version(),
        }
        return f"Status: {json.dumps(status)}"
        
    else:
        return f"Unknown command: {main_cmd}"

def handle_server_messages(client_socket):
    """Handle incoming messages from the server"""
    while True:
        try:
            data = client_socket.recv(1024).decode('utf-8')
            if not data:
                print("Connection to server lost.")
                break
                
            message = json.loads(data)
            
            if message["type"] == "command":
                # Execute command from another client
                source_id = message["source_id"]
                command = message["command"]
                
                # Execute the command
                result = execute_command(command, source_id)
                
                # Send result back to server
                response = {
                    "type": "command_result",
                    "target_id": source_id,
                    "result": result
                }
                client_socket.send(json.dumps(response).encode('utf-8'))
                
            elif message["type"] == "client_list_update":
                # Update the local list of available clients
                clients = message["clients"]
                print("\nConnected clients updated:")
                for client in clients:
                    if client != CLIENT_ID:  # Don't show self
                        print(f"- {client}")
                print(f"\n[{CLIENT_ID}]> ", end="")
                sys.stdout.flush()  # Make sure prompt is displayed
                
            elif message["type"] == "command_sent":
                # Confirmation that command was sent to target
                print(f"Command sent to {message['target_id']}")
                
            elif message["type"] == "command_error":
                # Error sending command to target
                print(f"Error sending command to {message['target_id']}: {message['error']}")
                
            elif message["type"] == "command_result":
                # Result from a command we sent
                print(f"\nResult from {message['source_id']}:")
                print(message["result"])
                print(f"\n[{CLIENT_ID}]> ", end="")
                sys.stdout.flush()
                
        except json.JSONDecodeError:
            print("Received invalid data from server")
        except Exception as e:
            print(f"Error receiving message: {e}")
            break
    
    print("Disconnected from server")
    os._exit(1)  # Exit application on disconnect

def register_client(client_socket, client_id):
    """Register this client with the server"""
    registration = {
        "type": "register",
        "client_id": client_id
    }
    client_socket.send(json.dumps(registration).encode('utf-8'))
    
    # Wait for confirmation
    data = client_socket.recv(1024).decode('utf-8')
    response = json.loads(data)
    
    if response["type"] == "registration_confirm" and response["status"] == "success":
        print(f"Successfully registered as {client_id}")
        print("Other connected clients:")
        for other_client in response["connected_clients"]:
            if other_client != client_id:  # Don't show self
                print(f"- {other_client}")
        return True
    else:
        print(f"Registration failed: {response.get('message', 'Unknown error')}")
        return False

def send_command(client_socket, target_id, command):
    """Send a command to another client through the server"""
    command_msg = {
        "type": "command",
        "source_id": CLIENT_ID,
        "target_id": target_id,
        "command": command
    }
    client_socket.send(json.dumps(command_msg).encode('utf-8'))

def request_client_list(client_socket):
    """Request an updated list of connected clients"""
    request = {
        "type": "list_clients"
    }
    client_socket.send(json.dumps(request).encode('utf-8'))

def interactive_shell(client_socket):
    """Provide an interactive shell for sending commands"""
    print("\nCommand format: <target_client_id> <command>")
    print("Special commands:")
    print("  .list - List connected clients")
    print("  .exit - Exit this client")
    print("  .help - Show this help message")
    print("\nExample: client2 shutdown")
    print("         client3 echo Hello from client1\n")
    
    while True:
        try:
            user_input = input(f"[{CLIENT_ID}]> ")
            
            if not user_input.strip():
                continue
                
            if user_input.startswith("."):
                # Special command
                cmd = user_input[1:].strip().lower()
                
                if cmd == "list":
                    request_client_list(client_socket)
                elif cmd == "exit":
                    print("Exiting...")
                    break
                elif cmd == "help":
                    print("\nCommand format: <target_client_id> <command>")
                    print("Special commands:")
                    print("  .list - List connected clients")
                    print("  .exit - Exit this client")
                    print("  .help - Show this help message")
                else:
                    print(f"Unknown special command: {cmd}")
            else:
                # Regular command to send to another client
                parts = user_input.strip().split(None, 1)
                if len(parts) < 2:
                    print("Invalid format. Use: <target_client_id> <command>")
                    continue
                    
                target_id, command = parts
                send_command(client_socket, target_id, command)
                
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")
    
    # Clean exit
    try:
        client_socket.close()
    except:
        pass
    os._exit(0)

def start_client():
    """Start the client application"""
    global CLIENT_ID
    
    # Get client ID from user or system
    if len(sys.argv) > 1:
        CLIENT_ID = sys.argv[1]
    else:
        import platform
        default_id = f"{platform.node()}"
        user_input = input(f"Enter client ID [default: {default_id}]: ").strip()
        CLIENT_ID = user_input if user_input else default_id
    
    # Connect to server
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    try:
        print(f"Connecting to server at {SERVER_IP}:{SERVER_PORT}...")
        client_socket.connect((SERVER_IP, SERVER_PORT))
        
        # Register with server
        if register_client(client_socket, CLIENT_ID):
            # Start thread to handle incoming messages
            recv_thread = threading.Thread(target=handle_server_messages, args=(client_socket,))
            recv_thread.daemon = True
            recv_thread.start()
            
            # Start interactive shell
            interactive_shell(client_socket)
        
    except ConnectionRefusedError:
        print("Connection refused. Is the server running?")
    except Exception as e:
        print(f"Error connecting to server: {e}")
    finally:
        try:
            client_socket.close()
        except:
            pass

if __name__ == "__main__":
    start_client()
