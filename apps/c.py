import os
import sys
import time
import socket
import subprocess
import threading
import platform
import shutil
import re
import json
import tkinter as tk
from tkinter import messagebox

# Import speech recognition with error handling
try:
    import speech_recognition as sr
except ImportError:
    print("Installing speech_recognition...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "SpeechRecognition"])
    import speech_recognition as sr

# Import pyttsx3 with error handling
try:
    import pyttsx3
except ImportError:
    print("Installing pyttsx3...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyttsx3"])
    import pyttsx3

# PyAudio might be needed for speech_recognition
try:
    import pyaudio
except ImportError:
    print("Installing PyAudio...")
    if platform.system() == "Windows":
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pipwin"])
        subprocess.check_call([sys.executable, "-m", "pipwin", "install", "pyaudio"])
    else:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyaudio"])


class VoiceFileManager:
    def __init__(self):
        # Network share settings
        self.server_ip = "192.168.9.63"  # FIB-By-Server
        self.share_name = "Shared"
        self.username = "aadish"  # FIB login username
        self.password = "1234"  # FIB password
        self.mapped_drive_letter = "S:"
        
        # Local settings
        self.current_drive = os.getcwd()[:2]  # Get current drive (e.g., "C:")
        self.connected = False
        
        # Status window
        self.root = tk.Tk()
        self.root.title("Voice File Manager")
        self.root.geometry("400x300")
        self.status_label = tk.Label(self.root, text="Initializing...", font=("Arial", 12))
        self.status_label.pack(pady=20)
        self.log_text = tk.Text(self.root, height=10, width=45)
        self.log_text.pack(pady=10)
        self.exit_button = tk.Button(self.root, text="Exit", command=self.exit_app)
        self.exit_button.pack(pady=10)
        
        # Initialize in a separate thread
        threading.Thread(target=self.initialize_assistant, daemon=True).start()
        self.root.protocol("WM_DELETE_WINDOW", self.exit_app)
        self.root.mainloop()

    def initialize_assistant(self):
        """Initialize the voice assistant components"""
        self.update_status("Initializing speech systems...")
        
        # Initialize voice engine
        try:
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', 150)
            self.engine.setProperty('volume', 0.9)
            
            # Check available voices and set a more natural one if available
            voices = self.engine.getProperty('voices')
            if len(voices) > 1:
                self.engine.setProperty('voice', voices[1].id)  # Often the second voice is female and clearer
        except Exception as e:
            self.log_error(f"Voice engine initialization error: {str(e)}")
            self.update_status("Voice engine failed to initialize.")
            return
        
        # Initialize speech recognizer
        try:
            self.recognizer = sr.Recognizer()
            self.recognizer.energy_threshold = 4000
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.pause_threshold = 0.8
        except Exception as e:
            self.log_error(f"Speech recognizer initialization error: {str(e)}")
            self.update_status("Speech recognition failed to initialize.")
            return
        
        # Connect to the share
        self.update_status("Connecting to network share...")
        if not self.connect_share():
            self.log_error("Failed to connect to network share.")
            self.update_status("Share connection failed. Continuing in local mode.")
        else:
            self.connected = True
            self.update_status("Connected to network share.")
        
        # Start the voice assistant
        self.update_status("Ready for commands")
        self.run_voice_assistant()

    def update_status(self, message):
        """Update the status label in the GUI"""
        self.status_label.config(text=message)
        self.root.update()

    def log_message(self, message):
        """Log a message to the GUI text area"""
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.root.update()

    def log_error(self, message):
        """Log an error message to the GUI text area"""
        self.log_text.insert(tk.END, f"ERROR: {message}\n")
        self.log_text.see(tk.END)
        self.root.update()

    def speak(self, text):
        """Convert text to speech"""
        self.log_message(f"Assistant: {text}")
        try:
            self.engine.say(text)
            self.engine.runAndWait()
        except Exception as e:
            self.log_error(f"Speech error: {str(e)}")

    def listen(self, prompt=None):
        """Listen for voice input with improved error handling"""
        if prompt:
            self.speak(prompt)
        
        self.update_status("Listening...")
        
        with sr.Microphone() as source:
            try:
                # Adjust for ambient noise
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                
                # Listen for audio input
                audio = self.recognizer.listen(source, timeout=10, phrase_time_limit=10)
                
                # Process the audio
                self.update_status("Processing speech...")
                text = self.recognizer.recognize_google(audio).lower()
                self.log_message(f"User said: {text}")
                self.update_status("Ready for commands")
                return text
            except sr.WaitTimeoutError:
                self.update_status("No speech detected. Try again.")
                return None
            except sr.UnknownValueError:
                self.update_status("Could not understand audio. Try again.")
                return None
            except Exception as e:
                self.log_error(f"Listening error: {str(e)}")
                self.update_status("Speech recognition error. Try again.")
                return None

    def connect_share(self):
        """Connect to network share with improved error handling"""
        try:
            if platform.system() == "Windows":
                # Disconnect first if already connected
                subprocess.run(f'net use {self.mapped_drive_letter} /delete /y', 
                             shell=True, capture_output=True)
                
                # Connect to share
                share_path = f"\\\\{self.server_ip}\\{self.share_name}"
                cmd = f'net use {self.mapped_drive_letter} {share_path} /user:{self.username} {self.password} /persistent:no'
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.returncode != 0:
                    self.log_error(f"Connection error: {result.stderr}")
                return result.returncode == 0
            else:
                # For Linux/Mac, use a different approach
                mount_point = f"/mnt/{self.share_name}"
                os.makedirs(mount_point, exist_ok=True)
                
                # Use mount command appropriate for the OS
                if platform.system() == "Darwin":  # macOS
                    cmd = f"mount -t smbfs //'{self.username}:{self.password}@{self.server_ip}/{self.share_name}' {mount_point}"
                else:  # Linux
                    cmd = f"mount -t cifs //{self.server_ip}/{self.share_name} {mount_point} -o username={self.username},password={self.password}"
                
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.returncode == 0:
                    self.mapped_drive_letter = mount_point
                    return True
                else:
                    self.log_error(f"Mount error: {result.stderr}")
                    return False
        except Exception as e:
            self.log_error(f"Connection error: {str(e)}")
            return False

    def disconnect_share(self):
        """Disconnect from network share"""
        if not self.connected:
            return
            
        try:
            if platform.system() == "Windows":
                subprocess.run(f'net use {self.mapped_drive_letter} /delete /y', 
                             shell=True, capture_output=True)
            else:
                subprocess.run(f'umount {self.mapped_drive_letter}', 
                             shell=True, capture_output=True)
            self.log_message("Disconnected from network share")
        except Exception as e:
            self.log_error(f"Disconnection error: {str(e)}")

    def run_voice_assistant(self):
        """Main voice interaction loop"""
        self.speak("Voice File Manager is ready. How can I assist you?")
        
        while True:
            command = self.listen("Waiting for your command...")
            if not command:
                continue
                
            if any(word in command for word in ["exit", "quit", "stop", "goodbye"]):
                self.speak("Shutting down Voice File Manager. Goodbye!")
                self.exit_app()
                break
                
            # Parse the command
            parsed = self.parse_command_with_nlp(command)
            
            # If unknown command, help the user
            if parsed['intent'] == 'unknown':
                self.speak("I didn't understand that command. Try saying things like 'copy project folder from C to S' or 'list files in C'.")
                continue
                
            # Execute the command
            success, message = self.execute_command(parsed)
            
            if success:
                self.speak(message)
            else:
                self.speak(f"Operation failed: {message}")

    def execute_command(self, parsed):
        """Execute parsed command"""
        intent = parsed.get('intent')
        
        if intent == "copy":
            return self.handle_copy_move(parsed, operation='copy')
        elif intent == "move":
            return self.handle_copy_move(parsed, operation='move')
        elif intent == "delete":
            return self.handle_delete(parsed)
        elif intent == "rename":
            return self.handle_rename(parsed)
        elif intent == "create_dir":
            return self.handle_create_dir(parsed)
        elif intent == "list":
            return self.handle_list(parsed)
        elif intent == "search":
            return self.handle_search(parsed)
        elif intent == "share":
            return self.handle_share(parsed)
        elif intent == "help":
            return self.handle_help()
        else:
            return False, "Command not recognized"

    def handle_copy_move(self, parsed, operation):
        """Handle copy/move operations with improved error handling"""
        item = parsed['item_name']
        source = parsed.get('source', self.current_drive)
        dest = parsed.get('destination', self.mapped_drive_letter if self.connected else self.current_drive)

        source_path = self.resolve_path(item, source)
        dest_path = self.resolve_path(item, dest)

        if not os.path.exists(source_path):
            return False, f"{item} not found in {source}"

        # Check if destination exists
        if os.path.exists(dest_path):
            confirm = self.listen(f"Warning: {item} already exists in destination. Overwrite? Say yes or no.")
            if not confirm or 'yes' not in confirm:
                return False, "Operation cancelled"

        # Confirm operation
        confirm = self.listen(f"Confirm {operation} {item} from {source} to {dest}? Say yes or no.")
        if not confirm or 'yes' not in confirm:
            return False, "Operation cancelled"

        try:
            if operation == 'copy':
                if os.path.isdir(source_path):
                    # Remove destination directory if it exists
                    if os.path.exists(dest_path):
                        shutil.rmtree(dest_path)
                    shutil.copytree(source_path, dest_path)
                else:
                    shutil.copy2(source_path, dest_path)
            else:  # move
                shutil.move(source_path, dest_path)
            return True, f"{operation.capitalize()} completed successfully"
        except PermissionError:
            return False, f"Permission denied. Unable to {operation} {item}."
        except Exception as e:
            return False, f"{operation.capitalize()} failed: {str(e)}"

    def handle_delete(self, parsed):
        """Handle delete operation with improved safety"""
        item = parsed['item_name']
        source = parsed.get('source', self.current_drive)
        path = self.resolve_path(item, source)

        if not os.path.exists(path):
            return False, f"{item} not found in {source}"

        # Double-confirm deletion
        confirm1 = self.listen(f"Are you sure you want to delete {item} from {source}? Say yes or no.")
        if not confirm1 or 'yes' not in confirm1:
            return False, "Deletion cancelled"
            
        confirm2 = self.listen(f"This action cannot be undone. Confirm deletion? Say yes or no.")
        if not confirm2 or 'yes' not in confirm2:
            return False, "Deletion cancelled"

        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            return True, f"{item} deleted successfully"
        except PermissionError:
            return False, f"Permission denied. Unable to delete {item}."
        except Exception as e:
            return False, f"Deletion failed: {str(e)}"

    def handle_rename(self, parsed):
        """Handle rename operation with improved validation"""
        old_name = parsed['item_name']
        new_name = parsed.get('new_name', '')
        source = parsed.get('source', self.current_drive)
        
        if not new_name:
            new_name = self.listen("What would you like to rename it to?")
            if not new_name:
                return False, "Rename cancelled. No new name provided."
        
        old_path = self.resolve_path(old_name, source)
        new_path = os.path.join(os.path.dirname(old_path), new_name)

        if not os.path.exists(old_path):
            return False, f"{old_name} not found in {source}"
            
        if os.path.exists(new_path):
            confirm = self.listen(f"{new_name} already exists. Overwrite? Say yes or no.")
            if not confirm or 'yes' not in confirm:
                return False, "Rename cancelled"

        try:
            os.rename(old_path, new_path)
            return True, f"Renamed {old_name} to {new_name}"
        except PermissionError:
            return False, f"Permission denied. Unable to rename {old_name}."
        except Exception as e:
            return False, f"Rename failed: {str(e)}"

    def handle_create_dir(self, parsed):
        """Handle directory creation with improved validation"""
        dir_name = parsed.get('dir_name', '')
        location = parsed.get('location', self.current_drive)
        
        if not dir_name:
            dir_name = self.listen("What would you like to name the new directory?")
            if not dir_name:
                return False, "Directory creation cancelled. No name provided."
        
        path = os.path.join(location, dir_name)

        if os.path.exists(path):
            return False, f"Directory {dir_name} already exists in {location}"

        try:
            os.makedirs(path, exist_ok=True)
            return True, f"Directory {dir_name} created successfully in {location}"
        except PermissionError:
            return False, f"Permission denied. Unable to create directory in {location}."
        except Exception as e:
            return False, f"Directory creation failed: {str(e)}"

    def handle_list(self, parsed):
        """Handle list directory contents with improved presentation"""
        location = parsed.get('location', self.current_drive)
        
        if not os.path.exists(location):
            return False, f"Location {location} not found"
            
        if not os.path.isdir(location):
            return False, f"{location} is not a directory"
        
        try:
            items = os.listdir(location)
            if not items:
                return True, f"No items found in {location}"
                
            dirs = [item for item in items if os.path.isdir(os.path.join(location, item))]
            files = [item for item in items if os.path.isfile(os.path.join(location, item))]
            
            # Sort items alphabetically
            dirs.sort()
            files.sort()
            
            # Prepare response
            response = f"Found {len(dirs)} directories and {len(files)} files in {location}.\n"
            
            if dirs:
                response += f"Directories: {', '.join(dirs[:5])}"
                if len(dirs) > 5:
                    response += f" and {len(dirs) - 5} more"
                response += ".\n"
                
            if files:
                response += f"Files: {', '.join(files[:5])}"
                if len(files) > 5:
                    response += f" and {len(files) - 5} more"
                response += "."
                
            return True, response
        except PermissionError:
            return False, f"Permission denied. Unable to list contents of {location}."
        except Exception as e:
            return False, f"Listing failed: {str(e)}"

    def handle_search(self, parsed):
        """Handle file search with improved search capabilities"""
        query = parsed.get('query', '')
        location = parsed.get('location', self.current_drive)
        
        if not query:
            query = self.listen("What would you like to search for?")
            if not query:
                return False, "Search cancelled. No query provided."
        
        if not os.path.exists(location):
            return False, f"Location {location} not found"
            
        if not os.path.isdir(location):
            return False, f"{location} is not a directory"
        
        self.speak(f"Searching for {query} in {location}. This may take a moment...")
        self.update_status(f"Searching for {query}...")
        
        try:
            results = []
            for root, dirs, files in os.walk(location):
                for item in dirs + files:
                    if query.lower() in item.lower():
                        results.append(os.path.relpath(os.path.join(root, item), location))
                
                # Limit search to prevent excessive processing
                if len(results) >= 20:
                    break
            
            self.update_status("Ready for commands")
            
            if not results:
                return True, f"No items matching '{query}' found in {location}"
            
            response = f"Found {len(results)} items matching '{query}':\n"
            for i, item in enumerate(results[:5], 1):
                response += f"{i}. {item}\n"
                
            if len(results) > 5:
                response += f"And {len(results) - 5} more matches."
                
            return True, response
        except PermissionError:
            return False, f"Permission denied. Unable to search in {location}."
        except Exception as e:
            return False, f"Search failed: {str(e)}"

    def handle_share(self, parsed):
        """Handle sharing to network drive with improved checks"""
        if not self.connected:
            return False, "Not connected to network share. Please check your connection and try again."
            
        item = parsed.get('item_name', '')
        source = parsed.get('source', self.current_drive)
        
        if not item:
            item = self.listen("What would you like to share?")
            if not item:
                return False, "Share operation cancelled. No item specified."
        
        source_path = self.resolve_path(item, source)
        dest_path = os.path.join(self.mapped_drive_letter, os.path.basename(source_path))

        if not os.path.exists(source_path):
            return False, f"{item} not found in {source}"

        if os.path.exists(dest_path):
            confirm = self.listen(f"{item} already exists in the shared location. Overwrite? Say yes or no.")
            if not confirm or 'yes' not in confirm:
                return False, "Share operation cancelled"

        try:
            if os.path.isdir(source_path):
                if os.path.exists(dest_path):
                    shutil.rmtree(dest_path)
                shutil.copytree(source_path, dest_path)
            else:
                shutil.copy2(source_path, dest_path)
            return True, f"{item} shared successfully to {self.mapped_drive_letter}"
        except PermissionError:
            return False, f"Permission denied. Unable to share {item}."
        except Exception as e:
            return False, f"Sharing failed: {str(e)}"

    def handle_help(self):
        """Display help information"""
        help_text = (
            "Here are the commands you can use:\n"
            "- Copy: 'copy [item] from [source] to [destination]'\n"
            "- Move: 'move [item] from [source] to [destination]'\n"
            "- Delete: 'delete [item] from [source]'\n"
            "- Rename: 'rename [item] to [new name] in [source]'\n"
            "- Create directory: 'create folder [name] in [location]'\n"
            "- List files: 'list files in [location]'\n"
            "- Search: 'search for [query] in [location]'\n"
            "- Share: 'share [item] to network'\n"
            "- Help: 'help' or 'what can you do'\n"
            "- Exit: 'exit', 'quit', or 'stop'"
        )
        return True, help_text

    def check_share_connection(self):
        """Verify network share connection"""
        if not self.connected:
            return False
            
        if not os.path.exists(self.mapped_drive_letter):
            self.log_message("Network share disconnected. Attempting to reconnect...")
            if self.connect_share():
                self.log_message("Reconnected to network share.")
                return True
            else:
                self.log_error("Failed to reconnect to network share.")
                self.connected = False
                return False
        return True

    def resolve_path(self, item, location):
        """Resolve full path for an item with improved validation"""
        # Handle Windows drive letters
        if location.endswith(':'):
            location = location + os.sep
            
        # Handle absolute paths
        if os.path.isabs(item):
            return item
            
        # Handle relative paths
        return os.path.join(location, item)

    def parse_command_with_nlp(self, command):
        """Natural language command parser with improved pattern matching"""
        command = command.lower()
        
        # Help command
        if any(word in command for word in ["help", "what can you do", "show commands"]):
            return {'intent': 'help'}
        
        # Improved patterns with more natural language variations
        patterns = [
            # Copy patterns
            (r'copy (.*?) from ([a-zA-Z]:?)\s*(?:drive)?\s*to ([a-zA-Z]:?)\s*(?:drive)?', 'copy'),
            (r'copy (.*?) to ([a-zA-Z]:?)\s*(?:drive)?', 'copy'),
            
            # Move patterns
            (r'move (.*?) from ([a-zA-Z]:?)\s*(?:drive)?\s*to ([a-zA-Z]:?)\s*(?:drive)?', 'move'),
            (r'move (.*?) to ([a-zA-Z]:?)\s*(?:drive)?', 'move'),
            
            # Delete patterns
            (r'delete (.*?) from ([a-zA-Z]:?)\s*(?:drive)?', 'delete'),
            (r'delete (.*)', 'delete'),
            
            # Rename patterns
            (r'rename (.*?) to (.*?) in ([a-zA-Z]:?)\s*(?:drive)?', 'rename'),
            (r'rename (.*?) to (.*)', 'rename'),
            
            # Create directory patterns
            (r'create (?:folder|directory) (.*?) in ([a-zA-Z]:?)\s*(?:drive)?', 'create_dir'),
            (r'create (?:folder|directory) (.*)', 'create_dir'),
            (r'make (?:folder|directory) (.*)', 'create_dir'),
            
            # List patterns
            (r'list (?:files|folders|directories) in ([a-zA-Z]:?)\s*(?:drive)?', 'list'),
            (r'show (?:files|folders|directories) in ([a-zA-Z]:?)\s*(?:drive)?', 'list'),
            (r'what(?:\'s)? in ([a-zA-Z]:?)\s*(?:drive)?', 'list'),
            
            # Search patterns
            (r'search for (.*?) in ([a-zA-Z]:?)\s*(?:drive)?', 'search'),
            (r'find (.*?) in ([a-zA-Z]:?)\s*(?:drive)?', 'search'),
            (r'look for (.*?) in ([a-zA-Z]:?)\s*(?:drive)?', 'search'),
            
            # Share patterns
            (r'share (.*?) to (?:network|shared drive)', 'share'),
            (r'upload (.*?) to (?:network|shared drive)', 'share'),
        ]

        for pattern, intent in patterns:
            match = re.search(pattern, command)
            if match:
                groups = match.groups()
                result = {'intent': intent}
                
                # Handle different intents
                if intent == 'copy' or intent == 'move':
                    result['item_name'] = groups[0].strip()
                    if len(groups) == 3:  # Full pattern with from/to
                        result['source'] = groups[1].upper() + ":" if groups[1] and not groups[1].endswith(':') else groups[1].upper()
                        result['destination'] = groups[2].upper() + ":" if groups[2] and not groups[2].endswith(':') else groups[2].upper()
                    else:  # Just "to" destination
                        result['source'] = self.current_drive
                        result['destination'] = groups[1].upper() + ":" if groups[1] and not groups[1].endswith(':') else groups[1].upper()
                
                elif intent == 'delete':
                    result['item_name'] = groups[0].strip()
                    if len(groups) > 1 and groups[1]:
                        result['source'] = groups[1].upper() + ":" if not groups[1].endswith(':') else groups[1].upper()
                    else:
                        result['source'] = self.current_drive
                
                elif intent == 'rename':
                    result['item_name'] = groups[0].strip()
                    result['new_name'] = groups[1].strip()
                    if len(groups) > 2 and groups[2]:
                        result['source'] = groups[2].upper() + ":" if not groups[2].endswith(':') else groups[2].upper()
                    else:
                        result['source'] = self.current_drive
                
                elif intent == 'create_dir':
                    result['dir_name'] = groups[0].strip()
                    if len(groups) > 1 and groups[1]:
                        result['location'] = groups[1].upper() + ":" if not groups[1].endswith(':') else groups[1].upper()
                    else:
                        result['location'] = self.current_drive
                
                elif intent == 'list':
                    result['location'] = groups[0].upper() + ":" if groups[0] and not groups[0].endswith(':') else groups[0].upper()
                
                elif intent == 'search':
                    result['query'] = groups[0].strip()
                    if len(groups) > 1 and groups[1]:
                        result['location'] = groups[1].upper() + ":" if not groups[1].endswith(':') else groups[1].upper()
                    else:
                        result['location'] = self.current_drive
                
                elif intent == 'share':
                    result['item_name'] = groups[0].strip()
                    result['source'] = self.current_drive
                
                return result

        return {'intent': 'unknown'}

    def exit_app(self):
        """Clean exit of the application"""
        self.update_status("Shutting down...")
        self.disconnect_share()
        self.root.quit()
        sys.exit(0)


if __name__ == "__main__":
    try:
        VoiceFileManager()
    except Exception as e:
        print(f"Fatal error: {str(e)}")
        messagebox.showerror("Fatal Error", f"An unexpected error occurred: {str(e)}")
        sys.exit(1)