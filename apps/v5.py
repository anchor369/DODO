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
        
        # Add context state to maintain conversation continuity
        self.conversation_context = {
            "last_action": None,
            "found_items": [],
            "selected_item": None,
            "last_command": None
        }
        
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

    def parse_command(self, command):
        """Parse user command using simple NLP techniques"""
        try:
            command = command.lower().strip()
            
            # Initialize response structure
            response = {
                "intent": "unknown",
                "item_name": None,
                "source": self.current_drive,
                "destination": None,
                "index": None,  # For selecting items by index
                "new_name": None  # For rename operations
            }
            
            # Check for continuity references (it, that, this file, etc.)
            continuity_references = ["it", "that", "this file", "this folder", "this directory", 
                                     "that file", "that folder", "that directory"]
            
            has_continuity_ref = any(ref in command for ref in continuity_references)
                
            # RENAME COMMANDS
            if "rename" in command:
                response["intent"] = "rename"
                
                # Pattern: "rename <item> to <new_name>"
                pattern1 = r"rename\s+(.+?)\s+to\s+(.+)"
                match = re.search(pattern1, command)
                
                if match:
                    response["item_name"] = match.group(1).strip()
                    response["new_name"] = match.group(2).strip()
                    return response
                
                # Pattern with continuity: "rename it to <new_name>" or "rename to <new_name>"
                if has_continuity_ref or command.startswith("rename to "):
                    pattern2 = r"rename(?:\s+(?:it|that|this|this file|this folder|that file|that folder))?\s+to\s+(.+)"
                    match = re.search(pattern2, command)
                    if match:
                        response["intent"] = "rename_last"
                        response["new_name"] = match.group(1).strip()
                        return response
            
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
            
            # MOVE/COPY/CUT/SHARE BY INDEX OR REFERENCE TO PREVIOUS RESULTS
            # Pattern: "move first one to <dest>" or "copy second file to <dest>"
            index_pattern = r"(move|copy|cut|share)\s+(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|last|\d+(?:st|nd|rd|th)?)\s+(?:one|file|folder|item|result)?\s+to\s+([a-z])\s+(?:drive)?"
            index_match = re.search(index_pattern, command)
            
            if index_match:
                response["intent"] = index_match.group(1)  # move, copy, cut, share
                index_word = index_match.group(2)
                
                # Convert word index to numeric
                index_map = {
                    "first": 0, "1st": 0,
                    "second": 1, "2nd": 1,
                    "third": 2, "3rd": 2,
                    "fourth": 3, "4th": 3,
                    "fifth": 4, "5th": 4,
                    "last": -1
                }
                
                # Try to get index from map, otherwise parse numeric value
                if index_word in index_map:
                    response["index"] = index_map[index_word]
                else:
                    # Try to extract numeric part
                    num_match = re.search(r"(\d+)", index_word)
                    if num_match:
                        # Convert to 0-based index
                        response["index"] = int(num_match.group(1)) - 1
                
                response["destination"] = f"{index_match.group(3).upper()}:"
                return response
            
            # CHECK FOR CONTINUITY IN OTHER COMMANDS (move it, copy it, etc.)
            if has_continuity_ref and any(action in command for action in ["move", "copy", "cut", "share"]):
                # Determine the action/intent
                if "move" in command:
                    response["intent"] = "move_last"
                elif "copy" in command:
                    response["intent"] = "copy_last"
                elif "cut" in command:
                    response["intent"] = "cut_last"
                elif "share" in command:
                    response["intent"] = "share_last"
                
                # Pattern: "<action> it to <destination>"
                pattern = r"(?:move|copy|cut|share)\s+(?:it|that|this|this file|this folder)\s+to\s+([a-z])\s+(?:drive)?"
                match = re.search(pattern, command)
                if match:
                    response["destination"] = f"{match.group(1).upper()}:"
                    return response
            
            # REGULAR COPY, MOVE, CUT, SHARE COMMANDS
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
            
            # Clean item name from common words if it exists
            if response["item_name"]:
                # Remove words like "folder", "file", etc.
                response["item_name"] = re.sub(r"\b(folder|file|directory|document)s?\b", "", response["item_name"]).strip()
            
            return response
            
        except Exception as e:
            print(f"Error parsing command: {str(e)}")
            return {"intent": "error", "message": f"Failed to parse: {str(e)}"}
    
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
        
        # Filter out messages like "...and more results"
        clean_results = [r for r in all_results if not r.startswith('...')]
        
        # Update conversation context with found items
        self.conversation_context["found_items"] = clean_results
        self.conversation_context["last_action"] = "find"
        
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
    
    def find_items_in_drive(self, drive, item_name):
        """Find items matching the name in a specific drive - legacy method for compatibility"""
        try:
            # Check if drive exists and is accessible
            if not os.path.exists(f"{drive}\\"):
                return
            
            search_term = item_name.lower()
            
            # Walk the directory tree
            for root, dirs, files in os.walk(drive + "\\"):
                # Check directories
                for dir in dirs:
                    if search_term in dir.lower():
                        yield os.path.join(root, dir)
                
                # Check files
                for file in files:
                    if search_term in file.lower():
                        yield os.path.join(root, file)
        except PermissionError:
            # Skip directories we don't have permission to access
            pass
        except Exception as e:
            print(f"Error in {drive}: {str(e)}")
    
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
            dir_path = os.path.dirname(source_path)
            
            # Create the new path
            new_path = os.path.join(dir_path, new_name)
            
            # Check if the destination already exists
            if os.path.exists(new_path):
                return False, f"Cannot rename: {new_name} already exists in this location"
            
            # Perform the rename
            os.rename(source_path, new_path)
            
            # Update the conversation context
            self.conversation_context["selected_item"] = new_path
            
            return True, f"Renamed {os.path.basename(source_path)} to {new_name}"
            
        except PermissionError:
            return False, f"Permission denied when renaming {os.path.basename(source_path)}"
        except Exception as e:
            return False, f"Error during rename: {str(e)}"
    
    def get_item_by_index(self, index):
        """Get an item from found_items by its index"""
        found_items = self.conversation_context.get("found_items", [])
        
        if not found_items:
            return None, "No items have been found in the previous search"
        
        # Handle negative index (last item)
        if index < 0:
            index = len(found_items) + index
        
        if 0 <= index < len(found_items):
            selected_item = found_items[index]
            self.conversation_context["selected_item"] = selected_item
            return selected_item, f"Selected {os.path.basename(selected_item)}"
        else:
            return None, f"Index {index+1} is out of range. Only {len(found_items)} items were found."
    
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
                    # Update context with the single found item
                    self.conversation_context["selected_item"] = result_entries[0]
                    print(location_message)
                    return True, location_message
                else:
                    # List the first few results with indexes for reference
                    result_summary = f"I found {num_results} matches for {item_name}. Here are the first few results:\n"
                    
                    for i, loc in enumerate(result_entries[:5]):
                        result_summary += f"{i+1}. {loc}\n"
                    
                    if len(result_entries) > 5:
                        result_summary += f"...and {len(result_entries) - 5} more results."
                    
                    result_summary += "\nYou can refer to these by number in your next command."
                    
                    return True, result_summary
            else:
                return False, f"I couldn't find {item_name} on any drive. Please check the spelling or try another search term."
        
        # Handle commands that reference previous results by index
        elif any(intent.startswith(action) for action in ["copy", "move", "cut", "share"]) and parsed_command.get("index") is not None:
            index = parsed_command.get("index")
            destination = parsed_command.get("destination")
            
            # Get the item from the found items list
            item_path, message = self.get_item_by_index(index)
            
            if not item_path:
                return False, message
            
            # Set up paths
            item_name = os.path.basename(item_path)
            dest_path = self.resolve_path(item_name, destination)
            
            # Execute the appropriate action
            if intent.startswith("copy"):
                return self.copy_item(item_path, dest_path)
            elif intent.startswith("move"):
                return self.move_item(item_path, dest_path)
            elif intent.startswith("cut"):
                return self.cut_item(item_name, os.path.dirname(item_path), destination)
            elif intent.startswith("share"):
                dest_path = os.path.join(self.mapped_drive_letter + "\\", item_name)
                return self.copy_item(item_path, dest_path)
        
        # Handle commands that reference the last selected/found item
        elif intent in ["move_last", "copy_last", "cut_last", "share_last", "rename_last"]:
            destination = parsed_command.get("destination")
            new_name = parsed_command.get("new_name")
            
            # Get the last selected item
            selected_item = self.conversation_context.get("selected_item")
            
            if not selected_item:
                return False, "No item has been selected previously. Please find or select an item first."
            
            item_name = os.path.basename(selected_item)
            
            # For rename_last operation
            if intent == "rename_last" and new_name:
                return self.rename_item(selected_item, new_name)
            
            # For other operations requiring destination
            if not destination and intent != "rename_last":
                return False, f"Please specify a destination drive for the {intent.split('_')[0]} operation."
            
            # Execute the appropriate action
            if intent == "copy_last":
                dest_path = self.resolve_path(item_name, destination)
                return self.copy_item(selected_item, dest_path)
            elif intent == "move_last":
                dest_path = self.resolve_path(item_name, destination)
                return self.move_item(selected_item, dest_path)
            elif intent == "cut_last":
                return self.cut_item(item_name, os.path.dirname(selected_item), destination)
            elif intent == "share_last":
                dest_path = os.path.join(self.mapped_drive_letter + "\\", item_name)
                return self.copy_item(selected_item, dest_path)
        
        # Handle standard copy, move, cut, share, rename operations
        elif intent in ["copy", "move", "cut", "share", "rename"]:
            item_name = parsed_command.get("item_name")
            source = parsed_command.get("source")
            destination = parsed_command.get("destination") 
            new_name = parsed_command.get("new_name")
            
            # Debug information
            print(f"Executing {intent} command:")
            print(f"  Item: {item_name}")
            print(f"  Source: {source}")
            print(f"  Destination: {destination}")
            print(f"  New name: {new_name}")
            
            if not item_name and intent != "rename":
                return False, f"I couldn't determine which file or folder to {intent}. Please specify a name."
            
            # For rename operation
            if intent == "rename" and new_name:
                source_path = self.resolve_path(item_name, source)
                return self.rename_item(source_path, new_name)
            
            # For other operations requiring destination
            if not destination and intent != "rename":
                if intent == "share":
                    destination = self.mapped_drive_letter
                else:
                    return False, f"Please specify a destination drive for the {intent} operation."
            
            # Resolve the paths
            source_path = self.resolve_path(item_name, source)
            dest_path = self.resolve_path(item_name, destination) if destination else None
            
            # Execute the appropriate action
            if intent == "copy":
                return self.copy_item(source_path, dest_path)
            elif intent == "move":
                return self.move_item(source_path, dest_path)
            elif intent == "cut":
                return self.cut_item(item_name, source, destination)
            elif intent == "share":
                dest_path = os.path.join(self.mapped_drive_letter + "\\", item_name)
                return self.copy_item(source_path, dest_path)
        
        return False, f"I don't know how to {intent} yet. Please try a different command."

    def run_voice_assistant(self):
        """Main loop for voice command processing"""
        self.speak("Voice File Manager activated. How can I help you today?")
        
        while True:
            command = self.listen()
            
            if not command:
                continue
            
            # Check for exit command
            if any(exit_word in command for exit_word in ["exit", "quit", "stop", "bye", "goodbye"]):
                self.speak("Voice File Manager shutting down. Goodbye!")
                self.disconnect_share()
                break
            
            # Parse and execute the command
            parsed_command = self.parse_command(command)
            success, message = self.execute_command(parsed_command)
            
            # Update context with the last command
            self.conversation_context["last_command"] = parsed_command
            
            # Provide feedback to the user
            if success:
                self.speak(message)
            else:
                self.speak(f"Sorry, {message}")
                
            # Ask if they want to do anything else
            if not any(word in command for word in ["find", "search", "locate"]):
                followup = self.listen("Is there anything else you would like to do?")
                if followup and any(no_word in followup for no_word in ["no", "nope", "that's all", "nothing"]):
                    self.speak("Voice File Manager shutting down. Goodbye!")
                    self.disconnect_share()
                    break

# Create and run the VoiceFileManager
if __name__ == "__main__":
    try:
        file_manager = VoiceFileManager()
    except Exception as e:
        print(f"Error starting Voice File Manager: {str(e)}")
        # Create a simple message box for errors
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Voice File Manager Error", f"Failed to start: {str(e)}\n\nPlease check your network connection and try again.")
        root.destroy()