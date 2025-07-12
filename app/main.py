# app/main.py
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from .models import ChatMessage, ChatResponse, CreateEventRequest, CalendarEvent, WaitlistSignup, WaitlistResponse, WaitlistStats, EmailCheck, EmailCheckResponse, InsightResponse, InsightContent, InsightSection
from .calendar_service import GoogleCalendarService
from .agent_w_tools import CalendarAIAgent
from .database import Base, engine, User, Conversation, Insight
from .database_utils import get_db, UserService, ConversationService, CalendarService, PendingActionService, InsightService
from .auth import AuthService, get_current_user
from datetime import datetime, timedelta, timezone
import os
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from .config import (
    GOOGLE_CLIENT_ID, 
    GOOGLE_CLIENT_SECRET, 
    LOGFIRE_TOKEN, 
    AUTH_REDIRECT_URI, 
    FRONTEND_URL
)
from .verification_service import VerificationService
import logfire
from .waitinglist_service import WaitlistManager
from .main_agent import MainAgent
from .insight_agent import InsightAgent
from .dashboard_service import DashboardService

logfire.configure(token=LOGFIRE_TOKEN, scrubbing=False)  
logfire.instrument_pydantic_ai() 
# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Calendar Agent API")
verification_service = VerificationService()

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

# Initialize waitlist manager
try:
    waitlist = WaitlistManager()
except Exception as e:
    print(f"Warning: Could not initialize waitlist manager: {e}")
    waitlist = None

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
        verification_result = verification_service.validate_user_input(message.message, current_user.id)
        logfire.info(f"User {current_user.id}, verification_result: {verification_result}")
        if not verification_result['valid']:
            return ChatResponse(
                response=verification_result['error'],
                suggested_actions=None,
                pending_actions=None,
                requires_approval=None
            )
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
        ai_agent = MainAgent(
            calendar_service, 
            current_user.id, 
            current_user, 
            db
        )
        
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
        assistant_message = ConversationService.add_message(db, conversation.id, response.message, "assistant")
        
        # If the response contains analytics (from ReflectionAgent), update the user message
        if response.analytics:
            # Get the most recent user message from this conversation
            messages = ConversationService.get_conversation_messages(db, conversation.id)
            user_messages = [msg for msg in messages if msg.role == 'user']
            if user_messages:
                latest_user_message = user_messages[-1]
                ConversationService.update_message_analytics(
                    db,
                    latest_user_message.id,
                    sentiment_score=response.analytics.sentiment_score,
                    energy_level=response.analytics.energy_level,
                    stress_level=response.analytics.stress_level,
                    satisfaction_level=response.analytics.satisfaction_level
                )
                # Update conversation analytics as well
                ConversationService.update_conversation_analytics(db, conversation.id)
        
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
        ai_agent = MainAgent(
            calendar_service, 
            current_user.id, 
            current_user, 
            db
        )
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
        
        ai_agent = MainAgent(
            calendar_service, 
            current_user.id, 
            current_user, 
            db
        )
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
        return {"events": [event.model_dump() for event in events]}
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
            ai_agent = MainAgent(
            calendar_service, 
            current_user.id, 
            current_user, 
            db
        )
            #TODO: make it costume time period
            prompt = await ai_agent.generate_insights()
            return {"prompt": prompt}
        else:
            return {"prompt": "How was your day today? What did you accomplish?"}
    except Exception as e:
        logfire.error(f"Error: {e}")
        return {"prompt": "How was your day today? What did you accomplish?", "error": str(e)}

