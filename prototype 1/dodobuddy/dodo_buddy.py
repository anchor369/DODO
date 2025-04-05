"""
Dodo Buddy - Main Integration File
Integrates all buddy components with dodo18.py
"""

import os
import time
import sys
import threading
import logging
import uuid
from typing import Dict, List, Any, Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='buddy_assistant.log'
)
logger = logging.getLogger("DodoBuddy")

# Import buddy components
from conversation_history import ConversationHistory, ConversationTurn
from conversation_modes import ConversationMode
from buddy_conversation_manager import BuddyConversationManager
from persona_memory import PersonaMemory
from history_commands import handle_history_command
from input_analyzer import InputAnalyzer
from response_generator import BuddyResponseGenerator
from command_handler import EnhancedCommandHandler
from buddy_integration import BuddyIntegration

class DodoBuddy:
    """Main class for Dodo Buddy integration"""
    
    def __init__(self, llm, original_speak_func=None):
        """Initialize the Dodo Buddy system"""
        self.llm = llm
        self.original_speak_func = original_speak_func
        
        # Component initialization flags
        self.initialized = False
        self.components_ready = {
            "history": False,
            "memory": False,
            "analyzer": False,
            "generator": False,
            "handler": False,
            "integration": False
        }
        
        # Initialize components
        self._initialize_components()
        
        logger.info("Dodo Buddy initialized")
    
    def _initialize_components(self):
        """Initialize all buddy components"""
        try:
            # Ensure dodo18 command_manager is available
            from dodo18 import command_manager
            
            # Initialize conversation history
            self.conversation_history = ConversationHistory()
            self.components_ready["history"] = True
            
            # Initialize persona memory
            self.persona_memory = PersonaMemory(self.llm)
            self.components_ready["memory"] = True
            
            # Initialize input analyzer
            self.input_analyzer = InputAnalyzer(self.llm)
            self.components_ready["analyzer"] = True
            
            # Setup buddy persona
            self.buddy_persona = {
                "name": "Dodo",
                "traits": ["helpful", "friendly", "supportive", "slightly witty"],
                "interests": ["helping users", "learning new things", "having meaningful conversations"],
                "speaking_style": "conversational, warm, and concise"
            }
            
            # Initialize response generator
            self.response_generator = BuddyResponseGenerator(self.llm, self.buddy_persona)
            self.components_ready["generator"] = True
            
            # Initialize buddy integration
            self.buddy_integration = BuddyIntegration(self.llm, command_manager)
            self.components_ready["integration"] = True
            
            # Initialize enhanced command handler
            self.command_handler = EnhancedCommandHandler(self.buddy_integration, command_manager)
            self.components_ready["handler"] = True
            
            # Initialize conversation manager
            self.conversation_manager = BuddyConversationManager(
                self.llm, command_manager, self.conversation_history
            )
            
            # Check if all components are ready
            self.initialized = all(self.components_ready.values())
            
            if self.initialized:
                logger.info("All components initialized successfully")
            else:
                missing = [comp for comp, ready in self.components_ready.items() if not ready]
                logger.warning(f"Not all components initialized. Missing: {missing}")
            
        except Exception as e:
            logger.error(f"Error initializing components: {e}")
            self.initialized = False
    
    def process_user_input(self, user_input: str) -> str:
        """Process user input with buddy features"""
        if not user_input:
            return "I didn't catch that. Could you please repeat?"
        
        if not self.initialized:
            logger.warning("Buddy not fully initialized, using fallback processing")
            return self._fallback_processing(user_input)
        
        try:
            # Get active window for context
            active_window = self._get_active_window()
            
            # Get conversation context
            recent_context = self.conversation_history.get_conversation_context(5)
            
            # Analyze input type (command vs conversation)
            input_mode, command_data = self.input_analyzer.analyze(
                user_input, recent_context, active_window
            )
            
            # Process based on input type
            if input_mode == ConversationMode.COMMAND:
                # It's primarily a command - process through command handler
                if command_data.get("is_command", False) and command_data.get("confidence", 0) > 0.6:
                    # Check if it's a history-related command
                    if command_data.get("command_type") == "history":
                        response = handle_history_command(user_input, self.conversation_history, self.llm)
                    else:
                        # Execute normal command
                        confirm_msg = self.response_generator.generate_command_confirmation(command_data)
                        self._speak(confirm_msg)
                        
                        success = self.command_handler.execute_command(user_input)
                        
                        response = self.response_generator.generate_command_completion(
                            command_data, success
                        )
                else:
                    # Low confidence command - treat as conversation
                    memory_context = self.persona_memory.get_memory_context()
                    response = self.response_generator.generate_response(
                        user_input, recent_context, memory_context
                    )
            
            elif input_mode == ConversationMode.MIXED:
                # Contains both command and conversation elements
                # First process any commands
                if command_data.get("is_command", False) and command_data.get("confidence", 0) > 0.4:
                    self.command_handler.execute_command(user_input)
                
                # Then generate conversational response
                memory_context = self.persona_memory.get_memory_context()
                response = self.response_generator.generate_response(
                    user_input, recent_context, memory_context
                )
            
            else:
                # Pure conversation
                memory_context = self.persona_memory.get_memory_context()
                response = self.response_generator.generate_response(
                    user_input, recent_context, memory_context
                )
                
                # Update persona memory with any new information
                self.persona_memory.update_from_conversation(user_input, recent_context)
            
            # Store the conversation turn
            self._store_conversation_turn(user_input, response, input_mode)
            
            # Occasionally add a follow-up question
            followup = None
            if input_mode == ConversationMode.CHAT and recent_context:
                followup = self.response_generator.generate_followup_question(recent_context)
                if followup:
                    response = f"{response} {followup}"
            
            return response
            
        except Exception as e:
            logger.error(f"Error processing input: {e}")
            return "I encountered an error processing your request. Could you try again?"
    
    def _store_conversation_turn(self, user_input: str, assistant_response: str, mode: str):
        """Store the conversation turn in history"""
        turn = ConversationTurn(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            user_input=user_input,
            assistant_response=assistant_response,
            mode=mode,
            detected_intents=[],
            actions_performed=[],
            context={}
        )
        
        self.conversation_history.add_turn(turn)
    
    def _get_active_window(self):
        """Get the active window info"""
        try:
            from dodo18 import get_active_window
            return get_active_window()
        except Exception as e:
            logger.error(f"Error getting active window: {e}")
            return None
    
    def _speak(self, text):
        """Use the original speak function or print as fallback"""
        if self.original_speak_func:
            self.original_speak_func(text)
        else:
            print(f"🎙️ Buddy: {text}")
    
    def _fallback_processing(self, user_input: str) -> str:
        """Fallback processing if components aren't initialized"""
        # Simple keyword-based processing
        if "help" in user_input.lower():
            return "I'm here to help! You can ask me questions or give me commands."
        
        if any(cmd in user_input.lower() for cmd in ["open", "launch", "start"]):
            return "I'll try to open that for you."
        
        if any(cmd in user_input.lower() for cmd in ["close", "exit", "quit"]):
            return "I'll try to close that for you."
        
        # General fallback
        return "I'm processing your request. My buddy features are still initializing."

