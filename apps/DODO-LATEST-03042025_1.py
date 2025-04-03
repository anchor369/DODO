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

# ✅ Initialize TTS Engine
engine = pyttsx3.init()
voices = engine.getProperty('voices')
engine.setProperty('voice', voices[1].id)
engine.setProperty('rate', 180)

# ✅ Wake Word
WAKE_WORD = "dodo"

# ✅ Global Variables
open_apps = {}
app_paths_cache = {}
system_volume = None
system_command_history = []

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
def handle_files(command):
    command = command.lower()
    
    try:
        if "find" in command or "search" in command:
            search_term = command.replace("find", "").replace("search", "").strip()
            search_files(search_term)
        
        elif "move" in command:
            speak("What file or folder would you like to move?")
            source = input("Enter source path: ")
            speak("Where would you like to move it to?")
            destination = input("Enter destination path: ")
            
            if os.path.exists(source):
                shutil.move(source, destination)
                speak(f"Moved {os.path.basename(source)} to {destination}")
            else:
                speak(f"Source {source} not found")
        
        elif "copy" in command:
            speak("What file or folder would you like to copy?")
            source = input("Enter source path: ")
            speak("Where would you like to copy it to?")
            destination = input("Enter destination path: ")
            
            if os.path.exists(source):
                if os.path.isdir(source):
                    shutil.copytree(source, destination)
                else:
                    shutil.copy2(source, destination)
                speak(f"Copied {os.path.basename(source)} to {destination}")
            else:
                speak(f"Source {source} not found")
        
        elif "rename" in command:
            speak("What file or folder would you like to rename?")
            source = input("Enter file/folder path: ")
            speak("What is the new name?")
            new_name = input("Enter new name: ")
            
            if os.path.exists(source):
                os.rename(source, os.path.join(os.path.dirname(source), new_name))
                speak(f"Renamed to {new_name}")
            else:
                speak(f"File or folder {source} not found")
        
        elif "delete" in command:
            speak("What file or folder would you like to delete?")
            source = input("Enter file/folder path: ")
            
            if os.path.exists(source):
                confirm = input(f"Are you sure you want to delete {os.path.basename(source)}? (yes/no): ")
                if confirm.lower() in ['yes', 'y']:
                    if os.path.isdir(source):
                        shutil.rmtree(source)
                    else:
                        os.remove(source)
                    speak(f"Deleted {os.path.basename(source)}")
                else:
                    speak("Delete operation cancelled")
            else:
                speak(f"File or folder {source} not found")
        
        elif "create" in command and "folder" in command:
            speak("Where would you like to create a new folder?")
            folder_path = input("Enter folder path: ")
            os.makedirs(folder_path, exist_ok=True)
            speak(f"Created folder at {folder_path}")
        
        elif "open" in command:
            speak("What file or folder would you like to open?")
            source = input("Enter file/folder path: ")
            if os.path.exists(source):
                os.startfile(source)
                speak(f"Opened {os.path.basename(source)}")
            else:
                speak(f"File or folder {source} not found")
        
        else:
            speak("I'm not sure what file operation you want to perform")
    
    except Exception as e:
        logger.error(f"File handling error: {e}")
        speak("I encountered an error handling your file operation.")

# ✅ Search Files
def search_files(search_term):
    speak(f"Searching for {search_term}")
    results = []
    start_path = os.path.expanduser("~")
    speak("Searching in your user directory. This might take a moment.")
    
    for root, dirs, files in os.walk(start_path):
        for file in files:
            if search_term.lower() in file.lower():
                file_path = os.path.join(root, file)
                results.append(file_path)
                if len(results) >= 10:  # Limit results to avoid overwhelming
                    break
        if len(results) >= 10:
            break
    
    if results:
        speak(f"Found {len(results)} matching files. Here are the top results:")
        for i, result in enumerate(results[:5]):
            speak(f"{i+1}: {os.path.basename(result)}")
        
        speak("Would you like to open any of these files?")
        response = listen_command()
        
        if response and any(x in response.lower() for x in ["yes", "sure", "open"]):
            if "number" in response or any(str(i) in response for i in range(1, 6)):
                for i in range(1, 6):
                    if str(i) in response:
                        index = i - 1
                        if index < len(results):
                            os.startfile(results[index])
                            speak(f"Opening {os.path.basename(results[index])}")
                        break
            else:
                os.startfile(results[0])
                speak(f"Opening {os.path.basename(results[0])}")
    else:
        speak(f"No files found matching '{search_term}'")


def is_browser_active():
    active_window = get_active_window()
    if not active_window:
        return None

    process_name = active_window["process_name"]
    browser_processes = ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"]
    
    if process_name in browser_processes:
        return process_name
    return None


