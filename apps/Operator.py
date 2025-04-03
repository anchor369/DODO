import os
import time
import threading
import speech_recognition as sr
import pyttsx3
import pyautogui
import pytesseract
import numpy as np
import cv2
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk, scrolledtext
import queue
import json
import logging
import google.generativeai as genai

# Issue with this, need to install tesseract manually in pc, need to add the file path (find something to automate).

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ScreenAIAssistant:
    def __init__(self, api_key=None):
        self.capturing = False
        self.listening = False
        self.capture_interval = 5  # seconds
        self.last_capture = None
        self.current_app_context = None
        self.message_queue = queue.Queue()
        
        # Initialize OCR
        pytesseract.pytesseract.tesseract_cmd = r'tesseract'  # Update path if needed
        
        # Initialize speech engine
        self.speech_recognizer = sr.Recognizer()
        self.speech_engine = pyttsx3.init()
        
        # Initialize AI (Gemini)
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Setup UI
        self.setup_ui()
    
    def setup_ui(self):
        self.root = tk.Tk()
        self.root.title("Screen AI Assistant")
        self.root.geometry("800x600")
        
        # Create main frame
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Control frame
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=10)
        
        # Capture button
        self.capture_btn = ttk.Button(control_frame, text="Start Capture", command=self.toggle_capture)
        self.capture_btn.pack(side=tk.LEFT, padx=5)
        
        # Voice button
        self.voice_btn = ttk.Button(control_frame, text="Start Listening", command=self.toggle_listening)
        self.voice_btn.pack(side=tk.LEFT, padx=5)
        
        # Capture interval settings
        ttk.Label(control_frame, text="Capture Interval (s):").pack(side=tk.LEFT, padx=5)
        self.interval_var = tk.StringVar(value=str(self.capture_interval))
        interval_entry = ttk.Entry(control_frame, textvariable=self.interval_var, width=5)
        interval_entry.pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Set", command=self.update_interval).pack(side=tk.LEFT, padx=5)
        
        # Status label
        self.status_var = tk.StringVar(value="Status: Idle")
        status_label = ttk.Label(control_frame, textvariable=self.status_var)
        status_label.pack(side=tk.RIGHT, padx=5)
        
        # Create notebook for tabs
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Create tabs
        captured_tab = ttk.Frame(notebook)
        analysis_tab = ttk.Frame(notebook)
        settings_tab = ttk.Frame(notebook)
        
        notebook.add(captured_tab, text="Captured Content")
        notebook.add(analysis_tab, text="AI Analysis")
        notebook.add(settings_tab, text="Settings")
        
        # Captured Content Tab
        self.capture_frame = ttk.Frame(captured_tab)
        self.capture_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.capture_display = ttk.Label(self.capture_frame, text="No capture yet")
        self.capture_display.pack(fill=tk.BOTH, expand=True)
        
        # OCR Text Display
        self.ocr_text = scrolledtext.ScrolledText(captured_tab, wrap=tk.WORD, height=10)
        self.ocr_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # AI Analysis Tab
        self.ai_output = scrolledtext.ScrolledText(analysis_tab, wrap=tk.WORD)
        self.ai_output.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Manual query frame
        query_frame = ttk.Frame(analysis_tab)
        query_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(query_frame, text="Ask AI:").pack(side=tk.LEFT, padx=5)
        self.query_var = tk.StringVar()
        query_entry = ttk.Entry(query_frame, textvariable=self.query_var, width=50)
        query_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(query_frame, text="Ask", command=self.send_manual_query).pack(side=tk.LEFT, padx=5)
        
        # Settings Tab
        settings_frame = ttk.Frame(settings_tab, padding=10)
        settings_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(settings_frame, text="Gemini API Key:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.api_key_var = tk.StringVar(value=self.api_key or "")
        api_key_entry = ttk.Entry(settings_frame, textvariable=self.api_key_var, width=40)
        api_key_entry.grid(row=0, column=1, sticky=tk.W, pady=5)
        ttk.Button(settings_frame, text="Save", command=self.save_settings).grid(row=0, column=2, padx=5)
        
        # Model selection
        ttk.Label(settings_frame, text="Gemini Model:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.model_var = tk.StringVar(value="gemini-2.0-flash")
        model_combo = ttk.Combobox(settings_frame, textvariable=self.model_var, width=20)
        model_combo['values'] = ('gemini-2.0-flash', 'gemini-2.0-pro')
        model_combo.grid(row=1, column=1, sticky=tk.W, pady=5)
        
        # Voice settings
        ttk.Label(settings_frame, text="Voice Settings:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.voice_enabled_var = tk.BooleanVar(value=True)
        voice_cb = ttk.Checkbutton(settings_frame, text="Enable Voice Responses", variable=self.voice_enabled_var)
        voice_cb.grid(row=2, column=1, sticky=tk.W, pady=5)
        
        # OCR settings
        ttk.Label(settings_frame, text="Tesseract Path:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.tesseract_var = tk.StringVar(value=pytesseract.pytesseract.tesseract_cmd)
        tesseract_entry = ttk.Entry(settings_frame, textvariable=self.tesseract_var, width=40)
        tesseract_entry.grid(row=3, column=1, sticky=tk.W, pady=5)
        
        # Start message processing thread
        self.processing_thread = threading.Thread(target=self.process_messages, daemon=True)
        self.processing_thread.start()
        
        # Set up periodic UI updates
        self.root.after(100, self.update_ui)
    
    def update_ui(self):
        """Update UI elements periodically"""
        # Update status based on current state
        if self.capturing and self.listening:
            status = "Capturing and Listening"
        elif self.capturing:
            status = "Capturing Only"
        elif self.listening:
            status = "Listening Only"
        else:
            status = "Idle"
        
        self.status_var.set(f"Status: {status}")
        
        # Schedule next update
        self.root.after(100, self.update_ui)
    
    def toggle_capture(self):
        """Toggle screen capture on/off"""
        self.capturing = not self.capturing
        
        if self.capturing:
            self.capture_btn.config(text="Stop Capture")
            self.capture_thread = threading.Thread(target=self.capture_loop, daemon=True)
            self.capture_thread.start()
        else:
            self.capture_btn.config(text="Start Capture")
    
    def toggle_listening(self):
        """Toggle voice listening on/off"""
        self.listening = not self.listening
        
        if self.listening:
            self.voice_btn.config(text="Stop Listening")
            self.listening_thread = threading.Thread(target=self.listen_loop, daemon=True)
            self.listening_thread.start()
        else:
            self.voice_btn.config(text="Start Listening")
    
    def update_interval(self):
        """Update the capture interval"""
        try:
            new_interval = float(self.interval_var.get())
            if new_interval > 0:
                self.capture_interval = new_interval
                logger.info(f"Capture interval updated to {new_interval} seconds")
            else:
                logger.warning("Interval must be greater than 0")
        except ValueError:
            logger.error("Invalid interval value")
    
    def save_settings(self):
        """Save API key and other settings"""
        self.api_key = self.api_key_var.get().strip()
        model_name = self.model_var.get()
        tesseract_path = self.tesseract_var.get().strip()
        
        # Update Tesseract path if specified
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
            logger.info(f"Tesseract path updated to: {tesseract_path}")
        
        # Update Gemini API settings
        if self.api_key:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel(model_name)
                logger.info(f"API key and model ({model_name}) updated")
            except Exception as e:
                logger.error(f"Error configuring Gemini API: {e}")
        else:
            logger.warning("No API key provided")
    
    def send_manual_query(self):
        """Send a manual query to the AI"""
        query = self.query_var.get().strip()
        if query:
            self.message_queue.put(("query", query))
            self.query_var.set("")
    
    def capture_loop(self):
        """Main loop for screen capture"""
        while self.capturing:
            try:
                # Capture screen
                screenshot = pyautogui.screenshot()
                self.last_capture = screenshot
                
                # Convert to OpenCV format for processing
                screenshot_np = np.array(screenshot)
                screenshot_cv = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)
                
                # Display thumbnail in UI (resize for display)
                height, width = screenshot_cv.shape[:2]
                max_size = 300
                scale = max_size / max(height, width)
                new_width, new_height = int(width * scale), int(height * scale)
                
                screenshot_resized = cv2.resize(screenshot_cv, (new_width, new_height))
                
                # Convert back to PIL for tkinter display
                img_pil = Image.fromarray(cv2.cvtColor(screenshot_resized, cv2.COLOR_BGR2RGB))
                
                # Use ImageTk to convert PIL image to Tkinter-compatible format
                img_tk = ImageTk.PhotoImage(img_pil)
                
                # Update image in UI from the main thread
                self.root.after(0, lambda: self.update_capture_display(img_tk))
                
                # Perform OCR
                try:
                    ocr_text = pytesseract.image_to_string(screenshot)
                    logger.info("OCR completed successfully")
                except Exception as ocr_error:
                    ocr_text = "OCR Error: Could not extract text from image"
                    logger.error(f"OCR error: {ocr_error}")
                
                # Identify active application context
                context = self.identify_context(ocr_text)
                
                # Process the captured data
                self.message_queue.put(("capture", {
                    "ocr_text": ocr_text,
                    "context": context,
                    "timestamp": time.time()
                }))
                
                # Wait for next capture
                time.sleep(self.capture_interval)
                
            except Exception as e:
                logger.error(f"Capture error: {e}")
                time.sleep(1)  # Wait before retrying
    
    def update_capture_display(self, img_tk):
        """Update the capture display with the latest screenshot thumbnail"""
        try:
            self.capture_display.configure(image=img_tk)
            self.capture_display.image = img_tk  # Keep a reference to prevent garbage collection
        except Exception as e:
            logger.error(f"Error updating display: {e}")
    
    def listen_loop(self):
        """Main loop for voice recognition"""
        while self.listening:
            try:
                with sr.Microphone() as source:
                    logger.info("Listening for voice commands...")
                    self.speech_recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    audio = self.speech_recognizer.listen(source, timeout=5, phrase_time_limit=10)
                
                try:
                    text = self.speech_recognizer.recognize_google(audio)
                    logger.info(f"Recognized: {text}")
                    
                    # Process voice command
                    self.message_queue.put(("voice", text))
                    
                except sr.UnknownValueError:
                    logger.info("Voice not understood")
                except sr.RequestError as e:
                    logger.error(f"Voice recognition error: {e}")
                    
            except Exception as e:
                logger.error(f"Listening error: {e}")
            
            time.sleep(0.1)
    
    def identify_context(self, ocr_text):
        """Identify the current application context from OCR text"""
        contexts = {
            "leetcode": ["leetcode", "problem", "solution", "runtime", "memory"],
            "file_explorer": ["file", "folder", "directory", "drive", "properties"],
            "browser": ["http", "https", "www", "search", "browser"],
            "code_editor": ["def", "function", "class", "import", "variable"]
        }
        
        ocr_lower = ocr_text.lower()
        detected_context = "unknown"
        max_matches = 0
        
        for context, keywords in contexts.items():
            matches = sum(1 for keyword in keywords if keyword in ocr_lower)
            if matches > max_matches:
                max_matches = matches
                detected_context = context
        
        if max_matches > 0:
            return detected_context
        return "unknown"
    
    def process_messages(self):
        """Process messages from the message queue"""
        while True:
            try:
                message_type, message_data = self.message_queue.get(timeout=1)
                
                if message_type == "capture":
                    self.process_capture_data(message_data)
                elif message_type == "voice":
                    self.process_voice_command(message_data)
                elif message_type == "query":
                    self.process_text_query(message_data)
                
                self.message_queue.task_done()
                
            except queue.Empty:
                pass
            except Exception as e:
                logger.error(f"Message processing error: {e}")
            
            time.sleep(0.1)
    
    def process_capture_data(self, data):
        """Process captured screen data"""
        ocr_text = data["ocr_text"]
        context = data["context"]
        
        # Update UI with OCR text
        self.root.after(0, lambda: self.update_ocr_text(ocr_text))
        
        # Update context if it has changed
        if context != self.current_app_context:
            self.current_app_context = context
            logger.info(f"Context changed to: {context}")
            
            # Generate initial AI analysis for the new context
            self.analyze_current_context()
    
    def update_ocr_text(self, text):
        """Update the OCR text display"""
        self.ocr_text.delete(1.0, tk.END)
        self.ocr_text.insert(tk.END, text)
    
    def process_voice_command(self, command):
        """Process a voice command"""
        # Simple keyword-based command processing
        command_lower = command.lower()
        
        if "capture" in command_lower and "screen" in command_lower:
            if not self.capturing:
                self.root.after(0, self.toggle_capture)
        
        elif "stop" in command_lower and "capture" in command_lower:
            if self.capturing:
                self.root.after(0, self.toggle_capture)
        
        elif "analyze" in command_lower or "explain" in command_lower:
            self.analyze_current_context(additional_query=command)
        
        else:
            # Treat as a general query about the current screen
            self.process_text_query(command)
    
    def process_text_query(self, query):
        """Process a text query to the AI using Gemini"""
        if not self.api_key:
            self.root.after(0, lambda: self.update_ai_output("API key is not set. Please add your Gemini API key in Settings."))
            return
        
        if not self.last_capture:
            self.root.after(0, lambda: self.update_ai_output("No screen capture available. Start capture first."))
            return
        
        try:
            # Get the most recent OCR text
            ocr_text = ""
            try:
                ocr_text = self.ocr_text.get(1.0, tk.END)
            except:
                pass
            
            # Prepare prompt for Gemini
            prompt = f"""
            Context: The user is looking at a screen with the following content:
            {ocr_text[:4000]}  # Limit text size
            
            The detected application context is: {self.current_app_context}
            
            User query: {query}
            
            Please analyze the screen content and provide a helpful response to the user's query.
            Focus on the relevant information from the screen and answer the specific question.
            """
            
            # Call Gemini API
            try:
                generation_config = {
                    "temperature": 0.7,
                    "top_p": 0.95,
                    "max_output_tokens": 1024,
                }
                
                response = self.model.generate_content(
                    prompt,
                    generation_config=generation_config
                )
                
                ai_response = response.text.strip()
                
                # Update UI with AI response
                self.root.after(0, lambda: self.update_ai_output(ai_response))
                
                # Speak response if voice is enabled
                if self.voice_enabled_var.get():
                    self.speak_text(ai_response)
                    
            except Exception as e:
                error_message = f"Gemini API error: {str(e)}"
                logger.error(error_message)
                self.root.after(0, lambda: self.update_ai_output(error_message))
                
        except Exception as e:
            error_message = f"AI processing error: {str(e)}"
            logger.error(error_message)
            self.root.after(0, lambda: self.update_ai_output(error_message))
    
    def analyze_current_context(self, additional_query=None):
        """Analyze the current screen context"""
        if additional_query:
            query = f"Please analyze what's on my screen and {additional_query}"
        else:
            query = "Please analyze what's on my screen and explain what I'm looking at."
            
        self.process_text_query(query)
    
    def update_ai_output(self, text):
        """Update the AI output display"""
        # Clear previous output
        self.ai_output.delete(1.0, tk.END)
        
        # Add timestamp
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        self.ai_output.insert(tk.END, f"[{timestamp}]\n\n")
        
        # Add AI response
        self.ai_output.insert(tk.END, text)
        
        # Scroll to the end
        self.ai_output.see(tk.END)
    
    def speak_text(self, text):
        """Convert text to speech"""
        try:
            # Limit text length for speech
            if len(text) > 500:
                text = text[:497] + "..."
                
            # Speak in a separate thread to avoid UI freezing
            def speak_thread():
                self.speech_engine.say(text)
                self.speech_engine.runAndWait()
                
            threading.Thread(target=speak_thread, daemon=True).start()
        except Exception as e:
            logger.error(f"Speech error: {e}")
    
    def run(self):
        """Run the application"""
        self.root.mainloop()


if __name__ == "__main__":
    # Set default Gemini API key
    default_api_key = "AIzaSyCK6YT332KT79i2JvgJ6Jjes76R2I1Dtk8"
    
    # Create and run application
    app = ScreenAIAssistant(api_key=default_api_key)
    app.run()