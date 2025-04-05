"""
Prompt Templates Module
Contains templates for various LLM prompts used in the assistant
"""

def create_mode_detection_prompt(user_input, conversation_context=None):
    """Create prompt for LLM to determine conversation mode"""
    if conversation_context:
        recent_context = "\n".join([
            f"User: {turn['content']}" if turn['role'] == 'user' else f"Assistant: {turn['content']}"
            for turn in conversation_context
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

def create_chat_response_prompt(user_input, conversation_context, persona):
    """Create a prompt for generating a chat response"""
    persona_traits = ", ".join(persona["traits"])
    speaking_style = persona["speaking_style"]
    
    context_str = ""
    if conversation_context:
        context_str = "\n".join([
            f"User: {item['content']}" if item['role'] == 'user' else f"Assistant: {item['content']}"
            for item in conversation_context
        ])
    
    prompt = f"""
You are {persona["name"]}, a voice assistant with the following traits: {persona_traits}.
Your speaking style is {speaking_style}.

Respond to the user in a natural, conversational way. Keep responses relatively brief (1-3 sentences) but engaging.
Remember details the user has shared in previous conversations and refer to them when relevant.

Previous conversation context:
{context_str}

Current user input: "{user_input}"

Generate a friendly, helpful response:
"""
    return prompt

def create_history_analysis_prompt(query):
    """Create a prompt for analyzing history-related queries"""
    prompt = f"""
Analyze this request about conversation history: "{query}"

Extract the following information in JSON format:
{{
    "query_type": "recent" or "date" or "search" or "statistics" or "summarize" or "unknown",
    "date": date in YYYY-MM-DD format if specified (null if not applicable),
    "time_period": "today", "yesterday", "this week", "this month", etc. (null if not applicable),
    "search_term": search term if specified (null if not applicable),
    "limit": number of results to return (default 5),
    "explanation": brief explanation of what the user is requesting
}}

Return ONLY the JSON object without any additional text.
"""
    return prompt

def create_persona_memory_prompt(user_input, conversation_context):
    """Create a prompt for extracting personal details to remember"""
    context_str = ""
    if conversation_context:
        context_str = "\n".join([
            f"User: {item['content']}" if item['role'] == 'user' else f"Assistant: {item['content']}"
            for item in conversation_context
        ])
    
    prompt = f"""
Analyze this conversation to extract any personal details about the user that should be remembered.

Previous conversation context:
{context_str}

Current user input: "{user_input}"

Extract the following information in JSON format:
{{
    "contains_personal_info": true/false,
    "details": {{
        "name": user's name if mentioned (null if not found),
        "preferences": list of preferences mentioned (empty list if none),
        "facts": list of personal facts mentioned (empty list if none),
        "relationships": mentioned family/friends/colleagues (empty list if none),
        "schedule": any mentioned events, appointments, etc. (empty list if none)
    }},
    "confidence": 0-1 float indicating certainty of extraction
}}

Return ONLY the JSON object without any additional text.
"""
    return prompt

def create_command_analysis_prompt(user_input, conversation_context=None, active_window=None, system_state=None):
    """Create a prompt for analyzing a potential command"""
    # Create system context for better analysis
    context_str = ""
    if conversation_context:
        context_str = "\n".join([
            f"User: {item['content']}" if item['role'] == 'user' else f"Assistant: {item['content']}"
            for item in conversation_context[-3:]  # Only use the most recent 3 turns
        ])
    
    system_context = ""
    if active_window:
        system_context += f"Active window: {active_window['title']} ({active_window['process_name']})\n"
    if system_state:
        system_context += f"System state: {system_state}\n"
    
    prompt = f"""
As a voice-activated Windows assistant, analyze this command: "{user_input}"

System Context:
{system_context}

Recent Conversation:
{context_str}

Determine:
1. Is this a direct command for the assistant to execute an action?
2. What specific task is the user requesting?
3. Is any additional context needed from the conversation history?

Extract the following information in JSON format:
{{
    "is_command": true/false,
    "command_type": One of [
        "open_app", "close_app", "window_control", "volume_control", "brightness_control", 
        "system_power", "screenshot", "calculator", "media_control", "search", 
        "file_operation", "email", "calendar", "web_search", "local_search", "history", "unknown"
    ],
    "sub_intent": relevant sub-category of command (e.g. "maximize" for window_control),
    "target": target of the command (app name, file name, etc.),
    "confidence": 0-1 float,
    "requires_confirmation": true/false,
    "needs_more_info": true/false,
    "explanation": "Brief explanation of the detected command"
}}

Return ONLY the JSON object without any additional text.
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