def search_in_browser(query, browser_name=None):
    active_browser = is_browser_active() if not browser_name else browser_name

    if active_browser is None:
        speak("No browser is active. Performing a local search.")
        search_files(query)  # Fallback to local search
        return
    
    try:
        hwnd = get_active_window()["hwnd"]
        win32gui.SetForegroundWindow(hwnd)
        pyautogui.hotkey('ctrl', 'l')  # Focus address bar
        time.sleep(0.2)
        pyautogui.typewrite(query)
        pyautogui.press('enter')
        speak(f"Searching for {query} on {active_browser}.")
    except Exception as e:
        logger.error(f"Failed to search on browser: {e}")
        speak("Couldn't complete the search.")


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
    """Listen for a command with continuous listening while speech is detected"""
    recognizer = sr.Recognizer()
    # Use the same noise handling settings as in background_listen
    recognizer.energy_threshold = 3000
    recognizer.dynamic_energy_threshold = True
    recognizer.dynamic_energy_adjustment_ratio = 1.5
    
    # Set the pause threshold before calling listen()
    recognizer.pause_threshold = 0.8  # Shorter pause to detect end of speech
    
    print("🎙️ Listening...")
    
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        
        # Remove the incorrect parameter
        try:
            audio = recognizer.listen(
                source,
                timeout=10,  # Longer timeout
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
        print("❌ Google STT Error.")
        return None

def background_listen():
    """Continuously listen for wake word in the background"""
    recognizer = sr.Recognizer()
    # Lower energy threshold for better trigger sensitivity
    recognizer.energy_threshold = 2000  # Lower from 3000
    recognizer.dynamic_energy_threshold = True
    recognizer.dynamic_energy_adjustment_ratio = 2.0  # Increased from 1.5
    
    # Set a shorter pause threshold to detect shorter wake word
    recognizer.pause_threshold = 1  # Shorter for the wake word "dodo"
    
    print("🔸 Assistant started and running in standby mode - listening for wake word 'dodo'...")
    
    last_adjustment_time = 0
    
    while True:
        with sr.Microphone() as source:
            # Adjust for ambient noise more frequently
            current_time = time.time()
            if current_time - last_adjustment_time > 30:  # Every 30 seconds
                print("Adjusting for ambient noise...")
                recognizer.adjust_for_ambient_noise(source, duration=1.0)
                print("Ready for wake word detection")
                last_adjustment_time = current_time
            
            try:
                # Use a shorter phrase time limit since "dodo" is a short wake word
                audio = recognizer.listen(source, timeout=1, phrase_time_limit=2)
                try:
                    text = recognizer.recognize_google(audio).lower()
                    
                    # More flexible wake word detection with word boundaries
                    if WAKE_WORD in text.split():
                        print(f"🔔 Wake word '{WAKE_WORD}' detected!")
                        # Visual feedback
                        print("=" * 40)
                        print(f"      ACTIVATED - Voice Command Mode      ")
                        print("=" * 40)
                        
                        # Audio feedback
                        speak("Yes?")
                        process_commands_after_wake_word()
                        
                        # Visual feedback when returning to standby
                        print("=" * 40)
                        print("      STANDBY MODE - Listening for 'dodo'  ")
                        print("=" * 40)
                except sr.UnknownValueError:
                    # Silent pass
                    pass
                except sr.RequestError:
                    logger.error("Google STT service unavailable")
                    time.sleep(3)  # Reduced wait time
            except sr.WaitTimeoutError:
                # Silent pass
                pass
        
        # Add a very small sleep to reduce CPU usage but keep responsive
        time.sleep(0.05)

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
    command = command.lower()
    
    calendar_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), "calendar.json")
    
    events = []
    if os.path.exists(calendar_file):
        try:
            with open(calendar_file, "r") as f:
                events = json.load(f)
        except:
            events = []
    
    if "add" in command or "create" in command:
        speak("What's the title of your event?")
        title = listen_command()
        
        speak("When is this event?")
        datetime_str = listen_command()
        
        try:
            event = {
                "title": title,
                "date": datetime_str,
                "created": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            
            events.append(event)
            with open(calendar_file, "w") as f:
                json.dump(events, f)
            
            speak(f"Added event: {title}")
        
        except Exception as e:
            logger.error(f"Calendar entry error: {e}")
            speak("I had trouble understanding the date and time")
    
    elif "list" in command:
        if events:
            speak(f"You have {len(events)} events.")
            for i, event in enumerate(events[:5]):
                speak(f"{i+1}: {event['title']} on {event['date']}")
        else:
            speak("You have no scheduled events.")
    
    elif "delete" in command:
        if events:
            speak("Which event would you like to delete? Please say the number.")
            for i, event in enumerate(events):
                speak(f"{i+1}: {event['title']} on {event['date']}")
            
            response = listen_command()
            try:
                index = int(response) - 1
                if 0 <= index < len(events):
                    deleted_event = events.pop(index)
                    with open(calendar_file, "w") as f:
                        json.dump(events, f)
                    speak(f"Deleted event: {deleted_event['title']}")
                else:
                    speak("I couldn't find that event.")
            except:
                speak("I didn't understand which event to delete.")
        else:
            speak("You have no scheduled events to delete.")

# Listening process command

def process_commands_after_wake_word():
    """Process commands after wake word and handle timeout"""
    active = True
    last_command_time = time.time()
    print("Waiting for command...")

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
            
            # Process the command using existing function with slight modification
            process_single_command(command)
        
        # Check if 5 seconds have passed without a command
        elif current_time - last_command_time > 5:
            print("⏰ No further commands detected - returning to standby mode")
            speak("Going back to standby mode")
            active = False
        
        # Small delay to prevent high CPU usage
        time.sleep(0.1)

# ✅ Process Command with Error Handling

def process_single_command(command):
    """Process a single command without the while loop"""
    try:
        if "open" in command:
            open_application(command)
        
        elif "close" in command:
            close_application(command)
        
        elif "calculate" in command:
            handle_calculator_command(command)
        
        elif "maximize" in command or "maximise" in command or "minimize" in command or "minimise" in command or "restore" in command:
            handle_window_commands(command)
        
        elif any(word in command for word in ["volume", "brightness", "shutdown", "restart", "lock", "sleep"]):
            system_control(command)
                
        elif "email" in command:
            handle_email(command)
                
        elif "screenshot" in command:
            system_control(command)
                
        elif any(word in command for word in ["file", "folder", "move", "copy", "delete", "rename"]):
            handle_files(command)
                
        elif any(word in command for word in ["calendar", "schedule", "event", "reminder"]):
            handle_calendar(command)
                
        elif "help" in command:
            show_help()

        elif any(word in command for word in ["play", "pause", "next", "previous", "track", "music", "media", "spotify", "song"]):
            if "next" in command:
                media_next()
            elif "previous" in command or "back" in command or "last" in command:
                media_previous()
            else:  # Default to play/pause for any other media command
                media_play_pause()

        elif "search" in command:
            search_query = command.replace("search", "").strip()

            # Check if user specified a browser
            if "on edge" in command:
                search_in_browser(search_query, browser_name="msedge.exe")
            elif "on chrome" in command:
                search_in_browser(search_query, browser_name="chrome.exe")
            elif "on firefox" in command:
                search_in_browser(search_query, browser_name="firefox.exe")
            elif "on brave" in command:
                search_in_browser(search_query, browser_name="brave.exe")
            else:
                # If no browser specified, check if a browser is currently active
                search_in_browser(search_query)
        
        else:
            speak("I didn't understand that command. Please try again.")
    
    except Exception as e:
        logger.error(f"Command processing error: {e}")
        speak("I encountered an error. Please try again.")


def process_command_old():
    while True:
        try:
            command = listen_command()
            if command:
                if "exit" in command or "goodbye" in command or "bye" in command:
                    speak("Exiting assistant mode. Say the wake word to activate me again.")
                    break
                
                if "open" in command:
                    open_application(command)
                
                elif "close" in command:
                    close_application(command)
                
                elif "calculate" in command:
                    handle_calculator_command(command)
                
                elif "maximize" in command or "maximise" in command or "minimize" in command or "minimise" in command or "restore" in command:
                    handle_window_commands(command)
                
                elif any(word in command for word in ["volume", "brightness", "shutdown", "restart", "lock", "sleep"]):
                    system_control(command)
                
                elif "email" in command:
                    handle_email(command)
                
                elif "screenshot" in command:
                    system_control(command)
                
                elif any(word in command for word in ["file", "folder", "move", "copy", "delete", "rename"]):
                    handle_files(command)
                
                elif any(word in command for word in ["calendar", "schedule", "event", "reminder"]):
                    handle_calendar(command)
                
                elif "help" in command:
                    show_help()

                elif any(word in command for word in ["play", "pause", "next", "previous", "track", "music", "media", "spotify", "song"]):
                    if "next" in command:
                        media_next()
                    elif "previous" in command or "back" in command or "last" in command:
                        media_previous()
                    else:  # Default to play/pause for any other media command
                        media_play_pause()

                elif "search" in command:
                    search_query = command.replace("search", "").strip()

                    # Check if user specified a browser
                    if "on edge" in command:
                        search_in_browser(search_query, browser_name="msedge.exe")
                    elif "on chrome" in command:
                        search_in_browser(search_query, browser_name="chrome.exe")
                    elif "on firefox" in command:
                        search_in_browser(search_query, browser_name="firefox.exe")
                    elif "on brave" in command:
                        search_in_browser(search_query, browser_name="brave.exe")
                    else:
                        # If no browser specified, check if a browser is currently active
                        search_in_browser(search_query)

                else:
                    speak("I didn't understand that command. Please try again.")
        
        except Exception as e:
            logger.error(f"Command processing error: {e}")
            speak("I encountered an error. Please try again.")
            continue


# ✅ Setup and Start the Assistant
def setup_assistant():
    """Setup and initialize the assistant"""
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
