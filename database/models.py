from sqlalchemy import Column, String, Integer, Float, DateTime, JSON, Boolean, ForeignKey, Text, Enum as SQLEnum, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()

class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    SUSPENDED = "suspended"

class ITRStatus(str, enum.Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    PROCESSED = "processed"

class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class User(Base):
    __tablename__ = "users"
    
    user_id = Column(String, primary_key=True, index=True)
    user_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=True)
    phone = Column(String, nullable=True)
    pan = Column(String(10), unique=True, nullable=True)
    aadhaar = Column(String, nullable=True)
    status = Column(SQLEnum(UserStatus), default=UserStatus.ACTIVE)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan")
    itr_filings = relationship("ITRFiling", back_populates="user", cascade="all, delete-orphan")
    capital_gains = relationship("CapitalGains", back_populates="user", cascade="all, delete-orphan")
    conversation_sessions = relationship("ConversationSession", back_populates="user", cascade="all, delete-orphan")
    user_memory = relationship("UserMemory", back_populates="user", uselist=False, cascade="all, delete-orphan")

class Document(Base):
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    document_type = Column(String, nullable=False)  # e.g., 'invoice', 'form16', 'salary_slip'
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer, nullable=True)
    extracted_data = Column(JSON, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="documents")

class ITRFiling(Base):
    __tablename__ = "itr_filings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    assessment_year = Column(String, nullable=False)
    itr_type = Column(String, nullable=False)  # ITR-1, ITR-2, etc.
    status = Column(SQLEnum(ITRStatus), default=ITRStatus.DRAFT)
    
    # Session IDs
    session_id = Column(String, nullable=True)
    client_reference_id = Column(String, nullable=True)
    validation_id = Column(String, nullable=True)
    draft_id = Column(String, nullable=True)
    acknowledgement_number = Column(String, nullable=True)
    
    # ITR Data
    itr_data = Column(JSON, nullable=True)
    prefill_data = Column(JSON, nullable=True)
    validation_errors = Column(JSON, nullable=True)
    verification_mode = Column(String, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    validated_at = Column(DateTime, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="itr_filings")

class CapitalGains(Base):
    __tablename__ = "capital_gains"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    
    # Transaction details
    asset_type = Column(String, nullable=False)  # 'equity', 'mutual_fund', 'property', 'bonds', etc.
    transaction_type = Column(String, nullable=False)  # 'buy', 'sell'
    
    # Buy details
    purchase_date = Column(DateTime, nullable=False)
    purchase_price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)
    
    # Sell details (if sold)
    sale_date = Column(DateTime, nullable=True)
    sale_price = Column(Float, nullable=True)
    
    # Computed fields
    holding_period_days = Column(Integer, nullable=True)
    is_long_term = Column(Boolean, nullable=True)  # True if holding > threshold
    gain_loss = Column(Float, nullable=True)
    tax_applicable = Column(Float, nullable=True)
    
    # Additional metadata
    asset_name = Column(String, nullable=True)  # Stock name, property address, etc.
    notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="capital_gains")

# ============================================================================
# MEMORY MODELS (Short-term & Long-term)
# ============================================================================

class ConversationSession(Base):
    """Short-term memory: stores conversation sessions"""
    __tablename__ = "conversation_sessions"
    
    session_id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    
    # Session metadata
    title = Column(String, nullable=True)  # Auto-generated from first message
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    started_at = Column(DateTime, default=datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    
    # Summary for long-term memory
    session_summary = Column(Text, nullable=True)
    key_intents = Column(JSON, nullable=True)  # ["file_gst", "tax_query", etc.]
    
    # Relationships
    user = relationship("User", back_populates="conversation_sessions")
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan", order_by="Message.created_at")
    
    __table_args__ = (
        Index('idx_user_active_sessions', 'user_id', 'is_active'),
    )

class Message(Base):
    """Individual messages in a conversation session"""
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("conversation_sessions.session_id"), nullable=False)
    
    # Message content
    role = Column(SQLEnum(MessageRole), nullable=False)
    content = Column(Text, nullable=False)
    
    # Metadata
    token_count = Column(Integer, nullable=True)
    intent = Column(String, nullable=True)  # Detected intent
    entities = Column(JSON, nullable=True)  # Extracted entities (dates, amounts, etc.)
    
    # Embeddings for semantic search (stored as JSON array)
    embedding = Column(JSON, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    session = relationship("ConversationSession", back_populates="messages")
    
    __table_args__ = (
        Index('idx_session_messages', 'session_id', 'created_at'),
    )

class UserMemory(Base):
    """Long-term memory: persistent user context across all conversations"""
    __tablename__ = "user_memory"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.user_id"), unique=True, nullable=False)
    
    # User profile and preferences
    profile_summary = Column(Text, nullable=True)  # AI-generated summary of user
    business_type = Column(String, nullable=True)  # "freelancer", "business", "salaried", etc.
    tax_regime = Column(String, nullable=True)  # "old", "new"
    
    # Financial context
    annual_income_range = Column(String, nullable=True)
    has_business_income = Column(Boolean, default=False)
    has_capital_gains = Column(Boolean, default=False)
    has_house_property = Column(Boolean, default=False)
    
    # User preferences
    communication_style = Column(String, nullable=True)  # "formal", "casual", "technical"
    language_preference = Column(String, nullable=True)
    
    # Entity memory (important facts about user)
    entities = Column(JSON, nullable=True)  # {"gstin": "...", "business_name": "...", etc.}
    
    # Demographics (extracted from conversations)
    demographics = Column(JSON, nullable=True)  # {"age": "...", "gender": "...", "occupation": "...", "location": "...", "marital_status": "...", etc.}
    
    # Conversation insights
    frequent_intents = Column(JSON, nullable=True)  # ["file_gst", "tax_query", ...]
    last_topics = Column(JSON, nullable=True)  # Recent topics discussed
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_summarized = Column(DateTime, nullable=True)  # When memory was last updated
    
    # Relationships
    user = relationship("User", back_populates="user_memory")
