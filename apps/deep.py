import os
import sys
import time
import socket
import subprocess
import threading
import platform
import shutil
import speech_recognition as sr
import pyttsx3
import ctypes
from tkinter import messagebox
import tkinter as tk
import re
import json
import requests
from datetime import datetime

class VoiceFileManager:
    def __init__(self):
        self.server_ip = "192.168.9.63"  # FIB-By-Server
        self.share_name = "Shared"
        self.username = "aadish"  # FIB login username
        self.password = "1234"  # FIB password
        self.mapped_drive_letter = "S:"
        self.current_drive = os.getcwd()[:2]  # Get current drive (e.g., "C:")
        self.clipboard = None  # For cut/copy operations
        self.clipboard_operation = None  # 'cut' or 'copy'
        
        # Initialize voice engine
        self.engine = pyttsx3.init()
        self.engine.setProperty('rate', 150)  # Speed of speech
        self.engine.setProperty('volume', 0.9)  # Volume (0 to 1)
        
        # Initialize speech recognizer
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 4000  # Adjust based on environment
        self.recognizer.dynamic_energy_threshold = True
        
        # Connect to the share before starting the voice interaction
        self.connect_share()
        
        # Start the voice interaction
        self.run_voice_assistant()

    def speak(self, text):
        """Convert text to speech"""
        print(f"Assistant: {text}")
        self.engine.say(text)
        self.engine.runAndWait()

    def listen(self, prompt=None):
        """Listen for voice input from the user"""
        if prompt:
            self.speak(prompt)
        
        with sr.Microphone() as source:
            print("Listening...")
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
            try:
                audio = self.recognizer.listen(source, timeout=10, phrase_time_limit=10)
                print("Processing speech...")
                text = self.recognizer.recognize_google(audio)
                print(f"User said: {text}")
                return text.lower()
            except sr.WaitTimeoutError:
                self.speak("I didn't hear anything. Please try again.")
                return None
            except sr.UnknownValueError:
                self.speak("I couldn't understand what you said. Please try again.")
                return None
            except sr.RequestError:
                self.speak("I'm having trouble connecting to the speech recognition service.")
                return None
            except Exception as e:
                print(f"Error in speech recognition: {e}")
                self.speak("There was an error. Please try again.")
                return None

    def connect_share(self):
        """Connect to the network share"""
        try:
            # First disconnect if already connected
            subprocess.run(f'net use {self.mapped_drive_letter} /delete /y', 
                          shell=True, capture_output=True)
            
            # Connect to the share
            share_path = f"\\\\{self.server_ip}\\{self.share_name}"
            cmd = f'net use {self.mapped_drive_letter} {share_path} /user:{self.username} {self.password} /persistent:no'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"Connected to {self.share_name} on {self.server_ip}")
                return True
            else:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                print(f"Failed to connect: {error_msg}")
                return False
        except Exception as e:
            print(f"Connection error: {str(e)}")
            return False

    def disconnect_share(self):
        """Disconnect from the network share"""
        try:
            subprocess.run(f'net use {self.mapped_drive_letter} /delete /y', 
                          shell=True, capture_output=True)
            print("Disconnected from network share")
        except Exception as e:
            print(f"Error during disconnect: {str(e)}")

    def get_available_drives(self):
        """Get list of available drives on the system"""
        drives = []
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            if bitmask & 1:
                drives.append(f"{letter}:")
            bitmask >>= 1
        return drives
    
    def parse_command_with_nlp(self, command):
        """
        Enhanced command parser with better pattern matching and validation
        """
        try:
            command = command.lower().strip()
            response = {
                "intent": "unknown",
                "item_name": None,
                "source": self.current_drive,
                "destination": None,
                "new_name": None  # For rename operations
            }

            # Clean up common speech artifacts
            command = re.sub(r"\b(?:please|kindly|would you)\b", "", command)
            
            # Predefined patterns with priority
            patterns = [
                # Find file/folder patterns
                {
                    "regex": r"^(?:find|search|locate)\s+(?:for\s+)?(.+?)(?:\s+in\s+([a-z])(?:\s+drive)?)?$",
                    "groups": ["intent", "item_name", "source"],
                    "defaults": {"intent": "find"}
                },
                
                # Rename patterns
                {
                    "regex": r"^rename\s+(.+?)\s+to\s+(.+?)(?:\s+in\s+([a-z])(?:\s+drive)?)?$",
                    "groups": ["intent", "item_name", "new_name", "source"],
                    "defaults": {"intent": "rename"}
                },
                
                # Delete patterns
                {
                    "regex": r"^(?:delete|remove)\s+(.+?)(?:\s+from\s+([a-z])(?:\s+drive)?)?$",
                    "groups": ["intent", "item_name", "source"],
                    "defaults": {"intent": "delete"}
                },
                
                # Create file/folder patterns
                {
                    "regex": r"^create\s+(?:a\s+)?(?:new\s+)?(?:(file|folder|directory))\s+(?:called|named)?\s+(.+?)(?:\s+in\s+([a-z])(?:\s+drive)?)?$",
                    "groups": ["item_type", "item_name", "destination"],
                    "defaults": {"intent": "create"}
                },
                {
                    "regex": r"^create\s+(?:a\s+)?(?:new\s+)?(.+?)\s+(?:file|folder|directory)(?:\s+in\s+([a-z])(?:\s+drive)?)?$",
                    "groups": ["item_name", "destination"],
                    "defaults": {"intent": "create", "item_type": "file"}
                },
                
                # Cut pattern
                {
                    "regex": r"^cut\s+(.+?)(?:\s+from\s+([a-z])(?:\s+drive)?)?$",
                    "groups": ["intent", "item_name", "source"],
                    "defaults": {"intent": "cut"}
                },
                
                # Paste pattern
                {
                    "regex": r"^paste\s+(?:to\s+)?(?:into\s+)?(?:([a-z])(?:\s+drive)?|(.+))$",
                    "groups": ["destination", "destination_path"],
                    "defaults": {"intent": "paste"}
                },
                {
                    "regex": r"^paste$",
                    "groups": [],
                    "defaults": {"intent": "paste"}
                },
                
                # List files pattern
                {
                    "regex": r"^(?:list|show)\s+(?:files|folders|directories)(?:\s+in\s+([a-z])(?:\s+drive)?)?$",
                    "groups": ["source"],
                    "defaults": {"intent": "list"}
                },
                
                # Copy/move patterns (from original code)
                {
                    "regex": r"^(copy|move|share)\s+(.+?)\s+from\s+([a-z])(?:\s+drive)?\s+to\s+([a-z])(?:\s+drive)?$",
                    "groups": ["intent", "item_name", "source", "destination"]
                },
                {
                    "regex": r"^(copy|move|share)\s+(.+?)\s+to\s+([a-z])(?:\s+drive)?$",
                    "groups": ["intent", "item_name", "destination"]
                },
                {
                    "regex": r"^(copy|move|share)\s+(.+?)\s+from\s+([a-z])(?:\s+drive)?$",
                    "groups": ["intent", "item_name", "source"]
                },
                {
                    "regex": r"^share\s+(.+?)(?:\s+on\s+shared)?$",
                    "groups": ["intent", "item_name"],
                    "defaults": {"destination": self.mapped_drive_letter}
                }
            ]

            for pattern in patterns:
                match = re.match(pattern["regex"], command)
                if match:
                    groups = match.groups()
                    
                    # Set values from matched groups
                    for i, group_name in enumerate(pattern["groups"]):
                        if i < len(groups) and groups[i]:  # Check if the group was matched
                            if group_name == "intent":
                                response[group_name] = groups[i]
                            elif group_name == "item_name" or group_name == "new_name":
                                # Clean item name from command artifacts
                                item = groups[i].replace(" folder", "").replace(" directory", "").replace(" file", "").strip()
                                response[group_name] = item
                            elif group_name in ("source", "destination"):
                                response[group_name] = f"{groups[i].upper()}:"
                            elif group_name == "destination_path":
                                # Handle destination path (for paste operations)
                                response["destination"] = groups[i]
                            elif group_name == "item_type":
                                response[group_name] = groups[i]
                    
                    # Apply defaults if needed
                    if "defaults" in pattern:
                        for k, v in pattern["defaults"].items():
                            if not response.get(k):  # Only set if not already set
                                response[k] = v
                    
                    # Validate drive formats
                    if response["source"] and len(response["source"]) == 1:
                        response["source"] += ":"
                    if response["destination"] and len(response["destination"]) == 1:
                        response["destination"] += ":"
                    
                    return response

            # Command not recognized
            return {"intent": "unknown"}

        except Exception as e:
            print(f"Parsing error: {str(e)}")
            return {"intent": "error", "message": "Failed to parse command"}
    
    def resolve_path(self, item_name, drive_letter):
        """Resolve the full path for an item on a specified drive"""
        # Handle root level path
        if drive_letter.endswith(':'):
            return os.path.join(drive_letter + "\\", item_name)
        # Handle full paths
        elif os.path.isabs(drive_letter):
            return os.path.join(drive_letter, item_name)
        # Handle relative paths
        else:
            return os.path.join(os.getcwd(), drive_letter, item_name)
    
    def find_item_in_directory(self, item_name, directory, recursive=True):
        """Search for an item in the specified directory tree"""
        found_items = []
        search_method = os.walk if recursive else os.listdir
        
        if recursive:
            # Recursive search through all subdirectories
            for root, dirs, files in search_method(directory):
                # Check directories
                for dir in dirs:
                    if item_name.lower() in dir.lower():
                        found_items.append(os.path.join(root, dir))
                
                # Check files
                for file in files:
                    if item_name.lower() in file.lower():
                        found_items.append(os.path.join(root, file))
        else:
            # Non-recursive search in current directory only
            for item in search_method(directory):
                if item_name.lower() in item.lower():
                    found_items.append(os.path.join(directory, item))
        
        return found_items
    
    def find_item_in_current_directory(self, item_name):
        """Search for an item in the current directory tree"""
        return self.find_item_in_directory(item_name, os.getcwd())
    
    def copy_item(self, source_path, dest_path):
        """Copy a file or directory to the destination"""
        try:
            # First, check if source exists
            if not os.path.exists(source_path):
                # Try to find the item in current directory
                found_path = self.find_item_in_current_directory(os.path.basename(source_path))
                if found_path and len(found_path) > 0:
                    source_path = found_path[0]
                    print(f"Found item at: {source_path}")
                else:
                    return False, f"Source {source_path} does not exist"
            
            if os.path.isfile(source_path):
                # Create destination directory if it doesn't exist
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                shutil.copy2(source_path, dest_path)
                return True, f"Copied file {os.path.basename(source_path)}"
            elif os.path.isdir(source_path):
                if os.path.exists(dest_path):
                    # If destination exists, copy into it
                    final_dest = os.path.join(dest_path, os.path.basename(source_path))
                else:
                    final_dest = dest_path
                    # Create parent directory if needed
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                
                # Use copytree with ignore_errors to handle permission issues
                shutil.copytree(source_path, final_dest, dirs_exist_ok=True)
                return True, f"Copied directory {os.path.basename(source_path)} with all contents"
            else:
                return False, f"Source {source_path} does not exist"
        except PermissionError:
            return False, f"Permission denied when copying {os.path.basename(source_path)}"
        except Exception as e:
            return False, f"Error during copy: {str(e)}"
    
    def move_item(self, source_path, dest_path):
        """Move a file or directory to the destination"""
        try:
            # First, check if source exists
            if not os.path.exists(source_path):
                # Try to find the item in current directory
                found_path = self.find_item_in_current_directory(os.path.basename(source_path))
                if found_path and len(found_path) > 0:
                    source_path = found_path[0]
                    print(f"Found item at: {source_path}")
                else:
                    return False, f"Source {source_path} does not exist"
            
            if os.path.isfile(source_path):
                # Create destination directory if it doesn't exist
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                shutil.move(source_path, dest_path)
                return True, f"Moved file {os.path.basename(source_path)}"
            elif os.path.isdir(source_path):
                if os.path.exists(dest_path):
                    # If destination exists, move into it
                    final_dest = os.path.join(dest_path, os.path.basename(source_path))
                else:
                    final_dest = dest_path
                    # Create parent directory if needed
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                
                shutil.move(source_path, final_dest)
                return True, f"Moved directory {os.path.basename(source_path)} with all contents"
            else:
                return False, f"Source {source_path} does not exist"
        except PermissionError:
            return False, f"Permission denied when moving {os.path.basename(source_path)}"
        except Exception as e:
            return False, f"Error during move: {str(e)}"
    
    def find_files(self, item_name, source_drive):
        """Find files or directories matching the given name"""
        try:
            # Determine the search directory
            if source_drive:
                search_dir = f"{source_drive}\\"
            else:
                search_dir = os.getcwd()
            
            # Check if search directory exists
            if not os.path.exists(search_dir):
                return False, f"Search location {search_dir} does not exist"
            
            # Find matching items
            found_items = self.find_item_in_directory(item_name, search_dir)
            
            if found_items:
                # Limit results if too many
                if len(found_items) > 5:
                    message = f"Found {len(found_items)} items. Here are the first 5 matches:"
                    for i, item in enumerate(found_items[:5]):
                        message += f"\n{i+1}. {item}"
                    message += f"\nAnd {len(found_items) - 5} more..."
                else:
                    message = f"Found {len(found_items)} items matching '{item_name}':"
                    for i, item in enumerate(found_items):
                        message += f"\n{i+1}. {item}"
                
                return True, message
            else:
                return False, f"No items found matching '{item_name}'"
        except Exception as e:
            return False, f"Error while searching: {str(e)}"
    
    def rename_item(self, item_name, new_name, source_drive):
        """Rename a file or directory"""
        try:
            # Determine source path
            if source_drive:
                source_dir = f"{source_drive}\\"
                source_path = os.path.join(source_dir, item_name)
            else:
                source_dir = os.getcwd()
                # Try to find the item in current directory
                found_items = self.find_item_in_directory(item_name, source_dir, recursive=False)
                if found_items and len(found_items) > 0:
                    source_path = found_items[0]
                else:
                    return False, f"Could not find '{item_name}' in the current directory"
            
            # Check if source exists
            if not os.path.exists(source_path):
                return False, f"Item '{item_name}' does not exist"
            
            # Create destination path (same directory but new name)
            dest_path = os.path.join(os.path.dirname(source_path), new_name)
            
            # Check if destination already exists
            if os.path.exists(dest_path):
                return False, f"An item named '{new_name}' already exists"
            
            # Rename the item
            os.rename(source_path, dest_path)
            return True, f"Renamed {os.path.basename(source_path)} to {new_name}"
        except PermissionError:
            return False, f"Permission denied when renaming {item_name}"
        except Exception as e:
            return False, f"Error during rename: {str(e)}"
    
    def delete_item(self, item_name, source_drive):
        """Delete a file or directory"""
        try:
            # Determine source path
            if source_drive:
                source_dir = f"{source_drive}\\"
                source_path = os.path.join(source_dir, item_name)
            else:
                source_dir = os.getcwd()
                # Try to find the item in current directory
                found_items = self.find_item_in_directory(item_name, source_dir)
                if found_items and len(found_items) > 0:
                    if len(found_items) > 1:
                        # If multiple matches, ask for confirmation with specific path
                        return False, f"Multiple items match '{item_name}'. Please be more specific."
                    source_path = found_items[0]
                else:
                    return False, f"Could not find '{item_name}'"
            
            # Check if source exists
            if not os.path.exists(source_path):
                return False, f"Item '{item_name}' does not exist"
            
            # Ask for confirmation
            confirmation = self.listen(f"Are you sure you want to delete {os.path.basename(source_path)}? Say yes or no.")
            if not confirmation or "yes" not in confirmation:
                return False, "Deletion cancelled."
            
            # Delete the item
            if os.path.isfile(source_path):
                os.remove(source_path)
                return True, f"Deleted file {os.path.basename(source_path)}"
            elif os.path.isdir(source_path):
                shutil.rmtree(source_path)
                return True, f"Deleted directory {os.path.basename(source_path)} and all its contents"
            
            return False, "Unknown item type"
        except PermissionError:
            return False, f"Permission denied when deleting {item_name}"
        except Exception as e:
            return False, f"Error during deletion: {str(e)}"
    
    def create_item(self, item_name, item_type, destination):
        """Create a new file or directory"""
        try:
            # Determine destination path
            if destination:
                dest_dir = f"{destination}\\"
            else:
                dest_dir = os.getcwd()
            
            # Create the full path
            item_path = os.path.join(dest_dir, item_name)
            
            # Check if item already exists
            if os.path.exists(item_path):
                return False, f"An item named '{item_name}' already exists"
            
            # Create the item based on type
            if item_type == "folder" or item_type == "directory":
                os.makedirs(item_path)
                return True, f"Created directory {item_name}"
            else:  # Default to file
                # Create parent directories if needed
                os.makedirs(os.path.dirname(item_path), exist_ok=True)
                
                # Create an empty file
                with open(item_path, 'w') as f:
                    # Optionally add a timestamp or other content
                    f.write(f"Created on {datetime.now()}\n")
                
                return True, f"Created file {item_name}"
        except PermissionError:
            return False, f"Permission denied when creating {item_name}"
        except Exception as e:
            return False, f"Error during creation: {str(e)}"
    
    def cut_item(self, item_name, source):
        """Cut a file or directory (prepare for move)"""
        try:
            # Determine source path
            if source:
                source_dir = f"{source}\\"
                source_path = os.path.join(source_dir, item_name)
            else:
                source_dir = os.getcwd()
                # Try to find the item in current directory
                found_items = self.find_item_in_directory(item_name, source_dir)
                if found_items and len(found_items) > 0:
                    if len(found_items) > 1:
                        # If multiple matches, ask for more specific info
                        return False, f"Multiple items match '{item_name}'. Please be more specific."
                    source_path = found_items[0]
                else:
                    return False, f"Could not find '{item_name}'"
            
            # Check if source exists
            if not os.path.exists(source_path):
                return False, f"Item '{item_name}' does not exist"
            
            # Store in clipboard
            self.clipboard = source_path
            self.clipboard_operation = "cut"
            
            return True, f"Cut {os.path.basename(source_path)} to clipboard. Use 'paste' to complete the operation."
        except Exception as e:
            return False, f"Error during cut operation: {str(e)}"
    
    def paste_item(self, destination):
        """Paste a previously cut or copied item"""
        try:
            # Check if clipboard has content
            if not self.clipboard:
                return False, "Nothing in clipboard to paste"
            
            # Determine destination path
            if destination:
                if destination.endswith(':'):
                    dest_dir = f"{destination}\\"
                else:
                    dest_dir = destination
            else:
                dest_dir = os.getcwd()
            
            # Create the full destination path
            dest_path = os.path.join(dest_dir, os.path.basename(self.clipboard))
            
            # Perform the operation
            if self.clipboard_operation == "cut":
                # Move the item
                result = self.move_item(self.clipboard, dest_path)
                # Clear clipboard after cut operation
                if result[0]:  # If successful
                    self.clipboard = None
                    self.clipboard_operation = None
                return result
            elif self.clipboard_operation == "copy":
                # Copy the item
                return self.copy_item(self.clipboard, dest_path)
            else:
                return False, "Unknown clipboard operation"
        except Exception as e:
            return False, f"Error during paste operation: {str(e)}"
    
    def list_files(self, source):
        """List files and directories in the specified location"""
        try:
            # Determine source directory
            if source:
                source_dir = f"{source}\\"
            else:
                source_dir = os.getcwd()
            
            # Check if directory exists
            if not os.path.exists(source_dir):
                return False, f"Directory {source_dir} does not exist"
            
            # List contents
            contents = os.listdir(source_dir)
            
            if contents:
                # Separate files and directories
                dirs = [item for item in contents if os.path.isdir(os.path.join(source_dir, item))]
                files = [item for item in contents if os.path.isfile(os.path.join(source_dir, item))]
                
                message = f"Found {len(dirs)} directories and {len(files)} files in {source_dir}"
                
                # List directories
                if dirs:
                    message += "\n\nDirectories:"
                    # List only first 10 if too many
                    if len(dirs) > 10:
                        for i, dir in enumerate(dirs[:10]):
                            message += f"\n{i+1}. {dir}"
                        message += f"\n...and {len(dirs) - 10} more directories"
                    else:
                        for i, dir in enumerate(dirs):
                            message += f"\n{i+1}. {dir}"
                
                # List files
                if files:
                    message += "\n\nFiles:"
                    # List only first 10 if too many
                    if len(files) > 10:
                        for i, file in enumerate(files[:10]):
                            message += f"\n{i+1}. {file}"
                        message += f"\n...and {len(files) - 10} more files"
                    else:
                        for i, file in enumerate(files):
                            message += f"\n{i+1}. {file}"
                
                return True, message
            else:
                return True, f"Directory {source_dir} is empty"
        except PermissionError:
            return False, f"Permission denied when accessing {source_dir}"
        except Exception as e:
            return False, f"Error listing files: {str(e)}"
    
    def execute_command(self, parsed_command):
        """Execute the parsed command"""
        intent = parsed_command.get("intent")
        
        if intent == "unknown":
            return False, "I couldn't understand your command. Please try again with a different phrasing."
        
        elif intent == "error":
            return False, f"Error processing command: {parsed_command.get('message')}"
        
        elif intent == "find":
            item_name = parsed_command.get("item_name")
            source = parsed_command.get("source")
            
            # Debug information
            print(f"Executing find command:")
            print(f"  Item: {item_name}")
            print(f"  Source: {source}")
            
            return self.find_files(item_name, source)
        
        elif intent == "rename":
            item_name = parsed_command.get("item_name")
            new_name = parsed_command.get("new_name")
            source = parsed_command.get("source")
            
            # Debug information
            print(f"Executing rename command:")
            print(f"  Item: {item_name}")
            print(f"  New name: {new_name}")
            print(f"  Source: {source}")
            
            return self.rename_item(item_name, new_name, source)
        
        elif intent == "delete":
            item_name = parsed_command.get("item_name")
            source = parsed_command.get("source")
            
            # Debug information
            print(f"Executing delete command:")
            print(f"  Item: {item_name}")
            print(f"  Source: {source}")
            
            return self.delete_item(item_name, source)
        
        elif intent == "create":
            item_name = parsed_command.get("item_name")
            item_type = parsed_command.get("item_type", "file")  # Default to file
            destination = parsed_command.get("destination")
            
            # Debug information
            print(f"Executing create command:")
            print(f"  Item name: {item_name}")
            print(f"  Item type: {item_type}")
            print(f"  Destination: {destination}")
            
            return self.create_item(item_name, item_type, destination)
        
        elif intent == "cut":
            item_name = parsed_command.get("item_name")
            source = parsed_command.get("source")
            
            # Debug information
            print(f"Executing cut command:")
            print(f"  Item: {item_name}")
            print(f"  Source: {source}")
            
            return self.cut_item(item_name, source)
        
        elif intent == "paste":
            destination = parsed_command.get("destination")
            
            # Debug information
            print(f"Executing paste command:")
            print(f"  Destination: {destination}")
            
            return self.paste_item(destination)
        
        elif intent == "list":
            source = parsed_command.get("source")
            
            # Debug information
            print(f"Executing list command:")
            print(f"  Source: {source}")
            
            return self.list_files(source)
        
        elif intent in ["copy", "move", "share"]:
            item_name = parsed_command.get("item_name")
            source = parsed_command.get("source")
            destination = parsed_command.get("destination")
            
            # Debug information
            print(f"Executing {intent} command:")
            print(f"  Item: {item_name}")
            print(f"  Source: {source}")
            print(f"  Destination: {destination}")
            
            # Resolve paths
            source_path = self.resolve_path(item_name, source if source else os.getcwd())
            
            # If source doesn't exist, try to find it
            if not os.path.exists(source_path):
                found_items = self.find_item_in_directory(item_name, source if source else os.getcwd())
                if found_items and len(found_items) > 0:
                    source_path = found_items[0]
                else:
                    return False, f"Could not find {item_name}"
            
            if not destination:
                # If no destination specified, use the mapped drive for "share" intent
                if intent == "share":
                    destination = self.mapped_drive_letter
                else:
                    return False, f"Destination not specified for {intent} operation"
            
            # Create destination path
            dest_path = os.path.join(destination, os.path.basename(source_path))
            
            # Execute the operation
            if intent == "copy" or intent == "share":
                return self.copy_item(source_path, dest_path)
            elif intent == "move":
                return self.move_item(source_path, dest_path)
        
        else:
            return False, f"Unknown command: {intent}"

    def run_voice_assistant(self):
        """Main loop for voice assistant"""
        self.speak("Voice File Manager is ready. How can I help you?")
        
        while True:
            try:
                command = self.listen()
                if not command:
                    continue
                
                # Process exit commands
                if any(word in command for word in ["exit", "quit", "goodbye", "bye"]):
                    self.speak("Exiting Voice File Manager. Goodbye!")
                    self.disconnect_share()
                    break
                
                # Process help command
                if "help" in command:
                    self.provide_help()
                    continue
                
                # Process change directory command
                if "change directory" in command or "cd" in command:
                    self.change_directory(command)
                    continue
                
                # Process current directory command
                if "current directory" in command or "where am i" in command:
                    self.speak(f"You are currently in {os.getcwd()}")
                    continue
                
                # Process list drives command
                if "list drives" in command:
                    drives = self.get_available_drives()
                    self.speak(f"Available drives are: {', '.join(drives)}")
                    continue
                
                # Parse and execute the command
                parsed_command = self.parse_command_with_nlp(command)
                success, result = self.execute_command(parsed_command)
                
                if success:
                    self.speak(result)
                else:
                    self.speak(f"Error: {result}")
            
            except Exception as e:
                print(f"Error in voice assistant: {str(e)}")
                self.speak("Sorry, I encountered an error. Please try again.")
    
    def change_directory(self, command):
        """Change the current working directory"""
        try:
            # Extract path from command
            match = re.search(r"(?:change directory|cd)(?:\s+to)?\s+(.+)", command, re.IGNORECASE)
            if match:
                path = match.group(1).strip()
                
                # Handle special paths
                if path == "..":
                    os.chdir("..")
                    self.speak(f"Changed to parent directory: {os.getcwd()}")
                    return
                
                # Handle drive letters
                if len(path) == 1 and path.isalpha():
                    drive = f"{path.upper()}:"
                    if os.path.exists(drive):
                        os.chdir(drive)
                        self.speak(f"Changed to drive {drive}")
                    else:
                        self.speak(f"Drive {drive} does not exist")
                    return
                
                # Handle full paths
                if os.path.exists(path):
                    os.chdir(path)
                    self.speak(f"Changed directory to {path}")
                    return
                
                # Try to find the directory
                found_dirs = self.find_item_in_directory(path, os.getcwd())
                if found_dirs:
                    # Filter to only directories
                    dirs = [d for d in found_dirs if os.path.isdir(d)]
                    if dirs:
                        os.chdir(dirs[0])
                        self.speak(f"Changed directory to {dirs[0]}")
                    else:
                        self.speak(f"Found {path} but it's not a directory")
                else:
                    self.speak(f"Could not find directory {path}")
            else:
                self.speak("Please specify a directory to change to")
        except Exception as e:
            self.speak(f"Error changing directory: {str(e)}")
    
    def copy_to_shared_drive(self, source_path):
        """Copy a file to the shared network drive"""
        try:
            # Make sure we're connected to the shared drive
            if not os.path.exists(self.mapped_drive_letter):
                self.connect_share()
            
            # Create the destination path
            dest_path = os.path.join(self.mapped_drive_letter, os.path.basename(source_path))
            
            # Copy the file
            success, message = self.copy_item(source_path, dest_path)
            return success, message
        except Exception as e:
            return False, f"Error copying to shared drive: {str(e)}"
    
    def compress_file(self, file_path, archive_name=None):
        """Compress a file or folder into a ZIP archive"""
        try:
            import zipfile
            
            # Check if the file exists
            if not os.path.exists(file_path):
                return False, f"File {file_path} does not exist"
            
            # Create archive name if not provided
            if not archive_name:
                archive_name = os.path.basename(file_path) + ".zip"
            
            # Make sure archive name ends with .zip
            if not archive_name.endswith('.zip'):
                archive_name += '.zip'
            
            # Create the archive path
            archive_path = os.path.join(os.path.dirname(file_path), archive_name)
            
            # Create the ZIP archive
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                if os.path.isfile(file_path):
                    # Add single file
                    zipf.write(file_path, os.path.basename(file_path))
                elif os.path.isdir(file_path):
                    # Add directory contents
                    for root, dirs, files in os.walk(file_path):
                        for file in files:
                            file_path_full = os.path.join(root, file)
                            zipf.write(
                                file_path_full, 
                                os.path.relpath(file_path_full, os.path.join(file_path, '..'))
                            )
            
            return True, f"Successfully compressed {os.path.basename(file_path)} to {archive_name}"
        except Exception as e:
            return False, f"Error compressing file: {str(e)}"
    
    def extract_archive(self, archive_path, extract_dir=None):
        """Extract a ZIP archive"""
        try:
            import zipfile
            
            # Check if the archive exists
            if not os.path.exists(archive_path):
                return False, f"Archive {archive_path} does not exist"
            
            # Create extract directory if not provided
            if not extract_dir:
                extract_dir = os.path.splitext(archive_path)[0]
            
            # Create the directory if it doesn't exist
            os.makedirs(extract_dir, exist_ok=True)
            
            # Extract the archive
            with zipfile.ZipFile(archive_path, 'r') as zipf:
                zipf.extractall(extract_dir)
            
            return True, f"Successfully extracted {os.path.basename(archive_path)} to {extract_dir}"
        except Exception as e:
            return False, f"Error extracting archive: {str(e)}"
    
    def search_file_content(self, search_term, file_path):
        """Search for text inside a file"""
        try:
            # Check if the file exists
            if not os.path.exists(file_path):
                return False, f"File {file_path} does not exist"
            
            # Check if the file is a text file
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    content = file.read()
            except UnicodeDecodeError:
                return False, f"File {os.path.basename(file_path)} is not a text file"
            
            # Search for the term
            matches = re.finditer(search_term, content, re.IGNORECASE)
            
            # Count matches and get context
            match_count = 0
            context_lines = []
            
            for match in matches:
                match_count += 1
                start_pos = max(0, match.start() - 50)
                end_pos = min(len(content), match.end() + 50)
                
                # Get context around the match
                context = content[start_pos:end_pos]
                context = context.replace(match.group(), f"**{match.group()}**")
                
                # Add line number info if possible
                line_num = content[:match.start()].count('\n') + 1
                context_lines.append(f"Line {line_num}: ...{context}...")
                
                # Limit to 5 matches for readability
                if match_count >= 5:
                    break
            
            if match_count > 0:
                result = f"Found {match_count} matches for '{search_term}' in {os.path.basename(file_path)}."
                if match_count > 5:
                    result += f" Showing first 5 matches:"
                else:
                    result += " Matches:"
                
                for context in context_lines:
                    result += f"\n{context}"
                
                return True, result
            else:
                return False, f"No matches found for '{search_term}' in {os.path.basename(file_path)}"
        except Exception as e:
            return False, f"Error searching file content: {str(e)}"
    
    def get_file_info(self, file_path):
        """Get detailed information about a file"""
        try:
            # Check if the file exists
            if not os.path.exists(file_path):
                return False, f"File {file_path} does not exist"
            
            # Get file stats
            file_stats = os.stat(file_path)
            
            # Get file size in human-readable format
            size_bytes = file_stats.st_size
            size_str = self.get_human_readable_size(size_bytes)
            
            # Get modification time
            mod_time = datetime.fromtimestamp(file_stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            
            # Get creation time
            create_time = datetime.fromtimestamp(file_stats.st_ctime).strftime('%Y-%m-%d %H:%M:%S')
            
            # Get file type
            file_type = "Directory" if os.path.isdir(file_path) else "File"
            
            # Get file extension
            file_ext = os.path.splitext(file_path)[1] if os.path.isfile(file_path) else ""
            
            # Build info string
            info = f"Information for {os.path.basename(file_path)}:\n"
            info += f"Type: {file_type}\n"
            info += f"Size: {size_str}\n"
            info += f"Created: {create_time}\n"
            info += f"Modified: {mod_time}\n"
            info += f"Path: {os.path.abspath(file_path)}\n"
            
            if file_ext:
                info += f"Extension: {file_ext}\n"
            
            return True, info
        except Exception as e:
            return False, f"Error getting file info: {str(e)}"
    
    def get_human_readable_size(self, size_bytes):
        """Convert bytes to human-readable size"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ("B", "KB", "MB", "GB", "TB")
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        
        return f"{s} {size_names[i]}"
    
    def batch_rename_files(self, directory, old_pattern, new_pattern):
        """Batch rename files based on a pattern"""
        try:
            # Check if directory exists
            if not os.path.exists(directory):
                return False, f"Directory {directory} does not exist"
            
            # Get list of files in directory
            files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
            
            # Filter files matching the pattern
            matching_files = [f for f in files if re.search(old_pattern, f)]
            
            if not matching_files:
                return False, f"No files matching pattern '{old_pattern}' found in {directory}"
            
            # Rename files
            renamed_count = 0
            for file in matching_files:
                new_name = re.sub(old_pattern, new_pattern, file)
                old_path = os.path.join(directory, file)
                new_path = os.path.join(directory, new_name)
                
                # Skip if new name is the same as old name
                if new_name == file:
                    continue
                
                # Rename the file
                os.rename(old_path, new_path)
                renamed_count += 1
            
            return True, f"Renamed {renamed_count} files from pattern '{old_pattern}' to '{new_pattern}'"
        except Exception as e:
            return False, f"Error batch renaming files: {str(e)}"
    
    def backup_file(self, file_path, backup_dir=None):
        """Create a backup of a file"""
        try:
            # Check if the file exists
            if not os.path.exists(file_path):
                return False, f"File {file_path} does not exist"
            
            # Create backup directory if not provided
            if not backup_dir:
                backup_dir = os.path.join(os.path.dirname(file_path), "Backups")
            
            # Create the directory if it doesn't exist
            os.makedirs(backup_dir, exist_ok=True)
            
            # Create backup filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            file_name = os.path.basename(file_path)
            backup_name = f"{os.path.splitext(file_name)[0]}_{timestamp}{os.path.splitext(file_name)[1]}"
            backup_path = os.path.join(backup_dir, backup_name)
            
            # Copy the file
            if os.path.isfile(file_path):
                shutil.copy2(file_path, backup_path)
            elif os.path.isdir(file_path):
                shutil.copytree(file_path, backup_path)
            
            return True, f"Created backup of {os.path.basename(file_path)} at {backup_path}"
        except Exception as e:
            return False, f"Error creating backup: {str(e)}"
    
    def read_text_file(self, file_path):
        """Read contents of a text file"""
        try:
            # Check if the file exists
            if not os.path.exists(file_path):
                return False, f"File {file_path} does not exist"
            
            # Try to read the file
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    content = file.read()
            except UnicodeDecodeError:
                return False, f"File {os.path.basename(file_path)} is not a text file"
            
            # Limit content length for speaking
            if len(content) > 1000:
                content = content[:1000] + "... (content truncated)"
            
            return True, f"Contents of {os.path.basename(file_path)}:\n{content}"
        except Exception as e:
            return False, f"Error reading file: {str(e)}"

# Import required for file size calculation
import math

if __name__ == "__main__":
    file_manager = VoiceFileManager()