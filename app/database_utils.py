from sqlalchemy.orm import Session
from .database import SessionLocal, User, Conversation, Message, CalendarConnection
from typing import Optional, List
import json
from cryptography.fernet import Fernet
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