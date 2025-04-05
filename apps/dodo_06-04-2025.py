import os
import subprocess
import pyttsx3
import pyautogui
import speech_recognition as sr
import shutil
import json
import time
import imaplib
import email
import smtplib
import PyPDF2
import docx
import pyaudio
import psutil
import winreg
import screen_brightness_control as sbc
import ctypes
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
import win32api
import win32con
import win32gui
import win32process
import win32com.client
import pandas as pd
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from fuzzywuzzy import process
import re
import logging
import threading
import pystray
from PIL import Image
import google.generativeai as genai
import pvporcupine
import struct
import concurrent.futures
import queue
import uuid
import webbrowser

# Add these global variables after your existing globals
command_queue = queue.Queue()
current_execution = None  # This already exists in your code
execution_lock = threading.Lock()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='assistant.log'
)
logger = logging.getLogger("AI_Assistant")

# ✅ Load Environment Variables
load_dotenv(".env")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ✅ Initialize LLM (LangChain + Gemini 2.0)
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0",
    api_key=GEMINI_API_KEY,
    temperature=0,
    timeout=60
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-2.0-flash')


# ✅ Initialize TTS Engine
engine = pyttsx3.init()
voices = engine.getProperty('voices')
engine.setProperty('voice', voices[1].id)
engine.setProperty('rate', 180)

#✅ Global Variables section
open_apps = {}
app_paths_cache = {}
system_volume = None
system_command_history = []
current_execution = None  # Add this line to track current execution
execution_stop_event = threading.Event()  # Add this for signaling execution to stop
WAKE_WORD = "hey dodo"
command_queue = queue.Queue()
execution_lock = threading.Lock()
# Initialize the command manager

class CommandManager:
    """Manages command execution to ensure proper interruption when wake word is detected"""
    
    def __init__(self):
        self.execution_lock = threading.Lock()
        self.current_command_thread = None
        self.stop_event = threading.Event()
    
    def execute_command(self, command):
        """Execute a command in a new thread, properly handling any existing commands"""
        with self.execution_lock:
            # If there's a command already running, stop it
            if self.current_command_thread and self.current_command_thread.is_alive():
                self.stop_current_command()
            
            # Clear the stop event before starting a new command
            self.stop_event.clear()
            
            # Start a new thread for this command
            thread = threading.Thread(target=self._run_command, args=(command,))
            self.current_command_thread = thread
            thread.start()
            return thread
    
    def _run_command(self, command):
        """Run a single command, checking for interruption signals"""
        try:
            # Use LLM for intent analysis
            intent_data = analyze_with_llm(command)
            
            # Check if this is a web search or unknown intent
            if intent_data["intent"] == "web_search":
                speak(f"I'll search for information about {intent_data['target']}")
                web_search(intent_data["target"])
                return
                
            # Execute the identified intent, passing the stop event
            if intent_data["intent"] != "unknown":
                execute_intent(intent_data, self.stop_event)
            else:
                # For unknown intents, ask if the user wants a web search
                speak("I'm not sure what you're asking. Would you like me to search the web for this?")
                response = listen_command()
                
                if response and any(word in response.lower() for word in ["yes", "sure", "search", "ok"]):
                    web_search(command)
                else:
                    speak("I'm not sure what you want me to do. Please try rephrasing your request.")
                    
        except Exception as e:
            logger.error(f"Command processing error: {e}")
            speak("I encountered an error. Please try again.")
    
    def stop_current_command(self):
        """Signal the current command to stop"""
        self.stop_event.set()
        # Give a short time for the command to clean up
        time.sleep(0.2)
        return True
    
    def is_command_running(self):
        """Check if a command is currently running"""
        return (self.current_command_thread and 
                self.current_command_thread.is_alive())
    
command_manager = CommandManager()
    

# ✅ analyzer with llm
def analyze_with_llm(command):
    """Use Gemini LLM to understand user intent and extract details from commands"""
    try:
        # Get system state for context
        active_window = get_active_window()
        window_title = active_window["title"] if active_window else "None"
        is_browser = is_browser_active()
        
        prompt = f"""
As a voice-activated Windows assistant, analyze this command: "{command}"

Current context:
- Active window: {window_title}
- Is browser active: {"Yes" if is_browser else "No"}
- Current drive: {os.getcwd()[:2]}

Extract the following information in JSON format:
{{
    "intent": [One of these values: "open_app", "close_app", "window_control", "volume_control", "brightness_control", "system_power", "screenshot", "calculator", "media_control", "search", "file_operation", "email", "calendar", "web_search", "local_search", "unknown"],
    
    "sub_intent": [Action specifier, examples below:
      - For window_control: "maximize", "minimize", "restore"
      - For volume_control: "up", "down", "mute", "set"
      - For brightness_control: "up", "down", "set"
      - For system_power: "shutdown", "restart", "sleep", "lock"
      - For media_control: "play", "pause", "next", "previous"
      - For file_operation: "find", "copy", "move", "delete", "rename", "create", "list"
      - For email: "check", "read", "send"
      - For calendar: "add", "list", "delete"
      - For search: "web", "local", "browser"],
    
    "target": [The app name, file name, search query, or other target of the command],
    "source": [Source location if applicable (e.g., drive letter or path)],
    "destination": [Destination location if applicable],
    "value": [Numerical value if applicable (like volume percentage)],
    "explanation": [A brief explanation of what the user wants to do]
}}

Intent Type Guidelines:
- "search" is for when a user explicitly asks to search (e.g., "search for...")
- "web_search" is for general knowledge questions or queries that are best answered with web information (e.g., "what's the weather", "who is the president", "how tall is Eiffel Tower") 
- "local_search" is specifically for searching files on the local computer
- If it's a non-command statement or question that doesn't fit other intents, classify as "web_search"

Return ONLY the JSON object without any additional text.
        """
        
        response = gemini_model.generate_content(prompt)
        response_text = response.text
        
        # Clean the response and extract JSON
        if '```json' in response_text:
            json_str = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            json_str = response_text.split('```')[1].strip()
        else:
            json_str = response_text.strip()
        
        parsed_response = json.loads(json_str)
        
        # Set default values for anything missing
        defaults = {
            "intent": "unknown",
            "sub_intent": None,
            "target": None,
            "source": None,
            "destination": None,
            "value": None,
            "explanation": "No explanation provided"
        }
        
        for key, default_value in defaults.items():
            if key not in parsed_response:
                parsed_response[key] = default_value
        
        print(f"LLM analyzed intent: {parsed_response}")
        return parsed_response
            
    except Exception as e:
        print(f"Error communicating with LLM: {e}")
        # Return a basic structure on failure
        return {
            "intent": "unknown",
            "explanation": f"Error in LLM analysis: {str(e)}"
        }
    
def analyze_file_command(command):
    """Use Gemini LLM to understand file operation intent"""
    global execution_stop_event
    
    try:
        # Check if execution should be interrupted
        if execution_stop_event.is_set():
            return {"intent": "unknown", "explanation": "Operation interrupted"}
            
        # Get available drives for context
        drives = get_available_drives()
        drives_list = ", ".join(drives)
        current_drive = os.getcwd()[:2]  # Get current drive (e.g., "C:")
        
        prompt = f"""
        As a voice-activated file manager assistant, analyze this command: "{command}"
        
        Available drives on this system: {drives_list}
        Current drive: {current_drive}
        
        Extract the following information in JSON format:
        {{
            "intent": "find" or "copy" or "move" or "cut" or "list" or "create" or "delete" or "rename" or "open" or "unknown",
            "item_name": the name of the file or folder being referenced,
            "source": the source location (drive letter or path),
            "destination": the destination location (drive letter or path) if applicable,
            "explanation": a brief explanation of what the user wants to do,
            "file_types": [list of specific file extensions to filter by, without the dot] or null if no specific types
        }}
        
        For example, if the user says "find my tax documents from last year", the response should be:
        {{
            "intent": "find",
            "item_name": "tax documents",
            "source": null,
            "destination": null,
            "explanation": "User wants to find files related to tax documents from last year",
            "file_types": ["pdf", "xlsx", "docx"]
        }}
        
        If the user says "move my presentation from C drive to the network share", the response should be:
        {{
            "intent": "move",
            "item_name": "presentation",
            "source": "C:",
            "destination": "S:",
            "explanation": "User wants to move their presentation from C drive to the network share",
            "file_types": ["pptx", "ppt"]
        }}
        
        If the user says "search for excel files with sales data", the response should be:
        {{
            "intent": "find",
            "item_name": "sales data",
            "source": null,
            "destination": null,
            "explanation": "User wants to find Excel files containing sales data",
            "file_types": ["xlsx", "xls", "csv"]
        }}
        
        Return ONLY the JSON object without any additional text.
        """
        
        response = gemini_model.generate_content(prompt)
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
                parsed_response["source"] = current_drive
            if "destination" not in parsed_response:
                parsed_response["destination"] = None
            if "explanation" not in parsed_response:
                parsed_response["explanation"] = "No explanation provided"
            if "file_types" not in parsed_response:
                parsed_response["file_types"] = None
            
            # Normalize drive letters to uppercase with colon
            if parsed_response["source"] and isinstance(parsed_response["source"], str) and len(parsed_response["source"]) == 1:
                parsed_response["source"] = f"{parsed_response['source'].upper()}:"
            if parsed_response["destination"] and isinstance(parsed_response["destination"], str) and len(parsed_response["destination"]) == 1:
                parsed_response["destination"] = f"{parsed_response['destination'].upper()}:"
            
            print(f"LLM analyzed file intent: {parsed_response}")
            return parsed_response
            
        except json.JSONDecodeError as e:
            print(f"Error parsing LLM response as JSON: {e}")
            print(f"Raw response: {response_text}")
            # Fall back to basic intent
            return {
                "intent": "unknown",
                "item_name": None,
                "source": current_drive,
                "destination": None,
                "explanation": "Failed to parse LLM response",
                "file_types": None
            }
            
    except Exception as e:
        print(f"Error communicating with LLM for file command: {e}")
        # Fall back to basic intent
        return {
            "intent": "unknown",
            "item_name": None,
            "source": os.getcwd()[:2],
            "destination": None,
            "explanation": f"Error in LLM analysis: {str(e)}",
            "file_types": None
        }
 

