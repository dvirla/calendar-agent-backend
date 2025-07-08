from sqlalchemy.orm import Session
from .database import SessionLocal, User, Conversation, Message, CalendarConnection, PendingAction, UserProfile, Insight
from typing import Optional, List, Dict, Any
import json
from cryptography.fernet import Fernet
from datetime import datetime, timedelta
import os

# Encryption key for storing sensitive data
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", Fernet.generate_key())
cipher_suite = Fernet(ENCRYPTION_KEY)

def get_db():
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class UserService:
    @staticmethod
    def get_user_by_email(db: Session, email: str) -> Optional[User]:
        return db.query(User).filter(User.email == email).first()
    
    @staticmethod
    def get_user_by_google_id(db: Session, google_id: str) -> Optional[User]:
        return db.query(User).filter(User.google_id == google_id).first()
    
    @staticmethod
    def create_user(db: Session, email: str, full_name: str = None, google_id: str = None) -> User:
        user = User(email=email, full_name=full_name, google_id=google_id)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

class ConversationService:
    @staticmethod
    def create_conversation(db: Session, user_id: int, title: str = "New Conversation") -> Conversation:
        conversation = Conversation(user_id=user_id, title=title)
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        return conversation
    
    @staticmethod
    def get_user_conversations(db: Session, user_id: int) -> List[Conversation]:
        return db.query(Conversation).filter(Conversation.user_id == user_id).order_by(Conversation.updated_at.desc()).all()
    
    @staticmethod
    def add_message(db: Session, conversation_id: int, content: str, role: str) -> Message:
        message = Message(conversation_id=conversation_id, content=content, role=role)
        db.add(message)
        
        # Update conversation timestamp
        conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if conversation:
            conversation.updated_at = message.timestamp
        
        db.commit()
        db.refresh(message)
        return message
    
    @staticmethod
    def get_conversation_messages(db: Session, conversation_id: int) -> List[Message]:
        return db.query(Message).filter(Message.conversation_id == conversation_id).order_by(Message.timestamp).all()
    
    @staticmethod
    def get_user_conversations_since(db: Session, user_id: int, since: datetime) -> List[Conversation]:
        return db.query(Conversation).filter(
            Conversation.user_id == user_id,
            Conversation.created_at >= since
        ).order_by(Conversation.created_at.desc()).all()

class CalendarService:
    @staticmethod
    def save_calendar_credentials(db: Session, user_id: int, credentials_dict: dict):
        # Encrypt credentials before storing
        credentials_json = json.dumps(credentials_dict)
        encrypted_credentials = cipher_suite.encrypt(credentials_json.encode())
        
        # Update or create calendar connection
        connection = db.query(CalendarConnection).filter(CalendarConnection.user_id == user_id).first()
        if connection:
            connection.google_credentials = encrypted_credentials.decode()
            connection.is_connected = True
        else:
            connection = CalendarConnection(
                user_id=user_id,
                google_credentials=encrypted_credentials.decode(),
                is_connected=True
            )
            db.add(connection)
        
        db.commit()
        db.refresh(connection)
        return connection
    
    @staticmethod
    def get_calendar_credentials(db: Session, user_id: int) -> Optional[dict]:
        connection = db.query(CalendarConnection).filter(CalendarConnection.user_id == user_id).first()
        if connection and connection.google_credentials:
            try:
                decrypted_data = cipher_suite.decrypt(connection.google_credentials.encode())
                return json.loads(decrypted_data.decode())
            except:
                return None
        return None

class PendingActionService:
    @staticmethod
    def create_pending_action(
        db: Session, 
        user_id: int,
        action_id: str, 
        action_type: str, 
        description: str, 
        details: Dict[str, Any],
        expires_in_minutes: int = 30
    ) -> PendingAction:
        expires_at = datetime.utcnow() + timedelta(minutes=expires_in_minutes)
        
        pending_action = PendingAction(
            action_id=action_id,
            user_id=user_id,
            action_type=action_type,
            description=description,
            details=details,
            expires_at=expires_at
        )
        
        db.add(pending_action)
        db.commit()
        db.refresh(pending_action)
        return pending_action
    
    @staticmethod
    def get_user_pending_actions(db: Session, user_id: int) -> List[PendingAction]:
        # Clean up expired actions first
        PendingActionService.cleanup_expired_actions(db)
        
        return db.query(PendingAction).filter(
            PendingAction.user_id == user_id,
            PendingAction.expires_at > datetime.utcnow()
        ).all()
    
    @staticmethod
    def get_pending_action(db: Session, action_id: str, user_id: int) -> Optional[PendingAction]:
        return db.query(PendingAction).filter(
            PendingAction.action_id == action_id,
            PendingAction.user_id == user_id,
            PendingAction.expires_at > datetime.utcnow()
        ).first()
    
    @staticmethod
    def delete_pending_action(db: Session, action_id: str, user_id: int) -> bool:
        action = db.query(PendingAction).filter(
            PendingAction.action_id == action_id,
            PendingAction.user_id == user_id
        ).first()
        
        if action:
            db.delete(action)
            db.commit()
            return True
        return False
    
    @staticmethod
    def cleanup_expired_actions(db: Session):
        expired_actions = db.query(PendingAction).filter(
            PendingAction.expires_at <= datetime.utcnow()
        ).all()
        
        for action in expired_actions:
            db.delete(action)
        
        if expired_actions:
            db.commit()

