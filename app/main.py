# app/main.py
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from .models import ChatMessage, ChatResponse, CreateEventRequest, CalendarEvent
from .calendar_service import GoogleCalendarService
from .agent_w_tools import CalendarAIAgent
from .database import Base, engine, User, Conversation
from .database_utils import get_db, UserService, ConversationService, CalendarService, PendingActionService
from .auth import AuthService, get_current_user
from datetime import datetime, timedelta
import os
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from .config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, AUTH_REDIRECT_URI, FRONTEND_URL

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Calendar Agent API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://memomindai.com", "https://www.memomindai.com", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services (will be per-user now)
# calendar_service and ai_agent will be initialized per request with user context

@app.get("/")
async def root():
    return {"message": "Calendar Agent API is running with autonomous tools!"}

@app.get("/auth/google")
async def auth_google():
    """Initiate Google OAuth flow for user authentication and calendar access"""
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [AUTH_REDIRECT_URI]
            }
        },
        scopes=[
            "openid",  # Add this explicitly
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile"
        ]
    )
    # Use production URL if available, otherwise fallback to localhost
    flow.redirect_uri = AUTH_REDIRECT_URI
    
    auth_url, _ = flow.authorization_url(prompt='consent')
    return {"auth_url": auth_url}

@app.get("/auth/callback")
async def auth_callback(code: str, db: Session = Depends(get_db)):
    """Handle Google OAuth callback and create user session"""
    try:
        # Exchange code for tokens
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [AUTH_REDIRECT_URI]
                }
            },
            scopes=[
                "openid",  # Add this explicitly here too
                "https://www.googleapis.com/auth/calendar",
                "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/userinfo.profile"
            ]
        )
        # Use production URL if available, otherwise fallback to localhost
        flow.redirect_uri = AUTH_REDIRECT_URI
        flow.fetch_token(code=code)
        
        credentials = flow.credentials
        
        # Get user info from Google
        from googleapiclient.discovery import build
        service = build('oauth2', 'v2', credentials=credentials)
        user_info = service.userinfo().get().execute()
        
        email = user_info.get('email')
        name = user_info.get('name')
        google_id = user_info.get('id')
        
        # Create or get user
        user = UserService.get_user_by_email(db, email)
        if not user:
            user = UserService.create_user(db, email, name, google_id)
        
        # Save calendar credentials
        credentials_dict = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        CalendarService.save_calendar_credentials(db, user.id, credentials_dict)
        
        # Create JWT token
        access_token = AuthService.create_access_token(data={"sub": email})
        
        frontend_url = FRONTEND_URL
        return RedirectResponse(url=f"{frontend_url}?auth=success&token={access_token}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/chat", response_model=ChatResponse)