# ✅ Intent Execution router
def execute_intent(intent_data, stop_event=None):
    """Route the analyzed intent to the appropriate function"""
    
    intent = intent_data.get("intent", "unknown")
    sub_intent = intent_data.get("sub_intent")
    target = intent_data.get("target")
    explanation = intent_data.get("explanation")
    
    print(f"Executing intent: {intent}, sub-intent: {sub_intent}, target: {target}")
    
    try:
        # Check if execution should be interrupted
        if stop_event and stop_event.is_set():
            print("Intent execution interrupted")
            return False
            
        # APPLICATION CONTROL
        if intent == "open_app":
            success = open_application(f"open {target}")
            return True  # Always return True to prevent fallback, even if opening failed
        
        # Check for interruption between major operations
        if stop_event and stop_event.is_set():
            print("Intent execution interrupted")
            return False
            
        elif intent == "close_app":
            success = close_application(f"close {target}")
            return True  # Always return True to prevent fallback
        
        # Check for interruption between major operations
        if stop_event and stop_event.is_set():
            print("Intent execution interrupted")
            return False
            
        # WINDOW CONTROL
        elif intent == "window_control":
            success = handle_window_commands(f"{sub_intent} window")
            return True  # Always return True to prevent fallback
        
        # Check for interruption
        if stop_event and stop_event.is_set():
            print("Intent execution interrupted")
            return False
            
        # SYSTEM CONTROL
        elif intent == "volume_control":
            value = intent_data.get("value")
            if value:
                system_control(f"volume set {value}")
            else:
                system_control(f"volume {sub_intent}")
            return True  # Indicate success even if the function doesn't return anything
        
        # Check for interruption
        if stop_event and stop_event.is_set():
            print("Intent execution interrupted")
            return False
            
        elif intent == "brightness_control":
            value = intent_data.get("value")
            if value:
                system_control(f"brightness set {value}")
            else:
                system_control(f"brightness {sub_intent}")
            return True
        
        # Check for interruption
        if stop_event and stop_event.is_set():
            print("Intent execution interrupted")
            return False
            
        elif intent == "system_power":
            system_control(sub_intent)
            return True
        
        # Check for interruption
        if stop_event and stop_event.is_set():
            print("Intent execution interrupted")
            return False
            
        elif intent == "screenshot":
            system_control("screenshot")
            return True
        
        # Check for interruption
        if stop_event and stop_event.is_set():
            print("Intent execution interrupted")
            return False
            
        # CALCULATOR
        elif intent == "calculator":
            handle_calculator_command(f"calculate {target}")
            return True
        
        # Check for interruption
        if stop_event and stop_event.is_set():
            print("Intent execution interrupted")
            return False
            
        # MEDIA CONTROL
        elif intent == "media_control":
            if stop_event and stop_event.is_set():
                print("Intent execution interrupted")
                return False
                
            if sub_intent == "play" or sub_intent == "pause":
                media_play_pause()
                return True
            elif sub_intent == "next":
                media_next()
                return True
            elif sub_intent == "previous":
                media_previous()
                return True
            return True  # Always return True to prevent fallback, even for unknown sub-intent
        
        # Check for interruption
        if stop_event and stop_event.is_set():
            print("Intent execution interrupted")
            return False
        
        # WEB SEARCH (New)
        elif intent == "web_search":
            # Ask for confirmation before web search
            speak(f"Would you like me to search the web for '{target}'?")
            confirmation = listen_command()
            
            if confirmation and any(word in confirmation.lower() for word in ["yes", "sure", "search", "okay", "go ahead"]):
                web_search(target)
            else:
                speak("Web search cancelled")
            return True
            
        # SEARCH HANDLING (Modified)
        elif intent == "search":
            # Check the sub_intent to determine search type
            if sub_intent == "browser":
                # Explicit browser search
                search_in_browser(target)
                return True
            elif sub_intent == "local":
                # Explicit local search
                search_files(target, None, stop_event)
                return True
            else:
                # General search - check context to determine best action
                active_browser = is_browser_active()
                
                if active_browser:
                    # If a browser is active, use it for search
                    search_in_browser(target, active_browser)
                else:
                    # Otherwise, ask the user what kind of search they want
                    speak(f"Do you want me to search the web or your files for '{target}'?")
                    search_type = listen_command()
                    
                    if search_type and any(word in search_type.lower() for word in ["web", "internet", "google", "online"]):
                        web_search(target)
                    elif search_type and any(word in search_type.lower() for word in ["file", "local", "computer", "document"]):
                        search_files(target, None, stop_event)
                    else:
                        # Default to web search if unclear
                        speak("I'll search the web for you")
                        web_search(target)
                return True
                
        # LOCAL SEARCH (New)
        elif intent == "local_search":
            # Search for files on the local computer
            search_files(target, None, stop_event)
            return True
            
        # Check for interruption
        if stop_event and stop_event.is_set():
            print("Intent execution interrupted")
            return False
            
        # FILE OPERATIONS
        elif intent == "file_operation":
            source = intent_data.get("source")
            dest = intent_data.get("destination")

            # Construct a command string
            file_command = f"{sub_intent} {target}"
            if source:
                file_command += f" from {source}"
            if dest:
                file_command += f" to {dest}"

            # Check for interruption before processing file command
            if stop_event and stop_event.is_set():
                print("File operation interrupted")
                return False
                
            # Handle file operation directly
            success = handle_files(file_command, stop_event)
            return True  # Always return True to prevent fallback
        
        # Check for interruption
        if stop_event and stop_event.is_set():
            print("Intent execution interrupted")
            return False
            
        # EMAIL
        elif intent == "email":
            handle_email(f"{sub_intent} email", stop_event)
            return True
        
        # Check for interruption
        if stop_event and stop_event.is_set():
            print("Intent execution interrupted")
            return False
            
        # CALENDAR
        elif intent == "calendar":
            handle_calendar(f"{sub_intent} {target}", stop_event)
            return True
        
        # UNKNOWN INTENT
        else:
            # For unknown intents that look like questions or statements
            if target and isinstance(target, str) and len(target) > 0:
                # Ask if the user wants to search the web for this
                speak(f"Would you like me to search the web for '{target}'?")
                response = listen_command()
                
                if response and any(word in response.lower() for word in ["yes", "sure", "please", "ok", "okay", "search"]):
                    web_search(target)
                    return True
                else:
                    speak(f"I'm not sure what you want me to do. {explanation}")
            else:
                speak(f"I'm not sure what you want me to do. {explanation}")
            return False  # Only return False for truly unknown intents
    
    except Exception as e:
        logger.error(f"Error executing intent {intent}: {e}")
        speak(f"I encountered an error while trying to {explanation}")
        return True  # Return True on exceptions to prevent fallback

# ✅ Setup Audio Control
def setup_audio_control():
    global system_volume
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        system_volume = cast(interface, POINTER(IAudioEndpointVolume))
        logger.info("Audio control initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize audio control: {e}")
        system_volume = None

# ✅ Speak Function
def speak(text):
    try:
        engine.say(text)
        engine.runAndWait()
        print(f"🎙️ Assistant: {text}")
    except Exception as e:
        logger.error(f"TTS error: {e}")
        print(f"🎙️ Assistant: {text}")

# ✅ Scan for Installed Applications
def scan_installed_apps():
    apps = {}
    
    # Method 1: Scan Start Menu
    start_menu = os.path.join(os.environ["PROGRAMDATA"], "Microsoft", "Windows", "Start Menu", "Programs")
    user_start_menu = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs")
    
    for folder in [start_menu, user_start_menu]:
        for root, dirs, files in os.walk(folder):
            for file in files:
                if file.endswith('.lnk'):
                    try:
                        shell = win32com.client.Dispatch("WScript.Shell")
                        shortcut = shell.CreateShortCut(os.path.join(root, file))
                        app_name = os.path.splitext(file)[0].lower()
                        apps[app_name] = shortcut.Targetpath
                    except Exception as e:
                        logger.warning(f"Error reading shortcut {file}: {e}")
    
    # Method 2: Scan Registry
    try:
        uninstall_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")
        for i in range(winreg.QueryInfoKey(uninstall_key)[0]):
            try:
                app_key_name = winreg.EnumKey(uninstall_key, i)
                app_key = winreg.OpenKey(uninstall_key, app_key_name)
                try:
                    app_name = winreg.QueryValueEx(app_key, "DisplayName")[0].lower()
                    app_path = winreg.QueryValueEx(app_key, "InstallLocation")[0]
                    
                    if app_path and os.path.exists(app_path):
                        executables = [f for f in os.listdir(app_path) if f.endswith('.exe')]
                        if executables:
                            apps[app_name] = os.path.join(app_path, executables[0])
                except:
                    pass
            except:
                pass
    except Exception as e:
        logger.warning(f"Registry scan error: {e}")
    
    # Add some common applications with typical paths
    common_apps = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "chrome": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        "edge": "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
        "firefox": "C:\\Program Files\\Mozilla Firefox\\firefox.exe",
        #"spotify": "C:\\Program Files\\Spotify\\Spotify.exe",
        "vlc": "C:\\Program Files\\VideoLAN\\VLC\\vlc.exe",
        "word": "C:\\Program Files\\Microsoft Office\\root\\Office16\\WINWORD.EXE",
        "excel": "C:\\Program Files\\Microsoft Office\\root\\Office16\\EXCEL.EXE",
        "powerpoint": "C:\\Program Files\\Microsoft Office\\root\\Office16\\POWERPNT.EXE",
        "explorer": "explorer.exe",
        "settings": "ms-settings:",
        "task manager": "taskmgr.exe",
        "control panel": "control.exe",
    }
    
    for app_name, app_path in common_apps.items():
        if app_name not in apps:
            apps[app_name] = app_path
    
    logger.info(f"Found {len(apps)} applications")
    return apps

# ✅ Find Application by Name
def find_app(app_name):
    global app_paths_cache
    
    if not app_paths_cache:
        app_paths_cache = scan_installed_apps()
    
    if app_name.lower() in app_paths_cache:
        return app_paths_cache[app_name.lower()]
    
    matches = process.extractBests(app_name.lower(), list(app_paths_cache.keys()), score_cutoff=60)
    if matches:
        best_match = matches[0][0]
        return app_paths_cache[best_match]
    
    try:
        result = subprocess.run(["where", app_name + ".exe"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return result.stdout.strip()
    except:
        pass
    
    return None

# ✅ Open Applications
def open_application(command):
    command = command.lower()
    app_name = command.replace("open", "").strip()
    
    # Check if app is already open
    if app_name in open_apps:
        print(f"🔹 {app_name} is already open, bringing to front...")
        try:
            # Try to bring the window to front
            hwnd = win32gui.FindWindow(None, app_name)
            if hwnd:
                win32gui.SetForegroundWindow(hwnd)
                speak(f"{app_name} is already open")
                return True
        except:
            # If bringing to front fails, continue with normal open process
            pass
    
    app_path = find_app(app_name)
    
    if app_path:
        try:
            print(f"🔹 Opening {app_name} from {app_path}...")
            speak(f"Opening {app_name}")
            
            if app_path.startswith("ms-"):
                proc = subprocess.Popen(["start", app_path], shell=True)
            else:
                proc = subprocess.Popen(app_path)
                
            open_apps[app_name] = proc
            return True
        except Exception as e:
            logger.error(f"Failed to open {app_name}: {e}")
            speak(f"Sorry, I couldn't open {app_name}")
    else:
        print(f"❌ Application {app_name} not found.")
        speak(f"I couldn't find {app_name} on your system")
    
    return False

def close_application(command):     
    command = command.lower()     
    app_name = command.replace("close", "").strip()          

    if app_name in open_apps:         
        try:             
            open_apps[app_name].terminate()             
            del open_apps[app_name]             
            speak(f"Closed {app_name}")             
            return True         
        except Exception as e:             
            logger.error(f"Failed to close {app_name}: {e}")          

    for proc in psutil.process_iter(['pid', 'name']):         
        try:             
            process_name = proc.info['name'].lower()             
            if app_name in process_name or process_name in app_name:                 
                proc.terminate()                 
                speak(f"Closed {app_name}")                 
                return True         
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):             
            pass          

    window_handles = []     
    def enum_windows_callback(hwnd, results):         
        if win32gui.IsWindowVisible(hwnd):             
            window_title = win32gui.GetWindowText(hwnd).lower()             
            if app_name in window_title:                 
                results.append(hwnd)          

    win32gui.EnumWindows(enum_windows_callback, window_handles)          

    if window_handles:         
        for hwnd in window_handles:             
            try:                 
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)                 
                speak(f"Closed {app_name}")                 
                return True             
            except:                 
                pass          

    # Use pyautogui to close the app using Alt+F4
    try:
        pyautogui.hotkey('alt', 'f4')
        speak(f"Attempted to close {app_name} using Alt+F4")
        return True
    except Exception as e:
        logger.error(f"Failed to close {app_name} using Alt+F4: {e}")
    
    speak(f"I couldn't find {app_name} running")     
    return False

#✅ Identify Active Window
def get_active_window():
    try:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd == 0:
            return None
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid)
        window_title = win32gui.GetWindowText(hwnd)
        
        return {
            "pid": pid,
            "title": window_title,
            "process_name": process.name().lower(),
            "hwnd": hwnd
        }
    except Exception as e:
        logger.error(f"Error fetching active window: {e}")
        return None


# ✅ Enhanced Window Control (Maximize, Minimize, Restore)
def handle_window_commands(command):
    active_window = get_active_window()
    if not active_window:
        speak("No active window detected.")
        return False

    hwnd = active_window["hwnd"]
    window_title = active_window["title"]
    success = False
    
    # Determine the command type
    if "maximize" in command or "maximise" in command:
        command_type = "maximize"
        speak(f"Maximizing {window_title}")
    elif "minimize" in command or "minimise" in command:
        command_type = "minimize"
        speak(f"Minimizing {window_title}")
    elif "restore" in command or "unminimize" in command or "bring back" in command:
        command_type = "restore"
        speak(f"Restoring {window_title}")
    else:
        speak("Unsupported window command")
        return False
    
    # Method 1: Using win32gui (primary method)
    try:
        if command_type == "maximize":
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
        elif command_type == "minimize":
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        elif command_type == "restore":
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        
        success = True
        logger.info(f"Successfully {command_type}d window using win32gui")
    except Exception as e:
        logger.error(f"Method 1 failed to {command_type} window: {e}")
    
    # Method 2: Using keyboard shortcuts if Method 1 fails
    if not success:
        try:
            # Ensure the window is focused first
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.2)  # Short delay to ensure window is focused
            
            if command_type == "maximize":
                pyautogui.hotkey('win', 'up')  # Windows key + Up maximizes
            elif command_type == "minimize":
                pyautogui.hotkey('win', 'down', 'down')  # Win + Down twice minimizes
            elif command_type == "restore":
                # If minimized, Win+Down restores, if maximized, Win+Down restores
                pyautogui.hotkey('win', 'down')
            
            success = True
            logger.info(f"Successfully {command_type}d window using keyboard shortcuts")
        except Exception as e:
            logger.error(f"Method 2 failed to {command_type} window: {e}")
    
    # Method 3: Using Alt+Space menu if Methods 1 and 2 fail
    if not success:
        try:
            # Focus the window first
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.2)
            
            # Open the system menu with Alt+Space
            pyautogui.hotkey('alt', 'space')
            time.sleep(0.2)
            
            # Send the appropriate key for the command
            if command_type == "maximize":
                pyautogui.press('x')  # 'x' is for maximize in system menu
            elif command_type == "minimize":
                pyautogui.press('n')  # 'n' is for minimize in system menu
            elif command_type == "restore":
                pyautogui.press('r')  # 'r' is for restore in system menu
            
            success = True
            logger.info(f"Successfully {command_type}d window using Alt+Space menu")
        except Exception as e:
            logger.error(f"Method 3 failed to {command_type} window: {e}")
    
    # Report result
    if success:
        return True
    else:
        speak(f"I couldn't {command_type} the window after multiple attempts.")
        return False

