"""
Conversation Modes Module
Defines modes for the conversation system and utilities to detect them
"""

class ConversationMode:
    """Enum-like class for tracking conversation modes"""
    COMMAND = "command"
    CHAT = "chat"
    MIXED = "mixed"  # For when the intent is unclear or contains both

def create_mode_detection_prompt(user_input, conversation_history=None):
    """Create prompt for LLM to determine conversation mode"""
    if conversation_history:
        recent_context = "\n".join([
            f"User: {turn['content']}" if turn['role'] == 'user' else f"Assistant: {turn['content']}"
            for turn in conversation_history
        ])
    else:
        recent_context = "No previous conversation context."
    
    prompt = f"""
As an AI assistant, analyze this user input and determine whether it's:
1. A command (instruction to perform a task or action)
2. A casual conversation (chat, social interaction)
3. Mixed (contains elements of both)

Previous conversation context:
{recent_context}

Current user input: "{user_input}"

Return ONLY a single word: "command", "chat", or "mixed".
    """
    return prompt

def create_command_detection_prompt(user_input, conversation_history=None):
    """Create prompt for LLM to extract command intents"""
    if conversation_history:
        recent_context = "\n".join([
            f"User: {turn['content']}" if turn['role'] == 'user' else f"Assistant: {turn['content']}"
            for turn in conversation_history
        ])
    else:
        recent_context = "No previous conversation context."
    
    prompt = f"""
As an AI assistant, analyze this user input to extract actionable commands:

Previous conversation context:
{recent_context}

Current user input: "{user_input}"

Return a JSON object with the following structure:
{{
    "is_command": true/false,
    "intents": ["intent1", "intent2", ...],
    "confidence": 0-1 float,
    "explanation": "Brief explanation of the detected command"
}}

If this is not a command or doesn't contain any actionable instructions, set "is_command" to false.
    """
    return prompt