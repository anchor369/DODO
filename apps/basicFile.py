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
        Enhanced command parser with better pattern matching and validation
        """
        try:
            command = command.lower().strip()
            response = {
                "intent": "unknown",
                "item_name": None,
                "source": self.current_drive,
                "destination": None
            }

            # Clean up common speech artifacts
            command = re.sub(r"\b(?:please|kindly|would you)\b", "", command)
            
            # Predefined patterns with priority
            patterns = [
                # Pattern 1: "copy <item> from <source> to <destination>"
                {
                    "regex": r"^(copy|move|share)\s+(.+?)\s+from\s+([a-z])(?:\s+drive)?\s+to\s+([a-z])(?:\s+drive)?$",
                    "groups": ["intent", "item_name", "source", "destination"]
                },
                # Pattern 2: "copy <item> to <destination>"
                {
                    "regex": r"^(copy|move|share)\s+(.+?)\s+to\s+([a-z])(?:\s+drive)?$",
                    "groups": ["intent", "item_name", "destination"]
                },
                # Pattern 3: "copy <item> from <source>"
                {
                    "regex": r"^(copy|move|share)\s+(.+?)\s+from\s+([a-z])(?:\s+drive)?$",
                    "groups": ["intent", "item_name", "source"]
                },
                # Pattern 4: "share <item>"
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
                        if group_name == "intent":
                            response[group_name] = groups[i]
                        elif group_name == "item_name":
                            # Clean item name from command artifacts
                            item = groups[i].replace(" folder", "").replace(" directory", "").replace(" file", "").strip()
                            response[group_name] = item
                        elif group_name in ("source", "destination"):
                            response[group_name] = f"{groups[i].upper()}:"
                    
                    # Apply defaults if needed
                    if "defaults" in pattern:
                        for k, v in pattern["defaults"].items():
                            response[k] = v
                    
                    # Validate drive formats
                    if response["source"] and len(response["source"]) == 1:
                        response["source"] += ":"
                    if response["destination"] and len(response["destination"]) == 1:
                        response["destination"] += ":"
                    
                    # Final validation
                    if response["intent"] in ("copy", "move") and not all([response["item_name"], response["destination"]]):
                        continue  # Skip invalid matches
                    
                    return response

            # Fallback: Advanced component extraction
            components = {
                "actions": ["copy", "move", "share", "cut"],
                "prepositions": ["from", "to", "into", "on"]
            }
            
            # Split command into meaningful parts
            parts = re.split(r"\s+(?=" + "|".join(components["prepositions"]) + ")", command)
            
            if len(parts) >= 2:
                # First part contains action and item
                action_part = parts[0].split()
                response["intent"] = action_part[0]
                response["item_name"] = " ".join(action_part[1:]).strip()
                
                # Process subsequent parts
                current_field = None
                for part in parts[1:]:
                    key_value = part.split(maxsplit=1)
                    preposition = key_value[0]
                    value = key_value[1] if len(key_value) > 1 else ""
                    
                    if preposition == "from":
                        current_field = "source"
                    elif preposition in ("to", "into", "on"):
                        current_field = "destination"
                    
                    if current_field:
                        # Extract drive letter or path
                        drive_match = re.search(r"([a-z])\s+drive", value)
                        if drive_match:
                            response[current_field] = f"{drive_match.group(1).upper()}:"
                        elif value:
                            response[current_field] = value.strip()

            # Post-processing
            response["item_name"] = re.sub(r"\b(?:folder|directory|file)\b", "", response["item_name"] or "").strip()
            
            # Convert single-letter drives
            for field in ("source", "destination"):
                if response[field] and len(response[field]) == 1:
                    response[field] += ":"
            
            return response

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
            print(f"  Source path: {source_path}")
            print(f"  Destination path: {dest_path}")
            
            # Execute the appropriate action
            if intent == "copy" or intent == "share":
                return self.copy_item(source_path, dest_path)
            elif intent == "move":
                return self.move_item(source_path, dest_path)
        
        return False, "Command not implemented yet."

    def run_voice_assistant(self):
        """Main function to run the voice assistant workflow"""
        self.speak("Welcome to Voice File Manager. How can I help you today?")
        
        while True:
            command = self.listen("Please tell me what files or directories you want to manage.")
            
            if not command:
                continue
            
            if "exit" in command or "quit" in command or "goodbye" in command:
                self.speak("Thank you for using Voice File Manager. Goodbye!")
                self.disconnect_share()
                break
            
            # Parse the command using NLP
            parsed_command = self.parse_command_with_nlp(command)
            print(f"Parsed command: {parsed_command}")
            
            # Execute the command
            success, message = self.execute_command(parsed_command)
            
            if success:
                self.speak(f"Success! {message}")
            else:
                self.speak(f"Sorry, there was a problem. {message}")
                
                # Offer helpful suggestions
                self.speak("Try being more specific with your command. For example, 'copy Documents folder from C to D drive'.")
            
            # Ask if the user wants to continue
            continue_response = self.listen("Do you want to perform another operation? Say yes or no.")
            if continue_response and "no" in continue_response:
                self.speak("Thank you for using Voice File Manager. Goodbye!")
                self.disconnect_share()
                break

def create_mutex():
    """Ensure only one instance of the application is running"""
    try:
        mutex = ctypes.windll.kernel32.CreateMutexA(None, False, b"VoiceFileManagerApp")
        if ctypes.windll.kernel32.GetLastError() == 183:
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo("Voice File Manager", "Application is already running.")
            root.destroy()
            sys.exit(0)
        return mutex
    except:
        return None

def main():
    if platform.system() != "Windows":
        print("This application is designed for Windows only.")
        sys.exit(1)

    create_mutex()
    
    # Check for required libraries
    try:
        import speech_recognition
        import pyttsx3
    except ImportError:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Missing Dependencies", 
                           "Please install required packages with:\n\n"
                           "pip install SpeechRecognition pyttsx3 pyaudio")
        root.destroy()
        sys.exit(1)
    
    app = VoiceFileManager()

if __name__ == "__main__":
    main()