# Updated server.py section to avoid LLMChain deprecation warning
import os
import socket
import threading
import json
import base64
import time
from pathlib import Path
import shutil
from langchain.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema.runnable import RunnableSequence

# Configure Gemini (or other LLM)
os.environ["GOOGLE_API_KEY"] = "AIzaSyCK6YT332KT79i2JvgJ6Jjes76R2I1Dtk8"
llm = ChatGoogleGenerativeAI(model="gemini-pro")

# Base directory for file storage on the server
BASE_DIR = Path("/Desktop")
BASE_DIR.mkdir(exist_ok=True)

# Device registry
DEVICES = {}

# Command template for interpreting natural language
command_template = PromptTemplate(
    input_variables=["command", "available_devices"],
    template="""
    Analyze this file operation command and extract the relevant information:
    Command: {command}
    Available devices: {available_devices}
    
    Return a JSON with:
    1. operation: [transfer_file, find_file, open_application, list_files, create_backup]
    2. source_device: the device where the file is currently located
    3. target_device: the device where the file should be moved/opened (if applicable)
    4. file_path: path to the file or directory
    5. application: application to open (if applicable)
    6. search_terms: terms to search for (if applicable)
    
    Only include fields that are relevant to the operation.
    """
)

# Create a RunnableSequence instead of LLMChain
command_chain = RunnableSequence(
    command_template,
    llm
)

# The rest of the file processing function
def process_command(command, available_devices):
    """Process natural language command using modern LangChain approach"""
    # Convert list of devices to string
    devices_str = ", ".join(available_devices)
    
    # Execute the chain with the input
    result = command_chain.invoke({
        "command": command,
        "available_devices": devices_str
    })
    
    # Extract the content from the result
    if hasattr(result, 'content'):
        # If result is an AIMessage or similar object
        return result.content
    else:
        # If result is already a string
        return result

# File operation handlers
def transfer_file(source_device, target_device, file_path):
    """Transfer a file from one device to another through the server"""
    # Request file from source device
    if source_device not in DEVICES:
        return {"status": "error", "message": f"Source device {source_device} not connected"}
    
    source_socket = DEVICES[source_device]["socket"]
    request = {
        "action": "send_file",
        "path": file_path
    }
    source_socket.send(json.dumps(request).encode('utf-8'))
    
    # Receive file data
    response = json.loads(source_socket.recv(4096).decode('utf-8'))
    if response["status"] != "success":
        return {"status": "error", "message": f"Failed to get file from source: {response['message']}"}
    
    # Store file temporarily on server
    filename = os.path.basename(file_path)
    temp_path = BASE_DIR / f"{filename}"
    
    # Check if this is the start of a file transfer
    if "file_data" in response:
        with open(temp_path, 'wb') as f:
            f.write(base64.b64decode(response["file_data"]))
    
    # Forward to target device
    if target_device not in DEVICES:
        return {"status": "error", "message": f"Target device {target_device} not connected"}
    
    target_socket = DEVICES[target_device]["socket"]
    with open(temp_path, 'rb') as f:
        file_data = base64.b64encode(f.read()).decode('utf-8')
    
    forward_request = {
        "action": "receive_file",
        "path": file_path,
        "file_data": file_data
    }
    target_socket.send(json.dumps(forward_request).encode('utf-8'))
    
    # Get confirmation from target
    target_response = json.loads(target_socket.recv(4096).decode('utf-8'))
    
    # Clean up temp file
    os.remove(temp_path)
    
    return target_response

def find_file(search_terms, devices=None):
    """Search for files across all devices"""
    results = {}
    devices_to_search = devices or DEVICES.keys()
    
    for device_name in devices_to_search:
        if device_name not in DEVICES:
            continue
            
        device_socket = DEVICES[device_name]["socket"]
        search_request = {
            "action": "search_files",
            "terms": search_terms
        }
        device_socket.send(json.dumps(search_request).encode('utf-8'))
        
        try:
            response = json.loads(device_socket.recv(8192).decode('utf-8'))
            if response["status"] == "success":
                results[device_name] = response["files"]
        except Exception as e:
            print(f"Error searching on {device_name}: {str(e)}")
    
    return {"status": "success", "results": results}