# ✅ Handle Calculator Commands (Improved Handling)

def handle_calculator_command(command):
    active_window = get_active_window()
    
    if not active_window:
        speak("No active window detected.")
        return

    process_name = active_window["process_name"]
    window_title = active_window["title"].lower()
    valid_titles = ["calculator", "notepad", "wordpad"]

    # Check if the active window title contains any of the valid titles
    if not any(valid_title in window_title for valid_title in valid_titles):
        speak(f"{window_title} is not a supported app for calculations.")
        return

    hwnd = active_window["hwnd"]
    try:
        # Bring the window to the front
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.5)
        
        # Format the command for input
        expression = command.lower().replace("calculate", "").strip()
        expression = expression.replace("plus", "+").replace("minus", "-")
        expression = expression.replace("times", "*").replace("divided by", "/")
        
        # Type the expression
        pyautogui.typewrite(expression)
        pyautogui.press("enter")
        
        speak(f"Calculated {expression}")
    except Exception as e:
        logger.error(f"Failed to process calculation: {e}")
        speak("I couldn't process the calculation.")



# ✅ System Control Functions
def system_control(command):
    command = command.lower()
    
    # Volume control
    if "volume" in command:
        if system_volume:
            current_volume = system_volume.GetMasterVolumeLevelScalar()
            
            if "up" in command or "increase" in command:
                new_volume = min(1.0, current_volume + 0.1)
                system_volume.SetMasterVolumeLevelScalar(new_volume, None)
                speak(f"Volume increased to {int(new_volume * 100)}%")
            
            elif "down" in command or "decrease" in command:
                new_volume = max(0.0, current_volume - 0.1)
                system_volume.SetMasterVolumeLevelScalar(new_volume, None)
                speak(f"Volume decreased to {int(new_volume * 100)}%")
            
            elif "mute" in command or "unmute" in command:
                mute_state = system_volume.GetMute()
                system_volume.SetMute(not mute_state, None)
                speak("Volume toggled mute")
            
            elif "set" in command:
                match = re.search(r"(\d+)(\s*%|\s*percent)?", command)
                if match:
                    percent = int(match.group(1))
                    new_volume = max(0.0, min(1.0, percent / 100))
                    system_volume.SetMasterVolumeLevelScalar(new_volume, None)
                    speak(f"Volume set to {percent}%")
                else:
                    speak("I couldn't understand the volume level")
            
            else:
                speak(f"Current volume is {int(current_volume * 100)}%")
        else:
            speak("Volume control is not available")
    
    # Brightness control
    elif "brightness" in command:
        try:
            current_brightness = sbc.get_brightness()[0]
            
            if "up" in command or "increase" in command:
                new_brightness = min(100, current_brightness + 10)
                sbc.set_brightness(new_brightness)
                speak(f"Brightness increased to {new_brightness}%")
            
            elif "down" in command or "decrease" in command:
                new_brightness = max(0, current_brightness - 10)
                sbc.set_brightness(new_brightness)
                speak(f"Brightness decreased to {new_brightness}%")
            
            elif "set" in command:
                match = re.search(r"(\d+)(\s*%|\s*percent)?", command)
                if match:
                    percent = int(match.group(1))
                    sbc.set_brightness(percent)
                    speak(f"Brightness set to {percent}%")
                else:
                    speak("I couldn't understand the brightness level")
            
            else:
                speak(f"Current brightness is {current_brightness}%")
        except Exception as e:
            logger.error(f"Brightness control error: {e}")
            speak("Brightness control is not available")
    
    # Power management
    elif any(x in command for x in ["shutdown", "restart", "log off", "sleep", "hibernate", "lock"]):
        if "shutdown" in command:
            os.system("shutdown /s /t 1")
        
        elif "restart" in command:
            os.system("shutdown /r /t 1")
        
        elif "log off" in command:
            os.system("shutdown /l")
        
        elif "sleep" in command:
            os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
        
        elif "hibernate" in command:
            os.system("shutdown /h")
        
        elif "lock" in command:
            ctypes.windll.user32.LockWorkStation()
    
    elif "screenshot" in command:
        screenshot_path = os.path.join(os.path.expanduser("~"), "Pictures", f"screenshot_{int(time.time())}.png")
        pyautogui.screenshot(screenshot_path)
        speak(f"Screenshot saved to {screenshot_path}")

# ✅ Email Handling
def handle_email(command):
    if "check" in command or "read" in command:
        speak("Checking your emails. Please wait.")
        try:
            # Your email credentials
            email_user = "your_email@gmail.com"
            email_password = "your_password"
            
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(email_user, email_password)
            mail.select("inbox")
            
            status, messages = mail.search(None, "UNSEEN")
            messages = messages[0].split()
            
            if len(messages) == 0:
                speak("You have no unread emails.")
            else:
                speak(f"You have {len(messages)} unread emails.")
                
                for num in messages[:5]:
                    status, data = mail.fetch(num, "(RFC822)")
                    email_msg = email.message_from_bytes(data[0][1])
                    
                    subject = email_msg["subject"]
                    sender = email_msg["from"]
                    speak(f"Email from {sender} with subject {subject}.")
                    
            mail.close()
            mail.logout()
        
        except Exception as e:
            logger.error(f"Email reading error: {e}")
            speak("I couldn't check your emails.")
    
    elif "send" in command:
        speak("What is the subject of the email?")
        subject = listen_command()
        
        speak("What is the content of the email?")
        content = listen_command()
        
        speak("Who should I send this email to?")
        recipient = listen_command()
        
        try:
            smtp_server = "smtp.gmail.com"
            smtp_port = 587
            email_user = "your_email@gmail.com"
            email_password = "your_password"
            
            msg = MIMEMultipart()
            msg["From"] = email_user
            msg["To"] = recipient
            msg["Subject"] = subject
            msg.attach(MIMEText(content, "plain"))
            
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(email_user, email_password)
            server.sendmail(email_user, recipient, msg.as_string())
            server.quit()
            
            speak("Email has been sent successfully.")
        
        except Exception as e:
            logger.error(f"Email sending error: {e}")
            speak("Failed to send the email.")

# ✅ Enhanced File Handling Function
def handle_files(command, stop_event=None):
    """Enhanced File Handling Function with LLM intent recognition and voice interaction"""
    command = command.lower()
    
    try:
        # Check for interruption
        if stop_event and stop_event.is_set():
            return False
            
        # Use LLM to analyze command
        intent_data = analyze_file_command(command)
        
        intent = intent_data.get("intent")
        item_name = intent_data.get("item_name")
        source = intent_data.get("source")
        destination = intent_data.get("destination")
        file_types = intent_data.get("file_types")
        explanation = intent_data.get("explanation")
        
        print(f"File operation intent: {intent}")
        print(f"Item: {item_name}, Source: {source}, Destination: {destination}")
        print(f"File types: {file_types}")
        print(f"Explanation: {explanation}")
        
        # Check for interruption after LLM analysis
        if stop_event and stop_event.is_set():
            return False
            
        # Process based on intent
        if intent == "find" or intent == "search":
            # Use the enhanced smart search for better results
            return smart_file_search(item_name if item_name else command, stop_event)
                
        elif intent == "list" or intent == "show" or intent == "display":
            directory_path = resolve_path(item_name, source) if item_name else source
            return list_directory(directory_path, stop_event)
                
        elif intent == "create" or intent == "make" or intent == "new":
            # Determine if it's a file or folder
            is_folder = not "file" in command.lower()
            item_path = resolve_path(item_name, source)
            return create_item(item_path, is_folder, stop_event)
                
        elif intent == "delete" or intent == "remove":
            item_path = resolve_path(item_name, source)
            return delete_item(item_path, stop_event)
                
        elif intent == "rename":
            old_path = resolve_path(item_name, source)
            if not destination:
                speak("What would you like to rename it to?")
                new_name = listen_command()
                if not new_name or (stop_event and stop_event.is_set()):
                    speak("Rename operation cancelled")
                    return False
                return rename_item(old_path, new_name, stop_event)
            else:
                return rename_item(old_path, os.path.basename(destination), stop_event)
                
        elif intent == "copy":
            source_path = resolve_path(item_name, source)
            dest_path = destination
            
            if not dest_path:
                speak("Where would you like to copy it to?")
                dest_response = listen_command()
                if not dest_response or (stop_event and stop_event.is_set()):
                    speak("Copy operation cancelled")
                    return False
                dest_path = resolve_path_with_llm(dest_response, os.getcwd())
            
            success, message = copy_item(source_path, dest_path, stop_event)
            if success:
                response = generate_file_success_response(f"copy {item_name}", message)
                speak(response)
            else:
                response = generate_file_error_response(f"copy {item_name}", message, "copy")
                speak(response)
            return success
                
        elif intent == "move" or intent == "cut":
            source_path = resolve_path(item_name, source)
            dest_path = destination
            
            if not dest_path:
                speak("Where would you like to move it to?")
                dest_response = listen_command()
                if not dest_response or (stop_event and stop_event.is_set()):
                    speak("Move operation cancelled")
                    return False
                dest_path = resolve_path_with_llm(dest_response, os.getcwd())
            
            success, message = move_item(source_path, dest_path, stop_event)
            if success:
                response = generate_file_success_response(f"move {item_name}", message)
                speak(response)
            else:
                response = generate_file_error_response(f"move {item_name}", message, "move")
                speak(response)
            return success
        
        elif intent == "open":
            item_path = resolve_path(item_name, source)
            return open_file(item_path, stop_event)
        
        # If LLM couldn't determine intent, fall back to traditional command parsing
        elif intent == "unknown":
            # Check for interruption before falling back
            if stop_event and stop_event.is_set():
                return False
                
            # Legacy handling for simple commands
            if "find" in command or "search" in command:
                search_term = command.replace("find", "").replace("search", "").strip()
                return search_files(search_term, None, stop_event)
            
            # ... rest of your legacy parsing code with stop_event checks
            # For example:
            elif "move" in command:
                speak("What file or folder would you like to move?")
                source_response = listen_command()
                if not source_response or (stop_event and stop_event.is_set()):
                    speak("Move operation cancelled")
                    return False
                    
                speak("Where would you like to move it to?")
                destination_response = listen_command()
                if not destination_response or (stop_event and stop_event.is_set()):
                    speak("Move operation cancelled")
                    return False
                    
                source_path = resolve_path_with_llm(source_response, os.getcwd())
                dest_path = resolve_path_with_llm(destination_response, os.getcwd())
                success, message = move_item(source_path, dest_path, stop_event)
                if success:
                    speak(f"Successfully moved {os.path.basename(source_path)}")
                else:
                    speak(f"Failed to move: {message}")
                return success
            
            # ... continue with other command types
            
            else:
                speak("I'm not sure what file operation you want to perform")
                return False
        
        else:
            speak(f"I don't know how to {intent} files")
            return False
    
    except Exception as e:
        logger.error(f"File handling error: {e}")
        speak("I encountered an error handling your file operation.")
        return False

