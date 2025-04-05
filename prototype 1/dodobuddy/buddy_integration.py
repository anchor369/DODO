"""
Buddy Integration Module
Integrates the buddy conversation system with the existing command infrastructure
"""

import os
import time
import json
import uuid
import threading
import logging
from typing import Dict, List, Any, Optional, Tuple

# Import from our modules
from conversation_history import ConversationHistory, ConversationTurn
from conversation_modes import ConversationMode
from buddy_conversation_manager import BuddyConversationManager
from persona_memory import PersonaMemory
from history_commands import handle_history_command, format_conversation_turns
from prompt_templates import create_command_analysis_prompt

# Setup logging
logger = logging.getLogger("BuddyIntegration")

class BuddyIntegration:
    """Integrates buddy conversation with existing command system"""
    
    def __init__(self, llm, command_manager):
        """Initialize the buddy integration"""
        self.llm = llm
        self.command_manager = command_manager
        
        # Initialize history, memory, and conversation manager
        self.conversation_history = ConversationHistory()
        self.persona_memory = PersonaMemory(llm)
        self.conversation_manager = BuddyConversationManager(
            llm, command_manager, self.conversation_history
        )
        
        # Track the current mode
        self.current_mode = ConversationMode.CHAT
        
        # Configure the buddy persona
        self.buddy_persona = {
            "name": "Dodo",
            "traits": ["helpful", "friendly", "supportive", "slightly witty"],
            "interests": ["helping users", "learning new things", "having meaningful conversations"],
            "speaking_style": "conversational, warm, and concise"
        }
        
        logger.info("Buddy integration initialized")
    
    def process_user_input(self, user_input: str, active_window=None) -> str:
        """Process user input and determine appropriate response"""
        if not user_input:
            return "I didn't catch that. Could you please repeat?"
        
        # First, check if this is a history-related command
        if self._is_history_command(user_input):
            # Handle history command directly
            response = handle_history_command(user_input, self.conversation_history, self.llm)
            
            # Store the conversation turn
            self._store_conversation_turn(user_input, response, ConversationMode.COMMAND, ["history_query"])
            return response
        
        # Determine input type and process accordingly
        response, actions, mode = self.conversation_manager.process_user_input(user_input)
        
        # Update current mode
        self.current_mode = mode
        
        # Update persona memory if in chat mode
        if mode == ConversationMode.CHAT or mode == ConversationMode.MIXED:
            recent_context = self.conversation_history.get_conversation_context(3)
            self.persona_memory.update_from_conversation(user_input, recent_context)
        
        return response
    
    def _is_history_command(self, command: str) -> bool:
        """Check if a command is related to conversation history"""
        history_keywords = [
            "conversation history", "chat history", "previous conversations",
            "what did we talk about", "show history", "our conversation",
            "what have we discussed", "remember when i said", "search history",
            "find in our conversations"
        ]
        
        command_lower = command.lower()
        return any(keyword in command_lower for keyword in history_keywords)
    
    def _store_conversation_turn(self, user_input: str, assistant_response: str, 
                               mode: str, actions_performed: List[str]):
        """Store the conversation turn in history"""
        turn = ConversationTurn(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            user_input=user_input,
            assistant_response=assistant_response,
            mode=mode,
            detected_intents=[],  # We could store detected intents here
            actions_performed=actions_performed,
            context={}  # Store any relevant context
        )
        
        self.conversation_history.add_turn(turn)
    
    def analyze_command(self, command: str, active_window=None) -> Dict[str, Any]:
        """Enhanced command analysis using LLM and persona context"""
        # Get recent conversation for context
        recent_context = self.conversation_history.get_conversation_context(3)
        
        # Create command analysis prompt
        prompt = create_command_analysis_prompt(command, recent_context, active_window)
        
        try:
            # Get analysis from LLM
            response = self.llm.generate_content(prompt)
            response_text = response.text
            
            # Extract JSON
            if '```json' in response_text:
                json_str = response_text.split('```json')[1].split('```')[0].strip()
            elif '```' in response_text:
                json_str = response_text.split('```')[1].strip()
            else:
                json_str = response_text.strip()
            
            intent_data = json.loads(json_str)
            
            # Add memory context if available
            memory_context = self.persona_memory.get_memory_context()
            
            # If there are user preferences that might be relevant, add them
            if "preferences" in memory_context and memory_context["preferences"]:
                intent_data["user_preferences"] = memory_context["preferences"]
            
            # If there's a user name, add it
            if "user_name" in memory_context and memory_context["user_name"]:
                intent_data["user_name"] = memory_context["user_name"]
            
            return intent_data
            
        except Exception as e:
            logger.error(f"Error analyzing command: {e}")
            # Return a basic structure on failure
            return {
                "is_command": False,
                "command_type": "unknown",
                "explanation": f"Error in command analysis: {str(e)}"
            }
    
    def get_buddy_persona(self) -> Dict[str, Any]:
        """Get the buddy persona configuration"""
        return self.buddy_persona
    
    def switch_mode(self, mode: str) -> str:
        """Explicitly switch conversation mode"""
        if mode.lower() in ["command", "cmd"]:
            self.current_mode = ConversationMode.COMMAND
            return "Switched to command mode. I'll focus on executing your instructions."
        
        elif mode.lower() in ["chat", "conversation"]:
            self.current_mode = ConversationMode.CHAT
            return "Switched to chat mode. Let's have a conversation!"
        
        elif mode.lower() in ["mixed", "auto"]:
            self.current_mode = ConversationMode.MIXED
            return "Switched to mixed mode. I'll automatically detect whether you want to chat or execute commands."
        
        else:
            return f"Unknown mode: {mode}. Valid modes are 'command', 'chat', or 'mixed'."