from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, ForeignKey, JSON, Numeric
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os
from dotenv import load_dotenv
load_dotenv()

# Database URL (Railway provides this for PostgreSQL)
DATABASE_URL = os.getenv("DATABASE_URL")

# Railway sometimes provides postgres:// URLs, but SQLAlchemy requires postgresql://
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=True)
    google_id = Column(String, unique=True, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    profile = relationship("UserProfile", back_populates="user", uselist=False)
    
    # Relationships
    conversations = relationship("Conversation", back_populates="user")
    calendar_connection = relationship("CalendarConnection", back_populates="user", uselist=False)
    reflections = relationship("Reflection", back_populates="user")
    insights = relationship("Insight", back_populates="user")

class CalendarConnection(Base):
    __tablename__ = "calendar_connections"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    google_credentials = Column(Text, nullable=True)  # Encrypted JSON
    is_connected = Column(Boolean, default=False)
    last_sync = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="calendar_connection")

class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, default="New Conversation")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Analytics columns
    overall_sentiment = Column(Numeric(5, 2), nullable=True)
    energy_trend = Column(Text, nullable=True)
    stress_indicators = Column(JSON, nullable=True)
    analyzed = Column(Boolean, default=False)
    last_analyzed_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation")

class PendingAction(Base):
    __tablename__ = "pending_actions"
    
    id = Column(Integer, primary_key=True, index=True)
    action_id = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action_type = Column(String, nullable=False)  # "create_event", "update_event", "delete_event"
    description = Column(Text, nullable=False)
    details = Column(JSON, nullable=False)  # Store action details as JSON
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)  # Auto-expire pending actions
    
    # Relationships
    user = relationship("User")

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    content = Column(Text, nullable=False)
    role = Column(String, nullable=False)  # 'user' or 'assistant'
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Analytics columns
    sentiment_score = Column(Numeric(5, 2), nullable=True)
    energy_level = Column(Integer, nullable=True)
    stress_level = Column(Integer, nullable=True)
    satisfaction_level = Column(Integer, nullable=True)
    analyzed = Column(Boolean, default=False)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    
class Reflection(Base):
    __tablename__ = "reflections"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    description = Column(Text, nullable=False)
    details = Column(JSON, nullable=False)  # Store action details as JSON
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="reflections")
    
class UserProfile(Base):
    __tablename__ = "user_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    
    # Personal goals and preferences
    short_term_goals = Column(JSON, nullable=True)  # List of goals for next 1-3 months
    long_term_goals = Column(JSON, nullable=True)   # List of goals for 6+ months
    work_preferences = Column(JSON, nullable=True)  # Work style, peak hours, etc.
    personal_interests = Column(JSON, nullable=True) # Hobbies, interests
    
    # Reflection preferences
    reflection_frequency = Column(String, default="weekly")  # daily, weekly, monthly
    reflection_focus_areas = Column(JSON, nullable=True)     # productivity, wellness, growth
    
    # Communication style
    communication_tone = Column(String, default="professional") # casual, professional, encouraging
    preferred_insights = Column(JSON, nullable=True)  # types of insights user wants
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="profile")

class Insight(Base):
    __tablename__ = "insights"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)  # The actual insights text
    analysis_period = Column(Integer, nullable=False)  # Days analyzed (7, 30, etc.)
    insights_type = Column(String, default="comprehensive")  # comprehensive, productivity, etc.
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="insights")


if __name__ == "__main__":
    # Create tables
    Base.metadata.create_all(bind=engine)