def handle_client(client_socket, addr):
    """Handle communication with a connected client device"""
    try:
        # Device registration
        registration = json.loads(client_socket.recv(1024).decode('utf-8'))
        device_name = registration["device_name"]
        device_info = registration["device_info"]
        
        print(f"Device registered: {device_name} ({addr[0]}:{addr[1]})")
        
        # Store device information
        DEVICES[device_name] = {
            "socket": client_socket,
            "address": addr,
            "info": device_info,
            "last_seen": time.time()
        }
        
        # Acknowledge registration
        client_socket.send(json.dumps({"status": "registered"}).encode('utf-8'))
        
        # Main communication loop
        while True:
            try:
                data = client_socket.recv(4096).decode('utf-8')
                if not data:
                    break
                    
                message = json.loads(data)
                
                if message["type"] == "command":
                    # Process natural language command
                    command = message["command"]
                    available_devices = list(DEVICES.keys())
                    
                    # Parse with LLM using updated method
                    llm_response = process_command(command, available_devices)
                    
                    try:
                        parsed_command = json.loads(llm_response)
                        
                        # Execute appropriate operation
                        operation = parsed_command.get("operation")
                        response = {"status": "error", "message": "Unknown operation"}
                        
                        if operation == "transfer_file":
                            response = transfer_file(
                                parsed_command.get("source_device"),
                                parsed_command.get("target_device"),
                                parsed_command.get("file_path")
                            )
                        elif operation == "find_file":
                            response = find_file(
                                parsed_command.get("search_terms"),
                                [parsed_command.get("source_device")] if "source_device" in parsed_command else None
                            )
                        elif operation == "list_files":
                            # TBD: Implement directory listing
                            pass
                        
                        client_socket.send(json.dumps(response).encode('utf-8'))
                    except json.JSONDecodeError:
                        client_socket.send(json.dumps({
                            "status": "error",
                            "message": "Failed to parse command"
                        }).encode('utf-8'))
                        
                elif message["type"] == "heartbeat":
                    # Update last seen timestamp
                    DEVICES[device_name]["last_seen"] = time.time()
                    client_socket.send(json.dumps({"status": "ok"}).encode('utf-8'))
                    
            except json.JSONDecodeError:
                client_socket.send(json.dumps({
                    "status": "error",
                    "message": "Invalid JSON"
                }).encode('utf-8'))
                
    except Exception as e:
        print(f"Error handling client {addr}: {str(e)}")
    finally:
        # Remove device from registry on disconnect
        for name, device in list(DEVICES.items()):
            if device["socket"] == client_socket:
                del DEVICES[name]
                print(f"Device {name} disconnected")
                break
                
        client_socket.close()

def start_server(host='192.168.1.15', port=9999):
    """Start the server to listen for client connections"""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server.bind((host, port))
        server.listen(5)
        print(f"[*] Server started on {host}:{port}")
        
        # Start heartbeat monitor
        threading.Thread(target=monitor_devices, daemon=True).start()
        
        while True:
            client, addr = server.accept()
            print(f"[*] Accepted connection from {addr[0]}:{addr[1]}")
            client_handler = threading.Thread(target=handle_client, args=(client, addr))
            client_handler.start()
            
    except KeyboardInterrupt:
        print("[*] Server shutting down")
    finally:
        server.close()

def monitor_devices():
    """Monitor connected devices and remove inactive ones"""
    while True:
        current_time = time.time()
        for name, device in list(DEVICES.items()):
            if current_time - device["last_seen"] > 60:  # 60 seconds timeout
                try:
                    device["socket"].close()
                except:
                    pass
                del DEVICES[name]
                print(f"Device {name} timed out")
        time.sleep(10)

if __name__ == "__main__":
    start_server()
