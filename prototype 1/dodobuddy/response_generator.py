"""
Buddy Response Generator
Generates conversational responses for the buddy assistant
"""

import json
import logging
from typing import Dict, List, Any, Optional

from prompt_templates import create_chat_response_prompt

# Setup logging
logger = logging.getLogger("ResponseGenerator")

class BuddyResponseGenerator:
    """Generates conversational responses for the buddy assistant"""
    
    def __init__(self, llm, persona=None):
        """Initialize the response generator"""
        self.llm = llm
        
        # Default persona if none provided
        if persona is None:
            self.persona = {
                "name": "Dodo",
                "traits": ["helpful", "friendly", "supportive", "slightly witty"],
                "interests": ["helping users", "learning new things"],
                "speaking_style": "conversational, warm, and concise"
            }
        else:
            self.persona = persona
        
        # Track conversation state
        self.current_topics = []
        self.response_count = 0
        
        logger.info("Response generator initialized")
    
    def generate_response(self, user_input: str, conversation_context=None, memory_context=None) -> str:
        """Generate a conversational response based on input and context"""
        if not user_input:
            return "I didn't catch that. Could you please repeat?"
        
        # Increment response counter
        self.response_count += 1
        
        # Update the persona with memory context if available
        enhanced_persona = self.persona.copy()
        if memory_context:
            # If we know the user's name, use it
            if memory_context.get("user_name"):
                enhanced_persona["user_name"] = memory_context["user_name"]
            
            # Add relevant user preferences and facts
            if memory_context.get("preferences") or memory_context.get("important_facts"):
                enhanced_persona["user_context"] = {
                    "preferences": memory_context.get("preferences", {}),
                    "facts": memory_context.get("important_facts", [])
                }
        
        # Create chat response prompt
        prompt = create_chat_response_prompt(user_input, conversation_context, enhanced_persona)
        
        try:
            # Get response from LLM
            response = self.llm.generate_content(prompt)
            response_text = response.text.strip()
            
            # Track topics (could be enhanced with topic extraction)
            if len(self.current_topics) < 5:  # Keep last 5 topics
                self.current_topics.append(user_input[:50])  # Simple approach using truncated input
            else:
                self.current_topics.pop(0)
                self.current_topics.append(user_input[:50])
            
            return response_text
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return "I'm having trouble processing that right now. Could you please try again?"
    
    def generate_followup_question(self, conversation_context) -> Optional[str]:
        """Occasionally generate a follow-up question to keep conversation flowing"""
        # Only generate follow-ups occasionally
        if self.response_count % 3 != 0:  # Every third response
            return None
            
        if not conversation_context or len(conversation_context) < 2:
            return None
        
        prompt = f"""
Based on this conversation, generate a single, natural follow-up question to keep the conversation going.
The question should be related to what's been discussed but introduce a slightly new angle.
Keep it brief, casual, and engaging.

Recent conversation:
"""
        # Add recent turns
        for turn in conversation_context[-4:]:  # Last 4 turns
            role = "User" if turn["role"] == "user" else "Assistant"
            prompt += f"{role}: {turn['content']}\n"
        
        prompt += "\nGenerate ONLY the follow-up question (1 sentence):"
        
        try:
            # Get response from LLM
            response = self.llm.generate_content(prompt)
            question = response.text.strip()
            
            # Ensure it's not too long
            if len(question) > 100:
                question = question[:100] + "..."
                
            return question
            
        except Exception as e:
            logger.error(f"Error generating follow-up question: {e}")
            return None
    
    def generate_command_confirmation(self, command_data: Dict[str, Any]) -> str:
        """Generate a confirmation message for a command that will be executed"""
        command_type = command_data.get("command_type", "unknown")
        target = command_data.get("target", "")
        explanation = command_data.get("explanation", "")
        
        # Form basic confirmation based on command type
        confirmations = {
            "open_app": f"I'll open {target} for you.",
            "close_app": f"Closing {target}.",
            "window_control": f"I'll adjust the window as requested.",
            "volume_control": "Adjusting the volume.",
            "brightness_control": "Changing the brightness.",
            "system_power": f"Initiating {command_data.get('sub_intent', 'power command')}.",
            "screenshot": "Taking a screenshot.",
            "calculator": f"Calculating {target}.",
            "media_control": f"Media control: {command_data.get('sub_intent', 'playback')}.",
            "search": f"Searching for {target}.",
            "file_operation": f"Performing file operation: {explanation}",
            "email": f"Managing emails: {explanation}",
            "calendar": f"Working with your calendar: {explanation}",
            "web_search": f"Searching the web for {target}.",
            "local_search": f"Searching your files for {target}."
        }
        
        if command_type in confirmations:
            return confirmations[command_type]
        else:
            return f"I'll execute your request: {explanation}"
    
    def generate_command_completion(self, command_data: Dict[str, Any], success: bool) -> str:
        """Generate a message indicating command completion status"""
        command_type = command_data.get("command_type", "unknown")
        target = command_data.get("target", "")
        
        if success:
            # Success messages
            success_messages = {
                "open_app": f"I've opened {target}.",
                "close_app": f"I've closed {target}.",
                "window_control": "Window adjusted successfully.",
                "volume_control": "Volume adjusted.",
                "brightness_control": "Brightness changed.",
                "system_power": "Power command executed.",
                "screenshot": "Screenshot taken.",
                "calculator": "Calculation complete.",
                "media_control": "Media command executed.",
                "search": f"Search for {target} complete.",
                "file_operation": "File operation completed successfully.",
                "email": "Email operation complete.",
                "calendar": "Calendar operation complete.",
                "web_search": f"I've searched for {target}.",
                "local_search": f"I've looked for {target} in your files."
            }
            
            if command_type in success_messages:
                return success_messages[command_type]
            else:
                return "Command executed successfully."
        else:
            # Failure messages
            failure_messages = {
                "open_app": f"I couldn't open {target}.",
                "close_app": f"I had trouble closing {target}.",
                "window_control": "I couldn't adjust the window.",
                "volume_control": "Volume adjustment failed.",
                "brightness_control": "Brightness adjustment failed.",
                "system_power": "Power command failed.",
                "screenshot": "Screenshot failed.",
                "calculator": "Calculation error.",
                "media_control": "Media command failed.",
                "search": f"Search for {target} failed.",
                "file_operation": "File operation failed.",
                "email": "Email operation failed.",
                "calendar": "Calendar operation failed.",
                "web_search": f"I couldn't search for {target}.",
                "local_search": f"I couldn't find {target} in your files."
            }
            
            if command_type in failure_messages:
                return failure_messages[command_type]
            else:
                return "The command couldn't be executed successfully. Would you like to try again?"