class UserProfileService:
    """Service for managing user profiles and preferences"""
    
    @staticmethod
    def get_user_profile(db: Session, user_id: int) -> Optional[UserProfile]:
        """Get user profile by user ID"""
        return db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    
    @staticmethod
    def create_user_profile(db: Session, user_id: int, profile_data: Dict[str, Any]) -> UserProfile:
        """Create a new user profile"""
        profile = UserProfile(
            user_id=user_id,
            short_term_goals=profile_data.get("short_term_goals", []),
            long_term_goals=profile_data.get("long_term_goals", []),
            work_preferences=profile_data.get("work_preferences", {}),
            personal_interests=profile_data.get("personal_interests", []),
            reflection_frequency=profile_data.get("reflection_frequency", "weekly"),
            reflection_focus_areas=profile_data.get("reflection_focus_areas", []),
            communication_tone=profile_data.get("communication_tone", "professional"),
            preferred_insights=profile_data.get("preferred_insights", [])
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile
    
    @staticmethod
    def update_user_profile(db: Session, user_id: int, profile_data: Dict[str, Any]) -> Optional[UserProfile]:
        """Update existing user profile"""
        profile = UserProfileService.get_user_profile(db, user_id)
        
        if not profile:
            # Create new profile if it doesn't exist
            return UserProfileService.create_user_profile(db, user_id, profile_data)
        
        # Update only provided fields
        if "short_term_goals" in profile_data:
            profile.short_term_goals = profile_data["short_term_goals"]
        if "long_term_goals" in profile_data:
            profile.long_term_goals = profile_data["long_term_goals"]
        if "work_preferences" in profile_data:
            profile.work_preferences = profile_data["work_preferences"]
        if "personal_interests" in profile_data:
            profile.personal_interests = profile_data["personal_interests"]
        if "reflection_frequency" in profile_data:
            profile.reflection_frequency = profile_data["reflection_frequency"]
        if "reflection_focus_areas" in profile_data:
            profile.reflection_focus_areas = profile_data["reflection_focus_areas"]
        if "communication_tone" in profile_data:
            profile.communication_tone = profile_data["communication_tone"]
        if "preferred_insights" in profile_data:
            profile.preferred_insights = profile_data["preferred_insights"]
        
        profile.updated_at = datetime.now()
        db.commit()
        db.refresh(profile)
        return profile
    
    @staticmethod
    def delete_user_profile(db: Session, user_id: int) -> bool:
        """Delete user profile"""
        profile = UserProfileService.get_user_profile(db, user_id)
        if profile:
            db.delete(profile)
            db.commit()
            return True
        return False

class InsightService:
    """Service for managing user insights"""
    
    @staticmethod
    def get_latest_insight(db: Session, user_id: int) -> Optional[Insight]:
        """Get the most recent insight for a user"""
        return db.query(Insight).filter(Insight.user_id == user_id).order_by(Insight.created_at.desc()).first()
    
    @staticmethod
    def get_insights_since(db: Session, user_id: int, since: datetime) -> List[Insight]:
        """Get insights for a user since a specific date"""
        return db.query(Insight).filter(
            Insight.user_id == user_id,
            Insight.created_at >= since
        ).order_by(Insight.created_at.desc()).all()
    
    @staticmethod
    def create_insight(db: Session, user_id: int, content: str, analysis_period: int, insights_type: str = "comprehensive") -> Insight:
        """Create a new insight"""
        insight = Insight(
            user_id=user_id,
            content=content,
            analysis_period=analysis_period,
            insights_type=insights_type
        )
        db.add(insight)
        db.commit()
        db.refresh(insight)
        return insight
    
    @staticmethod
    def should_generate_new_insight(db: Session, user_id: int, days_threshold: int = 7) -> bool:
        """Check if we should generate a new insight based on the last generation time"""
        latest_insight = InsightService.get_latest_insight(db, user_id)
        if not latest_insight:
            return True
        
        # Check if the latest insight is older than the threshold
        threshold_date = datetime.now() - timedelta(days=days_threshold)
        return latest_insight.created_at < threshold_date