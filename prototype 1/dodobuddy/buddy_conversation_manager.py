"""
Buddy Conversation Manager
Manages conversation flow between chat and command modes
"""

import uuid
import time
import json
from typing import Dict, List, Any, Optional, Tuple

from conversation_history import ConversationHistory, ConversationTurn
from conversation_modes import ConversationMode, create_mode_detection_prompt, create_command_detection_prompt

class BuddyConversationManager:
    """Manages conversation flow between chat and command modes"""
    
    def __init__(self, llm, command_manager, conversation_history=None):
        """Initialize the conversation manager"""
        self.llm = llm
        self.command_manager = command_manager
        
        # Initialize or use provided conversation history
        if conversation_history is None:
            self.history = ConversationHistory()
        else:
            self.history = conversation_history
        
        # Current conversation state
        self.current_mode = ConversationMode.CHAT
        self.current_context = {}
        
        # Define persona characteristics for the buddy mode
        self.persona = {
            "name": "Dodo",
            "traits": ["helpful", "friendly", "attentive", "slightly witty"],
            "interests": ["helping users", "learning new things"],
            "speaking_style": "conversational, warm, and concise"
        }
    
    def determine_input_type(self, user_input: str) -> str:
        """Use LLM to determine if input is a command or casual conversation"""
        if not user_input:
            return ConversationMode.CHAT
        
        # Get recent conversation for context
        recent_context = self.history.get_conversation_context(3)
        
        # Create prompt for the LLM
        prompt = create_mode_detection_prompt(user_input, recent_context)
        
        # Get response from LLM
        try:
            response = self.llm.generate_content(prompt)
            response_text = response.text.strip().lower()
            
            if "command" in response_text:
                return ConversationMode.COMMAND
            elif "mixed" in response_text:
                return ConversationMode.MIXED
            else:
                return ConversationMode.CHAT
        except Exception as e:
            print(f"Error determining input type: {e}")
            # Default to chat mode if there's an error
            return ConversationMode.CHAT
    
    def extract_command_intents(self, user_input: str) -> Dict[str, Any]:
        """Extract command intents from user input using LLM"""
        if not user_input:
            return {"is_command": False, "intents": [], "confidence": 0.0}
        
        # Get recent conversation for context
        recent_context = self.history.get_conversation_context(3)
        
        # Create prompt for command detection
        prompt = create_command_detection_prompt(user_input, recent_context)
        
        # Get response from LLM
        try:
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
            return intent_data
        except Exception as e:
            print(f"Error extracting command intents: {e}")
            # Return empty intents if there's an error
            return {"is_command": False, "intents": [], "confidence": 0.0}
    
    def generate_chat_response(self, user_input: str) -> str:
        """Generate a response for chat mode using LLM"""
        # Get conversation history for context
        recent_context = self.history.get_conversation_context(5)
        
        # Create persona context prompt
        persona_prompt = f"""
You are {self.persona['name']}, a voice assistant with the following traits: {', '.join(self.persona['traits'])}.
Your speaking style is {self.persona['speaking_style']}.

Respond to the user in a natural, conversational way. Keep responses relatively brief but engaging.
Remember details the user has shared in previous conversations and refer to them when relevant.

Recent conversation for context:
"""
        
        # Format the conversation context
        context_str = "\n".join([
            f"User: {turn['content']}" if turn['role'] == 'user' else f"Assistant: {turn['content']}"
            for turn in recent_context
        ])
        
        # Combine prompt and add the current user input
        full_prompt = f"{persona_prompt}\n{context_str}\n\nUser: {user_input}\n\nAssistant:"
        
        # Get response from LLM
        try:
            response = self.llm.generate_content(full_prompt)
            return response.text.strip()
        except Exception as e:
            print(f"Error generating chat response: {e}")
            return "I'm sorry, I'm having trouble processing that right now. Could you please try again?"
    
    def process_user_input(self, user_input: str) -> Tuple[str, List[str], str]:
        """Process user input and determine appropriate response"""
        # Determine input type
        mode = self.determine_input_type(user_input)
        self.current_mode = mode
        
        actions_performed = []
        response = ""
        
        if mode == ConversationMode.COMMAND or mode == ConversationMode.MIXED:
            # Extract command intents
            intent_data = self.extract_command_intents(user_input)
            
            if intent_data["is_command"] and intent_data["confidence"] > 0.6:
                # Execute the command
                print(f"Executing command with intents: {intent_data['intents']}")
                
                try:
                    # Use the command manager to execute the command
                    self.command_manager.execute_command(user_input)
                    actions_performed.extend(intent_data["intents"])
                    
                    # For pure commands, we can use the explanation as the response
                    if mode == ConversationMode.COMMAND:
                        response = f"I've processed your request to {intent_data['explanation']}"
                    else:
                        # For mixed mode, generate a more conversational response
                        response = self.generate_chat_response(user_input)
                except Exception as e:
                    print(f"Error executing command: {e}")
                    response = f"I tried to {intent_data['explanation']} but encountered an error. Would you like to try again?"
            else:
                # If it's not a high-confidence command or mixed mode, treat as chat
                response = self.generate_chat_response(user_input)
        else:
            # Pure chat mode
            response = self.generate_chat_response(user_input)
        
        # Store the conversation turn
        self._store_conversation_turn(user_input, response, mode, actions_performed)
        
        return response, actions_performed, mode
    
    def _store_conversation_turn(self, user_input: str, assistant_response: str, 
                               mode: str, actions_performed: List[str]):
        """Store the conversation turn in history"""
        turn = ConversationTurn(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            user_input=user_input,
            assistant_response=assistant_response,
            mode=mode,
            detected_intents=[],  # We could store the intents here
            actions_performed=actions_performed,
            context=self.current_context.copy()
        )
        
        self.history.add_turn(turn)
    
    def handle_history_query(self, query: str) -> str:
        """Handle queries about past conversations"""
        # Extract search parameters from the query
        search_prompt = f"""
Extract search parameters from this history query: "{query}"

Return a JSON object with:
{{
    "search_type": "text" or "date" or "recent",
    "search_term": the search term if applicable,
    "limit": suggested number of results (default 5),
    "explanation": brief explanation of what the user is looking for
}}
"""
        
        try:
            response = self.llm.generate_content(search_prompt)
            response_text = response.text
            
            # Extract JSON
            if '```json' in response_text:
                json_str = response_text.split('```json')[1].split('```')[0].strip()
            elif '```' in response_text:
                json_str = response_text.split('```')[1].strip()
            else:
                json_str = response_text.strip()
            
            search_params = json.loads(json_str)
            
            # Execute search based on parameters
            if search_params["search_type"] == "text":
                turns = self.history.search_by_text(search_params["search_term"], search_params["limit"])
            elif search_params["search_type"] == "date":
                turns = self.history.search_by_date(search_params["search_term"], search_params["limit"])
            else:  # recent
                turns = self.history.get_recent_turns(search_params["limit"])
            
            # Format results for response
            if not turns:
                return "I couldn't find any matching conversations in your history."
            
            result = f"Here's what I found in your conversation history:\n\n"
            
            for i, turn in enumerate(turns):
                date_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(turn.timestamp))
                result += f"{i+1}. On {date_str}:\n"
                result += f"   You: {turn.user_input}\n"
                result += f"   Me: {turn.assistant_response}\n\n"
            
            return result
            
        except Exception as e:
            print(f"Error handling history query: {e}")
            return "I'm having trouble searching your conversation history right now. Could you please try again with a simpler query?"