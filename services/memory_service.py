"""
Memory Service for TaxAI Bot
Handles short-term (session-based) and long-term (persistent) memory
"""

from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
import json

from database.models import (
    ConversationSession, Message, UserMemory, MessageRole, User
)
from database.connection import get_db


class MemoryService:
    """Manages conversation memory and user context"""
    
    # Short-term memory window (messages to keep in context)
    SHORT_TERM_WINDOW = 10  # Last 10 messages
    
    # Session timeout (inactive sessions)
    SESSION_TIMEOUT_HOURS = 2
    
    def __init__(self, db: Session):
        self.db = db
    
    # ========================================================================
    # SHORT-TERM MEMORY (Conversation Sessions)
    # ========================================================================
    
    def create_session(self, user_id: str, session_id: str) -> ConversationSession:
        """Create a new conversation session"""
        session = ConversationSession(
            session_id=session_id,
            user_id=user_id,
            is_active=True
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session
    
    def get_or_create_session(self, user_id: str, session_id: str) -> ConversationSession:
        """Get existing session or create new one"""
        session = self.db.query(ConversationSession).filter(
            ConversationSession.session_id == session_id
        ).first()
        
        if not session:
            session = self.create_session(user_id, session_id)
        
        return session
    
    def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        intent: Optional[str] = None,
        entities: Optional[Dict] = None
    ) -> Message:
        """Add a message to the conversation"""
        message = Message(
            session_id=session_id,
            role=role,
            content=content,
            intent=intent,
            entities=entities,
            token_count=len(content.split())  # Rough estimate
        )
        
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        
        # Update session activity
        session = self.db.query(ConversationSession).filter(
            ConversationSession.session_id == session_id
        ).first()
        if session:
            session.last_activity = datetime.utcnow()
            
            # Set title from first user message if not set
            if not session.title and role == MessageRole.USER:
                session.title = content[:50] + "..." if len(content) > 50 else content
            
            self.db.commit()
        
        return message
    
    def get_recent_messages(
        self,
        session_id: str,
        limit: int = None
    ) -> List[Message]:
        """Get recent messages from a session (short-term memory window)"""
        if limit is None:
            limit = self.SHORT_TERM_WINDOW
        
        messages = self.db.query(Message).filter(
            Message.session_id == session_id
        ).order_by(desc(Message.created_at)).limit(limit).all()
        
        return list(reversed(messages))  # Return in chronological order
    
    def get_session_history(self, session_id: str) -> List[Dict[str, str]]:
        """Get conversation history formatted for LLM"""
        messages = self.get_recent_messages(session_id)
        
        return [
            {
                "role": msg.role.value,
                "content": msg.content
            }
            for msg in messages
        ]
    
    def end_session(self, session_id: str):
        """Mark session as ended and generate summary"""
        session = self.db.query(ConversationSession).filter(
            ConversationSession.session_id == session_id
        ).first()
        
        if session:
            session.is_active = False
            session.ended_at = datetime.utcnow()
            
            # Generate session summary for long-term memory
            # This can be enhanced with LLM summarization
            messages = self.get_recent_messages(session_id, limit=100)
            
            # Extract intents
            intents = list(set([msg.intent for msg in messages if msg.intent]))
            session.key_intents = intents
            
            # Simple summary (can be replaced with LLM)
            session.session_summary = f"Session with {len(messages)} messages about {', '.join(intents) if intents else 'general queries'}"
            
            self.db.commit()
    
    def cleanup_old_sessions(self, user_id: str):
        """End inactive sessions"""
        timeout = datetime.utcnow() - timedelta(hours=self.SESSION_TIMEOUT_HOURS)
        
        old_sessions = self.db.query(ConversationSession).filter(
            and_(
                ConversationSession.user_id == user_id,
                ConversationSession.is_active == True,
                ConversationSession.last_activity < timeout
            )
        ).all()
        
        for session in old_sessions:
            self.end_session(session.session_id)
    
    # ========================================================================
    # LONG-TERM MEMORY (User Context)
    # ========================================================================
    
    def get_user_memory(self, user_id: str) -> Optional[UserMemory]:
        """Get user's long-term memory"""
        return self.db.query(UserMemory).filter(
            UserMemory.user_id == user_id
        ).first()
    
    def create_user_memory(self, user_id: str) -> UserMemory:
        """Initialize user memory"""
        memory = UserMemory(user_id=user_id)
        self.db.add(memory)
        self.db.commit()
        self.db.refresh(memory)
        return memory
    
    def get_or_create_user_memory(self, user_id: str) -> UserMemory:
        """Get or create user memory"""
        memory = self.get_user_memory(user_id)
        if not memory:
            memory = self.create_user_memory(user_id)
        return memory
    
    def update_user_memory(
        self,
        user_id: str,
        updates: Dict[str, Any]
    ):
        """Update user's long-term memory"""
        memory = self.get_or_create_user_memory(user_id)
        
        for key, value in updates.items():
            if hasattr(memory, key):
                setattr(memory, key, value)
        
        memory.updated_at = datetime.utcnow()
        self.db.commit()
    
    def add_entity(self, user_id: str, key: str, value: Any):
        """Add an entity to user's long-term memory"""
        memory = self.get_or_create_user_memory(user_id)
        
        entities = memory.entities or {}
        entities[key] = value
        memory.entities = entities
        memory.updated_at = datetime.utcnow()
        
        self.db.commit()
    
    def get_entity(self, user_id: str, key: str) -> Optional[Any]:
        """Retrieve an entity from user's memory"""
        memory = self.get_user_memory(user_id)
        if memory and memory.entities:
            return memory.entities.get(key)
        return None
    
    def track_intent(self, user_id: str, intent: str):
        """Track user's frequent intents"""
        memory = self.get_or_create_user_memory(user_id)
        
        frequent_intents = memory.frequent_intents or {}
        frequent_intents[intent] = frequent_intents.get(intent, 0) + 1
        memory.frequent_intents = frequent_intents
        
        self.db.commit()
    
    def update_profile_summary(self, user_id: str, llm_summary: str):
        """Update user profile summary (generated by LLM)"""
        memory = self.get_or_create_user_memory(user_id)
        memory.profile_summary = llm_summary
        memory.last_summarized = datetime.utcnow()
        self.db.commit()
    
    def update_demographics(self, user_id: str, demographics: Dict[str, Any]):
        """Update user demographics"""
        memory = self.get_or_create_user_memory(user_id)
        
        # Merge with existing demographics
        existing_demographics = memory.demographics or {}
        existing_demographics.update(demographics)
        
        memory.demographics = existing_demographics
        memory.updated_at = datetime.utcnow()
        self.db.commit()
    
    def get_demographics(self, user_id: str) -> Dict[str, Any]:
        """Get user demographics"""
        memory = self.get_user_memory(user_id)
        if memory and memory.demographics:
            return memory.demographics
        return {}

    
    # ========================================================================
    # CONTEXT RETRIEVAL (for LLM)
    # ========================================================================
    
    def get_full_context(self, user_id: str, session_id: str) -> Dict[str, Any]:
        """
        Get complete context for LLM:
        - Short-term: Recent conversation
        - Long-term: User profile and preferences
        """
        # Short-term memory
        recent_messages = self.get_session_history(session_id)
        
        # Long-term memory
        user_memory = self.get_user_memory(user_id)
        
        context = {
            "conversation_history": recent_messages,
            "user_profile": None,
            "entities": {},
            "demographics": {},
            "preferences": {}
        }
        
        if user_memory:
            context["user_profile"] = user_memory.profile_summary
            context["entities"] = user_memory.entities or {}
            context["demographics"] = user_memory.demographics or {}
            context["preferences"] = {
                "business_type": user_memory.business_type,
                "tax_regime": user_memory.tax_regime,
                "communication_style": user_memory.communication_style,
                "language": user_memory.language_preference
            }
            context["financial_context"] = {
                "has_business_income": user_memory.has_business_income,
                "has_capital_gains": user_memory.has_capital_gains,
                "has_house_property": user_memory.has_house_property
            }
        
        return context
    
    def get_context_summary(self, user_id: str, session_id: str) -> str:
        """Get a text summary of context for system prompt"""
        context = self.get_full_context(user_id, session_id)
        
        summary_parts = []
        
        if context["user_profile"]:
            summary_parts.append(f"User Profile: {context['user_profile']}")
        
        if context["demographics"]:
            demo_str = ", ".join([f"{k}: {v}" for k, v in context["demographics"].items()])
            summary_parts.append(f"Demographics: {demo_str}")
        
        if context["entities"]:
            entities_str = ", ".join([f"{k}: {v}" for k, v in context["entities"].items()])
            summary_parts.append(f"Known Entities: {entities_str}")
        
        prefs = context["preferences"]
        if any(prefs.values()):
            pref_str = ", ".join([f"{k}: {v}" for k, v in prefs.items() if v])
            summary_parts.append(f"Preferences: {pref_str}")
        
        return "\n".join(summary_parts) if summary_parts else "No prior context available."
    
    # ========================================================================
    # SESSION MANAGEMENT
    # ========================================================================
    
    def get_user_sessions(self, user_id: str, active_only: bool = False) -> List[ConversationSession]:
        """Get all user sessions"""
        query = self.db.query(ConversationSession).filter(
            ConversationSession.user_id == user_id
        )
        
        if active_only:
            query = query.filter(ConversationSession.is_active == True)
        
        return query.order_by(desc(ConversationSession.last_activity)).all()
    
    def delete_session(self, session_id: str):
        """Delete a session and its messages"""
        session = self.db.query(ConversationSession).filter(
            ConversationSession.session_id == session_id
        ).first()
        
        if session:
            self.db.delete(session)
            self.db.commit()