async def chat_with_agent(
    message: ChatMessage, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Chat with the autonomous AI agent"""
    try:
        # Get user's calendar credentials
        credentials_dict = CalendarService.get_calendar_credentials(db, current_user.id)
        if not credentials_dict:
            raise HTTPException(status_code=400, detail="Calendar not connected. Please authenticate first.")
        
        # Create credentials object
        credentials = Credentials(
            token=credentials_dict['token'],
            refresh_token=credentials_dict['refresh_token'],
            token_uri=credentials_dict['token_uri'],
            client_id=credentials_dict['client_id'],
            client_secret=credentials_dict['client_secret'],
            scopes=credentials_dict['scopes']
        )
        
        # Initialize user-specific services
        calendar_service = GoogleCalendarService(credentials)
        ai_agent = CalendarAIAgent(calendar_service, current_user.id, current_user, db)
        
        # Create or get conversation (use most recently created, not updated)
        conversations = db.query(Conversation).filter(Conversation.user_id == current_user.id).order_by(Conversation.created_at.desc()).all()
        if not conversations:
            conversation = ConversationService.create_conversation(db, current_user.id, "Chat Session")
        else:
            conversation = conversations[0]  # Use most recently created conversation
        
        # Save user message
        ConversationService.add_message(db, conversation.id, message.message, "user")
        
        # Get agent response with conversation history
        response = await ai_agent.chat(message.message, str(current_user.id), conversation.id)
        
        # Save agent response
        ConversationService.add_message(db, conversation.id, response.message, "assistant")
        
        return ChatResponse(
            response=response.message,
            suggested_actions=None,
            pending_actions=response.pending_actions,
            requires_approval=response.requires_approval
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/actions/approve/{action_id}")
async def approve_action(
    action_id: str, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Approve a pending action from the AI agent"""
    try:
        # Get user's calendar credentials
        credentials_dict = CalendarService.get_calendar_credentials(db, current_user.id)
        if not credentials_dict:
            raise HTTPException(status_code=400, detail="Calendar not connected")
        
        credentials = Credentials(
            token=credentials_dict['token'],
            refresh_token=credentials_dict['refresh_token'],
            token_uri=credentials_dict['token_uri'],
            client_id=credentials_dict['client_id'],
            client_secret=credentials_dict['client_secret'],
            scopes=credentials_dict['scopes']
        )
        
        # Initialize user-specific services
        calendar_service = GoogleCalendarService(credentials)
        ai_agent = CalendarAIAgent(calendar_service, current_user.id, current_user, db)
        
        result = await ai_agent.approve_action(action_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/actions/reject/{action_id}")
async def reject_action(
    action_id: str, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reject a pending action from the AI agent"""
    try:
        # Note: Rejection doesn't need calendar access, but we still need user context
        # Get user's calendar credentials for consistency
        credentials_dict = CalendarService.get_calendar_credentials(db, current_user.id)
        if credentials_dict:
            credentials = Credentials(
                token=credentials_dict['token'],
                refresh_token=credentials_dict['refresh_token'],
                token_uri=credentials_dict['token_uri'],
                client_id=credentials_dict['client_id'],
                client_secret=credentials_dict['client_secret'],
                scopes=credentials_dict['scopes']
            )
            calendar_service = GoogleCalendarService(credentials)
        else:
            calendar_service = GoogleCalendarService()
        
        ai_agent = CalendarAIAgent(calendar_service, current_user.id, current_user, db)
        
        result = await ai_agent.reject_action(action_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/actions/pending")
async def get_pending_actions(current_user: User = Depends(get_current_user),
                                  db: Session = Depends(get_db)):
    """Get all pending actions that need user approval"""
    try:
        # Get pending actions directly from database
        pending_actions = PendingActionService.get_user_pending_actions(db, current_user.id)
        
        pending = [
            {
                "action_id": action.action_id,
                "description": action.description,
                "type": action.action_type,
                "details": action.details
            }
            for action in pending_actions
        ]
        return {"pending_actions": pending}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/calendar/events")
async def get_calendar_events(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's calendar events"""
    try:
        # Get user's calendar credentials
        credentials_dict = CalendarService.get_calendar_credentials(db, current_user.id)
        if not credentials_dict:
            raise HTTPException(status_code=400, detail="Calendar not connected. Please authenticate first.")
        
        credentials = Credentials(
            token=credentials_dict['token'],
            refresh_token=credentials_dict['refresh_token'],
            token_uri=credentials_dict['token_uri'],
            client_id=credentials_dict['client_id'],
            client_secret=credentials_dict['client_secret'],
            scopes=credentials_dict['scopes']
        )
        
        # Initialize user-specific calendar service
        calendar_service = GoogleCalendarService(credentials)
        
        events = calendar_service.get_events(days_ahead=7)
        return {"events": [event.dict() for event in events]}
    except Exception as e:
        raise HTTPException(status_code=400, detail="Calendar not connected or error fetching events")

@app.post("/calendar/events")
async def create_calendar_event(
    event_request: CreateEventRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new calendar event directly (bypass agent)"""
    try:
        # Get user's calendar credentials
        credentials_dict = CalendarService.get_calendar_credentials(db, current_user.id)
        if not credentials_dict:
            raise HTTPException(status_code=400, detail="Calendar not connected. Please authenticate first.")
        
        credentials = Credentials(
            token=credentials_dict['token'],
            refresh_token=credentials_dict['refresh_token'],
            token_uri=credentials_dict['token_uri'],
            client_id=credentials_dict['client_id'],
            client_secret=credentials_dict['client_secret'],
            scopes=credentials_dict['scopes']
        )
        
        # Initialize user-specific calendar service
        calendar_service = GoogleCalendarService(credentials)
        
        event = CalendarEvent(
            title=event_request.title,
            start_time=datetime.fromisoformat(event_request.start_time),
            end_time=datetime.fromisoformat(event_request.end_time),
            description=event_request.description,
            location=event_request.location
        )
        
        event_id = calendar_service.create_event(event)
        return {"message": "Event created successfully", "event_id": event_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/reflection/prompt")
async def get_reflection_prompt(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get an autonomous daily reflection prompt"""
    try:
        # Get user's calendar credentials
        credentials_dict = CalendarService.get_calendar_credentials(db, current_user.id)
        if credentials_dict:
            credentials = Credentials(
                token=credentials_dict['token'],
                refresh_token=credentials_dict['refresh_token'],
                token_uri=credentials_dict['token_uri'],
                client_id=credentials_dict['client_id'],
                client_secret=credentials_dict['client_secret'],
                scopes=credentials_dict['scopes']
            )
            
            calendar_service = GoogleCalendarService(credentials)
            ai_agent = CalendarAIAgent(calendar_service, current_user.id, current_user, db)
            
            prompt = await ai_agent.daily_reflection_prompt()
            return {"prompt": prompt}
        else:
            return {"prompt": "How was your day today? What did you accomplish?"}
    except Exception as e:
        return {"prompt": "How was your day today? What did you accomplish?", "error": str(e)}

# User management endpoints
@app.get("/user/profile")
async def get_user_profile(current_user: User = Depends(get_current_user)):
    """Get current user profile"""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "is_active": current_user.is_active,
        "created_at": current_user.created_at
    }

@app.get("/user/conversations")
async def get_user_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's conversation history"""
    conversations = ConversationService.get_user_conversations(db, current_user.id)
    return {
        "conversations": [
            {
                "id": conv.id,
                "title": conv.title,
                "created_at": conv.created_at,
                "updated_at": conv.updated_at
            }
            for conv in conversations
        ]
    }

@app.get("/user/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get messages from a specific conversation"""
    # Verify conversation belongs to user
    conversations = ConversationService.get_user_conversations(db, current_user.id)
    conv_ids = [conv.id for conv in conversations]
    
    if conversation_id not in conv_ids:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    messages = ConversationService.get_conversation_messages(db, conversation_id)
    return {
        "messages": [
            {
                "id": msg.id,
                "content": msg.content,
                "role": msg.role,
                "timestamp": msg.timestamp
            }
            for msg in messages
        ]
    }

@app.post("/chat/clear")
async def clear_conversation(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Clear the current conversation and start a new one"""
    try:
        # Create a new conversation for the user
        new_conversation = ConversationService.create_conversation(db, current_user.id, "New Chat Session")
        
        return {
            "message": "Conversation cleared successfully",
            "conversation_id": new_conversation.id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# New endpoint for testing agent tools
@app.post("/test/agent-tools")
async def test_agent_tools(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Test the agent's autonomous capabilities"""
    try:
        # Get user's calendar credentials
        credentials_dict = CalendarService.get_calendar_credentials(db, current_user.id)
        if not credentials_dict:
            raise HTTPException(status_code=400, detail="Calendar not connected")
        
        credentials = Credentials(
            token=credentials_dict['token'],
            refresh_token=credentials_dict['refresh_token'],
            token_uri=credentials_dict['token_uri'],
            client_id=credentials_dict['client_id'],
            client_secret=credentials_dict['client_secret'],
            scopes=credentials_dict['scopes']
        )
        
        calendar_service = GoogleCalendarService(credentials)
        ai_agent = CalendarAIAgent(calendar_service, current_user.id, current_user, db)
        
        test_messages = [
            "What's on my schedule today?",
            "Can you help me find a free hour tomorrow afternoon?",
            "I need to schedule a team meeting for 2 hours sometime next week"
        ]
        
        results = []
        for msg in test_messages:
            response = await ai_agent.chat(msg, str(current_user.id))
            results.append({
                "question": msg,
                "response": response.message,
                "has_pending_actions": response.requires_approval
            })
        
        return {"test_results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)