"""
Input Analyzer Module
Analyzes user input to determine if it's a command or conversation
"""

import json
import logging
from typing import Dict, Any, Tuple

from conversation_modes import ConversationMode
from prompt_templates import create_mode_detection_prompt, create_command_analysis_prompt

# Setup logging
logger = logging.getLogger("InputAnalyzer")

class InputAnalyzer:
    """Analyzes user input to determine if it's a command or conversation"""
    
    def __init__(self, llm):
        """Initialize the input analyzer"""
        self.llm = llm
        logger.info("Input analyzer initialized")
    
    def analyze(self, user_input: str, conversation_context=None, active_window=None) -> Tuple[str, Dict[str, Any]]:
        """Analyze user input to determine its type and intent"""
        if not user_input:
            return ConversationMode.CHAT, {"is_command": False, "confidence": 0.0}
        
        # First, determine the mode (command vs chat)
        mode = self.determine_mode(user_input, conversation_context)
        
        # If it's potentially a command, analyze further
        if mode == ConversationMode.COMMAND or mode == ConversationMode.MIXED:
            command_data = self.analyze_command(user_input, conversation_context, active_window)
            
            # If command analysis doesn't think it's a command, override the mode
            if not command_data.get("is_command", False) and command_data.get("confidence", 0) > 0.7:
                if mode == ConversationMode.COMMAND:
                    mode = ConversationMode.CHAT
                # Keep mixed mode as is - it might still have conversational elements
            
            return mode, command_data
        else:
            # For chat mode, return minimal command data
            return mode, {"is_command": False, "confidence": 0.9}
    
    def determine_mode(self, user_input: str, conversation_context=None) -> str:
        """Determine if input is a command, chat, or mixed"""
        # Create mode detection prompt
        prompt = create_mode_detection_prompt(user_input, conversation_context)
        
        try:
            # Get response from LLM
            response = self.llm.generate_content(prompt)
            response_text = response.text.strip().lower()
            
            # Check for command keywords
            if "command" in response_text:
                return ConversationMode.COMMAND
            elif "mixed" in response_text:
                return ConversationMode.MIXED
            else:
                return ConversationMode.CHAT
                
        except Exception as e:
            logger.error(f"Error determining input mode: {e}")
            # Default to chat mode if there's an error
            return ConversationMode.CHAT
    
    def analyze_command(self, user_input: str, conversation_context=None, active_window=None) -> Dict[str, Any]:
        """Analyze potential command to extract intent and parameters"""
        # Create command analysis prompt
        prompt = create_command_analysis_prompt(user_input, conversation_context, active_window)
        
        try:
            # Get response from LLM
            response = self.llm.generate_content(prompt)
            response_text = response.text
            
            # Extract JSON
            if '```json' in response_text:
                json_str = response_text.split('```json')[1].split('```')[0].strip()
            elif '```' in response_text:
                json_str = response_text.split('```')[1].strip()
            else:
                json_str = response_text.strip()
            
            command_data = json.loads(json_str)
            logger.info(f"Command analysis: {command_data}")
            return command_data
            
        except Exception as e:
            logger.error(f"Error analyzing command: {e}")
            # Return basic data structure on error
            return {
                "is_command": False,
                "command_type": "unknown",
                "confidence": 0.0,
                "requires_confirmation": False,
                "needs_more_info": False,
                "explanation": f"Error analyzing input: {str(e)}"
            }
    
    def quick_classify(self, user_input: str) -> str:
        """Quickly classify input without LLM for common patterns"""
        # This is a faster backup method that uses simple patterns
        
        if not user_input:
            return ConversationMode.CHAT
        
        # Common command keywords
        command_keywords = [
            "open", "close", "launch", "shut down", "restart", 
            "volume", "brightness", "screenshot", "play", "pause",
            "search for", "find file", "create folder", "delete file",
            "check email", "set reminder", "schedule"
        ]
        
        # Common question patterns
        question_patterns = [
            "what is", "who is", "when is", "where is", "why is",
            "how do", "can you explain", "tell me about", 
            "do you know", "have you heard"
        ]
        
        # Check for command keywords
        user_input_lower = user_input.lower()
        
        if any(keyword in user_input_lower for keyword in command_keywords):
            # Check if it also has conversational elements
            if any(pattern in user_input_lower for pattern in question_patterns):
                return ConversationMode.MIXED
            return ConversationMode.COMMAND
            
        # Check for question patterns
        if any(pattern in user_input_lower for pattern in question_patterns):
            return ConversationMode.CHAT
            
        # Default to chat mode if uncertain
        return ConversationMode.CHAT