def replace_speak_function():
    """Replace the original speak function with one that uses buddy processing"""
    try:
        import dodo18
        
        # Store the original function
        original_speak = dodo18.speak
        
        # Create buddy instance
        buddy = DodoBuddy(dodo18.gemini_model, original_speak)
        
        def enhanced_speak(text):
            """Enhanced speak function that reports buddy's response"""
            original_speak(text)
        
        def enhanced_listen_command():
            """Enhanced listen function that processes input through buddy"""
            command = dodo18.listen_command()
            if command:
                response = buddy.process_user_input(command)
                return command
            return None
        
        def enhanced_process_commands_after_wake_word():
            """Enhanced command processing with buddy features"""
            active = True
            last_command_time = time.time()
            
            # Give a short moment after activation before listening
            time.sleep(0.5)
            original_speak("Yes?")

            while active:
                command = dodo18.listen_command()
                current_time = time.time()
                
                if command:
                    # Reset the timer when a command is received
                    last_command_time = current_time
                    
                    if "exit" in command or "goodbye" in command or "bye" in command or "stop listening" in command:
                        original_speak("Going back to standby mode")
                        active = False
                        continue
                    
                    # Process through buddy
                    response = buddy.process_user_input(command)
                    original_speak(response)
                    
                    # Give a short pause after processing a command
                    time.sleep(0.5)
                
                # Increase timeout to 30 seconds
                elif current_time - last_command_time > 30:
                    print("⏰ No further commands detected - returning to standby mode")
                    original_speak("Going back to standby mode")
                    active = False
                
                # Small delay to prevent high CPU usage
                time.sleep(0.1)
        
        # Replace the functions
        dodo18.process_commands_after_wake_word = enhanced_process_commands_after_wake_word
        
        logger.info("Function replacement complete")
        return buddy
        
    except Exception as e:
        logger.error(f"Error replacing functions: {e}")
        return None

if __name__ == "__main__":
    print("Initializing Dodo Buddy...")
    
    # Directly import dodo18 module
    try:
        import dodo18
        
        # Create buddy instance with dodo's LLM
        buddy = DodoBuddy(dodo18.gemini_model, dodo18.speak)
        
        # Replace process_commands function
        dodo18.process_single_command = buddy.process_user_input
        
        print("Integration complete. Run dodo18.py to start the assistant.")
        
    except ImportError:
        print("Could not import dodo18.py. Make sure it's in the same directory.")
        sys.exit(1)