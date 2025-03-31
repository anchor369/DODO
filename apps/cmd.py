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
WAKE_WORD = "hey assistant"

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
        "spotify": "C:\\Program Files\\Spotify\\Spotify.exe",
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

# ✅ Close Applications (Improved Handling)
# def close_application(command):
#     command = command.lower()
#     app_name = command.replace("close", "").strip()
    
#     if app_name in open_apps:
#         try:
#             open_apps[app_name].terminate()
#             del open_apps[app_name]
#             speak(f"Closed {app_name}")
#             return True
#         except Exception as e:
#             logger.error(f"Failed to close {app_name}: {e}")
    
#     for proc in psutil.process_iter(['pid', 'name']):
#         try:
#             process_name = proc.info['name'].lower()
#             if app_name in process_name or process_name in app_name:
#                 proc.terminate()
#                 speak(f"Closed {app_name}")
#                 return True
#         except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
#             pass
    
#     window_handles = []
#     def enum_windows_callback(hwnd, results):
#         if win32gui.IsWindowVisible(hwnd):
#             window_title = win32gui.GetWindowText(hwnd).lower()
#             if app_name in window_title:
#                 results.append(hwnd)
    
#     win32gui.EnumWindows(enum_windows_callback, window_handles)
    
#     if window_handles:
#         for hwnd in window_handles:
#             try:
#                 win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
#                 speak(f"Closed {app_name}")
#                 return True
#             except:
#                 pass
    
#     speak(f"I couldn't find {app_name} running")
#     return False

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


# ✅ Handle Maximize, Minimize, Restore Commands
def handle_window_commands(command):
    active_window = get_active_window()
    if not active_window:
        speak("No active window detected.")
        return

    hwnd = active_window["hwnd"]
    
    if "maximize" in command:
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            speak("Maximized window.")
        except Exception as e:
            logger.error(f"Failed to maximize window: {e}")
            speak("I couldn't maximize the window.")
    
    elif "minimize" in command:
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            speak("Minimized window.")
        except Exception as e:
            logger.error(f"Failed to minimize window: {e}")
            speak("I couldn't minimize the window.")
    
    elif "restore" in command or "unminimize" in command:
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            speak("Restored window.")
        except Exception as e:
            logger.error(f"Failed to restore window: {e}")
            speak("I couldn't restore the window.")

# ✅ Handle Calculator Commands (Improved Handling)
def handle_calculator_command(command):
    active_window = get_active_window()
    if not active_window or "calc" not in active_window["process_name"]:
        speak("Calculator is not the active window.")
        return

    hwnd = active_window["hwnd"]
    try:
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.5)
        
        expression = command.replace("calculate", "").strip()
        expression = expression.replace("plus", "+").replace("minus", "-").replace("times", "*").replace("divided by", "/").replace("equals", "")
        
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


# ✅ Process Command with Error Handling
def process_command():
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
                
                elif "maximize" in command or "minimize" in command or "restore" in command:
                    handle_window_commands(command)
                
                elif any(word in command for word in ["volume", "brightness", "shutdown", "restart", "lock", "sleep"]):
                    system_control(command)
                
                elif "email" in command:
                    handle_email(command)
                
                elif "screenshot" in command:
                    system_control(command)
                
                elif any(word in command for word in ["file", "folder", "move", "copy", "delete", "rename", "search"]):
                    handle_files(command)
                
                elif any(word in command for word in ["calendar", "schedule", "event", "reminder"]):
                    handle_calendar(command)
                
                elif "help" in command:
                    show_help()
                
                else:
                    speak("I didn't understand that command. Please try again.")
        
        except Exception as e:
            logger.error(f"Command processing error: {e}")
            speak("I encountered an error. Please try again.")
            continue

# ✅ Listen to Voice Command
def listen_command():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("🎙️ Listening...")
        recognizer.adjust_for_ambient_noise(source)
        try:
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=5)
        except sr.WaitTimeoutError:
            return None

    try:
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

# ✅ Setup and Start the Assistant
def setup_assistant():
    setup_audio_control()
    speak("Hello, I am your assistant. How can I assist you?")
    process_command()

# ✅ Start the Assistant
if __name__ == "__main__":
    setup_assistant()
