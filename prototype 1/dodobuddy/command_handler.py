"""
Command Handler Module
Enhanced command processing with buddy integration
"""

import time
import json
import logging
from typing import Dict, List, Any, Optional, Tuple

# Setup logging
logger = logging.getLogger("CommandHandler")

class EnhancedCommandHandler:
    """Enhanced command processing with buddy integration"""
    
    def __init__(self, buddy_integration, original_command_manager):
        """Initialize the enhanced command handler"""
        self.buddy_integration = buddy_integration
        self.original_command_manager = original_command_manager
        
        # Flag to track if we're in command execution
        self.is_executing = False
        
        logger.info("Enhanced command handler initialized")
    
    def execute_command(self, command: str) -> bool:
        """Execute a command with buddy integration and context awareness"""
        if not command:
            return False
        
        self.is_executing = True
        success = False
        
        try:
            # Get active window for context
            active_window = self._get_active_window()
            
            # Analyze the command with LLM and memory context
            intent_data = self.buddy_integration.analyze_command(command, active_window)
            
            # Decide if this is a history command
            if intent_data.get("command_type") == "history":
                # Handle history command through buddy integration
                response = self.buddy_integration.process_user_input(command, active_window)
                return True
            
            # Check if it's a recognized command type
            if intent_data.get("is_command", False) and intent_data.get("command_type") != "unknown":
                # Log the detected command intent
                logger.info(f"Executing command: {intent_data['command_type']} - {intent_data.get('explanation', '')}")
                
                # Add any user preferences to the command context if relevant
                user_preferences = intent_data.get("user_preferences", {})
                if user_preferences:
                    logger.info(f"Applying user preferences: {user_preferences}")
                
                # Execute through original command manager
                return self._execute_through_original(command, intent_data)
            else:
                # Not a command or unknown command type
                logger.info(f"Not a recognized command: {command}")
                
                # Process as a buddy conversation instead
                response = self.buddy_integration.process_user_input(command, active_window)
                return True
        
        except Exception as e:
            logger.error(f"Error executing command: {e}")
            return False
        
        finally:
            self.is_executing = False
    
    def _execute_through_original(self, command: str, intent_data: Dict[str, Any]) -> bool:
        """Execute through the original command manager with enhanced context"""
        try:
            # Map our command types to the original command manager's expected format
            command_type = intent_data.get("command_type")
            sub_intent = intent_data.get("sub_intent")
            target = intent_data.get("target")
            
            # Create enhanced intent data that the original command manager can use
            enhanced_intent = {
                "intent": command_type,
                "sub_intent": sub_intent,
                "target": target,
                "explanation": intent_data.get("explanation", "")
            }
            
            # If we have a confidence value, pass it through
            if "confidence" in intent_data:
                enhanced_intent["confidence"] = intent_data["confidence"]
            
            # Execute the command through the original manager
            success = self.original_command_manager.execute_command(command)
            
            # Record the command execution in buddy integration
            self.buddy_integration._store_conversation_turn(
                command,
                f"Executed command: {intent_data.get('explanation', command_type)}",
                "command",
                [command_type]
            )
            
            return success
        
        except Exception as e:
            logger.error(f"Error executing through original command manager: {e}")
            return False
    
    def _get_active_window(self):
        """Get the active window info using the original command system"""
        try:
            # This function should be defined in the original system
            from dodo18 import get_active_window
            return get_active_window()
        except Exception as e:
            logger.error(f"Error getting active window: {e}")
            return None
    
    def is_command_running(self) -> bool:
        """Check if a command is currently running"""
        return self.is_executing or self.original_command_manager.is_command_running()
    
    def stop_current_command(self) -> bool:
        """Signal the current command to stop"""
        try:
            # Stop any command running in the original manager
            result = self.original_command_manager.stop_current_command()
            self.is_executing = False
            return result
        except Exception as e:
            logger.error(f"Error stopping command: {e}")
            self.is_executing = False
            return False