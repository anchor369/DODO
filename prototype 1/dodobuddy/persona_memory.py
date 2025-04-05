"""
Persona Memory Module
Manages user-specific information and preferences
"""

import os
import json
import time
from typing import Dict, List, Any, Optional
from prompt_templates import create_persona_memory_prompt

class PersonaMemory:
    """Manages persistent memory of user preferences and details"""
    
    def __init__(self, llm, memory_file=None):
        """Initialize the persona memory manager"""
        self.llm = llm
        
        if memory_file is None:
            user_docs = os.path.join(os.path.expanduser("~"), "Documents")
            assistant_dir = os.path.join(user_docs, "DodoAssistant")
            os.makedirs(assistant_dir, exist_ok=True)
            memory_file = os.path.join(assistant_dir, "persona_memory.json")
        
        self.memory_file = memory_file
        self.memory = self._load_memory()
        
        # Memory categories
        self._ensure_categories()
    
    def _load_memory(self) -> Dict[str, Any]:
        """Load memory from file"""
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading memory file: {e}")
                return self._create_default_memory()
        else:
            return self._create_default_memory()
    
    def _create_default_memory(self) -> Dict[str, Any]:
        """Create default memory structure"""
        return {
            "user": {
                "name": None,
                "nicknames": [],
                "preferences": {},
                "important_dates": {},
                "relationships": {},
                "likes": [],
                "dislikes": [],
                "facts": []
            },
            "interaction": {
                "first_interaction": time.time(),
                "last_interaction": time.time(),
                "total_interactions": 0,
                "frequent_topics": {},
                "common_commands": {}
            },
            "meta": {
                "version": "1.0",
                "created": time.time(),
                "last_updated": time.time()
            }
        }
    
    def _ensure_categories(self):
        """Ensure all necessary categories exist in memory"""
        default = self._create_default_memory()
        
        # Check top level categories
        for key in default:
            if key not in self.memory:
                self.memory[key] = default[key]
        
        # Check user subcategories
        for key in default["user"]:
            if key not in self.memory["user"]:
                self.memory["user"][key] = default["user"][key]
        
        # Check interaction subcategories
        for key in default["interaction"]:
            if key not in self.memory["interaction"]:
                self.memory["interaction"][key] = default["interaction"][key]
    
    def save_memory(self):
        """Save memory to file"""
        self.memory["meta"]["last_updated"] = time.time()
        
        try:
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(self.memory, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving memory file: {e}")
            return False
    
    def update_from_conversation(self, user_input: str, conversation_context=None) -> bool:
        """Update memory based on conversation content"""
        if not user_input:
            return False
        
        # Create memory extraction prompt
        prompt = create_persona_memory_prompt(user_input, conversation_context)
        
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
            
            memory_data = json.loads(json_str)
            
            # Only update if personal information was found with reasonable confidence
            if memory_data.get("contains_personal_info", False) and memory_data.get("confidence", 0) > 0.7:
                details = memory_data.get("details", {})
                
                # Update user name if provided
                if details.get("name") and details["name"] != self.memory["user"]["name"]:
                    self.memory["user"]["name"] = details["name"]
                
                # Update preferences
                for pref in details.get("preferences", []):
                    if pref not in self.memory["user"]["preferences"]:
                        self.memory["user"]["preferences"][pref] = time.time()
                
                # Update facts
                for fact in details.get("facts", []):
                    if fact not in self.memory["user"]["facts"]:
                        self.memory["user"]["facts"].append(fact)
                
                # Update relationships
                for relation in details.get("relationships", []):
                    if isinstance(relation, dict):
                        # If it's a structured relation
                        name = relation.get("name")
                        if name and name not in self.memory["user"]["relationships"]:
                            self.memory["user"]["relationships"][name] = relation
                    elif isinstance(relation, str):
                        # If it's just a name
                        if relation not in self.memory["user"]["relationships"]:
                            self.memory["user"]["relationships"][relation] = {"name": relation, "mentioned_at": time.time()}
                
                # Update schedule/important dates
                for event in details.get("schedule", []):
                    if isinstance(event, dict) and "date" in event and "description" in event:
                        date_key = event["date"]
                        if date_key not in self.memory["user"]["important_dates"]:
                            self.memory["user"]["important_dates"][date_key] = event
                
                # Update interaction data
                self.memory["interaction"]["last_interaction"] = time.time()
                self.memory["interaction"]["total_interactions"] += 1
                
                # Save updates
                self.save_memory()
                return True
            
            # Still update interaction count even if no personal info was found
            self.memory["interaction"]["last_interaction"] = time.time()
            self.memory["interaction"]["total_interactions"] += 1
            self.save_memory()
            
            return False
            
        except Exception as e:
            print(f"Error updating memory from conversation: {e}")
            return False
    
    def get_memory_context(self) -> Dict[str, Any]:
        """Get memory context for conversation enhancements"""
        context = {
            "user_name": self.memory["user"]["name"],
            "preferences": self.memory["user"]["preferences"],
            "important_facts": self.memory["user"]["facts"][:5],  # Top 5 facts
            "key_relationships": list(self.memory["user"]["relationships"].keys())[:5],  # Top 5 relationships
            "interaction_count": self.memory["interaction"]["total_interactions"]
        }
        return context
    
    def get_formatted_memory(self) -> str:
        """Get a formatted string representation of memory for review"""
        result = "USER MEMORY:\n"
        
        user = self.memory["user"]
        if user["name"]:
            result += f"• Name: {user['name']}\n"
        
        if user["preferences"]:
            result += "• Preferences:\n"
            for pref, timestamp in user["preferences"].items():
                date_str = time.strftime("%Y-%m-%d", time.localtime(timestamp))
                result += f"  - {pref} (noted on {date_str})\n"
        
        if user["facts"]:
            result += "• Personal Facts:\n"
            for fact in user["facts"]:
                result += f"  - {fact}\n"
        
        if user["relationships"]:
            result += "• Relationships:\n"
            for name, details in user["relationships"].items():
                if isinstance(details, dict) and "relationship" in details:
                    result += f"  - {name} ({details['relationship']})\n"
                else:
                    result += f"  - {name}\n"
        
        if user["important_dates"]:
            result += "• Important Dates:\n"
            for date, event in user["important_dates"].items():
                result += f"  - {date}: {event['description']}\n"
        
        # Interaction statistics
        interaction = self.memory["interaction"]
        result += "\nINTERACTION STATISTICS:\n"
        result += f"• First interaction: {time.strftime('%Y-%m-%d', time.localtime(interaction['first_interaction']))}\n"
        result += f"• Last interaction: {time.strftime('%Y-%m-%d %H:%M', time.localtime(interaction['last_interaction']))}\n"
        result += f"• Total interactions: {interaction['total_interactions']}\n"
        
        return result
    
    def clear_memory(self, category=None):
        """Clear memory (complete or by category)"""
        if category is None:
            # Reset completely
            self.memory = self._create_default_memory()
        elif category == "user":
            # Reset user data
            self.memory["user"] = self._create_default_memory()["user"]
        elif category == "interaction":
            # Reset interaction data
            self.memory["interaction"] = self._create_default_memory()["interaction"]
        
        self.save_memory()
        return True