# ✅ Search Files
def search_files(search_term, file_types=None, stop_event=None):
    """Enhanced file search using multi-threading with optional file type filtering"""
    
    speak(f"Searching for {search_term}")
    
    # Check for interruption before starting search
    if stop_event and stop_event.is_set():
        return False
    
    # Use multi-threaded search across all drives
    results = find_item_across_drives(search_term, file_types, stop_event)
    
    # Check for interruption after search completes
    if stop_event and stop_event.is_set():
        return False
    
    # Filter out progress indicators
    actual_results = [loc for loc in results if not loc.startswith("...")]
    
    if actual_results:
        speak(f"Found {len(actual_results)} matching files or folders.")
        
        # Group results by drive for better organization
        drive_summary = {}
        for loc in actual_results:
            drive = loc[:2]  # Get the drive letter (e.g., "C:")
            if drive in drive_summary:
                drive_summary[drive] += 1
            else:
                drive_summary[drive] = 1
        
        # Provide a summary by drive
        summary = "Files/folders were found in: "
        summary += ", ".join([f"{count} matches on {drive}" for drive, count in drive_summary.items()])
        speak(summary)
        
        # Check for interruption before prioritizing results
        if stop_event and stop_event.is_set():
            return False
            
        # Prioritize results if we have too many
        if len(actual_results) > 5:
            prioritized_results = prioritize_search_results(actual_results, search_term, file_types)
            actual_results = prioritized_results
        
        # Display top 5 results
        speak("Here are the top results:")
        for i, result in enumerate(actual_results[:5]):
            speak(f"{i+1}: {os.path.basename(result)}")
        
        # Check for interruption before asking about opening files
        if stop_event and stop_event.is_set():
            return False
            
        speak("Would you like to open any of these files?")
        response = listen_command()
        
        # Check for interruption after listening for response
        if not response or (stop_event and stop_event.is_set()):
            return False
            
        if any(x in response.lower() for x in ["yes", "sure", "open"]):
            if "number" in response or any(str(i) in response for i in range(1, 6)):
                for i in range(1, 6):
                    if str(i) in response:
                        index = i - 1
                        if index < len(actual_results):
                            open_file(actual_results[index], stop_event)
                            speak(f"Opening {os.path.basename(actual_results[index])}")
                        break
            else:
                open_file(actual_results[0], stop_event)
                speak(f"Opening {os.path.basename(actual_results[0])}")
        return True
    else:
        speak(f"No files found matching '{search_term}'")
        return True
#Open file:

def open_file(file_path, stop_event=None):
    """Open a file with the appropriate application based on file type"""
    
    try:
        # Check if execution should be interrupted
        if stop_event and stop_event.is_set():
            return False
            
        # Check if the file exists
        if not os.path.exists(file_path):
            # Try to find it in current directory
            found_path = find_item_in_current_directory(os.path.basename(file_path))
            if found_path:
                file_path = found_path
                print(f"Found file to open at: {file_path}")
            else:
                speak(f"I couldn't find {os.path.basename(file_path)}")
                return False
        
        # If it's a directory, open in File Explorer
        if os.path.isdir(file_path):
            os.startfile(file_path)
            speak(f"Opened folder {os.path.basename(file_path)} in File Explorer")
            return True
        
        # Get the file extension
        file_ext = os.path.splitext(file_path)[1].lower()
        
        # Check for interruption before opening file
        if stop_event and stop_event.is_set():
            return False
            
        # Handle common file types specially
        if file_ext in ['.doc', '.docx']:
            # Try to open with Word, fall back to default
            try:
                word_app = win32com.client.Dispatch("Word.Application")
                word_app.Visible = True
                word_app.Documents.Open(file_path)
                speak(f"Opened {os.path.basename(file_path)} in Microsoft Word")
            except:
                os.startfile(file_path)
                speak(f"Opened {os.path.basename(file_path)}")
        
        elif file_ext in ['.xls', '.xlsx']:
            # Try to open with Excel, fall back to default
            try:
                excel_app = win32com.client.Dispatch("Excel.Application")
                excel_app.Visible = True
                excel_app.Workbooks.Open(file_path)
                speak(f"Opened {os.path.basename(file_path)} in Microsoft Excel")
            except:
                os.startfile(file_path)
                speak(f"Opened {os.path.basename(file_path)}")
        
        elif file_ext in ['.ppt', '.pptx']:
            # Try to open with PowerPoint, fall back to default
            try:
                ppt_app = win32com.client.Dispatch("PowerPoint.Application")
                ppt_app.Visible = True
                ppt_app.Presentations.Open(file_path)
                speak(f"Opened {os.path.basename(file_path)} in Microsoft PowerPoint")
            except:
                os.startfile(file_path)
                speak(f"Opened {os.path.basename(file_path)}")
        
        elif file_ext == '.pdf':
            # Just use system default
            os.startfile(file_path)
            speak(f"Opened PDF {os.path.basename(file_path)}")
        
        elif file_ext in ['.txt', '.md', '.py', '.js', '.html', '.css', '.json', '.xml']:
            # Try to open with Notepad or system default for text files
            try:
                subprocess.Popen(['notepad.exe', file_path])
                speak(f"Opened {os.path.basename(file_path)} in Notepad")
            except:
                os.startfile(file_path)
                speak(f"Opened {os.path.basename(file_path)}")
        
        elif file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
            # Open with system default for images
            os.startfile(file_path)
            speak(f"Opened image {os.path.basename(file_path)}")
        
        elif file_ext in ['.mp3', '.wav', '.aac', '.flac', '.ogg']:
            # Open with system default for audio
            os.startfile(file_path)
            speak(f"Playing audio file {os.path.basename(file_path)}")
        
        elif file_ext in ['.mp4', '.mkv', '.avi', '.mov', '.wmv']:
            # Open with system default for video
            os.startfile(file_path)
            speak(f"Playing video file {os.path.basename(file_path)}")
        
        else:
            # Use system default for any other file type
            os.startfile(file_path)
            speak(f"Opened {os.path.basename(file_path)}")
        
        return True
    
    except Exception as e:
        logger.error(f"Error opening file: {e}")
        speak(f"I couldn't open {os.path.basename(file_path)}")
        return False

#Prioritize Search Results.
def prioritize_search_results(results, search_term, file_types=None):
    """Prioritize search results using LLM and file metadata"""
    try:
        # If we have just a few results, no need for complex prioritization
        if len(results) <= 5:
            return results
        
        # Basic prioritization based on simple rules for performance
        prioritized = []
        other_results = []
        
        for path in results:
            filename = os.path.basename(path).lower()
            # Exact matches go first
            if search_term.lower() == filename.lower():
                prioritized.insert(0, path)
            # Files with search term at the start of the name
            elif filename.lower().startswith(search_term.lower()):
                prioritized.append(path)
            # Everything else
            else:
                other_results.append(path)
        
        # Further prioritize by file type if specified
        if file_types:
            type_matches = []
            other_typed = []
            
            for path in other_results:
                if os.path.isfile(path):
                    ext = os.path.splitext(path)[1].lower()
                    if ext and ext[1:] in file_types:  # Remove the dot and compare
                        type_matches.append(path)
                    else:
                        other_typed.append(path)
                else:  # It's a directory
                    other_typed.append(path)
            
            # Recombine with type matches first
            other_results = type_matches + other_typed
        
        # Recombine all results
        return prioritized + other_results
            
    except Exception as e:
        logger.error(f"Error prioritizing search results: {e}")
        # Return original results on error
        return results

def generate_file_success_response(command, result=""):
    """Generate a natural success response for file operations using LLM"""
    try:
        # Check if result is empty and provide a default
        if not result:
            result = "Operation completed successfully"
            
        prompt = f"""
        Generate a natural, friendly response for a voice assistant that has successfully completed this file operation:
        Command: "{command}"
        Result: "{result}"
        
        Give a short, conversational response (maximum 2 sentences) that confirms the task was completed successfully.
        Include the key information from the result.
        """
        
        response = gemini_model.generate_content(prompt)
        response_text = response.text.strip('"\'').strip()
        return response_text
    except Exception as e:
        print(f"Error generating success response: {e}")
        return f"Success! {result}"

def generate_file_error_response(command, error, intent):
    """Generate a helpful error message for file operations using LLM"""
    try:
        prompt = f"""
        Generate a natural, helpful response for a voice assistant that could not complete this file operation:
        Command: "{command}"
        Error: "{error}"
        Intent: "{intent}"
        
        Give a short, conversational response (maximum 2 sentences) that:
        1. Acknowledges the error in a friendly way
        2. Briefly explains what went wrong
        
        Be specific but keep it simple and conversational.
        """
        
        response = gemini_model.generate_content(prompt)
        response_text = response.text.strip('"\'').strip()
        return response_text
    except Exception as e:
        print(f"Error generating failure response: {e}")
        return f"Sorry, there was a problem. {error}"

#----------------------------------------
def get_available_drives():
    """Get list of available drives on the system"""
    drives = []
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        if bitmask & 1:
            drives.append(f"{letter}:")
        bitmask >>= 1
    return drives

def find_item_in_current_directory(item_name):
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


def resolve_path_with_llm(description, current_directory):
    """Use LLM to intelligently resolve a natural language path description"""
    global execution_stop_event
    
    try:
        # Check if execution should be interrupted
        if execution_stop_event.is_set():
            return None
            
        # First try standard resolution
        direct_path = resolve_path(description, current_directory)
        if os.path.exists(direct_path):
            return direct_path
        
        # If that fails, use LLM to interpret
        prompt = f"""
        As a voice-activated file system assistant, interpret this file or folder location description: "{description}"
        
        Current directory: {current_directory}
        Available drives: {', '.join(get_available_drives())}
        Common folders: Desktop, Documents, Downloads, Pictures, Music, Videos
        
        Return ONLY the most likely absolute file path that matches this description, with no explanation or additional text.
        If the description is ambiguous, make your best guess based on common Windows file organization.
        
        Examples:
        "my downloads folder" -> "C:\\Users\\Username\\Downloads"
        "excel spreadsheet from yesterday" -> "C:\\Users\\Username\\Documents\\Recent\\spreadsheet.xlsx"
        """
        
        response = gemini_model.generate_content(prompt)
        response_text = response.text.strip().strip('"')
        
        # Validate the path makes sense
        if os.path.exists(response_text) or os.path.exists(os.path.dirname(response_text)):
            return response_text
        
        # If LLM path doesn't exist, return the original resolution
        return direct_path
            
    except Exception as e:
        logger.error(f"Error using LLM for path resolution: {e}")
        # Fall back to standard resolution
        return resolve_path(description, current_directory)

def resolve_path(item_name, drive_letter):
    """Resolve the full path for an item on a specified drive or path"""
    # Handle empty cases
    if not item_name:
        return drive_letter
    
    # Handle when drive_letter is None
    if not drive_letter:
        drive_letter = os.getcwd()
    
    # Check if item_name already has a full path
    if os.path.isabs(item_name):
        return item_name
    
    # Handle root level path
    if isinstance(drive_letter, str) and drive_letter.endswith(':'):
        return os.path.join(drive_letter + "\\", item_name)
    # Handle full paths
    elif isinstance(drive_letter, str) and os.path.isabs(drive_letter):
        return os.path.join(drive_letter, item_name)
    # Handle drive letters without colon
    elif isinstance(drive_letter, str) and len(drive_letter) == 1 and drive_letter.isalpha():
        return os.path.join(drive_letter.upper() + ":\\", item_name)
    # Handle common locations
    elif isinstance(drive_letter, str) and drive_letter.lower() in ["desktop", "documents", "downloads", "music", "pictures", "videos"]:
        user_folder = os.path.expanduser("~")
        return os.path.join(user_folder, drive_letter, item_name)
    # Handle relative paths
    else:
        return os.path.join(os.getcwd(), str(drive_letter), item_name)

def search_drive(drive, item_name, result_queue, stop_event, max_results=10, file_types=None):
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
            # Check if search is taking too long or interrupted
            if time.time() - start_time > max_search_time or (stop_event and stop_event.is_set()):
                print(f"Search on drive {drive} stopped - {'timeout' if not (stop_event and stop_event.is_set()) else 'interrupted'}")
                if drive_results:
                    drive_results.append(f"...search stopped on {drive}")
                break
            
            # Optimize search by skipping system directories
            dirs[:] = [d for d in dirs if not d.startswith('$') and d not in ['System Volume Information', 'Windows']]
            
            # Check directories
            for dir in dirs:
                # Check for interruption
                if stop_event and stop_event.is_set():
                    if drive_results:
                        drive_results.append(f"...search interrupted on {drive}")
                    return
                
                if search_term in dir.lower():
                    drive_results.append(os.path.join(root, dir))
                    count += 1
                    if count >= max_results:
                        drive_results.append(f"...and more results on {drive}")
                        result_queue.put((drive, drive_results))
                        return
            
            # Check files with optional file type filtering
            for file in files:
                # Check for interruption
                if stop_event and stop_event.is_set():
                    if drive_results:
                        drive_results.append(f"...search interrupted on {drive}")
                    return
                
                file_lower = file.lower()
                if search_term in file_lower:
                    # Apply file type filtering if specified
                    if file_types:
                        file_ext = os.path.splitext(file_lower)[1]
                        if file_ext and file_ext[1:] not in file_types:  # Remove the dot and compare
                            continue
                    
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

