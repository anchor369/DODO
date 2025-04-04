#########try#########
import socket

# Create a socket
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

# Configure the server
SERVER_IP = '0.0.0.0'  # Listen on all interfaces
SERVER_PORT = 8765

# Bind and listen
server.bind((SERVER_IP, SERVER_PORT))
server.listen(5)
print(f"Server listening on {SERVER_IP}:{SERVER_PORT}...")

try:
    # Accept a connection
    client_sock, client_addr = server.accept()
    print(f"Connection from {client_addr}")
    
    # Send test message
    client_sock.send("Connection successful!".encode('utf-8'))
    
    # Receive response
    response = client_sock.recv(1024).decode('utf-8')
    print(f"Client response: {response}")
    
    # Close connection
    client_sock.close()
    
except KeyboardInterrupt:
    print("Server shutting down...")
finally:
    server.close()


###############################################
import socket
import threading
import json
import time
from datetime import datetime

# Configuration
SERVER_IP = '0.0.0.0'  # Listen on all interfaces
SERVER_PORT = 8765
CLIENT_REGISTRY = {}  # Store connected clients {client_id: (ip, port, socket)}

# Command execution functions
def log_command(source_id, target_id, command):
    """Log commands to a file for auditing"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {source_id} -> {target_id}: {command}\n"
    
    with open("command_log.txt", "a") as log_file:
        log_file.write(log_entry)

def handle_client_connection(client_socket, client_address):
    """Handle incoming client connections and messages"""
    client_id = None
    
    try:
        # First message should be registration
        data = client_socket.recv(1024).decode('utf-8')
        message = json.loads(data)
        
        if message["type"] == "register":
            client_id = message["client_id"]
            print(f"Client registered: {client_id} from {client_address}")
            
            # Add to registry with socket for direct communication
            CLIENT_REGISTRY[client_id] = (client_address[0], client_address[1], client_socket)
            
            # Send confirmation
            response = {
                "type": "registration_confirm",
                "status": "success",
                "message": f"Registered as {client_id}",
                "connected_clients": list(CLIENT_REGISTRY.keys())
            }
            client_socket.send(json.dumps(response).encode('utf-8'))
            
            # Main message loop
            while True:
                try:
                    data = client_socket.recv(1024).decode('utf-8')
                    if not data:
                        break  # Client disconnected
                    
                    message = json.loads(data)
                    
                    if message["type"] == "command":
                        source_id = message["source_id"]
                        target_id = message["target_id"]
                        command = message["command"]
                        
                        print(f"Command from {source_id} to {target_id}: {command}")
                        log_command(source_id, target_id, command)
                        
                        # Forward to target client
                        if target_id in CLIENT_REGISTRY:
                            try:
                                target_socket = CLIENT_REGISTRY[target_id][2]
                                forward_message = {
                                    "type": "command",
                                    "source_id": source_id,
                                    "command": command
                                }
                                target_socket.send(json.dumps(forward_message).encode('utf-8'))
                                
                                # Send confirmation to source
                                confirm = {
                                    "type": "command_sent",
                                    "target_id": target_id,
                                    "status": "success"
                                }
                                client_socket.send(json.dumps(confirm).encode('utf-8'))
                            except Exception as e:
                                # Target client likely disconnected
                                error_msg = {
                                    "type": "command_error",
                                    "target_id": target_id,
                                    "error": f"Failed to send: {str(e)}"
                                }
                                client_socket.send(json.dumps(error_msg).encode('utf-8'))
                                # Remove dead client from registry
                                if target_id in CLIENT_REGISTRY:
                                    del CLIENT_REGISTRY[target_id]
                        else:
                            # Target not found
                            error_msg = {
                                "type": "command_error",
                                "target_id": target_id,
                                "error": "Client not connected"
                            }
                            client_socket.send(json.dumps(error_msg).encode('utf-8'))
                    
                    elif message["type"] == "list_clients":
                        # Send list of connected clients
                        response = {
                            "type": "client_list",
                            "clients": list(CLIENT_REGISTRY.keys())
                        }
                        client_socket.send(json.dumps(response).encode('utf-8'))
                        
                except json.JSONDecodeError:
                    print(f"Invalid JSON from {client_id}")
                    continue
                    
        else:
            # First message wasn't registration
            client_socket.send(json.dumps({
                "type": "error",
                "message": "First message must be registration"
            }).encode('utf-8'))
            
    except Exception as e:
        print(f"Error handling client {client_id if client_id else 'unknown'}: {e}")
    finally:
        # Clean up when client disconnects
        if client_id and client_id in CLIENT_REGISTRY:
            del CLIENT_REGISTRY[client_id]
            print(f"Client disconnected: {client_id}")
        try:
            client_socket.close()
        except:
            pass

def broadcast_client_list():
    """Periodically broadcast the list of connected clients to all clients"""
    while True:
        if CLIENT_REGISTRY:
            client_list = {
                "type": "client_list_update",
                "clients": list(CLIENT_REGISTRY.keys())
            }
            message = json.dumps(client_list).encode('utf-8')
            
            # Make a copy to avoid "dictionary changed during iteration" errors
            clients_copy = dict(CLIENT_REGISTRY)
            for client_id, (_, _, sock) in clients_copy.items():
                try:
                    sock.send(message)
                except:
                    # Client probably disconnected, will be cleaned up in its thread
                    pass
        
        time.sleep(30)  # Update every 30 seconds

def start_server():
    """Start the command routing server"""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server.bind((SERVER_IP, SERVER_PORT))
        server.listen(10)
        print(f"Command Router Server started on {SERVER_IP}:{SERVER_PORT}")
        
        # Start client list broadcast thread
        broadcast_thread = threading.Thread(target=broadcast_client_list)
        broadcast_thread.daemon = True
        broadcast_thread.start()
        
        while True:
            client_sock, client_addr = server.accept()
            client_thread = threading.Thread(
                target=handle_client_connection,
                args=(client_sock, client_addr)
            )
            client_thread.daemon = True
            client_thread.start()
            
    except KeyboardInterrupt:
        print("Server shutting down...")
    except Exception as e:
        print(f"Server error: {e}")
    finally:
        server.close()

if __name__ == "__main__":
    start_server()
