"""
Conversation History Module
Handles storage and retrieval of conversation interactions between user and assistant
"""

import os
import json
import sqlite3
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

@dataclass
class ConversationTurn:
    """Data structure for a single turn in a conversation"""
    id: str  # Unique ID for the turn
    timestamp: float  # Unix timestamp
    user_input: str  # What the user said
    assistant_response: str  # What the assistant replied
    mode: str  # Conversation mode (command, chat, mixed)
    detected_intents: List[str]  # List of intents detected, if any
    actions_performed: List[str]  # List of actions taken, if any
    context: Dict[str, Any]  # Additional context for this turn

class ConversationHistory:
    """Manages storage and retrieval of conversation history"""
    
    def __init__(self, db_path: str = None):
        """Initialize the conversation history manager"""
        if db_path is None:
            user_docs = os.path.join(os.path.expanduser("~"), "Documents")
            assistant_dir = os.path.join(user_docs, "DodoAssistant")
            os.makedirs(assistant_dir, exist_ok=True)
            db_path = os.path.join(assistant_dir, "conversation_history.db")
        
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Initialize the SQLite database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create the conversations table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversation_turns (
            id TEXT PRIMARY KEY,
            timestamp REAL,
            user_input TEXT,
            assistant_response TEXT,
            mode TEXT,
            detected_intents TEXT,
            actions_performed TEXT,
            context TEXT,
            date TEXT
        )
        ''')
        
        # Create indices for better search performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON conversation_turns(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_date ON conversation_turns(date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_mode ON conversation_turns(mode)')
        
        # Create full-text search index
        cursor.execute('CREATE VIRTUAL TABLE IF NOT EXISTS conversation_fts USING fts5(id, user_input, assistant_response)')
        
        conn.commit()
        conn.close()
    
    def add_turn(self, turn: ConversationTurn):
        """Add a new conversation turn to the history"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Convert lists and dictionaries to JSON strings
        detected_intents_json = json.dumps(turn.detected_intents)
        actions_performed_json = json.dumps(turn.actions_performed)
        context_json = json.dumps(turn.context)
        
        # Extract date in YYYY-MM-DD format for easier querying
        date_str = datetime.fromtimestamp(turn.timestamp).strftime('%Y-%m-%d')
        
        # Insert into main table
        cursor.execute('''
        INSERT INTO conversation_turns 
        (id, timestamp, user_input, assistant_response, mode, detected_intents, actions_performed, context, date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            turn.id, 
            turn.timestamp, 
            turn.user_input, 
            turn.assistant_response, 
            turn.mode, 
            detected_intents_json, 
            actions_performed_json, 
            context_json,
            date_str
        ))
        
        # Insert into FTS table for full-text search
        cursor.execute('''
        INSERT INTO conversation_fts (id, user_input, assistant_response)
        VALUES (?, ?, ?)
        ''', (turn.id, turn.user_input, turn.assistant_response))
        
        conn.commit()
        conn.close()
    
    def get_recent_turns(self, limit: int = 10) -> List[ConversationTurn]:
        """Get the most recent conversation turns"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT id, timestamp, user_input, assistant_response, mode, detected_intents, actions_performed, context
        FROM conversation_turns
        ORDER BY timestamp DESC
        LIMIT ?
        ''', (limit,))
        
        turns = []
        for row in cursor.fetchall():
            turn = ConversationTurn(
                id=row[0],
                timestamp=row[1],
                user_input=row[2],
                assistant_response=row[3],
                mode=row[4],
                detected_intents=json.loads(row[5]),
                actions_performed=json.loads(row[6]),
                context=json.loads(row[7])
            )
            turns.append(turn)
        
        conn.close()
        return turns
    
    def search_by_text(self, query: str, limit: int = 10) -> List[ConversationTurn]:
        """Search conversation history by text content"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Use FTS5 to search in both user input and assistant responses
        cursor.execute('''
        SELECT c.id, c.timestamp, c.user_input, c.assistant_response, c.mode, 
               c.detected_intents, c.actions_performed, c.context
        FROM conversation_turns c
        JOIN conversation_fts f ON c.id = f.id
        WHERE f.user_input MATCH ? OR f.assistant_response MATCH ?
        ORDER BY c.timestamp DESC
        LIMIT ?
        ''', (query, query, limit))
        
        turns = []
        for row in cursor.fetchall():
            turn = ConversationTurn(
                id=row[0],
                timestamp=row[1],
                user_input=row[2],
                assistant_response=row[3],
                mode=row[4],
                detected_intents=json.loads(row[5]),
                actions_performed=json.loads(row[6]),
                context=json.loads(row[7])
            )
            turns.append(turn)
        
        conn.close()
        return turns
    
    def search_by_date(self, date_str: str, limit: int = 10) -> List[ConversationTurn]:
        """Search conversation history by date (YYYY-MM-DD format)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT id, timestamp, user_input, assistant_response, mode, 
               detected_intents, actions_performed, context
        FROM conversation_turns
        WHERE date = ?
        ORDER BY timestamp DESC
        LIMIT ?
        ''', (date_str, limit))
        
        turns = []
        for row in cursor.fetchall():
            turn = ConversationTurn(
                id=row[0],
                timestamp=row[1],
                user_input=row[2],
                assistant_response=row[3],
                mode=row[4],
                detected_intents=json.loads(row[5]),
                actions_performed=json.loads(row[6]),
                context=json.loads(row[7])
            )
            turns.append(turn)
        
        conn.close()
        return turns
    
    def get_conversation_context(self, num_turns: int = 5) -> List[Dict]:
        """Get recent conversation context formatted for LLM input"""
        recent_turns = self.get_recent_turns(num_turns)
        context = []
        
        for turn in recent_turns:
            context.append({
                "role": "user",
                "content": turn.user_input
            })
            context.append({
                "role": "assistant",
                "content": turn.assistant_response
            })
        
        # Reverse to get chronological order
        return context[::-1]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get conversation history statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Total conversations
        cursor.execute('SELECT COUNT(*) FROM conversation_turns')
        total_turns = cursor.fetchone()[0]
        
        # Conversations by mode
        cursor.execute('''
        SELECT mode, COUNT(*) 
        FROM conversation_turns 
        GROUP BY mode
        ''')
        mode_counts = {mode: count for mode, count in cursor.fetchall()}
        
        # Conversations by date (last 7 days)
        cursor.execute('''
        SELECT date, COUNT(*) 
        FROM conversation_turns 
        GROUP BY date 
        ORDER BY date DESC 
        LIMIT 7
        ''')
        date_counts = {date: count for date, count in cursor.fetchall()}
        
        conn.close()
        
        return {
            "total_turns": total_turns,
            "mode_counts": mode_counts,
            "recent_date_counts": date_counts
        }