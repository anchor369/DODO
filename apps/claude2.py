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

class VoiceFileManager:
    def __init__(self):
        self.server_ip = "192.168.9.63"  # FIB-By-Server
        self.share_name = "Shared"
        self.username = "aadish"  # FIB login username
        self.password = "1234"  # FIB password
        self.mapped_drive_letter = "S:"
        self.current_drive = os.getcwd()[:2]  # Get current drive (e.g., "C:")
        
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
        Parse the voice command using improved pattern matching for all file operations
        """
        try:
            command = command.lower()
            
            # COPY command patterns
            copy_from_to_pattern = r"copy\s+(?:the\s+)?([\w\s]+?)(?:\s+directory|\s+folder|\s+file)?\s+from\s+([a-z])(?:\s+drive)?\s+to\s+([a-z])(?:\s+drive)?"
            copy_to_pattern = r"copy\s+(?:the\s+)?([\w\s]+?)(?:\s+directory|\s+folder|\s+file)?\s+to\s+([a-z])(?:\s+drive)?"
            
            # DELETE command patterns
            delete_pattern = r"(?:delete|remove)\s+(?:the\s+)?([\w\s]+?)(?:\s+directory|\s+folder|\s+file)?(?:\s+from\s+([a-z])(?:\s+drive)?)?"
            
            # RENAME command patterns
            rename_pattern = r"rename\s+(?:the\s+)?([\w\s]+?)(?:\s+directory|\s+folder|\s+file)?\s+to\s+([\w\s]+?)(?:\s+(?:in|on|from)\s+([a-z])(?:\s+drive)?)?"
            
            # CUT/MOVE command patterns
            cut_pattern = r"(?:cut|move)\s+(?:the\s+)?([\w\s]+?)(?:\s+directory|\s+folder|\s+file)?\s+from\s+([a-z])(?:\s+drive)?\s+to\s+([a-z])(?:\s+drive)?"
            
            # CREATE directory pattern
            create_dir_pattern = r"(?:create|make|new)\s+(?:a\s+)?(?:directory|folder)\s+([\w\s]+?)(?:\s+(?:in|on)\s+([a-z])(?:\s+drive)?)?"
            
            # LIST files pattern
            list_pattern = r"(?:list|show|display)\s+(?:all\s+)?(?:files|directories|folders)(?:\s+(?:in|on|from)\s+([a-z])(?:\s+drive)?)?"
            
            # SEARCH pattern
            search_pattern = r"(?:search|find|locate)\s+(?:for\s+)?(?:a\s+)?(?:file|directory|folder)?\s+([\w\s]+?)(?:\s+(?:in|on|from)\s+([a-z])(?:\s+drive)?)?"
            
            # Check COPY patterns
            match = re.match(copy_from_to_pattern, command)
            if match:
                item_name = match.group(1).strip()
                source = match.group(2).upper() + ":"
                destination = match.group(3).upper() + ":"
                
                return {
                    "intent": "copy",
                    "item_name": item_name,
                    "source": source,
                    "destination": destination
                }
            
            match = re.match(copy_to_pattern, command)
            if match:
                item_name = match.group(1).strip()
                destination = match.group(2).upper() + ":"
                
                return {
                    "intent": "copy",
                    "item_name": item_name,
                    "source": self.current_drive,
                    "destination": destination
                }
            
            # Check DELETE patterns
            match = re.match(delete_pattern, command)
            if match:
                item_name = match.group(1).strip()
                source = match.group(2).upper() + ":" if match.group(2) else self.current_drive
                
                return {
                    "intent": "delete",
                    "item_name": item_name,
                    "source": source
                }
            
            # Check RENAME patterns
            match = re.match(rename_pattern, command)
            if match:
                item_name = match.group(1).strip()
                new_name = match.group(2).strip()
                source = match.group(3).upper() + ":" if match.group(3) else self.current_drive
                
                return {
                    "intent": "rename",
                    "item_name": item_name,
                    "new_name": new_name,
                    "source": source
                }
            
            # Check CUT/MOVE patterns
            match = re.match(cut_pattern, command)
            if match:
                item_name = match.group(1).strip()
                source = match.group(2).upper() + ":"
                destination = match.group(3).upper() + ":"
                
                return {
                    "intent": "move",  # Using move intent for cut operation
                    "item_name": item_name,
                    "source": source,
                    "destination": destination
                }
            
            # Check CREATE directory pattern
            match = re.match(create_dir_pattern, command)
            if match:
                dir_name = match.group(1).strip()
                location = match.group(2).upper() + ":" if match.group(2) else self.current_drive
                
                return {
                    "intent": "create_dir",
                    "dir_name": dir_name,
                    "location": location
                }
            
            # Check LIST files pattern
            match = re.match(list_pattern, command)
            if match:
                location = match.group(1).upper() + ":" if match.group(1) else self.current_drive
                
                return {
                    "intent": "list",
                    "location": location
                }
            
            # Check SEARCH pattern
            match = re.match(search_pattern, command)
            if match:
                query = match.group(1).strip()
                location = match.group(2).upper() + ":" if match.group(2) else self.current_drive
                
                return {
                    "intent": "search",
                    "query": query,
                    "location": location
                }
            
            # Simple direct patterns for common variations - fallback patterns
            simplest_patterns = [
                # "copy X to Y" pattern
                r"copy\s+(?:the\s+)?([\w\s]+)(?:\s+directory|\s+folder|\s+file)?\s+(?:to|into|in|on)\s+(?:the\s+)?([a-z])(?:\s+drive)?",
                
                # "copy X and paste it to Y" pattern
                r"copy\s+(?:the\s+)?([\w\s]+)(?:\s+directory|\s+folder|\s+file)?\s+and\s+paste\s+it\s+(?:to|into|in|on)\s+(?:the\s+)?([a-z])(?:\s+drive)?"
            ]
            
            # Try simple patterns as fallback
            for pattern in simplest_patterns:
                match = re.match(pattern, command)
                if match:
                    groups = match.groups()
                    item_name = groups[0].strip()
                    destination = groups[1].upper() + ":"
                    
                    return {
                        "intent": "copy",
                        "item_name": item_name,
                        "source": self.current_drive,
                        "destination": destination
                    }
            
            # More complex patterns with drive letters or paths
            copy_patterns = [
                r"copy\s+(?:the\s+)?(.*?)\s+(?:directory|folder|file|dir)\s+(?:from\s+)?(.*?)\s+(?:drive\s+)?(?:to|into|in|on)\s+(?:the\s+)?(.*?)(?:\s+drive|\s+folder|\s+directory)?$",
                r"copy\s+(?:the\s+)?(.*?)\s+(?:from\s+)?(.*?)\s+(?:drive\s+)?(?:to|into|in|on)\s+(?:the\s+)?(.*?)(?:\s+drive)?$"
            ]
            
            move_patterns = [
                r"(?:move|cut)\s+(?:the\s+)?(.*?)\s+(?:directory|folder|file|dir)\s+(?:from\s+)?(.*?)\s+(?:drive\s+)?(?:to|into|in|on)\s+(?:the\s+)?(.*?)(?:\s+drive|\s+folder|\s+directory)?$",
                r"(?:move|cut and paste|cut)\s+(?:the\s+)?(.*?)\s+(?:from\s+)?(.*?)\s+(?:drive\s+)?(?:to|into|in|on)\s+(?:the\s+)?(.*?)(?:\s+drive)?$"
            ]
            
            share_patterns = [
                r"share\s+(?:the\s+)?(.*?)\s+(?:directory|folder|file|dir)\s+(?:from\s+)?(.*?)\s+(?:drive\s+)?(?:to|into|in|on)\s+(?:the\s+)?shared\s+(?:drive|\s+folder|\s+directory)?$",
                r"share\s+(?:the\s+)?(.*?)\s+(?:from\s+)?(.*?)\s+(?:drive\s+)?$"
            ]
            
            # Check for copy patterns
            for pattern in copy_patterns:
                match = re.match(pattern, command)
                if match:
                    item_name = match.group(1).strip()
                    source = match.group(2).strip() if match.group(2) else self.current_drive
                    destination = match.group(3).strip() if len(match.groups()) >= 3 and match.group(3) else None
                    
                    # Convert single letter to drive format
                    if len(source) == 1:
                        source = f"{source.upper()}:"
                    if destination and len(destination) == 1:
                        destination = f"{destination.upper()}:"
                    
                    return {
                        "intent": "copy",
                        "item_name": item_name,
                        "source": source,
                        "destination": destination
                    }
            
            # Check for move patterns
            for pattern in move_patterns:
                match = re.match(pattern, command)
                if match:
                    item_name = match.group(1).strip()
                    source = match.group(2).strip() if match.group(2) else self.current_drive
                    destination = match.group(3).strip() if len(match.groups()) >= 3 and match.group(3) else None
                    
                    # Convert single letter to drive format
                    if len(source) == 1:
                        source = f"{source.upper()}:"
                    if destination and len(destination) == 1:
                        destination = f"{destination.upper()}:"
                    
                    return {
                        "intent": "move",
                        "item_name": item_name,
                        "source": source,
                        "destination": destination
                    }
            
            # Check for share patterns
            for pattern in share_patterns:
                match = re.match(pattern, command)
                if match:
                    item_name = match.group(1).strip()
                    source = match.group(2).strip() if len(match.groups()) >= 2 and match.group(2) else self.current_drive
                    
                    # Convert single letter to drive format
                    if source and len(source) == 1:
                        source = f"{source.upper()}:"
                    
                    return {
                        "intent": "share",
                        "item_name": item_name,
                        "source": source,
                        "destination": self.mapped_drive_letter
                    }
            
            # If we reach here, try to extract basic information
            # Look for item names
            item_match = re.search(r"(?:copy|move|share|cut)\s+(?:the\s+)?([\w\s]+)(?:\s+directory|\s+folder|\s+file)", command)
            item_name = item_match.group(1).strip() if item_match else None
            
            # Look for drive letters
            drive_letters = re.findall(r"(?:(?:drive|from|to|in|on|into)\s+)([a-z])(?:\s+drive)?", command)
            
            if item_name and drive_letters:
                if "copy" in command:
                    intent = "copy"
                elif "move" in command or "cut" in command:
                    intent = "move"
                elif "share" in command:
                    intent = "share"
                else:
                    intent = "unknown"
                
                # Default source to current drive
                source = self.current_drive
                
                # If we have drive letters, assign them appropriately
                if len(drive_letters) >= 2:
                    source = f"{drive_letters[0].upper()}:"
                    destination = f"{drive_letters[1].upper()}:"
                elif len(drive_letters) == 1:
                    destination = f"{drive_letters[0].upper()}:"
                else:
                    destination = None
                
                return {
                    "intent": intent,
                    "item_name": item_name,
                    "source": source,
                    "destination": destination
                }
            
            # Fallback
            if not item_name:
                # Try to extract anything that looks like a file or directory name
                words = command.split()
                potential_names = [word for word in words if word not in ["copy", "move", "cut", "paste", "to", "from", "drive", "shared", "file", "folder", "directory"]]
                
                if potential_names:
                    item_name = potential_names[0]
                    
                    # Check for "to X drive" pattern
                    drive_match = re.search(r"to\s+([a-z])\s+drive", command)
                    if drive_match:
                        destination = f"{drive_match.group(1).upper()}:"
                        
                        return {
                            "intent": "copy",  # Default to copy if unclear
                            "item_name": item_name,
                            "source": self.current_drive,
                            "destination": destination
                        }
            
            # If all else fails
            return {"intent": "unknown", "original_command": command}
        
        except Exception as e:
            print(f"Error in NLP parsing: {str(e)}")
            return {"intent": "error", "message": str(e)}
    
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
    
    def find_item_in_current_directory(self, item_name):
        """Search for an item in the current directory tree"""
        for root, dirs, files in os.walk(os.getcwd()):
            # Check directories
            for dir in dirs:
                if item_name.lower() in dir.lower():
                    return os.path.join(root, dir)
            
            # Check files
            for file in files:
                if item_name.lower() in file.lower():
                    return os.path.join(root, file)
        
        return None
    
    def copy_item(self, source_path, dest_path):
        """Copy a file or directory to the destination"""
        try:
            # First, check if source exists
            if not os.path.exists(source_path):
                # Try to find the item in current directory
                found_path = self.find_item_in_current_directory(os.path.basename(source_path))
                if found_path:
                    source_path = found_path
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
                if found_path:
                    source_path = found_path
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
    
    def delete_item(self, source_path):
        """Delete a file or directory"""
        try:
            # First, check if source exists
            if not os.path.exists(source_path):
                # Try to find the item in current directory
                found_path = self.find_item_in_current_directory(os.path.basename(source_path))
                if found_path:
                    source_path = found_path
                    print(f"Found item at: {source_path}")
                else:
                    return False, f"Source {source_path} does not exist"
            
            if os.path.isfile(source_path):
                os.remove(source_path)
                return True, f"Deleted file {os.path.basename(source_path)}"
            elif os.path.isdir(source_path):
                shutil.rmtree(source_path)
                return True, f"Deleted directory {os.path.basename(source_path)} with all contents"
            else:
                return False, f"Source {source_path} does not exist"
        except PermissionError:
            return False, f"Permission denied when deleting {os.path.basename(source_path)}"
        except Exception as e:
            return False, f"Error during deletion: {str(e)}"

    def rename_item(self, source_path, new_name):
        """Rename a file or directory"""
        try:
            # First, check if source exists
            if not os.path.exists(source_path):
                # Try to find the item in current directory
                found_path = self.find_item_in_current_directory(os.path.basename(source_path))
                if found_path:
                    source_path = found_path
                    print(f"Found item at: {source_path}")
                else:
                    return False, f"Source {source_path} does not exist"
            
            # Get the directory of the source
            source_dir = os.path.dirname(source_path)
            
            # Create the new path with the new name
            new_path = os.path.join(source_dir, new_name)
            
            # Check if destination already exists
            if os.path.exists(new_path):
                return False, f"Cannot rename: {new_name} already exists"
            
            os.rename(source_path, new_path)
            return True, f"Renamed {os.path.basename(source_path)} to {new_name}"
        except PermissionError:
            return False, f"Permission denied when renaming {os.path.basename(source_path)}"
        except Exception as e:
            return False, f"Error during rename: {str(e)}"
    
    def create_directory(self, dir_path):
        """Create a new directory"""
        try:
            if os.path.exists(dir_path):
                return False, f"Directory {os.path.basename(dir_path)} already exists"
            
            os.makedirs(dir_path, exist_ok=True)
            return True, f"Created directory {os.path.basename(dir_path)}"
        except PermissionError:
            return False, f"Permission denied when creating directory"
        except Exception as e:
            return False, f"Error during directory creation: {str(e)}"
    
    def list_files(self, location):
        """List files and directories in the specified location"""
        try:
            if not os.path.exists(location):
                return False, f"Location {location} does not exist"
            
            items = os.listdir(location)
            
            if not items:
                return True, f"No files or directories found in {location}"
            
            # Group items by type
            directories = []
            files = []
            
            for item in items:
                full_path = os.path.join(location, item)
                if os.path.isdir(full_path):
                    directories.append(item)
                else:
                    files.append(item)
            
            # Prepare the result
            result = f"Found {len(directories)} directories and {len(files)} files in {location}.\n"
            
            if directories:
                result += "Directories: " + ", ".join(directories[:5])
                if len(directories) > 5:
                    result += f" and {len(directories) - 5} more"
                result += ".\n"
            
            if files:
                result += "Files: " + ", ".join(files[:5])
                if len(files) > 5:
                    result += f" and {len(files) - 5} more"
                result += "."
            
            return True, result
        except PermissionError:
            return False, f"Permission denied when listing files in {location}"
        except Exception as e:
            return False, f"Error listing files: {str(e)}"
    
    def search_files(self, query, location):
        """Search for files and directories matching the query"""
        try:
            if not os.path.exists(location):
                return False, f"Location {location} does not exist"
            
            results = []
            
            for root, dirs, files in os.walk(location):
                # Limit search depth to avoid taking too long
                if root.count(os.sep) - location.count(os.sep) > 3:
                    continue
                
                # Check directories
                for dir in dirs:
                    if query.lower() in dir.lower():
                        results.append(os.path.join(root, dir))
                
                # Check files
                for file in files:
                    if query.lower() in file.lower():
                        results.append(os.path.join(root, file))
                
                # Limit results to prevent overwhelming the user
                if len(results) >= 10:
                    break
            
            if not results:
                return True, f"No items matching '{query}' found in {location}"
            
            result_message = f"Found {len(results)} items matching '{query}':\n"
            for i, item in enumerate(results[:5], 1):
                relative_path = os.path.relpath(item, location)
                result_message += f"{i}. {relative_path}\n"
            
            if len(results) > 5:
                result_message += f"...and {len(results) - 5} more results."
            
            return True, result_message
        except PermissionError:
            return False, f"Permission denied when searching in {location}"
        except Exception as e:
            return False, f"Error during search: {str(e)}"
    
    def run_voice_assistant(self):
        """Main loop for voice assistant interaction"""
        self.speak("Voice File Manager is now ready. What would you like to do?")
        
        while True:
            command = self.listen()
            if not command:
                continue
                
            if "exit" in command or "quit" in command or "stop" in command:
                self.speak("Exiting Voice File Manager. Goodbye!")
                break
                
            parsed_command = self.parse_command_with_nlp(command)
            success, message = self.execute_command(parsed_command)
            
            self.speak(message)
    
    def execute_command(self, parsed_command):
        """Execute the parsed command"""
        intent = parsed_command.get("intent")
        
        if intent == "unknown":
            return False, "I couldn't understand your command. Please try again with a different phrasing."
        
        elif intent == "error":
            return False, f"Error processing command: {parsed_command.get('message')}"
        
        elif intent in ["copy", "move", "share"]:
            item_name = parsed_command.get("item_name")
            source = parsed_command.get("source")
            destination = parsed_command.get("destination")
            
            # Debug information
            print(f"Executing {intent} command:")
            print(f"  Item: {item_name}")
            print(f"  Source: {source}")
            print(f"  Destination: {destination}")
            
            # Validate source and destination
            if not source:
                return False, "I couldn't determine the source location."
            
            if intent != "share" and not destination:
                return False, "I couldn't determine the destination location."
            
            # Resolve full paths
            source_path = self.resolve_path(item_name, source)
            
            if intent == "share":
                dest_path = os.path.join(self.mapped_drive_letter + "\\", item_name)
            else:
                dest_path = self.resolve_path(item_name, destination)
            
            # Print paths for debugging

if __name__ == "__main__":
    voice_manager = VoiceFileManager()