def search_progress_reporter(result_queue, total_drives, stop_event):
    """Report search progress while threads are working"""
    drives_completed = set()
    start_time = time.time()
    
    while len(drives_completed) < total_drives:
        # Break if search is taking too long (over 60 seconds) or interrupted
        if time.time() - start_time > 60 or (stop_event and stop_event.is_set()):
            print("Search stopped - " + ("timed out" if not (stop_event and stop_event.is_set()) else "interrupted"))
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

def find_item_across_drives(item_name, file_types=None, stop_event=None):
    """Search for an item across all available drives using parallel threads"""
    
    print(f"Searching for '{item_name}' across all drives...")
    speak(f"Searching for {item_name} across all drives. This might take a moment...")
    
    drives = get_available_drives()
    result_queue = queue.Queue()
    max_workers = min(len(drives), 4)  # Limit to 4 concurrent threads
    
    # Create thread pool
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit search tasks for each drive
        future_to_drive = {
            executor.submit(search_drive, drive, item_name, result_queue, stop_event, 10, file_types): drive
            for drive in drives
        }
        
        # Start a separate thread to provide progress updates to the user
        progress_thread = threading.Thread(target=search_progress_reporter, args=(result_queue, len(drives), stop_event))
        progress_thread.daemon = True
        progress_thread.start()
        
        # Wait for all futures to complete (with timeout) or until interrupted
        completed, _ = concurrent.futures.wait(
            future_to_drive, 
            timeout=60,
            return_when=concurrent.futures.FIRST_EXCEPTION
        )
        
        # Check for interruption
        if stop_event and stop_event.is_set():
            for future in future_to_drive:
                if not future.done():
                    future.cancel()
            speak("Search interrupted")
            return []
    
    # Collect results from the queue
    all_results = []
    while not result_queue.empty():
        drive, results = result_queue.get()
        all_results.extend(results)
    
    return all_results

def list_directory(directory_path, stop_event=None):
    """List contents of a directory"""
    
    try:
        # Check if execution should be interrupted
        if stop_event and stop_event.is_set():
            return False
            
        if not os.path.exists(directory_path):
            speak(f"The path {directory_path} does not exist")
            return False
        
        if not os.path.isdir(directory_path):
            speak(f"{directory_path} is not a directory")
            return False
        
        items = os.listdir(directory_path)
        
        # Separate files and folders
        folders = [item for item in items if os.path.isdir(os.path.join(directory_path, item))]
        files = [item for item in items if os.path.isfile(os.path.join(directory_path, item))]
        
        # Check for interruption before speaking results
        if stop_event and stop_event.is_set():
            return False
            
        # Report to user
        speak(f"Contents of {directory_path}:")
        if folders:
            speak(f"Found {len(folders)} folders")
            for i, folder in enumerate(folders[:5]):
                # Check for interruption between items
                if stop_event and stop_event.is_set():
                    return False
                speak(f"Folder {i+1}: {folder}")
            if len(folders) > 5:
                speak(f"And {len(folders) - 5} more folders")
        
        # Check for interruption before speaking about files
        if stop_event and stop_event.is_set():
            return False
            
        if files:
            speak(f"Found {len(files)} files")
            for i, file in enumerate(files[:5]):
                # Check for interruption between items
                if stop_event and stop_event.is_set():
                    return False
                speak(f"File {i+1}: {file}")
            if len(files) > 5:
                speak(f"And {len(files) - 5} more files")
        
        return True
    except PermissionError:
        speak(f"Permission denied when accessing {directory_path}")
        return False
    except Exception as e:
        logger.error(f"Error listing directory: {e}")
        speak(f"Error listing directory: {str(e)}")
        return False


def create_item(item_path, is_folder=True, stop_event=None):
    """Create a new folder or file at the specified path"""
    
    try:
        # Check if execution should be interrupted
        if stop_event and stop_event.is_set():
            return False
            
        # Check if item already exists
        if os.path.exists(item_path):
            speak(f"The item {os.path.basename(item_path)} already exists")
            return False
        
        if is_folder:
            os.makedirs(item_path)
            speak(f"Created folder {os.path.basename(item_path)}")
            return True
        else:
            # Create parent directories if they don't exist
            parent_dir = os.path.dirname(item_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir)
            
            # Create an empty file
            with open(item_path, 'w') as f:
                pass
            speak(f"Created file {os.path.basename(item_path)}")
            return True
            
    except PermissionError:
        speak(f"Permission denied when creating {os.path.basename(item_path)}")
        return False
    except Exception as e:
        logger.error(f"Error creating item: {e}")
        speak(f"Error creating item: {str(e)}")
        return False

def delete_item(item_path, stop_event=None):
    """Delete a file or folder at the specified path"""
    
    try:
        # Check if execution should be interrupted
        if stop_event and stop_event.is_set():
            return False
            
        # Check if item exists
        if not os.path.exists(item_path):
            # Try to find it in current directory
            found_path = find_item_in_current_directory(os.path.basename(item_path))
            if found_path:
                item_path = found_path
                print(f"Found item to delete at: {item_path}")
            else:
                speak(f"The item {os.path.basename(item_path)} does not exist")
                return False
        
        # Confirm deletion
        speak(f"Are you sure you want to delete {os.path.basename(item_path)}?")
        
        # Check for interruption before getting confirmation
        if stop_event and stop_event.is_set():
            return False
            
        confirmation = listen_command()
        
        # Check if user responded and no interruption
        if not confirmation or (stop_event and stop_event.is_set()):
            speak("Deletion cancelled")
            return False
            
        if any(word in confirmation.lower() for word in ["yes", "sure", "confirm", "delete"]):
            # Check for interruption before actual deletion
            if stop_event and stop_event.is_set():
                return False
                
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
                speak(f"Deleted folder {os.path.basename(item_path)} and all its contents")
            else:
                os.remove(item_path)
                speak(f"Deleted file {os.path.basename(item_path)}")
            return True
        else:
            speak("Deletion cancelled")
            return False
            
    except PermissionError:
        speak(f"Permission denied when deleting {os.path.basename(item_path)}")
        return False
    except Exception as e:
        logger.error(f"Error deleting item: {e}")
        speak(f"Error deleting item: {str(e)}")
        return False

def rename_item(old_path, new_name, stop_event=None):
    """Rename a file or folder"""
    
    try:
        # Check if execution should be interrupted
        if stop_event and stop_event.is_set():
            return False
            
        # Check if source exists
        if not os.path.exists(old_path):
            # Try to find it in current directory
            found_path = find_item_in_current_directory(os.path.basename(old_path))
            if found_path:
                old_path = found_path
                print(f"Found item to rename at: {old_path}")
            else:
                speak(f"The item {os.path.basename(old_path)} does not exist")
                return False
        
        # Create new path with the same directory but new name
        new_path = os.path.join(os.path.dirname(old_path), new_name)
        
        # Check if destination already exists
        if os.path.exists(new_path):
            speak(f"An item named {new_name} already exists at this location")
            return False
        
        # Check for interruption before renaming
        if stop_event and stop_event.is_set():
            return False
            
        # Rename the item
        os.rename(old_path, new_path)
        speak(f"Renamed {os.path.basename(old_path)} to {new_name}")
        return True
            
    except PermissionError:
        speak(f"Permission denied when renaming {os.path.basename(old_path)}")
        return False
    except Exception as e:
        logger.error(f"Error renaming item: {e}")
        speak(f"Error renaming item: {str(e)}")
        return False

def copy_item(source_path, dest_path, stop_event=None):
    """Copy a file or directory to the destination"""
    
    try:
        # Check if execution should be interrupted
        if stop_event and stop_event.is_set():
            return False, "Operation interrupted"
            
        # First, check if source exists
        if not os.path.exists(source_path):
            # Try to find the item in current directory
            found_path = find_item_in_current_directory(os.path.basename(source_path))
            if found_path:
                source_path = found_path
                print(f"Found item at: {source_path}")
            else:
                return False, f"Source {source_path} does not exist"
        
        # Check for interruption before starting copy
        if stop_event and stop_event.is_set():
            return False, "Operation interrupted"
            
        if os.path.isfile(source_path):
            # Create destination directory if it doesn't exist
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.copy2(source_path, dest_path)
            return True, f"Copied file {os.path.basename(source_path)}"
            
        elif os.path.isdir(source_path):
            # Check for interruption before copying directory
            if stop_event and stop_event.is_set():
                return False, "Operation interrupted"
                
            if os.path.exists(dest_path):
                # If destination exists, copy into it
                final_dest = os.path.join(dest_path, os.path.basename(source_path))
            else:
                final_dest = dest_path
                # Create parent directory if needed
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            
            # Use copytree with dirs_exist_ok=True for Python 3.8+
            try:
                # For directories, implement a custom copytree with interruption checks
                if stop_event:
                    # Custom directory copy with interruption checks
                    for root, dirs, files in os.walk(source_path):
                        if stop_event.is_set():
                            return False, "Operation interrupted"
                            
                        # Get relative path from source root
                        rel_path = os.path.relpath(root, source_path)
                        if rel_path == '.':
                            rel_path = ''
                            
                        # Create corresponding dir in destination
                        dest_dir = os.path.join(final_dest, rel_path)
                        os.makedirs(dest_dir, exist_ok=True)
                        
                        # Copy each file
                        for file in files:
                            if stop_event.is_set():
                                return False, "Operation interrupted"
                                
                            src_file = os.path.join(root, file)
                            dst_file = os.path.join(dest_dir, file)
                            shutil.copy2(src_file, dst_file)
                else:
                    # Standard copytree if no interruption needed
                    shutil.copytree(source_path, final_dest, dirs_exist_ok=True)
            except TypeError:
                # Fall back for older Python versions that don't have dirs_exist_ok
                if os.path.exists(final_dest):
                    shutil.rmtree(final_dest)
                shutil.copytree(source_path, final_dest)
                
            return True, f"Copied directory {os.path.basename(source_path)} with all contents"
        else:
            return False, f"Source {source_path} does not exist"
    except PermissionError:
        return False, f"Permission denied when copying {os.path.basename(source_path)}"
    except Exception as e:
        logger.error(f"Error during copy: {e}")
        return False, f"Error during copy: {str(e)}"

def move_item(source_path, dest_path, stop_event=None):
    """Move a file or directory to the destination"""
    
    try:
        # Check if execution should be interrupted
        if stop_event and stop_event.is_set():
            return False, "Operation interrupted"
            
        # First, check if source exists
        if not os.path.exists(source_path):
            # Try to find the item in current directory
            found_path = find_item_in_current_directory(os.path.basename(source_path))
            if found_path:
                source_path = found_path
                print(f"Found item at: {source_path}")
            else:
                return False, f"Source {source_path} does not exist"
        
        # For large directories, it's better to copy and then delete for interruptibility
        if os.path.isdir(source_path) and stop_event:
            # First copy
            copy_success, copy_message = copy_item(source_path, dest_path, stop_event)
            
            # Check if copy succeeded and wasn't interrupted
            if copy_success and not (stop_event and stop_event.is_set()):
                # Then delete original
                try:
                    shutil.rmtree(source_path)
                    return True, f"Moved directory {os.path.basename(source_path)} with all contents"
                except Exception as e:
                    # If delete fails, let the user know the copy succeeded but delete failed
                    logger.error(f"Error deleting source after copy: {e}")
                    return True, f"Copied directory {os.path.basename(source_path)} but couldn't remove the original"
            else:
                # If copy failed or was interrupted
                return copy_success, copy_message
        
        # For files or if no interruption needed, use standard move
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
        logger.error(f"Error during move: {e}")
        return False, f"Error during move: {str(e)}"

def list_directory(directory_path):
    """List contents of a directory"""
    global execution_stop_event
    
    try:
        # Check if execution should be interrupted
        if execution_stop_event.is_set():
            return False
            
        if not os.path.exists(directory_path):
            speak(f"The path {directory_path} does not exist")
            return False
        
        if not os.path.isdir(directory_path):
            speak(f"{directory_path} is not a directory")
            return False
        
        items = os.listdir(directory_path)
        
        # Separate files and folders
        folders = [item for item in items if os.path.isdir(os.path.join(directory_path, item))]
        files = [item for item in items if os.path.isfile(os.path.join(directory_path, item))]
        
        # Report to user
        speak(f"Contents of {directory_path}:")
        if folders:
            speak(f"Found {len(folders)} folders")
            for i, folder in enumerate(folders[:5]):
                speak(f"Folder {i+1}: {folder}")
            if len(folders) > 5:
                speak(f"And {len(folders) - 5} more folders")
        
        if files:
            speak(f"Found {len(files)} files")
            for i, file in enumerate(files[:5]):
                speak(f"File {i+1}: {file}")
            if len(files) > 5:
                speak(f"And {len(files) - 5} more files")
        
        return True
    except PermissionError:
        speak(f"Permission denied when accessing {directory_path}")
        return False
    except Exception as e:
        logger.error(f"Error listing directory: {e}")
        speak(f"Error listing directory: {str(e)}")
        return False
    
