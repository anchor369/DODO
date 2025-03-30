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

class VoiceEnabledSync:
    def __init__(self):
        self.server_ip = "192.168.9.63"  # FIB-By-Server
        self.share_name = "Shared"
        self.username = "aadish"  # FIB login username
        self.password = "1234"  # FIB password
        self.mapped_drive_letter = "S:"
        
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
                audio = self.recognizer.listen(source, timeout=10, phrase_time_limit=5)
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

    def check_directory_exists(self, username):
        """Check if a directory with the username exists on the network share"""
        user_dir_path = os.path.join(self.mapped_drive_letter + "\\", username)
        return os.path.exists(user_dir_path)

    def create_directory(self, username):
        """Create a directory with the username on the network share"""
        try:
            user_dir_path = os.path.join(self.mapped_drive_letter + "\\", username)
            if not os.path.exists(user_dir_path):
                os.makedirs(user_dir_path)
                print(f"Created directory: {username}")
                return True
            return True  # Directory already exists
        except Exception as e:
            print(f"Failed to create directory: {str(e)}")
            return False

    def copy_directory(self, username, destination_drive):
        """Copy the user directory to the specified drive"""
        try:
            source_dir = os.path.join(self.mapped_drive_letter + "\\", username)
            dest_dir = os.path.join(destination_drive + "\\", username)
            
            # Create destination directory if it doesn't exist
            if not os.path.exists(dest_dir):
                os.makedirs(dest_dir)
            
            # Copy all files from source to destination
            file_count = 0
            for item in os.listdir(source_dir):
                source_item = os.path.join(source_dir, item)
                dest_item = os.path.join(dest_dir, item)
                
                # Only copy files, not directories
                if os.path.isfile(source_item):
                    shutil.copy2(source_item, dest_item)
                    file_count += 1
            
            return file_count
            
        except Exception as e:
            print(f"Copy error: {str(e)}")
            return 0

    def run_voice_assistant(self):
        """Main function to run the voice assistant workflow"""
        self.speak("Welcome to Voice Enabled Directory Sync.")
        
        # Step 1: Get username
        username = None
        while not username:
            username_input = self.listen("Please say your username.")
            if username_input:
                # Confirm the username
                confirmation = self.listen(f"I heard {username_input}. Is that correct? Please say yes or no.")
                if confirmation and "yes" in confirmation:
                    username = username_input
                else:
                    self.speak("Let's try again.")
        
        # Step 2: Check if directory exists
        directory_exists = self.check_directory_exists(username)
        
        if not directory_exists:
            self.speak(f"The directory for {username} does not exist. I will create it for you.")
            if self.create_directory(username):
                self.speak(f"Directory for {username} created successfully.")
            else:
                self.speak("There was a problem creating the directory. The program will exit.")
                return
        else:
            self.speak(f"Directory for {username} found on the network.")
        
        # Step 3: Ask for destination drive
        available_drives = self.get_available_drives()
        available_drives_text = ", ".join([drive[0] for drive in available_drives])
        
        destination_drive = None
        while not destination_drive:
            drive_input = self.listen(f"Which drive would you like to copy the files to? Available drives are {available_drives_text}.")
            
            if drive_input:
                # Extract first letter and check if it's a valid drive
                drive_letter = drive_input[0].upper()
                drive_path = f"{drive_letter}:"
                
                if drive_path in available_drives:
                    confirmation = self.listen(f"You selected drive {drive_letter}. Is that correct? Please say yes or no.")
                    if confirmation and "yes" in confirmation:
                        destination_drive = drive_path
                else:
                    self.speak(f"Drive {drive_letter} is not available. Please choose from {available_drives_text}.")
        
        # Step 4: Copy the directory
        self.speak(f"Copying files from {username} directory to {destination_drive} drive. Please wait...")
        file_count = self.copy_directory(username, destination_drive)
        
        if file_count > 0:
            self.speak(f"Successfully copied {file_count} files to {destination_drive}\\{username}")
        else:
            self.speak("No files were copied. The directory might be empty.")
        
        # Step 5: Open the directory in Explorer
        try:
            dest_dir = f"{destination_drive}\\{username}"
            os.system(f'explorer "{dest_dir}"')
            self.speak(f"Opening {username} folder.")
        except Exception as e:
            print(f"Error opening explorer: {e}")
        
        # Clean up
        self.speak("Thank you for using Voice Enabled Directory Sync. Goodbye!")
        self.disconnect_share()

def create_mutex():
    """Ensure only one instance of the application is running"""
    try:
        mutex = ctypes.windll.kernel32.CreateMutexA(None, False, b"VoiceEnabledSyncApp")
        if ctypes.windll.kernel32.GetLastError() == 183:
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo("Voice Sync", "Application is already running.")
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
    
    app = VoiceEnabledSync()

if __name__ == "__main__":
    main()