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
from langchain_google_genai import GoogleGenerativeAI
#from langchain_core.messages import HumanMessage, SystemMessage
#from langchain_community.llms import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
import logging


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("voice_file_manager.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class VoiceFileManager:
    def __init__(self, gemini_api_key):
        self.server_ip = "192.168.9.63"  # FIB-By-Server
        self.share_name = "Shared"
        self.username = "aadish"  # FIB login username
        self.password = "1234"  # FIB password
        self.mapped_drive_letter = "S:"
        self.current_drive = os.getcwd()[:2]  # Get current drive (e.g., "C:")
        
        # Initialize LLM for intent recognition
        try:
            self.llm = ChatGoogleGenerativeAI(
                model="gemini-2.0",
                api_key="AIzaSyCK6YT332KT79i2JvgJ6Jjes76R2I1Dtk8",
                temperature=0,
                timeout=60
            )
            logger.info("LLM initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing LLM: {str(e)}")
            self.llm = None
        
        # Initialize voice engine
        self.engine = pyttsx3.init()
        self.engine.setProperty('rate', 150)  # Speed of speech
        self.engine.setProperty('volume', 0.9)  # Volume (0 to 1)
        
        # Initialize speech recognizer
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 4000  # Adjust based on environment
        self.recognizer.dynamic_energy_threshold = True
        
        # Command dictionary for phonetic similarity matching
        self.command_phonetics = {
            # Cut command variations
            "cut": ["cut", "kat", "cat", "kut", "ct"],
            # Copy command variations
            "copy": ["copy", "copi", "kopi", "cop", "kop", "copee"],
            # Move command variations
            "move": ["move", "mov", "muhv", "moov", "muve"],
            # Find command variations
            "find": ["find", "fined", "faind", "look", "look for", "search", "locate"],
            # Share command variations
            "share": ["share", "sher", "shair", "sharing"],
            # Exit command variations
            "exit": ["exit", "quit", "goodbye", "bye", "stop", "end"]
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

    def get_llm_intent(self, command):
        """Use LLM to understand the user's intent from their command"""
        if not self.llm:
            return None
            
        try:
            prompt = f"""
            You are an assistant that helps understand file management commands.
            
            Please analyze the following voice command and extract the user's intent, item name, source drive, and destination drive.
            Respond in JSON format with the following structure:
            {{
              "intent": "one of [copy, move, cut, find, share, exit, unknown]",
              "item_name": "name of file or folder without 'folder' or 'file' words",
              "source": "source drive letter with colon (e.g., 'C:') or null",
              "destination": "destination drive letter with colon (e.g., 'D:') or null"
            }}
            
            For example:
            - "kat documents from C drive to D drive" should be understood as a "cut" command
            - "muhv photos to E drive" should be understood as a "move" command
            - "where are my budget files" should be understood as a "find" command
            
            Command: {command}
            """
            
            response = self.llm([HumanMessage(content=prompt)])
            
            # Extract JSON from the response
            response_text = response.content
            try:
                # Try to extract the JSON part
                json_match = re.search(r'({.*})', response_text, re.DOTALL)
                if json_match:
                    json_string = json_match.group(1)
                    result = json.loads(json_string)
                    logger.info(f"LLM parsed command: {result}")
                    return result
                else:
                    logger.warning(f"Could not extract JSON from LLM response: {response_text}")
                    return None
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing LLM JSON response: {e}, Response: {response_text}")
                return None
                
        except Exception as e:
            logger.error(f"Error using LLM for intent recognition: {str(e)}")
            return None

    def fuzzy_match_command(self, command):
        """Use phonetic matching for command recognition"""
        first_word = command.split()[0] if command.split() else ""
        
        # Check if the first word matches any known command variants
        for intent, variants in self.command_phonetics.items():
            if first_word in variants:
                return intent
            
            # Check for partial matches (e.g., "cu" for "cut")
            for variant in variants:
                if len(first_word) >= 2 and first_word in variant:
                    return intent
        
        return None

    def parse_command(self, command):
        """Parse user command using LLM and fallback to rule-based approach"""
        try:
            command = command.lower().strip()
            
            # Initialize response structure
            response = {
                "intent": "unknown",
                "item_name": None,
                "source": self.current_drive,
                "destination": None
            }
            
            # First try with LLM
            llm_result = self.get_llm_intent(command)
            if llm_result and llm_result.get("intent") != "unknown":
                logger.info(f"Using LLM parsing result: {llm_result}")
                return llm_result
                
            # Fallback: Check for exit command first
            if any(exit_word in command for exit_word in self.command_phonetics["exit"]):
                response["intent"] = "exit"
                return response
            
            # Fallback: Try fuzzy matching for the command
            fuzzy_intent = self.fuzzy_match_command(command)
            if fuzzy_intent:
                response["intent"] = fuzzy_intent
                
                # If this is a find command, extract the item name
                if fuzzy_intent == "find":
                    # Extract item name after the find keyword
                    for keyword in self.command_phonetics["find"]:
                        if keyword in command:
                            parts = command.split(keyword, 1)
                            if len(parts) > 1:
                                item_name = parts[1].strip()
                                # Clean up common words
                                for word in ["for", "my", "the", "folder", "file", "directory", "document"]:
                                    item_name = item_name.replace(f" {word} ", " ").replace(f" {word}", "")
                                response["item_name"] = item_name.strip()
                                return response
                
                # For other commands, use regex to extract parameters
                # Pattern: "<action> <item> from <source> to <destination>"
                pattern1 = r"\w+\s+(.+?)\s+from\s+([a-z])\s+(?:drive\s+)?to\s+([a-z])\s+(?:drive)?"
                match = re.search(pattern1, command)
                if match:
                    response["item_name"] = match.group(1).strip()
                    response["source"] = f"{match.group(2).upper()}:"
                    response["destination"] = f"{match.group(3).upper()}:"
                    return response
                
                # Pattern: "<action> <item> to <destination>"
                pattern2 = r"\w+\s+(.+?)\s+to\s+([a-z])\s+(?:drive)?"
                match = re.search(pattern2, command)
                if match:
                    response["item_name"] = match.group(1).strip()
                    response["destination"] = f"{match.group(2).upper()}:"
                    return response
                
                # Pattern: "<action> <item> from <source>"
                pattern3 = r"\w+\s+(.+?)\s+from\s+([a-z])\s+(?:drive)?"
                match = re.search(pattern3, command)
                if match:
                    response["item_name"] = match.group(1).strip()
                    response["source"] = f"{match.group(2).upper()}:"
                    return response
                
                # Pattern: "<action> <item>"
                pattern4 = r"\w+\s+(.+)"
                match = re.search(pattern4, command)
                if match:
                    response["item_name"] = match.group(1).strip()
                    return response
            
            # FIND COMMANDS - Check these as a last resort
            find_keywords = ["find", "search", "locate", "look for", "where is", "where are", 
                           "lookup", "look up", "seeking", "seek", "hunt for", "hunting for"]
            
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
            
            # Clean item name from common words if it exists
            if response["item_name"]:
                # Remove words like "folder", "file", etc.
                response["item_name"] = re.sub(r"\b(folder|file|directory|document)s?\b", "", response["item_name"]).strip()
            
            return response
            
        except Exception as e:
            logger.error(f"Error parsing command: {str(e)}")
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
            logger.info(f"Started searching drive {drive}...")
            
            # Check if drive exists and is accessible
            if not os.path.exists(f"{drive}\\"):
                logger.info(f"Drive {drive} is not accessible")
                return
            
            search_term = item_name.lower()
            
            # Set a timeout to prevent very long searches
            start_time = time.time()
            max_search_time = 30  # Max 30 seconds per drive
            
            # Walk the directory tree
            for root, dirs, files in os.walk(drive + "\\"):
                # Check if search is taking too long
                if time.time() - start_time > max_search_time:
                    logger.info(f"Search timeout on drive {drive} after {max_search_time} seconds")
                    if drive_results:
                        drive_results.append(f"...search timeout after {max_search_time} seconds")
                    break
                
                # Optimize search by skipping system directories
                dirs[:] = [d for d in dirs if not d.startswith('$') and 
                           d not in ['System Volume Information', 'Windows', '$Recycle.Bin', 'Program Files', 'Program Files (x86)']]
                
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
                logger.info(f"Found {len(drive_results)} matches on drive {drive}")
                result_queue.put((drive, drive_results))
            else:
                logger.info(f"No matches found on drive {drive}")
                
        except PermissionError:
            logger.info(f"Permission error on drive {drive}")
            pass
        except Exception as e:
            logger.error(f"Error searching drive {drive}: {str(e)}")
            pass

    def find_item_across_drives(self, item_name):
        """Search for an item across all available drives using parallel threads"""
        logger.info(f"Searching for '{item_name}' across all drives...")
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
                logger.info("Search timed out after 60 seconds")
                break
                
            # Check for new results
            try:
                drive, _ = result_queue.get(block=True, timeout=1)
                drives_completed.add(drive)
                logger.info(f"Completed {len(drives_completed)}/{total_drives} drives")
                result_queue.put((drive, _))  # Put the result back for collection later
            except queue.Empty:
                # No new results yet
                pass
            
            # Sleep briefly to avoid burning CPU
            time.sleep(0.1)
    
    def copy_item(self, source_path, dest_path):
        """Copy a file or directory to the destination"""
        try:
            # First, check if source exists
            if not os.path.exists(source_path):
                # Try to find the item in current directory
                found_path = self.find_item_in_current_directory(os.path.basename(source_path))
                if found_path:
                    source_path = found_path
                    logger.info(f"Found item at: {source_path}")
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
            logger.error(f"Error during copy: {str(e)}")
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
                    logger.info(f"Found item at: {source_path}")
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
            logger.error(f"Error during move: {str(e)}")
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
                    logger.info(f"Found item at: {source_path}")
                else:
                    return False, f"Source {source_path} does not exist"
            
            # Move the item directly to destination
            return self.move_item(source_path, dest_path)
            
        except Exception as e:
            logger.error(f"Error during cut operation: {str(e)}")
            return False, f"Error during cut operation: {str(e)}"
    
    def execute_command(self, parsed_command):
        """Execute the parsed command"""
        intent = parsed_command.get("intent")
        
        if intent == "unknown":
            return False, "I couldn't understand your command. Please try again with a different phrasing."
        
        elif intent == "error":
            return False, f"Error processing command: {parsed_command.get('message')}"
            
        elif intent == "exit":
            return True, "Exiting the application"
        
        elif intent == "find":
            item_name = parsed_command.get("item_name")
            
            # Debug information
            logger.info(f"Executing find command:")
            logger.info(f"  Item to find: {item_name}")
            
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
                    logger.info(location_message)
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
                    logger.info(f"Detailed results for '{item_name}':")
                    for loc in result_entries[:10]:  # Show first 10 results
                        logger.info(f"  - {loc}")
                    if len(result_entries) > 10:
                        logger.info(f"  ... and {len(result_entries) - 10} more")
                    
                    return True, summary
            else:
                return False, f"I couldn't find {item_name} on any drive. Please check the spelling or try another search term."
        
        elif intent in ["copy", "move", "share"]:
            item_name = parsed_command.get("item_name")
            source = parsed_command.get("source")
            destination = parsed_command.get("destination")
            
            # Debug information
            logger.info(f"Executing {intent} command:")
            logger.info(f"  Item: {item_name}")
            logger.info(f"  Source: {source}")
            logger.info(f"  Destination: {destination}")
            
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
            logger.info(f"  Source path: {source_path}")
            logger.info(f"  Destination path: {dest_path}")
            
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
            logger.info(f"Executing cut command:")
            logger.info(f"  Item: {item_name}")
            logger.info(f"  Source: {source}")
            logger.info(f"  Destination: {destination}")
            
            # Validate source and destination
            if not source:
                return False, "I couldn't determine the source location."
            
            if not destination:
                return False, "I couldn't determine the destination location."
                
            return self.cut_item(item_name, source, destination)
        
        return False, "Command not implemented yet."

    def run_voice_assistant(self):
        """Main function to run the voice assistant workflow"""
        self.speak("Welcome to Voice File Manager. How can I help you today?")
        
        while True:
            command = self.listen("Please tell me what files or directories you want to manage.")
            
            if not command:
                continue
            
            # Parse the command
            parsed_command = self.parse_command(command)
            logger.info(f"Parsed command: {parsed_command}")
            
            # Check for exit command first
            if parsed_command.get("intent") == "exit":
                self.speak("Thank you for using Voice File Manager. Goodbye!")
                self.disconnect_share()
                break
            
            # Execute the command
            success, message = self.execute_command(parsed_command)
            
            if success:
                self.speak(f"Success! {message}")
            else:
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
    # Check for platform compatibility
    if platform.system() != "Windows":
        print("This application is designed for Windows only.")
        sys.exit(1)

    # Ensure only one instance is running
    create_mutex()
    
    # Check for required libraries
    try:
        import speech_recognition
        import pyttsx3
        from langchain.chat_models import ChatGoogleGenerativeAI
    except ImportError as e:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Missing Dependencies", 
                           f"Missing package: {str(e)}\n\n"
                           "Please install required packages with:\n\n"
                           "pip install SpeechRecognition pyttsx3 pyaudio langchain langchain-google-genai")
        root.destroy()
        sys.exit(1)
    
    # Get Gemini API key
    api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        # Try to read from a config file
        try:
            config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    config = json.load(f)
                    api_key = config.get("GEMINI_API_KEY")
        except Exception as e:
            logger.error(f"Error reading config file: {str(e)}")
    
    if not api_key:
        root = tk.Tk()
        root.title("Gemini API Key")
        root.geometry("400x150")
        
        tk.Label(root, text="Please enter your Gemini API Key:").pack(pady=10)
        
        api_key_var = tk.StringVar()
        entry = tk.Entry(root, textvariable=api_key_var, width=40)
        entry.pack(pady=10)
        
        def submit():
            nonlocal api_key
            api_key = api_key_var.get().strip()
            if api_key:
                # Save to config file for future use
                try:
                    config = {"GEMINI_API_KEY": api_key}
                    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
                    with open(config_path, "w") as f:
                        json.dump(config, f)
                except Exception as e:
                    logger.error(f"Error saving config file: {str(e)}")
                
                root.destroy()
            else:
                messagebox.showwarning("Warning", "API Key is required for LLM functionality")
        
        def skip():
            nonlocal api_key
            api_key = ""
            messagebox.showinfo("Information", "Running without LLM functionality")
            root.destroy()
        
        tk.Button(root, text="Submit", command=submit).pack(side=tk.LEFT, padx=(100, 10))
        tk.Button(root, text="Skip", command=skip).pack(side=tk.RIGHT, padx=(10, 100))
        
        root.mainloop()
    
    # Start the application
    app = VoiceFileManager(api_key)

if __name__ == "__main__":
    main()