@app.post("/reflection/chat", response_model=ChatResponse)
async def chat_with_reflection_agent(
    message: ChatMessage, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Chat with the reflection AI agent for insights and personal growth"""
    try:
        verification_result = verification_service.validate_user_input(message.message, current_user.id)
        if not verification_result['valid']:
            return ChatResponse(
                response=verification_result['error'],
                suggested_actions=None,
                pending_actions=None,
                requires_approval=None
            )
        
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
        calendar_service = GoogleCalendarService(credentials)
        ai_agent = MainAgent(
            calendar_service, 
            current_user.id, 
            current_user, 
            db
        )
        conversations = db.query(Conversation).filter(Conversation.user_id == current_user.id).order_by(Conversation.created_at.desc()).all()
        if not conversations:
            conversation = ConversationService.create_conversation(db, current_user.id, "Reflection Chat Session")
        else:
            conversation = conversations[0]  # Use most recently created conversation
        ConversationService.add_message(db, conversation.id, message.message, "user")
        response = await ai_agent.chat(message.message, str(current_user.id), conversation.id)
        ConversationService.add_message(db, conversation.id, response.message, "assistant")
        
        return ChatResponse(
            response=response.message,
            suggested_actions=None,
            pending_actions=response.pending_actions,
            requires_approval=response.requires_approval
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/insights/get_insights", response_model=InsightResponse)
async def get_insights(
    days: int = 7,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get comprehensive behavioral insights for the user"""
    try:
        # Check if we should generate new insights or use cached ones
        if not InsightService.should_generate_new_insight(db, current_user.id, days_threshold=7):
            # Return the latest cached insight
            latest_insight = InsightService.get_latest_insight(db, current_user.id)
            if latest_insight:
                logfire.info(f"Returning cached insights for user {current_user.id}")
                content_dict = latest_insight.content
                
                insight_content = InsightContent(
                    goal_alignment=content_dict.get('goal_alignment', {}),
                    energy_management=content_dict.get('energy_management', {}),
                    time_allocation=content_dict.get('time_allocation', {}),
                    behavioral_trends=content_dict.get('behavioral_trends', {}),
                )
                insight_response = InsightResponse(
                    id=latest_insight.id,
                    user_id=latest_insight.user_id,
                    content=insight_content,
                    analysis_period=latest_insight.analysis_period,
                    insights_type=latest_insight.insights_type,
                    created_at=latest_insight.created_at,
                    from_cache=True
                )
                logfire.info(f"Sending insights to user {current_user.id}: period={latest_insight.analysis_period} days, type={latest_insight.insights_type}, from_cache=True")
                return insight_response
        
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
        calendar_service = GoogleCalendarService(credentials)
        insight_agent = InsightAgent(
            calendar_service,
            current_user.id,
            current_user,
            db
        )
        insights_content_dict = await insight_agent.generate_comprehensive_insights(days)
        insight_record = InsightService.create_insight(
            db, 
            current_user.id, 
            insights_content_dict, 
            days, 
            "comprehensive"
        )
        insight_content = InsightContent(
            goal_alignment=insights_content_dict.get('goal_alignment', {}),
            energy_management=insights_content_dict.get('energy_management', {}),
            time_allocation=insights_content_dict.get('time_allocation', {}),
            behavioral_trends=insights_content_dict.get('behavioral_trends', {}),
        )
        insight_response = InsightResponse(
            id=insight_record.id,
            user_id=insight_record.user_id,
            content=insight_content,
            analysis_period=insight_record.analysis_period,
            insights_type=insight_record.insights_type,
            created_at=insight_record.created_at,
            from_cache=False
        )
        logfire.info(f"Sending insights to user {current_user.id}: period={days} days, type=comprehensive, from_cache=False")
        return insight_response
        
    except Exception as e:
        logfire.error(f"Error generating insights: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating insights: {str(e)}")

        
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
        ai_agent = MainAgent(
            calendar_service, 
            current_user.id, 
            current_user, 
            db
        )
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

# Waitinglist endpoints
@app.post("/api/waitlist", response_model=WaitlistResponse)
async def add_to_waitlist(signup: WaitlistSignup):
    """Handle waitlist signup"""
    if not waitlist:
        raise HTTPException(status_code=503, detail="Waitlist service unavailable")
    
    try:
        data = signup.model_dump()
        
        # Add to waitlist
        result = waitlist.add_to_waitlist(data)
        
        # if result['success']:
        return WaitlistResponse(**result)
        # else:
        #     raise HTTPException(status_code=400, detail=result.get('error', 'Failed to add to waitlist'))
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/waitlist/stats", response_model=WaitlistStats)
async def get_waitlist_stats():
    """Get waitlist statistics"""
    if not waitlist:
        raise HTTPException(status_code=503, detail="Waitlist service unavailable")
    
    try:
        stats = waitlist.get_waitlist_stats()
        if stats['error']:
            raise HTTPException(status_code=500, detail=stats['error'])
        return WaitlistStats(**stats)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/waitlist/check", response_model=EmailCheckResponse)
async def check_existing(email_check: EmailCheck):
    """Check if email already exists"""
    if not waitlist:
        raise HTTPException(status_code=503, detail="Waitlist service unavailable")
    
    try:
        exists = waitlist.check_existing_signup(email_check.email)
        return EmailCheckResponse(exists=exists)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Dashboard analytics endpoint
@app.get("/dashboard/analytics")
async def get_dashboard_analytics(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get analytics data for dashboard visualization"""
    try:
        analytics_data = DashboardService.get_analytics_data(db, current_user.id, days)
        return analytics_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)