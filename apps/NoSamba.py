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
import queue
import concurrent.futures
import google.generativeai as genai

class VoiceFileManager:
    def __init__(self):
        self.current_drive = os.getcwd()[:2]  # Get current drive (e.g., "C:")
        
        # Initialize Gemini LLM
        self.GEMINI_API_KEY = "AIzaSyCK6YT332KT79i2JvgJ6Jjes76R2I1Dtk8"
        genai.configure(api_key=self.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        
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

    def analyze_with_llm(self, command):
        """Use Gemini LLM to understand user intent and extract details from commands"""
        try:
            # Get available drives for context
            drives = self.get_available_drives()
            drives_list = ", ".join(drives)
            
            prompt = f"""
            As a voice-activated file manager assistant, analyze this command: "{command}"
            
            Available drives on this system: {drives_list}
            Current drive: {self.current_drive}
            Network share mounted at: {self.mapped_drive_letter}
            
            Extract the following information in JSON format:
            {{
                "intent": "find" or "copy" or "move" or "cut" or "share" or "list" or "create" or "delete" or "rename" or "unknown",
                "item_name": the name of the file or folder being referenced,
                "source": the source location (drive letter or path),
                "destination": the destination location (drive letter or path) if applicable,
                "explanation": a brief explanation of what the user wants to do
            }}
            
            For example, if the user says "find my tax documents from last year", the response should be:
            {{
                "intent": "find",
                "item_name": "tax documents",
                "source": null,
                "destination": null,
                "explanation": "User wants to find files related to tax documents from last year"
            }}
            
            If the user says "move my presentation from C drive to the network share", the response should be:
            {{
                "intent": "move",
                "item_name": "presentation",
                "source": "C:",
                "destination": "S:",
                "explanation": "User wants to move their presentation from C drive to the network share"
            }}
            
            Return ONLY the JSON object without any additional text.
            """
            
            response = self.model.generate_content(prompt)
            response_text = response.text
            
            # Clean the response in case the LLM added markdown or extra text
            try:
                # Extract JSON if wrapped in code blocks
                if '```json' in response_text:
                    json_str = response_text.split('```json')[1].split('```')[0].strip()
                elif '```' in response_text:
                    json_str = response_text.split('```')[1].strip()
                else:
                    json_str = response_text.strip()
                
                parsed_response = json.loads(json_str)
                
                # Add default values for anything missing
                if "intent" not in parsed_response:
                    parsed_response["intent"] = "unknown"
                if "item_name" not in parsed_response:
                    parsed_response["item_name"] = None
                if "source" not in parsed_response:
                    parsed_response["source"] = self.current_drive
                if "destination" not in parsed_response:
                    parsed_response["destination"] = None
                if "explanation" not in parsed_response:
                    parsed_response["explanation"] = "No explanation provided"
                
                # Normalize drive letters to uppercase with colon
                if parsed_response["source"] and len(parsed_response["source"]) == 1:
                    parsed_response["source"] = f"{parsed_response['source'].upper()}:"
                if parsed_response["destination"] and len(parsed_response["destination"]) == 1:
                    parsed_response["destination"] = f"{parsed_response['destination'].upper()}:"
                
                print(f"LLM analyzed intent: {parsed_response}")
                return parsed_response
                
            except json.JSONDecodeError as e:
                print(f"Error parsing LLM response as JSON: {e}")
                print(f"Raw response: {response_text}")
                # Fall back to rule-based parsing if LLM fails
                return self.parse_command(command)
                
        except Exception as e:
            print(f"Error communicating with LLM: {e}")
            # Fall back to rule-based parsing as backup
            return self.parse_command(command)

    def get_available_drives(self):
        """Get list of available drives on the system"""
        drives = []
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            if bitmask & 1:
                drives.append(f"{letter}:")
            bitmask >>= 1
        return drives

    def parse_command(self, command):
        """Legacy parse user command using simple NLP techniques (backup method)"""
        try:
            command = command.lower().strip()
            
            # Initialize response structure
            response = {
                "intent": "unknown",
                "item_name": None,
                "source": self.current_drive,
                "destination": None,
                "explanation": "Command parsed using backup method"
            }
            
            # FIND COMMANDS - Check these first with high priority
            find_keywords = ["find", "search", "locate", "look for", "where is", "where are"]
            
            if any(keyword in command for keyword in find_keywords):
                response["intent"] = "find"
                
                # Extract item name after the find keyword
                for keyword in find_keywords:
                    if keyword in command:
                        parts = command.split(keyword, 1)
                        if len(parts) > 1:
                            item_name = parts[1].strip()
                            # Clean up common words
                            for word in ["for", "my", "the", "folder", "file", "directory", "document"]:
                                item_name = item_name.replace(f" {word} ", " ").replace(f" {word}", "")
                            response["item_name"] = item_name.strip()
                            return response
            
            # COPY, MOVE, CUT, SHARE COMMANDS
            if any(action in command for action in ["copy", "move", "cut", "share"]):
                # Determine the action/intent
                if "copy" in command:
                    response["intent"] = "copy"
                elif "move" in command:
                    response["intent"] = "move"
                elif "cut" in command:
                    response["intent"] = "cut"
                elif "share" in command:
                    response["intent"] = "share"
                    response["destination"] = self.mapped_drive_letter
                
                # Pattern: "<action> <item> from <source> to <destination>"
                pattern1 = r"(copy|move|cut|share)\s+(.+?)\s+from\s+([a-z])\s+(?:drive\s+)?to\s+([a-z])\s+(?:drive)?"
                match = re.search(pattern1, command)
                if match:
                    response["item_name"] = match.group(2).strip()
                    response["source"] = f"{match.group(3).upper()}:"
                    response["destination"] = f"{match.group(4).upper()}:"
                    return response
                
                # Pattern: "<action> <item> to <destination>"
                pattern2 = r"(copy|move|cut|share)\s+(.+?)\s+to\s+([a-z])\s+(?:drive)?"
                match = re.search(pattern2, command)
                if match:
                    response["item_name"] = match.group(2).strip()
                    response["destination"] = f"{match.group(3).upper()}:"
                    return response
                
                # Pattern: "<action> <item> from <source>"
                pattern3 = r"(copy|move|cut|share)\s+(.+?)\s+from\s+([a-z])\s+(?:drive)?"
                match = re.search(pattern3, command)
                if match:
                    response["item_name"] = match.group(2).strip()
                    response["source"] = f"{match.group(3).upper()}:"
                    return response
                
                # Pattern: "<action> <item>"
                pattern4 = r"(copy|move|cut|share)\s+(.+)"
                match = re.search(pattern4, command)
                if match:
                    response["item_name"] = match.group(2).strip()
                    return response
            
            # ADDITIONAL INTENTS FOR ENHANCED FEATURES
            
            # LIST COMMANDS
            list_keywords = ["list", "show", "display", "what's in", "what is in", "contents of"]
            if any(keyword in command for keyword in list_keywords):
                response["intent"] = "list"
                # Extract location
                for keyword in list_keywords:
                    if keyword in command:
                        parts = command.split(keyword, 1)
                        if len(parts) > 1:
                            location = parts[1].strip()
                            # Look for drive references
                            drive_match = re.search(r"([a-z])\s+drive", location)
                            if drive_match:
                                response["source"] = f"{drive_match.group(1).upper()}:"
                            response["item_name"] = location
                            return response
            
            # CREATE COMMANDS
            create_keywords = ["create", "make", "new"]
            if any(keyword in command for keyword in create_keywords):
                response["intent"] = "create"
                for keyword in create_keywords:
                    if keyword in command:
                        parts = command.split(keyword, 1)
                        if len(parts) > 1:
                            item_name = parts[1].strip()
                            # Check for folder/file keywords
                            if "folder" in item_name or "directory" in item_name:
                                response["item_name"] = item_name.replace("folder", "").replace("directory", "").strip()
                            else:
                                response["item_name"] = item_name
                            return response
            
            # DELETE COMMANDS
            delete_keywords = ["delete", "remove", "trash", "get rid of"]
            if any(keyword in command for keyword in delete_keywords):
                response["intent"] = "delete"
                for keyword in delete_keywords:
                    if keyword in command:
                        parts = command.split(keyword, 1)
                        if len(parts) > 1:
                            response["item_name"] = parts[1].strip()
                            return response
            
            # RENAME COMMANDS
            if "rename" in command:
                response["intent"] = "rename"
                rename_pattern = r"rename\s+(.+?)\s+to\s+(.+)"
                match = re.search(rename_pattern, command)
                if match:
                    response["item_name"] = match.group(1).strip()
                    response["destination"] = match.group(2).strip()  # Using destination for new name
                    return response
            
            # Clean item name from common words if it exists
            if response["item_name"]:
                # Remove words like "folder", "file", etc.
                response["item_name"] = re.sub(r"\b(folder|file|directory|document)s?\b", "", response["item_name"]).strip()
            
            return response
            
        except Exception as e:
            print(f"Error parsing command: {str(e)}")
            return {
                "intent": "error", 
                "message": f"Failed to parse: {str(e)}",
                "explanation": f"Error occurred: {str(e)}"
            }
    
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

    def search_drive(self, drive, item_name, result_queue, max_results=5):
        """Search a specific drive for files/folders matching item_name"""
        try:
            count = 0
            drive_results = []
            print(f"Started searching drive {drive}...")
            
            # Check if drive exists and is accessible
            if not os.path.exists(f"{drive}\\"):
                print(f"Drive {drive} is not accessible")
                return
            
            search_term = item_name.lower()
            
            # Set a timeout to prevent very long searches
            start_time = time.time()
            max_search_time = 30  # Max 30 seconds per drive
            
            # Walk the directory tree
            for root, dirs, files in os.walk(drive + "\\"):
                # Check if search is taking too long
                if time.time() - start_time > max_search_time:
                    print(f"Search timeout on drive {drive} after {max_search_time} seconds")
                    if drive_results:
                        drive_results.append(f"...search timeout after {max_search_time} seconds")
                    break
                
                # Optimize search by skipping system directories
                dirs[:] = [d for d in dirs if not d.startswith('$') and d not in ['System Volume Information', 'Windows']]
                
                # Check directories
                for dir in dirs:
                    if search_term in dir.lower():
                        drive_results.append(os.path.join(root, dir))
                        count += 1
                        if count >= max_results:
                            drive_results.append(f"...and more results on {drive}")
                            result_queue.put((drive, drive_results))
                            return
                
                # Check files
                for file in files:
                    if search_term in file.lower():
                        drive_results.append(os.path.join(root, file))
                        count += 1
                        if count >= max_results:
                            drive_results.append(f"...and more results on {drive}")
                            result_queue.put((drive, drive_results))
                            return
            
            # Add results to queue if any found
            if drive_results:
                print(f"Found {len(drive_results)} matches on drive {drive}")
                result_queue.put((drive, drive_results))
            else:
                print(f"No matches found on drive {drive}")
                
        except PermissionError:
            print(f"Permission error on drive {drive}")
            pass
        except Exception as e:
            print(f"Error searching drive {drive}: {str(e)}")
            pass

    def find_item_across_drives(self, item_name):
        """Search for an item across all available drives using parallel threads"""
        print(f"Searching for '{item_name}' across all drives...")
        self.speak(f"Searching for {item_name} across all drives. This might take a moment...")
        
        drives = self.get_available_drives()
        result_queue = queue.Queue()
        threads = []
        max_workers = min(len(drives), 4)  # Limit to 4 concurrent threads to avoid overloading the system
        
        # Create thread pool
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit search tasks for each drive
            future_to_drive = {
                executor.submit(self.search_drive, drive, item_name, result_queue): drive
                for drive in drives
            }
            
            # Start a separate thread to provide progress updates to the user
            progress_thread = threading.Thread(target=self.search_progress_reporter, args=(result_queue, len(drives)))
            progress_thread.daemon = True
            progress_thread.start()
            
            # Wait for all futures to complete (with timeout)
            concurrent.futures.wait(future_to_drive, timeout=60)
        
        # Collect results from the queue
        all_results = []
        while not result_queue.empty():
            drive, results = result_queue.get()
            all_results.extend(results)
        
        return all_results

    def search_progress_reporter(self, result_queue, total_drives):
        """Report search progress while threads are working"""
        drives_completed = set()
        start_time = time.time()
        
        while len(drives_completed) < total_drives:
            # Break if search is taking too long (over 60 seconds)
            if time.time() - start_time > 60:
                print("Search timed out after 60 seconds")
                break
                
            # Check for new results
            try:
                drive, _ = result_queue.get(block=True, timeout=1)
                drives_completed.add(drive)
                print(f"Completed {len(drives_completed)}/{total_drives} drives")
                result_queue.put((drive, _))  # Put the result back for collection later
            except queue.Empty:
                # No new results yet
                pass
            
            # Sleep briefly to avoid burning CPU
            time.sleep(0.1)
    
    def list_directory(self, directory_path):
        """List contents of a directory"""
        try:
            if not os.path.exists(directory_path):
                return False, f"The path {directory_path} does not exist"
            
            if not os.path.isdir(directory_path):
                return False, f"{directory_path} is not a directory"
            
            items = os.listdir(directory_path)
            
            # Separate files and folders
            folders = [item for item in items if os.path.isdir(os.path.join(directory_path, item))]
            files = [item for item in items if os.path.isfile(os.path.join(directory_path, item))]
            
            # Format the result
            result = f"Contents of {directory_path}:\n"
            if folders:
                result += f"Folders ({len(folders)}): {', '.join(folders[:5])}"
                if len(folders) > 5:
                    result += f" and {len(folders) - 5} more"
                result += "\n"
            
            if files:
                result += f"Files ({len(files)}): {', '.join(files[:5])}"
                if len(files) > 5:
                    result += f" and {len(files) - 5} more"
            
            return True, result
            
        except PermissionError:
            return False, f"Permission denied when accessing {directory_path}"
        except Exception as e:
            return False, f"Error listing directory: {str(e)}"
    
    def create_item(self, item_path, is_folder=True):
        """Create a new folder or file at the specified path"""
        try:
            # Check if item already exists
            if os.path.exists(item_path):
                return False, f"The item {os.path.basename(item_path)} already exists"
            
            if is_folder:
                os.makedirs(item_path)
                return True, f"Created folder {os.path.basename(item_path)}"
            else:
                # Create parent directories if they don't exist
                parent_dir = os.path.dirname(item_path)
                if parent_dir and not os.path.exists(parent_dir):
                    os.makedirs(parent_dir)
                
                # Create an empty file
                with open(item_path, 'w') as f:
                    pass
                return True, f"Created file {os.path.basename(item_path)}"
                
        except PermissionError:
            return False, f"Permission denied when creating {os.path.basename(item_path)}"
        except Exception as e:
            return False, f"Error creating item: {str(e)}"
    
    def delete_item(self, item_path):
        """Delete a file or folder at the specified path"""
        try:
            # Check if item exists
            if not os.path.exists(item_path):
                # Try to find it in current directory
                found_path = self.find_item_in_current_directory(os.path.basename(item_path))
                if found_path:
                    item_path = found_path
                    print(f"Found item to delete at: {item_path}")
                else:
                    return False, f"The item {os.path.basename(item_path)} does not exist"
            
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
                return True, f"Deleted folder {os.path.basename(item_path)} and all its contents"
            else:
                os.remove(item_path)
                return True, f"Deleted file {os.path.basename(item_path)}"
                
        except PermissionError:
            return False, f"Permission denied when deleting {os.path.basename(item_path)}"
        except Exception as e:
            return False, f"Error deleting item: {str(e)}"
    
    def rename_item(self, old_path, new_name):
        """Rename a file or folder"""
        try:
            # Check if source exists
            if not os.path.exists(old_path):
                # Try to find it in current directory
                found_path = self.find_item_in_current_directory(os.path.basename(old_path))
                if found_path:
                    old_path = found_path
                    print(f"Found item to rename at: {old_path}")
                else:
                    return False, f"The item {os.path.basename(old_path)} does not exist"
            
            # Create new path with the same directory but new name
            new_path = os.path.join(os.path.dirname(old_path), new_name)
            
            # Check if destination already exists
            if os.path.exists(new_path):
                return False, f"An item named {new_name} already exists at this location"
            
            # Rename the item
            os.rename(old_path, new_path)
            return True, f"Renamed {os.path.basename(old_path)} to {new_name}"
                
        except PermissionError:
            return False, f"Permission denied when renaming {os.path.basename(old_path)}"
        except Exception as e:
            return False, f"Error renaming item: {str(e)}"
    
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
    
    def cut_item(self, item_name, source, destination):
        """Cut (move) an item from source to destination"""
        try:
            source_path = self.resolve_path(item_name, source)
            dest_path = self.resolve_path(item_name, destination)
            
            # Check if source exists
            if not os.path.exists(source_path):
                # Try to find the item in current directory
                found_path = self.find_item_in_current_directory(os.path.basename(source_path))
                if found_path:
                    source_path = found_path
                    print(f"Found item at: {source_path}")
                else:
                    return False, f"Source {source_path} does not exist"
            
            # Move the item directly to destination
            return self.move_item(source_path, dest_path)
            
        except Exception as e:
            return False, f"Error during cut operation: {str(e)}"
    
    def execute_command(self, parsed_command):
        """Execute the parsed command"""
        intent = parsed_command.get("intent")
        
        if intent == "unknown":
            return False, "I couldn't understand your command. Please try again with a different phrasing."
        
        elif intent == "error":
            return False, f"Error processing command: {parsed_command.get('message')}"
        
        elif intent == "find":
            item_name = parsed_command.get("item_name")
            
            # Debug information
            print(f"Executing find command:")
            print(f"  Item to find: {item_name}")
            
            if not item_name:
                return False, "I couldn't determine what you're looking for. Please specify a file or folder name."
                        
            # Execute the search
            found_locations = self.find_item_across_drives(item_name)
            
            if found_locations:
                # Remove entries that are progress indicators
                result_entries = [loc for loc in found_locations if not loc.startswith("...")]
                num_results = len(result_entries)
                
                if num_results == 0:
                    return False, f"Search was incomplete. Please try with a more specific term than '{item_name}'."
                elif num_results == 1:
                    location_message = f"I found {item_name} at: {result_entries[0]}"
                    print(location_message)
                    return True, location_message
                else:
                    # Summarize by drive for cleaner output
                    drive_summary = {}
                    for loc in result_entries:
                        drive = loc[:2]  # Get the drive letter (e.g., "C:")
                        if drive in drive_summary:
                            drive_summary[drive] += 1
                        else:
                            drive_summary[drive] = 1
                    
                    summary = f"I found {num_results} matches for {item_name}. "
                    summary += "Files/folders were found in: "
                    summary += ", ".join([f"{count} matches on {drive}" for drive, count in drive_summary.items()])
                    
                    # Log detailed results
                    print(f"Detailed results for '{item_name}':")
                    for loc in result_entries[:10]:  # Show first 10 results
                        print(f"  - {loc}")
                    if len(result_entries) > 10:
                        print(f"  ... and {len(result_entries) - 10} more")
                    
                    return True, summary
            else:
                return False, f"I couldn't find {item_name} on any drive. Please check the spelling or try another search term."
        
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
        
        elif intent == "cut":
            item_name = parsed_command.get("item_name")
            source = parsed_command.get("source")
            destination = parsed_command.get("destination")
            
            # Debug information
            print(f"Executing cut command:")
            print(f"  Item: {item_name}")
            print(f"  Source: {source}")
            print(f"  Destination: {destination}")
            
            # Validate source and destination
            if not source:
                return False, "I couldn't determine the source location."
            
            if not destination:
                return False, "I couldn't determine the destination location."
                
            return self.cut_item(item_name, source, destination)
        
        elif intent == "list":
            item_name = parsed_command.get("item_name")
            source = parsed_command.get("source")
            
            # Debug information
            print(f"Executing list command:")
            print(f"  Location: {item_name}")
            print(f"  Drive: {source}")
            
            # Try to determine the directory to list
            directory_path = None
            
            # If a specific drive was mentioned
            if source and source != self.current_drive:
                # If item_name is empty, list the root of the drive
                if not item_name or item_name.strip() == "":
                    directory_path = f"{source}\\"
                else:
                    directory_path = self.resolve_path(item_name, source)
            # If no specific drive, use the current directory or the specified subdirectory
            else:
                if not item_name or item_name.strip() == "":
                    directory_path = os.getcwd()
                else:
                    # Check if item_name is a subdirectory of current directory
                    potential_path = os.path.join(os.getcwd(), item_name)
                    if os.path.isdir(potential_path):
                        directory_path = potential_path
                    else:
                        # Try to find the directory
                        found_path = self.find_item_in_current_directory(item_name)
                        if found_path and os.path.isdir(found_path):
                            directory_path = found_path
                        else:
                            directory_path = os.getcwd()
            
            print(f"  Final directory path to list: {directory_path}")
            return self.list_directory(directory_path)
        
        elif intent == "create":
            item_name = parsed_command.get("item_name")
            source = parsed_command.get("source")
            
            # Debug information
            print(f"Executing create command:")
            print(f"  Item name: {item_name}")
            print(f"  Location: {source}")
            
            # Determine if it's a file or folder
            is_folder = True
            if "file" in parsed_command.get("explanation", "").lower():
                is_folder = False
            
            # Resolve the path
            item_path = self.resolve_path(item_name, source)
            
            print(f"  Creating {'folder' if is_folder else 'file'} at: {item_path}")
            return self.create_item(item_path, is_folder)
        
        elif intent == "delete":
            item_name = parsed_command.get("item_name")
            source = parsed_command.get("source")
            
            # Debug information
            print(f"Executing delete command:")
            print(f"  Item name: {item_name}")
            print(f"  Location: {source}")
            
            # Resolve the path
            item_path = self.resolve_path(item_name, source)
            
            print(f"  Deleting item at: {item_path}")
            return self.delete_item(item_path)
        
        elif intent == "rename":
            item_name = parsed_command.get("item_name")  # Old name
            new_name = parsed_command.get("destination")  # New name
            source = parsed_command.get("source")
            
            # Debug information
            print(f"Executing rename command:")
            print(f"  Old name: {item_name}")
            print(f"  New name: {new_name}")
            print(f"  Location: {source}")
            
            # Validate new name
            if not new_name:
                return False, "I couldn't determine the new name for the item."
            
            # Resolve the path
            old_path = self.resolve_path(item_name, source)
            
            print(f"  Renaming item at: {old_path} to {new_name}")
            return self.rename_item(old_path, new_name)
        
        return False, "Command not implemented yet."

    def run_voice_assistant(self):
        """Main function to run the voice assistant workflow"""
        self.speak("Welcome to Enhanced Voice File Manager powered by Gemini AI. How can I help you today?")
        
        while True:
            command = self.listen("What would you like me to do with your files or directories?")
            
            if not command:
                continue
            
            if "exit" in command or "quit" in command or "goodbye" in command:
                self.speak("Thank you for using Enhanced Voice File Manager. Goodbye!")
                self.disconnect_share()
                break
            
            # Use Gemini LLM to analyze the command
            try:
                print("Analyzing command with Gemini LLM...")
                parsed_command = self.analyze_with_llm(command)
                print(f"LLM parsed command: {parsed_command}")
                
                # Fall back to legacy parser if LLM returns an unknown intent
                if parsed_command.get("intent") == "unknown":
                    print("LLM couldn't determine intent, falling back to legacy parser...")
                    legacy_parsed = self.parse_command(command)
                    # Only use legacy result if it found a valid intent
                    if legacy_parsed.get("intent") != "unknown":
                        parsed_command = legacy_parsed
                        print(f"Legacy parser result: {parsed_command}")
            except Exception as e:
                print(f"Error in LLM analysis: {e}")
                # Fall back to legacy parser on error
                parsed_command = self.parse_command(command)
                print(f"Fallback to legacy parser: {parsed_command}")
            
            # Execute the command
            success, message = self.execute_command(parsed_command)
            
            # Generate a more natural response using Gemini
            if success:
                try:
                    # Try to generate a more natural success response
                    success_prompt = f"""
                    Generate a natural, friendly response for a voice assistant that has successfully completed this task:
                    Command: "{command}"
                    Result: "{message}"
                    
                    Give a short, conversational response (maximum 2 sentences) that confirms the task was completed successfully.
                    Include the key information from the result.
                    """
                    
                    success_response = self.model.generate_content(success_prompt).text
                    # Clean up response if needed (remove quotes, etc.)
                    success_response = success_response.strip('"\'').strip()
                    self.speak(success_response)
                except Exception as e:
                    print(f"Error generating LLM success response: {e}")
                    # Fallback to standard success message
                    self.speak(f"Success! {message}")
            else:
                # For failures, include suggestions for improvement
                try:
                    # Generate a helpful failure response with suggestions
                    failure_prompt = f"""
                    Generate a natural, helpful response for a voice assistant that could not complete this task:
                    Command: "{command}"
                    Error: "{message}"
                    Intent: "{parsed_command.get('intent')}"
                    
                    Give a short, conversational response (maximum 3 sentences) that:
                    1. Acknowledges the error in a friendly way
                    2. Explains what went wrong
                    3. Provides a clear example of how to phrase the command correctly
                    """
                    
                    failure_response = self.model.generate_content(failure_prompt).text
                    # Clean up response
                    failure_response = failure_response.strip('"\'').strip()
                    self.speak(failure_response)
                except Exception as e:
                    print(f"Error generating LLM failure response: {e}")
                    # Fallback to standard error message with basic suggestions
                    self.speak(f"Sorry, there was a problem. {message}")
                    
                    # Offer helpful suggestions
                    if parsed_command.get("intent") == "cut":
                        self.speak("To cut a file or folder, try saying 'cut Documents folder from C drive to D drive'.")
                    elif parsed_command.get("intent") == "find":
                        self.speak("To find a file or folder, try saying 'find budget spreadsheet' or 'where is my presentation'.")
                    else:
                        self.speak("Try being more specific with your command. For example, 'copy Documents folder from C to D drive'.")


def create_mutex():
    """Ensure only one instance of the application is running"""
    try:
        mutex = ctypes.windll.kernel32.CreateMutexA(None, False, b"EnhancedVoiceFileManagerApp")
        if ctypes.windll.kernel32.GetLastError() == 183:
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo("Enhanced Voice File Manager", "Application is already running.")
            root.destroy()
            sys.exit(0)
        return mutex
    except:
        return None

def show_splash_screen():
    """Display a splash screen while the application is loading"""
    root = tk.Tk()
    root.title("Enhanced Voice File Manager")
    
    # Center the window
    window_width = 400
    window_height = 200
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    center_x = int(screen_width/2 - window_width/2)
    center_y = int(screen_height/2 - window_height/2)
    
    root.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
    root.resizable(False, False)
    
    # Add a label
    label = tk.Label(
        root, 
        text="Enhanced Voice File Manager\nPowered by Gemini AI",
        font=("Arial", 16),
        pady=20
    )
    label.pack()
    
    # Add a progress message
    message = tk.Label(
        root,
        text="Initializing voice recognition and AI services...",
        font=("Arial", 10),
        pady=10
    )
    message.pack()
    
    # Add a progress bar
    progress = tk.Label(
        root,
        text="⬜⬜⬜⬜⬜",
        font=("Arial", 24),
        pady=10
    )
    progress.pack()
    
    # Function to update progress
    def update_progress():
        progress_states = ["⬛⬜⬜⬜⬜", "⬛⬛⬜⬜⬜", "⬛⬛⬛⬜⬜", "⬛⬛⬛⬛⬜", "⬛⬛⬛⬛⬛"]
        for state in progress_states:
            progress.config(text=state)
            root.update()
            time.sleep(0.5)
        root.destroy()
    
    # Start progress update in a separate thread
    threading.Thread(target=update_progress, daemon=True).start()
    
    root.mainloop()

def main():
    if platform.system() != "Windows":
        print("This application is designed for Windows only.")
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Platform Error", "This application is designed for Windows only.")
        root.destroy()
        sys.exit(1)

    create_mutex()
    
    # Display splash screen
    show_splash_screen()
    
    # Check for required libraries
    try:
        import speech_recognition
        import pyttsx3
        import google.generativeai
    except ImportError:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Missing Dependencies", 
                           "Please install required packages with:\n\n"
                           "pip install SpeechRecognition pyttsx3 pyaudio google-generativeai")
        root.destroy()
        sys.exit(1)
    
    # Check for internet connection
    if not check_network_connection():
        root = tk.Tk()
        root.withdraw()
        response = messagebox.askquestion("No Internet Connection", 
                                       "No internet connection detected. The AI features will not work.\n\n"
                                       "Do you want to continue with limited functionality?")
        root.destroy()
        
        if response == 'no':
            sys.exit(0)
    
    try:
        app = VoiceFileManager()
    except Exception as e:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Initialization Error", 
                           f"Error starting the application:\n\n{str(e)}\n\n"
                           "Please check your internet connection and API key.")
        root.destroy()
        sys.exit(1)

if __name__ == "__main__":
    main()