def smart_file_search(query, stop_event=None):
    """Enhanced search with LLM context understanding and prioritization"""
    
    try:
        # Check for interruption
        if stop_event and stop_event.is_set():
            return False
            
        # Use LLM to understand search intent
        prompt = f"""
        Analyze this file or document search query: "{query}"
        
        Extract the following information in JSON format:
        {{
            "search_terms": [list of key words or phrases to search for],
            "file_types": [list of file extensions without the dot, e.g. "pdf", "docx", null if no specific type],
            "time_period": "recent" or "old" or null if unspecified,
            "locations": [specific folders to search in, or null for everywhere],
            "content_hints": [words or phrases that might be IN the document, not just in filename],
            "explanation": [brief explanation of what the user is searching for]
        }}
        
        Return ONLY the JSON object without any additional text.
        """
        
        # Get LLM analysis
        response = gemini_model.generate_content(prompt)
        response_text = response.text
        
        # Check for interruption after LLM response
        if stop_event and stop_event.is_set():
            return False
            
        # Extract JSON
        if '```json' in response_text:
            json_str = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            json_str = response_text.split('```')[1].strip()
        else:
            json_str = response_text.strip()
        
        try:
            search_context = json.loads(json_str)
        except json.JSONDecodeError:
            # Fall back to simple search
            return search_files(query, None, stop_event)
        
        # Extract search parameters
        search_terms = search_context.get("search_terms", [query])
        if isinstance(search_terms, list) and search_terms:
            search_query = " ".join(search_terms)
        else:
            search_query = query
            
        file_types = search_context.get("file_types")
        locations = search_context.get("locations")
        explanation = search_context.get("explanation", f"Searching for {search_query}")
        
        # Inform user about the search
        speak(explanation)
        
        # Check for interruption before starting search
        if stop_event and stop_event.is_set():
            return False
            
        # Check if specific locations were mentioned
        if locations and isinstance(locations, list) and any(locations):
            # Search in specific locations
            results = []
            for location in locations:
                if location and not (stop_event and stop_event.is_set()):
                    try:
                        loc_path = resolve_path_with_llm(location, os.getcwd())
                        if os.path.exists(loc_path) and os.path.isdir(loc_path):
                            # Search just this location
                            for root, dirs, files in os.walk(loc_path):
                                # Skip system and hidden folders
                                dirs[:] = [d for d in dirs if not d.startswith('$') and not d.startswith('.')]
                                
                                # Check for interruption during search
                                if stop_event and stop_event.is_set():
                                    break
                                
                                # Check files
                                for file in files:
                                    if stop_event and stop_event.is_set():
                                        break
                                        
                                    file_path = os.path.join(root, file)
                                    file_lower = file.lower()
                                    
                                    # Check if file matches search terms
                                    if any(term.lower() in file_lower for term in search_terms):
                                        # Apply file type filter if specified
                                        if file_types:
                                            ext = os.path.splitext(file_lower)[1]
                                            if ext and ext[1:] in file_types:
                                                results.append(file_path)
                                        else:
                                            results.append(file_path)
                                            
                                    # Limit results
                                    if len(results) >= 20:
                                        break
                                        
                                if len(results) >= 20 or (stop_event and stop_event.is_set()):
                                    break
                    except Exception as e:
                        logger.error(f"Error searching location {location}: {e}")
            
            # Check for interruption after all locations searched
            if stop_event and stop_event.is_set():
                return False
                
            # If we found results in specific locations
            if results:
                return present_search_results(results, search_query, stop_event)
        
        # If no specific locations or no results found, search everywhere
        return search_files(search_query, file_types, stop_event)
            
    except Exception as e:
        logger.error(f"Error in smart search: {e}")
        # Fall back to simple search
        return search_files(query, None, stop_event)

def present_search_results(results, search_query, stop_event=None):
    """Present search results to the user with options to open them"""
    
    try:
        # Check if execution should be interrupted
        if stop_event and stop_event.is_set():
            return False
            
        # Filter out progress indicators
        actual_results = [loc for loc in results if isinstance(loc, str) and not loc.startswith("...")]
        
        if not actual_results:
            speak(f"No files found matching '{search_query}'")
            return False
        
        speak(f"Found {len(actual_results)} matching files or folders.")
        
        # Check for interruption
        if stop_event and stop_event.is_set():
            return False
            
        # Group results by drive or location for better organization
        location_summary = {}
        for loc in actual_results:
            base_dir = os.path.dirname(loc)
            parent_folder = os.path.basename(base_dir)
            drive = loc[:2]  # Get the drive letter (e.g., "C:")
            key = f"{drive} in {parent_folder}"
            
            if key in location_summary:
                location_summary[key] += 1
            else:
                location_summary[key] = 1
        
        # Provide a summary by location
        summary = "Files were found in: "
        summary += ", ".join([f"{count} in {loc}" for loc, count in location_summary.items()])
        speak(summary)
        
        # Check for interruption
        if stop_event and stop_event.is_set():
            return False
            
        # Display top 5 results
        speak("Here are the top results:")
        for i, result in enumerate(actual_results[:5]):
            # Check for interruption between result announcements
            if stop_event and stop_event.is_set():
                return False
                
            filename = os.path.basename(result)
            parent = os.path.basename(os.path.dirname(result))
            speak(f"{i+1}: {filename} in {parent}")
        
        # Check for interruption
        if stop_event and stop_event.is_set():
            return False
            
        # Ask user if they want to open any files
        speak("Would you like to open any of these files?")
        
        # Listen for response without exiting
        response = listen_command()
        
        # If no response or interrupted, just return without opening anything
        if not response or (stop_event and stop_event.is_set()):
            return True
        
        # Process response for file opening
        if "yes" in response.lower() or "sure" in response.lower() or "open" in response.lower():
            # Check for interruption
            if stop_event and stop_event.is_set():
                return False
                
            if "number" in response or any(str(i) in response for i in range(1, 6)):
                for i in range(1, 6):
                    if str(i) in response:
                        index = i - 1
                        if index < len(actual_results):
                            open_file(actual_results[index], stop_event)
                            speak(f"Opening {os.path.basename(actual_results[index])}")
                            return True
                        break
            else:
                # Open the first result by default
                open_file(actual_results[0], stop_event)
                speak(f"Opening {os.path.basename(actual_results[0])}")
                return True
        else:
            # User declined to open files
            speak("Okay, not opening any files.")
        
        # Return True regardless to prevent exiting
        return True
        
    except Exception as e:
        logger.error(f"Error presenting search results: {e}")
        speak("I encountered an error while showing the search results.")
        # Still return True to prevent exiting
        return True

def generate_file_help():
    """Generate helpful information about file commands using LLM"""
    try:
        # Get system context for better help
        available_drives = get_available_drives()
        user_directory = os.path.expanduser("~")
        current_directory = os.getcwd()
        
        prompt = f"""
        Generate a concise help guide about voice file commands for a Windows voice assistant.
        
        Context:
        - Current directory: {current_directory}
        - Available drives: {', '.join(available_drives)}
        - User directory: {user_directory}
        
        Include:
        1. Basic commands for finding, opening, creating, copying, moving and deleting files
        2. Examples of natural language commands that work well
        3. Tips for specifying file locations or types
        
        Format as a brief, helpful guide optimized for voice reading (bullet points, short sentences).
        Maximum 10 points total.
        """
        
        response = gemini_model.generate_content(prompt)
        help_text = response.text.strip()
        
        speak("Here's how you can work with files:")
        print(help_text)
        
        # Split the text into sentences or bullet points for better voice reading
        lines = help_text.split('\n')
        for line in lines:
            line = line.strip()
            if line and not execution_stop_event.is_set():
                # Remove bullet points and numbering for cleaner speech
                clean_line = re.sub(r'^[\d\-\*\•]+\.?\s*', '', line)
                if clean_line:
                    speak(clean_line)
                    # Small pause between points
                    time.sleep(0.2)
        
        return True
            
    except Exception as e:
        logger.error(f"Error generating file help: {e}")
        # Fall back to basic help
        speak("I can help you find, open, create, copy, move, rename, and delete files and folders. Just tell me what you'd like to do.")
        return False
#----------------------------------------
def web_search(query):
    """Search the web for general queries like weather, time, facts, etc."""
    try:
        # Check if any browser is already open and use it
        active_browser = is_browser_active()
        
        if active_browser:
            # Use existing browser
            success = search_in_browser(query, active_browser)
            if success:
                return True
        
        # If no browser is active or browser search failed, launch a new one
        print(f"🔍 Opening browser to search for: {query}")
        
        # Try to open default browser with the search query
        search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        webbrowser.open(search_url)
        speak(f"I've looked up {query} for you")
        return True
        
    except Exception as e:
        logger.error(f"Web search error: {e}")
        speak("I couldn't complete the web search")
        return False
    
def is_browser_active():
    """Check if a browser window is active and return its type"""
    active_window = get_active_window()
    if not active_window:
        return None

    # Check process name
    process_name = active_window["process_name"].lower()
    browser_processes = {
        "chrome.exe": "chrome", 
        "msedge.exe": "edge", 
        "firefox.exe": "firefox", 
        "brave.exe": "brave",
        "opera.exe": "opera",
        "iexplore.exe": "internet explorer"
    }
    
    if process_name in browser_processes:
        return browser_processes[process_name]
    
    # Backup check by window title for cases where the process name might be different
    window_title = active_window["title"].lower()
    browser_keywords = [
        "chrome", "firefox", "edge", "brave", "opera", "internet explorer", 
        "google", "bing", "yahoo", "duckduckgo"
    ]
    
    for keyword in browser_keywords:
        if keyword in window_title:
            # Return a generic "browser" if we can't determine which one
            return "browser"
    
    return None


def search_in_browser(query, browser_name=None):
    """Search for a query in the active browser or specified browser"""
    
    active_browser = browser_name if browser_name else is_browser_active()
    
    if active_browser is None:
        # No browser active, open default browser with search
        try:
            search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            webbrowser.open(search_url)
            speak(f"Searching for {query} in your default browser")
            return True
        except Exception as e:
            logger.error(f"Failed to open browser: {e}")
            speak("I couldn't open the browser")
            return False
    
    try:
        # Try to use the active browser window
        hwnd = get_active_window()["hwnd"]
        win32gui.SetForegroundWindow(hwnd)
        
        # Give the browser a moment to come into focus
        time.sleep(0.2)
        
        # Different browsers have different address bar keyboard shortcuts
        if active_browser == "firefox":
            pyautogui.hotkey('ctrl', 'l')  # Firefox address bar
        else:
            pyautogui.hotkey('alt', 'd')  # Works in Chrome, Edge, IE, many others
            
        # Clear any existing text
        pyautogui.hotkey('ctrl', 'a')
        
        # Wait a brief moment
        time.sleep(0.1)
        
        # Type the search query
        pyautogui.typewrite(query)
        pyautogui.press('enter')
        
        # Confirm to the user
        speak(f"Searching for {query} in {active_browser}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to search in browser: {e}")
        
        # Fall back to opening a new browser window
        try:
            search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            webbrowser.open(search_url)
            speak(f"Opened a new search for {query}")
            return True
        except:
            speak("I couldn't complete the search")
            return False

def media_play_pause():
    try:
        pyautogui.press('playpause')  # Presses the play/pause media key
        speak("Playing or pausing media")
    except Exception as e:
        logger.error(f"Failed to toggle play/pause: {e}")
        speak("Couldn't control media playback")

def media_next():
    try:
        pyautogui.press('nexttrack')  # Presses the next track media key
        speak("Playing next track")
    except Exception as e:
        logger.error(f"Failed to play next track: {e}")
        speak("Couldn't skip to the next track")

def media_previous():
    try:
        pyautogui.press('prevtrack')  # Presses the previous track media key
        speak("Playing previous track")
    except Exception as e:
        logger.error(f"Failed to play previous track: {e}")
        speak("Couldn't go back to the previous track")

