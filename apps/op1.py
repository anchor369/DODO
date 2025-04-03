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
import re

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
        
        # Conversation tracking
        self.conversation_history = []
        self.current_context = {
            "screen_understood": False,
            "current_question": None,
            "question_understood": False,
            "awaiting_approach": False,
            "last_ocr_text": "",
            "question_type": None  # coding, math, text, etc.
        }
        
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
        chat_tab = ttk.Frame(notebook)
        settings_tab = ttk.Frame(notebook)
        
        notebook.add(captured_tab, text="Captured Content")
        notebook.add(analysis_tab, text="AI Analysis")
        notebook.add(chat_tab, text="Chat History")
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
        
        # Chat History Tab
        self.chat_history = scrolledtext.ScrolledText(chat_tab, wrap=tk.WORD)
        self.chat_history.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.chat_history.tag_config('user', foreground='blue')
        self.chat_history.tag_config('assistant', foreground='green')
        
        # Quick command buttons
        command_frame = ttk.Frame(chat_tab)
        command_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(command_frame, text="What's this question?", 
                  command=lambda: self.send_manual_query("What is the question or problem on my screen?")).pack(side=tk.LEFT, padx=5)
        ttk.Button(command_frame, text="Give me an approach", 
                  command=lambda: self.send_manual_query("What would be a good approach to solve this problem?")).pack(side=tk.LEFT, padx=5)
        ttk.Button(command_frame, text="Clear Chat", 
                  command=self.clear_chat_history).pack(side=tk.RIGHT, padx=5)
        
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
        
        # Conversation flow settings
        ttk.Label(settings_frame, text="Conversation Flow:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.flow_enabled_var = tk.BooleanVar(value=True)
        flow_cb = ttk.Checkbutton(settings_frame, text="Enable Smart Conversation", variable=self.flow_enabled_var)
        flow_cb.grid(row=4, column=1, sticky=tk.W, pady=5)
        
        # Start message processing thread
        self.processing_thread = threading.Thread(target=self.process_messages, daemon=True)
        self.processing_thread.start()
        
        # Set up periodic UI updates
        self.root.after(100, self.update_ui)
    
    def clear_chat_history(self):
        """Clear the chat history"""
        self.chat_history.delete(1.0, tk.END)
        self.conversation_history = []
        # Reset context
        self.current_context = {
            "screen_understood": False,
            "current_question": None,
            "question_understood": False,
            "awaiting_approach": False,
            "last_ocr_text": "",
            "question_type": None
        }
    
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
    
    def send_manual_query(self, predefined_query=None):
        """Send a manual query to the AI"""
        query = predefined_query or self.query_var.get().strip()
        if query:
            # Add to chat history
            self.add_to_chat_history("User", query)
            
            # Process the query
            self.message_queue.put(("query", query))
            self.query_var.set("")
    
    def add_to_chat_history(self, speaker, message):
        """Add a message to the chat history with formatting"""
        self.chat_history.config(state=tk.NORMAL)
        
        # Add timestamp
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        self.chat_history.insert(tk.END, f"[{timestamp}] ", "timestamp")
        
        # Add speaker and message with appropriate tag
        tag = 'user' if speaker == "User" else 'assistant'
        self.chat_history.insert(tk.END, f"{speaker}: ", tag)
        self.chat_history.insert(tk.END, f"{message}\n\n")
        
        # Scroll to the end
        self.chat_history.see(tk.END)
        
        # Store in conversation history
        self.conversation_history.append({
            "role": "user" if speaker == "User" else "assistant",
            "content": message,
            "timestamp": timestamp
        })
    
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
                    self.current_context["last_ocr_text"] = ocr_text
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
                    
                    # Add to chat history
                    self.root.after(0, lambda t=text: self.add_to_chat_history("User", t))
                    
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
            
            # When context changes, reset some conversation state
            self.current_context["screen_understood"] = False
            
            # Generate initial AI analysis for the new context
            self.analyze_current_context()
    
    def update_ocr_text(self, text):
        """Update the OCR text display"""
        self.ocr_text.delete(1.0, tk.END)
        self.ocr_text.insert(tk.END, text)
        
    def detect_query_intent(self, command):
        """Detect the user's intent from their query"""
        command_lower = command.lower()
        
        # Question about what's on screen
        if any(phrase in command_lower for phrase in [
            "what is this", "what am i looking at", "what's on my screen", 
            "explain this", "analyze this"
        ]):
            return "analyze_screen"
            
        # Question about the problem/question
        elif any(phrase in command_lower for phrase in [
            "what is the question", "what is the problem", "what am i supposed to do",
            "what's the task", "what's being asked"
        ]):
            return "identify_question"
            
        # Request for approach/solution
        elif any(phrase in command_lower for phrase in [
            "how do i solve this", "what's the approach", "how would you solve this",
            "give me a solution", "help me solve this", "what should i do"
        ]):
            return "provide_approach"
            
        # Question about specific part of problem
        elif any(phrase in command_lower for phrase in [
            "what does this mean", "explain this part", "i don't understand this",
            "clarify this", "what is this asking for"
        ]):
            return "explain_part"
            
        # Default: treat as general query
        return "general_query"
    
    def process_voice_command(self, command):
        """Process a voice command with contextual awareness"""
        # Detect user intent
        intent = self.detect_query_intent(command)
        
        if "capture" in command.lower() and "screen" in command.lower():
            if not self.capturing:
                self.root.after(0, self.toggle_capture)
                return
        
        elif "stop" in command.lower() and "capture" in command.lower():
            if self.capturing:
                self.root.after(0, self.toggle_capture)
                return
        
        # Handle intents with conversation flow if enabled
        if self.flow_enabled_var.get():
            if intent == "analyze_screen":
                self.analyze_current_context(additional_query=command)
                self.current_context["screen_understood"] = True
                return
                
            elif intent == "identify_question":
                self.identify_question_from_screen()
                return
                
            elif intent == "provide_approach":
                self.provide_solution_approach()
                return
                
            elif intent == "explain_part":
                # Extract what part needs explanation if possible
                part_to_explain = command.lower().replace("what does", "").replace("explain", "").replace("clarify", "").strip()
                self.explain_specific_part(part_to_explain)
                return
        
        # Default: treat as general query if no specific flow matched
        self.process_text_query(command)
    
    def identify_question_from_screen(self):
        """Identify and explain the main question or problem on screen"""
        if not self.last_capture:
            response = "No screen capture available. Start capture first."
            self.root.after(0, lambda: self.update_ai_output(response))
            self.root.after(0, lambda: self.add_to_chat_history("Assistant", response))
            return
            
        # Get the most recent OCR text
        ocr_text = self.current_context["last_ocr_text"]
        
        # Special prompt for identifying the main question
        prompt = f"""
        You are an assistant helping to identify the main question or problem from a screen capture.
        
        SCREEN CONTENT:
        {ocr_text[:10000]}
        
        APPLICATION CONTEXT: {self.current_app_context}
        
        TASK:
        Identify and clearly state what the main question or problem is from the screen content.
        Focus specifically on extracting the core question or task that needs to be solved.
        
        RESPONSE GUIDELINES:
        - Start with "The question is:" or "The problem asks:"
        - Be direct and clear about what needs to be done
        - Include any relevant constraints or requirements
        - Avoid unnecessary explanations - just identify the question/problem
        - Use simple language suitable for speech
        - If you can't identify a clear question or problem, say so directly
        """
        
        # Process with AI
        try:
            generation_config = {
                "temperature": 0.3,  # Lower temperature for more focused responses on question identification
                "top_p": 0.85,
                "max_output_tokens": 1024,  # Shorter response for question identification
            }
            
            response = self.model.generate_content(
                prompt,
                generation_config=generation_config
            )
            
            question = response.text.strip()
            
            # Update context with the identified question
            self.current_context["current_question"] = question
            self.current_context["question_understood"] = True
            self.current_context["awaiting_approach"] = True
            
            # Update UI
            self.root.after(0, lambda: self.update_ai_output(question))
            self.root.after(0, lambda: self.add_to_chat_history("Assistant", question))
            
            # Speak response if voice is enabled
            if self.voice_enabled_var.get():
                self.speak_text_in_chunks(question)
                
        except Exception as e:
            error_message = f"Error identifying question: {str(e)}"
            logger.error(error_message)
            self.root.after(0, lambda: self.update_ai_output(error_message))
    
    def provide_solution_approach(self):
        """Provide a solution approach for the identified question"""
        if not self.last_capture:
            response = "No screen capture available. Start capture first."
            self.root.after(0, lambda: self.update_ai_output(response))
            self.root.after(0, lambda: self.add_to_chat_history("Assistant", response))
            return
            
        # Get the most recent OCR text
        ocr_text = self.current_context["last_ocr_text"]
        
        # Check if we already identified the question
        question_context = ""
        if self.current_context["question_understood"] and self.current_context["current_question"]:
            question_context = f"""
            PREVIOUSLY IDENTIFIED QUESTION:
            {self.current_context["current_question"]}
            """
        
        # Special prompt for providing a solution approach
        prompt = f"""
        You are an assistant helping to provide a solution approach for a problem.
        
        SCREEN CONTENT:
        {ocr_text[:10000]}
        
        APPLICATION CONTEXT: {self.current_app_context}
        
        {question_context}
        
        TASK:
        Provide a clear step-by-step approach to solve the problem shown on screen.
        
        RESPONSE GUIDELINES:
        - Do NOT repeat the question/problem statement - jump straight to the solution approach
        - Break down the solution into clear logical steps
        - Explain the reasoning behind each step
        - Use simple clear language suitable for text-to-speech conversion
        - Avoid using commas semicolons colons or other punctuation when possible
        - Use short sentences with natural pauses
        - If this is a coding problem include pseudocode or actual code if appropriate
        - If there are multiple approaches list the most efficient one first
        - Keep explanations concise but complete
        
        Your response must be coherent focused on the solution approach only.
        """
        
        # Process with AI
        try:
            generation_config = {
                "temperature": 0.5,
                "top_p": 0.85,
                "max_output_tokens": 8192,
            }
            
            # Use streamed response to handle long outputs
            response_parts = []
            
            # Stream the response
            for response_chunk in self.model.generate_content(
                prompt,
                generation_config=generation_config,
                stream=True
            ):
                if response_chunk.text:
                    response_parts.append(response_chunk.text)
                    # Update UI with partial response
                    partial_text = "".join(response_parts)
                    self.root.after(0, lambda t=partial_text: self.update_ai_output_streaming(t))
            
            # Combine all chunks for the final response
            approach = "".join(response_parts).strip()
            
            # Mark that we've provided an approach
            self.current_context["awaiting_approach"] = False
            
            # Update UI with complete response
            self.root.after(0, lambda: self.update_ai_output(approach))
            self.root.after(0, lambda: self.add_to_chat_history("Assistant", approach))
            
            # Speak response if voice is enabled
            if self.voice_enabled_var.get():
                self.speak_text_in_chunks(approach)
                
        except Exception as e:
            error_message = f"Error providing solution approach: {str(e)}"
            logger.error(error_message)
            self.root.after(0, lambda: self.update_ai_output(error_message))
    
    def explain_specific_part(self, part_to_explain):
        """Explain a specific part of the problem that the user is asking about"""
        if not self.last_capture:
            response = "No screen capture available. Start capture first."
            self.root.after(0, lambda: self.update_ai_output(response))
            self.root.after(0, lambda: self.add_to_chat_history("Assistant", response))
            return
            
        # Get the most recent OCR text
        ocr_text = self.current_context["last_ocr_text"]
        
        # Special prompt for explaining a specific part
        prompt = f"""
        You are an assistant helping to explain a specific part of a problem.
        
        SCREEN CONTENT:
        {ocr_text[:10000]}
        
        APPLICATION CONTEXT: {self.current_app_context}
        
        SPECIFIC PART TO EXPLAIN: {part_to_explain}
        
        TASK:
        Explain the specific part of the problem that the user is asking about.
        
        RESPONSE GUIDELINES:
        - Focus only on explaining the specific part mentioned
        - Be clear and educational in your explanation
        - Provide context if needed for understanding
        - Use simple language suitable for speech
        - Keep your explanation concise but thorough
        - Avoid using commas semicolons colons or other punctuation when possible
        """
        
        # Process with AI
        try:
            generation_config = {
                "temperature": 0.4,
                "top_p": 0.85,
                "max_output_tokens": 2048,
            }
            
            response = self.model.generate_content(
                prompt,
                generation_config=generation_config
            )
            
            explanation = response.text.strip()
            
            # Update UI
            self.root.after(0, lambda: self.update_ai_output(explanation))
            self.root.after(0, lambda: self.add_to_chat_history("Assistant", explanation))
            
            # Speak response if voice is enabled
            if self.voice_enabled_var.get():
                self.speak_text_in_chunks(explanation)
                
        except Exception as e:
            error_message = f"Error explaining part: {str(e)}"
            logger.error(error_message)
            self.root.after(0, lambda: self.update_ai_output(error_message))
    
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
            ocr_text = self.current_context["last_ocr_text"]
            
            # Check if we should use the contextual flow
            if self.flow_enabled_var.get():
                intent = self.detect_query_intent(query)
                
                if intent == "identify_question":
                    self.identify_question_from_screen()
                    return
                elif intent == "provide_approach" and self.current_context["question_understood"]:
                    self.provide_solution_approach()
                    return
                elif intent == "explain_part":
                    part_to_explain = query.lower().replace("what does", "").replace("explain", "").replace("clarify", "").strip()
                    self.explain_specific_part(part_to_explain)
                    return
            
            # Default processing for general queries or when flow is disabled
            
            # Prepare improved prompt for Gemini
            prompt = f"""
            You are a helpful AI assistant that analyzes screen content and responds to user questions.

            SCREEN CONTENT:
            {ocr_text[:10000]}

            APPLICATION CONTEXT: {self.current_app_context}

            USER QUESTION: {query}

            RESPONSE GUIDELINES:
            - Answer directly and conversationally about the content shown on screen
            - Focus only on information relevant to the user's specific question
            - Use simple clear language suitable for text-to-speech conversion
            - Avoid using commas semicolons colons or other punctuation when possible
            - Use short sentences with natural pauses
            - For lists use new lines instead of commas
            - Structure complex information with clear headers and sections
            - If you can't answer from the available information say so clearly and suggest what's needed
            - Complete your thoughts fully and never leave sentences unfinished
            - Keep paragraphs short with 2-3 sentences maximum
            - Summarize information instead of listing every detail
            - Never mention "OCR text" or "screen content" directly

            Your response must be complete coherent and helpful.
            """
            
            # Call Gemini API with streaming to handle long responses
            try:
                generation_config = {
                    "temperature": 0.5,
                    "top_p": 0.85,
                    "max_output_tokens": 8192,
                }
                
                # Use streamed response to handle long outputs
                response_parts = []
                
                # Stream the response
                for response_chunk in self.model.generate_content(
                    prompt,
                    generation_config=generation_config,
                    stream=True
                ):
                    if response_chunk.text:
                        response_parts.append(response_chunk.text)
                        # Update UI with partial response
                        partial_text = "".join(response_parts)
                        self.root.after(0, lambda t=partial_text: self.update_ai_output_streaming(t))
                
                # Combine all chunks for the final response
                ai_response = "".join(response_parts).strip()
                
                # Prepare response for TTS by removing punctuation that affects speech
                tts_response = ai_response
                if self.voice_enabled_var.get():
                    # Keep some punctuation for TTS pacing but remove others
                    for char in [':', ';', '(', ')', '"', '*', '`', '|', '/', '\\']:
                        tts_response = tts_response.replace(char, '')
                
                # Update UI with complete AI response
                self.root.after(0, lambda: self.update_ai_output(ai_response))
                self.root.after(0, lambda: self.add_to_chat_history("Assistant", ai_response))
                
                # Speak response if voice is enabled
                if self.voice_enabled_var.get():
                    # Process text for speech in chunks to avoid cut-offs
                    self.speak_text_in_chunks(tts_response)
                    
            except Exception as e:
                error_message = f"Gemini API error: {str(e)}"
                logger.error(error_message)
                self.root.after(0, lambda: self.update_ai_output(error_message))
                
        except Exception as e:
            error_message = f"AI processing error: {str(e)}"
            logger.error(error_message)
            self.root.after(0, lambda: self.update_ai_output(error_message))
    
    def update_ai_output_streaming(self, text):
        """Update the AI output display with streaming text"""
        # Clear previous output
        self.ai_output.delete(1.0, tk.END)
        
        # Add timestamp
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        self.ai_output.insert(tk.END, f"[{timestamp}]\n\n")
        
        # Add AI response
        self.ai_output.insert(tk.END, text)
        
        # Scroll to the end
        self.ai_output.see(tk.END)
    
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
    
    def speak_text_in_chunks(self, text):
        """Convert text to speech in manageable chunks"""
        try:
            # Split text into sentences or sections for better TTS handling
            
            # Split by periods, question marks, exclamation points, and new lines
            chunks = re.split(r'(?<=[.!?])\s+|(?<=\n)', text)
            
            # Filter out empty chunks
            chunks = [chunk.strip() for chunk in chunks if chunk.strip()]
            
            # Combine very short chunks
            processed_chunks = []
            current_chunk = ""
            
            for chunk in chunks:
                if len(current_chunk) + len(chunk) < 150:  # Combine chunks up to ~150 chars
                    current_chunk += " " + chunk if current_chunk else chunk
                else:
                    if current_chunk:
                        processed_chunks.append(current_chunk)
                    current_chunk = chunk
            
            if current_chunk:  # Add the last chunk
                processed_chunks.append(current_chunk)
            
            # Speak in a separate thread to avoid UI freezing
            def speak_thread():
                for chunk in processed_chunks:
                    if chunk.strip():
                        self.speech_engine.say(chunk)
                        self.speech_engine.runAndWait()
                        # Small pause between chunks for natural speech
                        time.sleep(0.3)
                    
            threading.Thread(target=speak_thread, daemon=True).start()
        except Exception as e:
            logger.error(f"Speech chunking error: {e}")
    
    def analyze_current_context(self, additional_query=None):
        """Analyze the current screen context"""
        if additional_query:
            query = f"Please analyze what's on my screen and {additional_query}"
        else:
            query = "Please analyze what's on my screen and explain what I'm looking at."
            
        self.process_text_query(query)
    
    def run(self):
        """Run the application"""
        self.root.mainloop()


if __name__ == "__main__":
    # Set default Gemini API key
    default_api_key = "AIzaSyCK6YT332KT79i2JvgJ6Jjes76R2I1Dtk8"
    
    # Create and run application
    app = ScreenAIAssistant(api_key=default_api_key)
    app.run()