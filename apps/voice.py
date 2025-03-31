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
import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='voice_file_manager.log'
)
logger = logging.getLogger("AI_Voice_File_Manager")

class AIVoiceFileManager:
    def __init__(self):
        # Network share configuration
        self.server_ip = "192.168.9.63"  # FIB-By-Server
        self.share_name = "Shared"
        self.username = "aadish"  # FIB login username
        self.password = "1234"  # FIB password
        self.mapped_drive_letter = "S:"
        self.current_drive = "D:"  # Default to D: drive
        
        # Gemini API Key
        self.GEMINI_API_KEY = "AIzaSyCK6YT332KT79i2JvgJ6Jjes76R2I1Dtk8"
        
        # Initialize components
        self.setup_ai()
        self.setup_voice()
        
        # Connect to the network share
        self.connect_share()
        
        # Command history for debugging
        self.command_history = []
        
    def setup_ai(self):
        """Initialize the AI components"""
        try:
            # Initialize LLM (LangChain + Gemini 2.0)
            self.llm = ChatGoogleGenerativeAI(
                model="gemini-2.0",
                api_key=self.GEMINI_API_KEY,
                temperature=0,
                timeout=60
            )
            
            logger.info("AI components initialized successfully")
            print("AI components initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize AI components: {e}")
            print(f"AI initialization error: {e}")
    
    def setup_voice(self):
        """Initialize voice components"""
        try:
            # Initialize text-to-speech engine
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', 150)  # Speed of speech
            self.engine.setProperty('volume', 0.9)  # Volume (0 to 1)
            voices = self.engine.getProperty('voices')
            if len(voices) > 1:  # If there are multiple voices, use the second one (usually female)
                self.engine.setProperty('voice', voices[1].id)
            
            # Initialize speech recognizer
            self.recognizer = sr.Recognizer()
            self.recognizer.energy_threshold = 4000  # Adjust based on environment
            self.recognizer.dynamic_energy_threshold = True
            
            logger.info("Voice components initialized successfully")
            print("Voice components initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize voice components: {e}")
            print(f"Voice initialization error: {e}")
    
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
                return True # Change to False
        except Exception as e:
            print(f"Connection error: {str(e)}")
            return True # Change to False

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
    
    def ai_parse_command(self, command):
        """Use AI to parse the user's command with improved intent detection"""
        system_prompt = """
        You are a file management assistant. Your task is to accurately parse user commands for file operations.
        
        Parse the user's command and extract the following information in a structured JSON format:
        1. "intent": MUST be exactly one of these values: "copy", "move", "share", "delete", "rename", "list", "find", or "unknown"
        2. "item_name": The specific name of the file or folder mentioned
        3. "source": The source location (drive letter or path)
        4. "destination": The destination location (drive letter or path) when applicable
        
        Command examples and their expected parsing:
        - "Copy my documents folder to D drive" → {"intent": "copy", "item_name": "documents", "source": "C:", "destination": "D:"}
        - "Move vacation photos from desktop to external drive" → {"intent": "move", "item_name": "vacation photos", "source": "desktop", "destination": "E:"}
        - "Share project report with team" → {"intent": "share", "item_name": "project report", "source": "C:", "destination": "S:"}
        - "Delete old backups from downloads folder" → {"intent": "delete", "item_name": "old backups", "source": "downloads"}
        - "Rename thesis draft to final thesis" → {"intent": "rename", "item_name": "thesis draft", "source": "C:", "destination": "final thesis"}
        - "List all files in my downloads folder" → {"intent": "list", "item_name": "downloads"}
        - "Find budget spreadsheets" → {"intent": "find", "item_name": "budget spreadsheets"}
        
        Always set "source" to "D:" by default if not explicitly mentioned.
        For "share" commands, always set "destination" to "S:".
        
        Return ONLY the JSON without any explanations, markdown formatting, or code blocks.
        """
        
        try:
            # Direct single-turn query for better parsing
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Parse this file management command: '{command}'")
            ]
            
            response = self.llm.invoke(messages)
            content = response.content.strip()
            
            # Clean up any JSON formatting artifacts
            # Remove markdown code blocks if present
            json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
            if json_match:
                content = json_match.group(1)
            
            # Remove any leading/trailing characters that aren't part of JSON
            content = re.sub(r'^[^{]*', '', content)
            content = re.sub(r'[^}]*$', '', content)
            
            print(f"Cleaned JSON content: {content}")
            
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                # Fallback parsing if response isn't valid JSON
                print("JSON decode error, trying fallback parsing...")
                parsed = self.fallback_parse(command)
            
            # Validate and standardize the parsed command
            if "intent" not in parsed or parsed["intent"] not in ["copy", "move", "share", "delete", "rename", "list", "find"]:
                parsed["intent"] = "unknown"
            
            # Ensure item_name exists
            if "item_name" not in parsed or not parsed["item_name"]:
                if parsed["intent"] in ["copy", "move", "share", "delete", "rename"]:
                    # Extract potential item name from command for these operations
                    words = command.split()
                    if len(words) > 1:
                        parsed["item_name"] = words[1]  # Simple fallback - take second word
            
            # Format drive letters with colon
            for field in ["source", "destination"]:
                if field in parsed and parsed[field]:
                    # Convert single letter to drive letter
                    if len(parsed[field]) == 1:
                        parsed[field] = f"{parsed[field].upper()}:"
                    # Add colon if missing
                    elif len(parsed[field]) > 1 and parsed[field][1] != ":" and parsed[field][0].isalpha():
                        parsed[field] = f"{parsed[field][0].upper()}:{parsed[field][1:]}"
            
            # Set D: drive as default source
            if "source" not in parsed or not parsed["source"]:
                parsed["source"] = "D:"
                
            # Ensure S: for shared folder
            if parsed["intent"] == "share" and ("destination" not in parsed or not parsed["destination"]):
                parsed["destination"] = self.mapped_drive_letter
                
            print(f"Final parsed command: {parsed}")
            return parsed
            
        except Exception as e:
            logger.error(f"AI parsing error: {e}")
            print(f"AI parsing error: {e}")
            return {"intent": "unknown", "item_name": None, "source": "D:", "destination": None}
    
    def fallback_parse(self, command):
        """Fallback parsing method when AI fails to return valid JSON"""
        command = command.lower()
        result = {
            "intent": "unknown",
            "item_name": None,
            "source": "D:",
            "destination": None
        }
        
        # Simple rule-based fallback parser
        if "copy" in command:
            result["intent"] = "copy"
            # Try to find destination
            if "to" in command:
                dest_parts = command.split("to")
                if len(dest_parts) > 1:
                    dest = dest_parts[1].strip()
                    # Look for drive letter
                    drive_match = re.search(r'\b([a-z])\b\s*(?:drive)?', dest)
                    if drive_match:
                        result["destination"] = f"{drive_match.group(1).upper()}:"
                    else:
                        result["destination"] = dest
        
        elif "move" in command:
            result["intent"] = "move"
            if "to" in command:
                dest_parts = command.split("to")
                if len(dest_parts) > 1:
                    result["destination"] = dest_parts[1].strip()
        
        elif "share" in command:
            result["intent"] = "share"
            result["destination"] = self.mapped_drive_letter
        
        elif "delete" in command or "remove" in command:
            result["intent"] = "delete"
        
        elif "rename" in command:
            result["intent"] = "rename"
            if "to" in command:
                parts = command.split("to")
                if len(parts) > 1:
                    result["destination"] = parts[1].strip()
        
        elif "list" in command or "show" in command:
            result["intent"] = "list"
        
        elif "find" in command or "search" in command:
            result["intent"] = "find"
        
        # Try to extract item name
        if result["intent"] != "unknown":
            # Remove the intent word
            item_text = command.replace(result["intent"], "", 1).strip()
            # Remove destination part if it exists
            if "to" in item_text:
                item_text = item_text.split("to")[0].strip()
            # Clean up common words
            item_text = re.sub(r'\b(file|folder|directory|in|from|the)\b', '', item_text).strip()
            result["item_name"] = item_text
        
        return result
    
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
            
    def list_items(self, path):
        """List files and folders in the specified path"""
        try:
            if not os.path.exists(path):
                return False, f"Path {path} does not exist"
                
            items = os.listdir(path)
            folders = [item for item in items if os.path.isdir(os.path.join(path, item))]
            files = [item for item in items if os.path.isfile(os.path.join(path, item))]
            
            message = f"Found {len(folders)} folders and {len(files)} files in {path}"
            if folders:
                message += "\nFolders: " + ", ".join(folders[:5])
                if len(folders) > 5:
                    message += f"... and {len(folders) - 5} more"
            
            if files:
                message += "\nFiles: " + ", ".join(files[:5])
                if len(files) > 5:
                    message += f"... and {len(files) - 5} more"
                
            return True, message
        except Exception as e:
            return False, f"Error listing items: {str(e)}"
    
    def delete_item(self, path):
        """Delete a file or directory"""
        try:
            if not os.path.exists(path):
                found_path = self.find_item_in_current_directory(os.path.basename(path))
                if found_path:
                    path = found_path
                    print(f"Found item to delete at: {path}")
                else:
                    return False, f"Item {path} does not exist"
            
            if os.path.isfile(path):
                os.remove(path)
                return True, f"Deleted file {os.path.basename(path)}"
            elif os.path.isdir(path):
                shutil.rmtree(path)
                return True, f"Deleted directory {os.path.basename(path)} and all its contents"
        except PermissionError:
            return False, f"Permission denied when deleting {os.path.basename(path)}"
        except Exception as e:
            return False, f"Error during deletion: {str(e)}"
    
    def rename_item(self, source_path, new_name):
        """Rename a file or directory"""
        try:
            if not os.path.exists(source_path):
                found_path = self.find_item_in_current_directory(os.path.basename(source_path))
                if found_path:
                    source_path = found_path
                    print(f"Found item to rename at: {source_path}")
                else:
                    return False, f"Item {source_path} does not exist"
            
            dir_path = os.path.dirname(source_path)
            new_path = os.path.join(dir_path, new_name)
            
            os.rename(source_path, new_path)
            return True, f"Renamed {os.path.basename(source_path)} to {new_name}"
        except PermissionError:
            return False, f"Permission denied when renaming {os.path.basename(source_path)}"
        except Exception as e:
            return False, f"Error during rename: {str(e)}"
    
    def find_items(self, search_term, start_path=None):
        """Find files and folders matching the search term"""
        if not start_path:
            start_path = os.getcwd()
            
        try:
            results = []
            count = 0
            
            self.speak(f"Searching for {search_term}. This might take a moment.")
            
            for root, dirs, files in os.walk(start_path):
                # Check directories
                for dir_name in dirs:
                    if search_term.lower() in dir_name.lower():
                        results.append(os.path.join(root, dir_name))
                        count += 1
                        if count >= 10:
                            break
                
                # Check files
                for file_name in files:
                    if search_term.lower() in file_name.lower():
                        results.append(os.path.join(root, file_name))
                        count += 1
                        if count >= 10:
                            break
                
                if count >= 10:
                    break
            
            if results:
                message = f"Found {len(results)} items matching '{search_term}':\n"
                for i, path in enumerate(results[:5], 1):
                    message += f"{i}. {os.path.basename(path)} at {path}\n"
                if len(results) > 5:
                    message += f"...and {len(results) - 5} more results."
                return True, message
            else:
                return False, f"No items found matching '{search_term}'"
        except Exception as e:
            return False, f"Error during search: {str(e)}"
    
    def execute_command(self, parsed_command):
        """Execute the parsed command with improved error handling and debugging"""
        intent = parsed_command.get("intent", "unknown")
        item_name = parsed_command.get("item_name")
        source = parsed_command.get("source", "D:")  # Default to D: drive
        destination = parsed_command.get("destination")
        
        # Debug information
        print(f"Executing {intent} command:")
        print(f"  Item: {item_name}")
        print(f"  Source: {source}")
        print(f"  Destination: {destination}")
        
        if intent == "unknown":
            return False, "I couldn't understand your command. Please try again with a different phrasing."
        
        # Pre-process item_name if it exists
        if item_name:
            # Remove common filler words
            item_name = re.sub(r'\b(the|my|a|an|this|that)\b', '', item_name).strip()
            # Remove trailing "file" or "folder" words
            item_name = re.sub(r'(file|folder|directory)$', '', item_name).strip()
            print(f"  Processed Item Name: {item_name}")
        
        # Validate command data with better error messages
        if intent in ["copy", "move", "share", "delete", "rename"] and not item_name:
            return False, f"Please specify which file or folder you want to {intent}."
        
        if intent in ["copy", "move", "share"] and not source:
            source = "D:"  # Default to D: drive
            print(f"  Using default source: {source}")
        
        if intent in ["copy", "move"] and not destination:
            return False, f"Please specify where you want to {intent} '{item_name}' to."
        
        # Make sure source drive exists
        if source and source[0].isalpha() and source[1] == ":":
            if not os.path.exists(f"{source}\\"):
                print(f"  Warning: Source drive {source} does not exist or is not accessible")
                self.speak(f"I can't access drive {source}. Please check if it's connected.")
                # Try to find an available drive
                available_drives = self.get_available_drives()
                if available_drives:
                    source = available_drives[0]
                    print(f"  Falling back to available drive: {source}")
                    self.speak(f"I'll use drive {source} instead.")
        
        # Execute different types of commands with detailed logging
        try:
            if intent in ["copy", "move", "share"]:
                # Resolve full paths
                source_path = self.resolve_path(item_name, source)
                print(f"  Source path: {source_path}")
                
                if intent == "share":
                    dest_path = os.path.join(self.mapped_drive_letter + "\\", item_name)
                else:
                    dest_path = self.resolve_path(item_name, destination)
                print(f"  Destination path: {dest_path}")
                
                # Execute the appropriate action
                if intent == "copy" or intent == "share":
                    return self.copy_item(source_path, dest_path)
                elif intent == "move":
                    return self.move_item(source_path, dest_path)
                    
            elif intent == "list":
                list_path = source
                if item_name:
                    # Handle special folder names
                    if item_name.lower() in ["downloads", "documents", "desktop", "pictures", "music", "videos"]:
                        user_folder = os.path.expanduser("~")
                        special_folder_path = os.path.join(user_folder, item_name)
                        if os.path.exists(special_folder_path):
                            list_path = special_folder_path
                            print(f"  Using special folder path: {list_path}")
                        else:
                            list_path = self.resolve_path(item_name, source)
                    else:
                        list_path = self.resolve_path(item_name, source)
                
                print(f"  List path: {list_path}")
                return self.list_items(list_path)
                
            elif intent == "delete":
                delete_path = self.resolve_path(item_name, source)
                print(f"  Delete path: {delete_path}")
                
                # Double-check with user before deleting
                confirm = self.listen(f"Are you sure you want to delete {item_name}? Say yes or no.")
                if confirm and "yes" in confirm.lower():
                    return self.delete_item(delete_path)
                else:
                    return False, "Delete operation cancelled."
                
            elif intent == "rename":
                if not destination:  # Use destination as the new name
                    return False, "Please specify the new name for renaming."
                    
                source_path = self.resolve_path(item_name, source)
                print(f"  Rename path: {source_path} to {destination}")
                return self.rename_item(source_path, destination)
                
            elif intent == "find":
                search_path = source
                print(f"  Search path: {search_path}, Search term: {item_name}")
                return self.find_items(item_name, search_path)
            
            return False, f"I don't know how to {intent} files or folders."
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Command execution error: {error_msg}")
            print(f"ERROR EXECUTING COMMAND: {error_msg}")
            return False, f"I encountered an error: {error_msg}"
    
    def run(self):
        """Main function to run the voice assistant workflow"""
        self.speak("Welcome to AI-Powered Voice File Manager. How can I help you today?")
        
        while True:
            command = self.listen("Please tell me what files or directories you want to manage.")
            
            if not command:
                continue
            
            if "exit" in command or "quit" in command or "goodbye" in command:
                self.speak("Thank you for using Voice File Manager. Goodbye!")
                self.disconnect_share()
                break
            
            # Store command in history for debugging
            self.command_history.append(command)
            
            # For improved debugging
            print(f"\n{'='*50}")
            print(f"COMMAND: {command}")
            
            # Parse the command using AI
            parsed_command = self.ai_parse_command(command)
            print(f"AI-PARSED COMMAND: {json.dumps(parsed_command, indent=2)}")
            
            # If intent is unknown, try a more direct approach
            if parsed_command["intent"] == "unknown":
                self.speak("I'm having trouble understanding that command. Let me try to break it down.")
                
                # Try to extract operation type with direct questions
                operation_type = self.listen("What operation do you want to perform? Copy, move, delete, list, find, rename, or share?")
                
                if operation_type:
                    if "copy" in operation_type.lower():
                        parsed_command["intent"] = "copy"
                    elif "move" in operation_type.lower():
                        parsed_command["intent"] = "move"
                    elif "delete" in operation_type.lower():
                        parsed_command["intent"] = "delete"
                    elif "list" in operation_type.lower():
                        parsed_command["intent"] = "list"
                    elif "find" in operation_type.lower():
                        parsed_command["intent"] = "find"
                    elif "rename" in operation_type.lower():
                        parsed_command["intent"] = "rename"
                    elif "share" in operation_type.lower():
                        parsed_command["intent"] = "share"
                    
                    # Get item name if needed
                    if parsed_command["intent"] in ["copy", "move", "delete", "rename", "share"] and not parsed_command["item_name"]:
                        item_response = self.listen(f"What file or folder do you want to {parsed_command['intent']}?")
                        if item_response:
                            parsed_command["item_name"] = item_response
                            
                    # Get destination if needed
                    if parsed_command["intent"] in ["copy", "move"] and not parsed_command["destination"]:
                        dest_response = self.listen(f"Where do you want to {parsed_command['intent']} it to?")
                        if dest_response:
                            # Extract drive letter if present
                            drive_match = re.search(r'\b([a-z])\b\s*(?:drive)?', dest_response.lower())
                            if drive_match:
                                parsed_command["destination"] = f"{drive_match.group(1).upper()}:"
                            else:
                                parsed_command["destination"] = dest_response
                
                print(f"UPDATED PARSED COMMAND: {json.dumps(parsed_command, indent=2)}")
            
            # Execute the command
            print(f"EXECUTING COMMAND: {json.dumps(parsed_command, indent=2)}")
            success, message = self.execute_command(parsed_command)
            print(f"RESULT: Success={success}, Message={message}")
            print(f"{'='*50}\n")
            
            if success:
                self.speak(f"Success! {message}")
            else:
                self.speak(f"Sorry, there was a problem. {message}")
                
                # Offer helpful suggestions based on the specific command type
                if parsed_command["intent"] == "copy":
                    self.speak("For copy commands, try saying something like 'copy documents folder to E drive'.")
                elif parsed_command["intent"] == "move":
                    self.speak("For move commands, try saying something like 'move vacation photos from downloads to pictures folder'.")
                elif parsed_command["intent"] == "unknown":
                    self.speak("Try being specific about what operation you want to perform (copy, move, delete, list, find, rename, or share).")
                else:
                    self.speak("Try being more specific with your command. For example, 'copy Documents folder from D to C drive'.")
            
            # Ask if the user wants to continue
            continue_response = self.listen("Do you want to perform another operation? Say yes or no.")
            if continue_response and "no" in continue_response:
                self.speak("Thank you for using Voice File Manager. Goodbye!")
                self.disconnect_share()
                break

if __name__ == "__main__":
    file_manager = AIVoiceFileManager()