def listen_command():
    """Listen for a command with improved stability"""
    recognizer = sr.Recognizer()
    
    # More conservative energy settings
    recognizer.energy_threshold = 3500  # Increased from 3000
    recognizer.dynamic_energy_threshold = True
    recognizer.dynamic_energy_adjustment_ratio = 1.2  # Reduced from 1.5
    
    # Longer pause threshold to better detect end of speech
    recognizer.pause_threshold = 1.2  # Increased from 0.8
    
    print("🎙️ Listening...")
    
    with sr.Microphone() as source:
        # More thorough ambient noise adjustment
        recognizer.adjust_for_ambient_noise(source, duration=1.0)  # Increased from 0.5
        
        try:
            # Longer timeout and no phrase time limit
            audio = recognizer.listen(
                source,
                timeout=15,  # Increased from 10
                phrase_time_limit=None  # No limit on phrase length
            )
        except sr.WaitTimeoutError:
            print("❌ Listening timed out.")
            return None

    try:
        print("Processing speech...")
        text = recognizer.recognize_google(audio).lower()
        print(f"🗣️ Recognized: {text}")
        system_command_history.append(text)
        return text
    except sr.UnknownValueError:
        print("❌ Couldn't understand.")
        return None
    except sr.RequestError:
        print("❌ Google STT service unavailable.")
        time.sleep(1)  # Wait a moment after an error
        return None

# background listening funvtion
# At the top of your file with other imports
# pip install pvporcupine

# Then replace background_listen with a version using Porcupine
def background_listen():
    """Continuously listen for wake word in the background with improved stability"""
    global command_manager
    recognizer = sr.Recognizer()
    
    # Reduce sensitivity to avoid false activations
    recognizer.energy_threshold = 2500  # Increased threshold
    recognizer.dynamic_energy_threshold = True
    recognizer.dynamic_energy_adjustment_ratio = 1.5  # Reduced from 2.5
    recognizer.pause_threshold = 1.0  # Increased from 0.6
    
    print("🔸 Assistant started and running in standby mode - listening for wake word 'hey dodo'...")
    
    last_adjustment_time = 0
    last_activation_time = 0
    cooldown_period = 2  # 2 second cooldown between activations
    
    while True:
        with sr.Microphone() as source:
            current_time = time.time()
            
            # Only adjust for ambient noise periodically
            if current_time - last_adjustment_time > 120:  # Adjust every 2 minutes instead of 1
                print("Adjusting for ambient noise...")
                recognizer.adjust_for_ambient_noise(source, duration=1.0)  # Longer duration
                print("Ready for wake word detection")
                last_adjustment_time = current_time
            
            try:
                # Use a longer timeout and phrase time limit
                audio = recognizer.listen(source, timeout=1, phrase_time_limit=2.0)  # Increased from 1.2
                
                # Prevent rapid re-activation
                if current_time - last_activation_time < cooldown_period:
                    continue
                    
                try:
                    text = recognizer.recognize_google(audio).lower()
                    
                    # Check if the wake word is in the recognized text
                    if WAKE_WORD in text:
                        last_activation_time = current_time
                        print(f"🔔 Wake word '{WAKE_WORD}' detected!")
                        
                        # Check if there's a command execution in progress using the command manager
                        if command_manager.is_command_running():
                            print("Interrupting current execution...")
                            command_manager.stop_current_command()
                            speak("Yes, I'm listening")
                        else:
                            print("=" * 40)
                            print(f"      ACTIVATED - Voice Command Mode      ")
                            print("=" * 40)
                            speak("Yes?")
                        
                        process_commands_after_wake_word()
                        print("=" * 40)
                        print(f"      STANDBY MODE - Listening for '{WAKE_WORD}'  ")
                        print("=" * 40)
                except sr.UnknownValueError:
                    pass
                except sr.RequestError:
                    logger.error("Google STT service unavailable")
                    time.sleep(3)  # Longer pause on error
            except sr.WaitTimeoutError:
                pass
        
        time.sleep(0.05)  # Slightly longer sleep to reduce CPU usage

def enhanced_wake_word_detection():
    """Use dedicated keyword spotting for more efficient wake word detection"""
    global command_manager
    
    # Initialize Porcupine for wake word detection
    try:
        porcupine = pvporcupine.create(keywords=["dodo"])
        pa = pyaudio.PyAudio()
        
        audio_stream = pa.open(
            rate=porcupine.sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=porcupine.frame_length
        )
        
        print("🔸 Assistant started and running in standby mode - listening for wake word 'hey dodo'...")
        
        last_activation_time = 0
        cooldown_period = 2  # 2 second cooldown between activations
        
        while True:
            # Read audio frame from microphone
            pcm = audio_stream.read(porcupine.frame_length)
            pcm = struct.unpack_from("h" * porcupine.frame_length, pcm)
            
            # Process the audio frame
            keyword_index = porcupine.process(pcm)
            current_time = time.time()
            
            # If wake word detected and not in cooldown period
            if keyword_index >= 0 and current_time - last_activation_time > cooldown_period:
                last_activation_time = current_time
                print(f"🔔 Wake word 'hey dodo' detected!")
                
                # Check if there's a command execution in progress
                if command_manager.is_command_running():
                    print("Interrupting current execution...")
                    command_manager.stop_current_command()
                    speak("Yes, I'm listening")
                else:
                    print("=" * 40)
                    print(f"      ACTIVATED - Voice Command Mode      ")
                    print("=" * 40)
                    speak("Yes?")
                    
                process_commands_after_wake_word()
                print("=" * 40)
                print(f"      STANDBY MODE - Listening for 'hey dodo'  ")
                print("=" * 40)
                
            # Small delay to reduce CPU usage
            time.sleep(0.01)
    
    except Exception as e:
        logger.error(f"Wake word detection error: {e}")
        # Fall back to standard speech recognition if Porcupine fails
        print("Falling back to standard speech recognition due to error:", e)
        background_listen()
    finally:
        # Clean up resources when exiting
        if 'porcupine' in locals():
            porcupine.delete()
        if 'audio_stream' in locals():
            audio_stream.close()
        if 'pa' in locals():
            pa.terminate()

# ✅ Show Help Function
def show_help():
    help_text = """
    Here are some things you can say:
    - "Open [application name]"
    - "Close [application name]"
    - "Volume up/down/mute"
    - "Brightness up/down"
    - "Shutdown, restart, lock, sleep"
    - "Calculate [math operation]"
    - "Take a screenshot"
    - "Check/send email"
    - "Create, move, copy, delete, rename files and folders"
    - "Add/list/delete calendar events"
    - "Help"
    - "Exit"
    """
    speak("Here are some things I can help you with:")
    print(help_text)
    speak("I can control your applications, manage files, adjust system settings, and much more.")

