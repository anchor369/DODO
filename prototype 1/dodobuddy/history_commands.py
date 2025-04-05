"""
History Commands
Handlers for conversation history-related commands
"""

import time
from datetime import datetime, timedelta
from typing import List, Dict, Any
import os

from conversation_history import ConversationHistory, ConversationTurn

def format_conversation_turns(turns: List[ConversationTurn], include_mode=False) -> str:
    """Format conversation turns for display or speech"""
    if not turns:
        return "No conversations found."
    
    result = []
    
    for i, turn in enumerate(turns):
        date_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(turn.timestamp))
        entry = f"{i+1}. On {date_str}:"
        
        if include_mode:
            entry += f" [{turn.mode}]"
            
        entry += f"\n   You: {turn.user_input}"
        entry += f"\n   Dodo: {turn.assistant_response}"
        
        result.append(entry)
    
    return "\n\n".join(result)

def handle_history_command(command: str, history: ConversationHistory, llm) -> str:
    """Process and respond to history-related commands"""
    # Quick check for common history commands
    if "show history" in command.lower() or "recent conversations" in command.lower():
        recent_turns = history.get_recent_turns(5)
        return format_conversation_turns(recent_turns)
    
    elif "today's conversations" in command.lower() or "today's history" in command.lower():
        today = datetime.now().strftime("%Y-%m-%d")
        today_turns = history.search_by_date(today, 10)
        return format_conversation_turns(today_turns)
    
    elif "yesterday's conversations" in command.lower() or "yesterday's history" in command.lower():
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        yesterday_turns = history.search_by_date(yesterday, 10)
        return format_conversation_turns(yesterday_turns)
    
    # Use LLM for more complex queries
    prompt = f"""
Analyze this history-related command: "{command}"

Extract the following information in JSON format:
{{
    "query_type": "recent" or "date" or "search" or "statistics" or "unknown",
    "date": date in YYYY-MM-DD format if specified (null if not applicable),
    "search_term": search term if specified (null if not applicable),
    "limit": number of results to return (default 5),
    "explanation": brief explanation of what the user is requesting
}}

Return ONLY the JSON object.
"""
    
    try:
        response = llm.generate_content(prompt)
        response_text = response.text
        
        # Extract JSON
        if '```json' in response_text:
            json_str = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            json_str = response_text.split('```')[1].strip()
        else:
            json_str = response_text.strip()
        
        import json
        query_params = json.loads(json_str)
        
        # Process based on query type
        if query_params["query_type"] == "recent":
            limit = query_params.get("limit", 5)
            recent_turns = history.get_recent_turns(limit)
            return format_conversation_turns(recent_turns)
        
        elif query_params["query_type"] == "date":
            date_str = query_params.get("date")
            limit = query_params.get("limit", 10)
            
            if not date_str:
                return "I need a specific date to show conversations from that day."
            
            date_turns = history.search_by_date(date_str, limit)
            if not date_turns:
                return f"No conversations found for {date_str}."
            
            return format_conversation_turns(date_turns)
        
        elif query_params["query_type"] == "search":
            search_term = query_params.get("search_term")
            limit = query_params.get("limit", 10)
            
            if not search_term:
                return "I need a search term to look for in our conversation history."
            
            search_turns = history.search_by_text(search_term, limit)
            if not search_turns:
                return f"No conversations found matching '{search_term}'."
            
            return format_conversation_turns(search_turns)
        
        elif query_params["query_type"] == "statistics":
            stats = history.get_statistics()
            
            # Format statistics for a response
            stats_response = "Here's a summary of our conversation history:\n\n"
            stats_response += f"• Total conversations: {stats['total_turns']}\n"
            
            if 'mode_counts' in stats:
                stats_response += "• Conversation types:\n"
                for mode, count in stats['mode_counts'].items():
                    mode_name = "Commands" if mode == "command" else "Chats" if mode == "chat" else "Mixed conversations"
                    stats_response += f"  - {mode_name}: {count}\n"
            
            if 'recent_date_counts' in stats:
                stats_response += "• Recent activity:\n"
                for date, count in stats['recent_date_counts'].items():
                    stats_response += f"  - {date}: {count} conversations\n"
            
            return stats_response
        
        else:
            return "I'm not sure how to process that history request. You can ask for recent conversations, search for specific topics, or request statistics about our conversations."
    
    except Exception as e:
        print(f"Error processing history command: {e}")
        return "I encountered an error while processing your history request. Please try again with a simpler query."

def save_history_to_file(history: ConversationHistory, file_path: str = None) -> str:
    """Save conversation history to a file"""
    if not file_path:
        user_docs = os.path.join(os.path.expanduser("~"), "Documents")
        assistant_dir = os.path.join(user_docs, "DodoAssistant")
        os.makedirs(assistant_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join(assistant_dir, f"conversation_history_{timestamp}.txt")
    
    try:
        # Get all history for export
        turns = history.get_recent_turns(1000)  # Large number to get most/all history
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("DODO ASSISTANT CONVERSATION HISTORY\n")
            f.write("=================================\n\n")
            
            for turn in turns:
                date_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(turn.timestamp))
                f.write(f"Date: {date_str}\n")
                f.write(f"Mode: {turn.mode}\n")
                f.write(f"User: {turn.user_input}\n")
                f.write(f"Dodo: {turn.assistant_response}\n")
                
                if turn.actions_performed:
                    f.write(f"Actions: {', '.join(turn.actions_performed)}\n")
                
                f.write("\n" + "-"*50 + "\n\n")
        
        return f"Conversation history saved to {file_path}"
    
    except Exception as e:
        print(f"Error saving history to file: {e}")
        return "I encountered an error while trying to save the conversation history."