# ✅ Calendar and Reminder Management
def handle_calendar(command):
    """Enhanced calendar function with LLM understanding and better event management"""
    global execution_stop_event
    command = command.lower()
    
    # Define calendar file path - store in user's documents folder for better accessibility
    user_docs = os.path.join(os.path.expanduser("~"), "Documents")
    calendar_dir = os.path.join(user_docs, "DodoAssistant")
    calendar_file = os.path.join(calendar_dir, "calendar.json")
    
    # Create directory if it doesn't exist
    if not os.path.exists(calendar_dir):
        os.makedirs(calendar_dir)
    
    # Load existing events
    events = []
    if os.path.exists(calendar_file):
        try:
            with open(calendar_file, "r") as f:
                events = json.load(f)
        except Exception as e:
            logger.error(f"Error loading calendar file: {e}")
            events = []
    
    # Use LLM to understand calendar intent
    try:
        prompt = f"""
        As a voice assistant managing calendar events, analyze this command: "{command}"
        
        Extract the following information in JSON format:
        {{
            "intent": "add" or "list" or "delete" or "update" or "find" or "unknown",
            "event_title": the title/subject of the event (null if not applicable),
            "date": the event date in YYYY-MM-DD format (null if not applicable),
            "time": the event time (null if not applicable),
            "duration": the event duration (null if not applicable),
            "description": additional details about the event (null if not applicable),
            "index": the event number if referencing a specific event (null if not applicable),
            "explanation": brief explanation of what the user wants to do
        }}
        
        Return ONLY the JSON object without any additional text.
        """
        
        response = gemini_model.generate_content(prompt)
        response_text = response.text
        
        # Extract JSON
        if '```json' in response_text:
            json_str = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            json_str = response_text.split('```')[1].strip()
        else:
            json_str = response_text.strip()
        
        calendar_intent = json.loads(json_str)
        print(f"Calendar intent: {calendar_intent}")
        
        intent = calendar_intent.get("intent", "unknown")
        event_title = calendar_intent.get("event_title")
        event_date = calendar_intent.get("date")
        event_time = calendar_intent.get("time")
        event_duration = calendar_intent.get("duration")
        event_description = calendar_intent.get("description")
        event_index = calendar_intent.get("index")
        
        # ADD EVENT
        if intent == "add" or intent == "create":
            # If we're missing critical information, ask for it
            if not event_title:
                speak("What's the title of your event?")
                event_title = listen_command()
                if not event_title or execution_stop_event.is_set():
                    speak("Event creation cancelled")
                    return False
            
            if not event_date:
                speak("When is this event? Please specify a date.")
                date_response = listen_command()
                if not date_response or execution_stop_event.is_set():
                    speak("Event creation cancelled")
                    return False
                
                # Use LLM to parse the date
                date_prompt = f'Convert this date description "{date_response}" to YYYY-MM-DD format. Return ONLY the date without any explanation.'
                date_response = gemini_model.generate_content(date_prompt)
                event_date = date_response.text.strip()
            
            if not event_time and "time" not in command.lower():
                speak("What time is this event?")
                event_time = listen_command()
                if not event_time or execution_stop_event.is_set():
                    # If user doesn't specify time, that's okay
                    event_time = "all day"
            
            # Create the event
            new_event = {
                "title": event_title,
                "date": event_date,
                "time": event_time if event_time else "all day",
                "duration": event_duration if event_duration else "1 hour",
                "description": event_description if event_description else "",
                "created": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # Add to events list
            events.append(new_event)
            
            # Save updated events
            with open(calendar_file, "w") as f:
                json.dump(events, f, indent=2)
            
            speak(f"Added event: {event_title} on {event_date} at {new_event['time']}")
            return True
        
        # LIST EVENTS
        elif intent == "list" or intent == "show":
            if not events:
                speak("You have no scheduled events.")
                return True
            
            # Sort events by date
            sorted_events = sorted(events, key=lambda e: e.get("date", "9999-99-99"))
            
            # Filter by date if specified
            if event_date:
                filtered_events = [e for e in sorted_events if e.get("date") == event_date]
                speak(f"Events on {event_date}:")
            else:
                filtered_events = sorted_events
                speak(f"You have {len(filtered_events)} upcoming events:")
            
            # Handle no events after filtering
            if not filtered_events:
                speak(f"No events found{' on ' + event_date if event_date else ''}.")
                return True
            
            # List events
            for i, event in enumerate(filtered_events[:5]):
                event_info = f"{i+1}: {event['title']} on {event['date']} at {event['time']}"
                if event.get("description"):
                    event_info += f". {event['description']}"
                speak(event_info)
            
            # Mention if there are more events
            if len(filtered_events) > 5:
                speak(f"And {len(filtered_events) - 5} more events.")
            
            return True
        
        # DELETE EVENT
        elif intent == "delete" or intent == "remove":
            if not events:
                speak("You have no scheduled events to delete.")
                return True
            
            if event_title:
                # Find events matching the title
                matching_events = [i for i, e in enumerate(events) if event_title.lower() in e['title'].lower()]
                
                if not matching_events:
                    speak(f"No events found with title '{event_title}'.")
                    return True
                
                if len(matching_events) == 1:
                    # Only one match, delete it
                    index = matching_events[0]
                    deleted_event = events.pop(index)
                    with open(calendar_file, "w") as f:
                        json.dump(events, f, indent=2)
                    speak(f"Deleted event: {deleted_event['title']} on {deleted_event['date']}")
                    return True
                
                # Multiple matches, list them and ask which to delete
                speak(f"Found {len(matching_events)} matching events:")
                for i, idx in enumerate(matching_events[:5]):
                    speak(f"{i+1}: {events[idx]['title']} on {events[idx]['date']}")
                
                speak("Which event would you like to delete? Please say the number.")
                number_response = listen_command()
                
                if not number_response or execution_stop_event.is_set():
                    speak("Deletion cancelled")
                    return False
                
                try:
                    selected = int(number_response.strip(",.")) - 1
                    if 0 <= selected < len(matching_events[:5]):
                        index_to_delete = matching_events[selected]
                        deleted_event = events.pop(index_to_delete)
                        with open(calendar_file, "w") as f:
                            json.dump(events, f, indent=2)
                        speak(f"Deleted event: {deleted_event['title']} on {deleted_event['date']}")
                        return True
                    else:
                        speak("Invalid selection. Deletion cancelled.")
                        return False
                except ValueError:
                    speak("I didn't understand which event to delete.")
                    return False
            
            # If no specific event title given, list all events
            elif event_index is not None:
                # Convert index to zero-based
                index = int(event_index) - 1
                if 0 <= index < len(events):
                    deleted_event = events.pop(index)
                    with open(calendar_file, "w") as f:
                        json.dump(events, f, indent=2)
                    speak(f"Deleted event: {deleted_event['title']} on {deleted_event['date']}")
                    return True
                else:
                    speak("Invalid event number.")
                    return False
            else:
                # No specific event, show all and ask which to delete
                speak("Which event would you like to delete? Here are your events:")
                sorted_events = sorted(events, key=lambda e: e.get("date", "9999-99-99"))
                for i, event in enumerate(sorted_events[:5]):
                    speak(f"{i+1}: {event['title']} on {event['date']}")
                
                if len(sorted_events) > 5:
                    speak(f"And {len(sorted_events) - 5} more events.")
                
                speak("Please say the number of the event to delete.")
                number_response = listen_command()
                
                if not number_response or execution_stop_event.is_set():
                    speak("Deletion cancelled")
                    return False
                
                try:
                    selected = int(number_response.strip(",.")) - 1
                    if 0 <= selected < len(sorted_events[:5]):
                        # Find this event in the original list
                        event_to_delete = sorted_events[selected]
                        for i, event in enumerate(events):
                            if (event['title'] == event_to_delete['title'] and 
                                event['date'] == event_to_delete['date']):
                                deleted_event = events.pop(i)
                                with open(calendar_file, "w") as f:
                                    json.dump(events, f, indent=2)
                                speak(f"Deleted event: {deleted_event['title']} on {deleted_event['date']}")
                                return True
                    else:
                        speak("Invalid selection. Deletion cancelled.")
                        return False
                except ValueError:
                    speak("I didn't understand which event to delete.")
                    return False
        
        # FIND EVENTS
        elif intent == "find" or intent == "search":
            if not events:
                speak("You have no scheduled events.")
                return True
            
            search_term = event_title.lower() if event_title else ""
            if not search_term and "what" in command and "today" in command:
                # Handle "what's on today" type queries
                today = time.strftime("%Y-%m-%d")
                filtered_events = [e for e in events if e.get("date") == today]
                
                if filtered_events:
                    speak(f"You have {len(filtered_events)} events today:")
                    for i, event in enumerate(filtered_events):
                        speak(f"{i+1}: {event['title']} at {event['time']}")
                else:
                    speak("You have no events scheduled for today.")
                return True
                
            if not search_term:
                speak("What would you like to search for in your calendar?")
                search_term = listen_command()
                if not search_term or execution_stop_event.is_set():
                    speak("Search cancelled")
                    return False
                search_term = search_term.lower()
            
            # Search for matching events
            matching_events = []
            for event in events:
                if (search_term in event['title'].lower() or 
                    (event.get('description') and search_term in event['description'].lower())):
                    matching_events.append(event)
            
            if matching_events:
                speak(f"Found {len(matching_events)} matching events:")
                for i, event in enumerate(matching_events[:5]):
                    speak(f"{i+1}: {event['title']} on {event['date']} at {event['time']}")
                
                if len(matching_events) > 5:
                    speak(f"And {len(matching_events) - 5} more events.")
            else:
                speak(f"No events found matching '{search_term}'.")
            
            return True
            
        # UPDATE EVENT
        elif intent == "update" or intent == "edit":
            if not events:
                speak("You have no scheduled events to update.")
                return True
            
            # First identify which event to update
            if event_title:
                # Find events matching the title
                matching_events = [i for i, e in enumerate(events) if event_title.lower() in e['title'].lower()]
                
                if not matching_events:
                    speak(f"No events found with title '{event_title}'.")
                    return True
                
                if len(matching_events) == 1:
                    # Only one match
                    index = matching_events[0]
                else:
                    # Multiple matches, ask which one
                    speak(f"Found {len(matching_events)} matching events:")
                    for i, idx in enumerate(matching_events[:5]):
                        speak(f"{i+1}: {events[idx]['title']} on {events[idx]['date']}")
                    
                    speak("Which event would you like to update? Please say the number.")
                    number_response = listen_command()
                    
                    if not number_response or execution_stop_event.is_set():
                        speak("Update cancelled")
                        return False
                    
                    try:
                        selected = int(number_response.strip(",.")) - 1
                        if 0 <= selected < len(matching_events[:5]):
                            index = matching_events[selected]
                        else:
                            speak("Invalid selection. Update cancelled.")
                            return False
                    except ValueError:
                        speak("I didn't understand which event to update.")
                        return False
            else:
                # No specific event, show all and ask which to update
                speak("Which event would you like to update? Here are your events:")
                sorted_events = sorted(events, key=lambda e: e.get("date", "9999-99-99"))
                for i, event in enumerate(sorted_events[:5]):
                    speak(f"{i+1}: {event['title']} on {event['date']}")
                
                if len(sorted_events) > 5:
                    speak(f"And {len(sorted_events) - 5} more events.")
                
                speak("Please say the number of the event to update.")
                number_response = listen_command()
                
                if not number_response or execution_stop_event.is_set():
                    speak("Update cancelled")
                    return False
                
                try:
                    selected = int(number_response.strip(",.")) - 1
                    if 0 <= selected < len(sorted_events[:5]):
                        # Find this event in the original list
                        event_to_update = sorted_events[selected]
                        for i, event in enumerate(events):
                            if (event['title'] == event_to_update['title'] and 
                                event['date'] == event_to_update['date']):
                                index = i
                                break
                    else:
                        speak("Invalid selection. Update cancelled.")
                        return False
                except ValueError:
                    speak("I didn't understand which event to update.")
                    return False
            
            # Now update the event
            event_to_update = events[index]
            speak(f"Updating event: {event_to_update['title']} on {event_to_update['date']}")
            
            # Ask what to update
            speak("What would you like to change? You can say title, date, time, or description.")
            update_field = listen_command()
            
            if not update_field or execution_stop_event.is_set():
                speak("Update cancelled")
                return False
            
            if "title" in update_field.lower():
                speak("What's the new title?")
                new_value = listen_command()
                if new_value and not execution_stop_event.is_set():
                    events[index]['title'] = new_value
                    speak(f"Updated title to: {new_value}")
            
            elif "date" in update_field.lower():
                speak("What's the new date?")
                date_response = listen_command()
                if date_response and not execution_stop_event.is_set():
                    # Use LLM to parse the date
                    date_prompt = f'Convert this date description "{date_response}" to YYYY-MM-DD format. Return ONLY the date without any explanation.'
                    date_response = gemini_model.generate_content(date_prompt)
                    new_date = date_response.text.strip()
                    events[index]['date'] = new_date
                    speak(f"Updated date to: {new_date}")
            
            elif "time" in update_field.lower():
                speak("What's the new time?")
                new_value = listen_command()
                if new_value and not execution_stop_event.is_set():
                    events[index]['time'] = new_value
                    speak(f"Updated time to: {new_value}")
            
            elif "description" in update_field.lower():
                speak("What's the new description?")
                new_value = listen_command()
                if new_value and not execution_stop_event.is_set():
                    events[index]['description'] = new_value
                    speak(f"Updated description to: {new_value}")
            
            # Save updated events
            with open(calendar_file, "w") as f:
                json.dump(events, f, indent=2)
            
            speak("Event updated successfully")
            return True
        
        # Unknown calendar intent
        else:
            speak("I'm not sure what you want to do with your calendar. You can add, list, delete, or update events.")
            return False
            
    except Exception as e:
        logger.error(f"Calendar operation error: {e}")
        speak("I encountered an error managing your calendar.")
        return False
# Listening process command
def process_commands_after_wake_word():
    """Process commands after wake word with improved stability"""
    global command_manager
    active = True
    last_command_time = time.time()
    print("Waiting for command...")
    
    # Give a short moment after activation before listening
    time.sleep(0.5)

    while active:
        command = listen_command()
        current_time = time.time()
        
        if command:
            # Reset the timer when a command is received
            last_command_time = current_time
            
            if "exit" in command or "goodbye" in command or "bye" in command or "stop listening" in command:
                speak("Going back to standby mode")
                active = False
                continue
            
            # Process the command using the command manager
            process_single_command(command)
            
            # Give a short pause after processing a command
            time.sleep(0.5)
        
        # Increase timeout to 30 seconds
        elif current_time - last_command_time > 30:
            print("⏰ No further commands detected - returning to standby mode")
            speak("Going back to standby mode")
            active = False
        
        # Small delay to prevent high CPU usage
        time.sleep(0.1)


# Create a new function to wrap command execution in a thread
def execute_command_with_interrupt(command):
    """Execute a command in a separate thread that can be interrupted"""
    global current_execution, execution_stop_event
    
    def execution_thread():
        try:
            # Check for interruption periodically
            if execution_stop_event.is_set():
                print("Command execution was interrupted")
                return
                
            # Use LLM for intent analysis
            intent_data = analyze_with_llm(command)
            
            # Execute the identified intent
            success = False
            if intent_data["intent"] != "unknown":
                success = execute_intent(intent_data)
                
                # If the LLM-based execution was successful, we're done
                if success:
                    return
            
            # If LLM couldn't determine intent or execution failed
            # Just inform the user instead of falling back to rule-based processing
            if intent_data["intent"] == "unknown":
                speak("I'm not sure what you're asking me to do. Could you try rephrasing that?")
            else:
                speak("I understood what you want, but couldn't complete the action. Please try again.")
                
        except Exception as e:
            logger.error(f"Command processing error: {e}")
            speak("I encountered an error. Please try again.")
        
        finally:
            # Clear the current execution when done
            current_execution = None
    
    # Create and start the thread
    thread = threading.Thread(target=execution_thread)
    current_execution = thread
    thread.start()
    
    return thread

# Update process_single_command to use the new threaded execution
def process_single_command(command):
    """Process a single command with LLM intent recognition and interruptible execution"""
    global command_manager
    
    try:
        # For direct commands that don't need intent analysis
        if "exit" in command or "goodbye" in command or "bye" in command or "stop listening" in command:
            speak("Going back to standby mode")
            return False
        
        if "help" in command:
            show_help()
            return True
        
        if "file help" in command or "help with files" in command or "how to use files" in command:
            generate_file_help()
            return True
            
        # Check if it's an explicit search command
        if command.lower().startswith("search for") or command.lower().startswith("find"):
            # Execute command using the command manager
            command_manager.execute_command(command)
            return True
            
        # Check if it's an explicit web question
        if command.lower().startswith("what") or command.lower().startswith("who") or \
           command.lower().startswith("when") or command.lower().startswith("where") or \
           command.lower().startswith("why") or command.lower().startswith("how") or \
           "weather" in command.lower() or "time" in command.lower():
            # Treat this as an explicit web search
            speak(f"I'll look that up for you.")
            web_search(command)
            return True
        
        # Execute command normally using the command manager for everything else
        command_manager.execute_command(command)
        return True
        
    except Exception as e:
        logger.error(f"Command processing error: {e}")
        speak("I encountered an error. Please try again.")
        return False
    
# ✅ Setup and Start the Assistant
def setup_assistant():
    """Setup and initialize the assistant"""
    global command_manager
    
    # Initialize the command manager
    command_manager = CommandManager()
    
    # Setup audio control
    setup_audio_control()
    speak("Assistant initialized and running in the background. Say wake word to activate.")
    
    # Start background listening
    background_thread = threading.Thread(target=background_listen, daemon=True)
    background_thread.start()
    
    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Assistant terminated by user")

def create_system_tray():
    """Create a system tray icon for the assistant"""
    # Create a simple icon (consider replacing with a proper icon file)
    icon_data = Image.new('RGB', (64, 64), color = (255, 0, 0))
    
    def on_exit(icon):
        icon.stop()
        # Use os._exit to force exit all threads
        os._exit(0)
    
    menu = pystray.Menu(
        pystray.MenuItem('Exit', on_exit)
    )
    
    icon = pystray.Icon("assistant", icon_data, "Voice Assistant", menu)
    return icon

# Add this to the main section
if __name__ == "__main__":
    # Start the assistant in a separate thread
    assistant_thread = threading.Thread(target=setup_assistant, daemon=True)
    assistant_thread.start()
    
    # Create and run the system tray in the main thread
    icon = create_system_tray()
    icon.run()
