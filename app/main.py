# app/main.py
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from .models import ChatMessage, ChatResponse, CreateEventRequest, CalendarEvent
from .calendar_service import GoogleCalendarService
from .agent_w_tools import CalendarAIAgent
from datetime import datetime, timedelta
import os

app = FastAPI(title="Calendar Agent API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
calendar_service = GoogleCalendarService()
ai_agent = CalendarAIAgent(calendar_service)  # Pass calendar_service to agent

@app.get("/")
async def root():
    return {"message": "Calendar Agent API is running with autonomous tools!"}

@app.get("/auth/google")
async def auth_google():
    """Initiate Google OAuth flow"""
    auth_url = calendar_service.get_auth_url()
    return {"auth_url": auth_url}

@app.get("/auth/callback")
async def auth_callback(code: str):
    """Handle Google OAuth callback"""
    try:
        result = calendar_service.handle_oauth_callback(code)
        return RedirectResponse(url="http://localhost:5173?auth=success")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/chat", response_model=ChatResponse)
async def chat_with_agent(message: ChatMessage):
    """Chat with the autonomous AI agent"""
    try:
        # The agent now autonomously decides when to read calendar
        response = await ai_agent.chat(message.message, message.user_id)
        
        return ChatResponse(
            response=response.message,
            suggested_actions=None,  # Agent handles its own suggestions now
            # Add new fields for pending actions
            pending_actions=response.pending_actions,
            requires_approval=response.requires_approval
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/actions/approve/{action_id}")
async def approve_action(action_id: str):
    """Approve a pending action from the AI agent"""
    try:
        result = await ai_agent.approve_action(action_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/actions/reject/{action_id}")
async def reject_action(action_id: str):
    """Reject a pending action from the AI agent"""
    try:
        result = await ai_agent.reject_action(action_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/actions/pending")
async def get_pending_actions():
    """Get all pending actions that need user approval"""
    try:
        pending = [
            {
                "action_id": action.action_id,
                "description": action.description,
                "type": action.action_type,
                "details": action.details
            }
            for action in ai_agent.pending_actions.values()
        ]
        return {"pending_actions": pending}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/calendar/events")
async def get_calendar_events():
    """Get user's calendar events (now mainly for direct API access)"""
    try:
        events = calendar_service.get_events(days_ahead=7)
        return {"events": [event.dict() for event in events]}
    except Exception as e:
        raise HTTPException(status_code=400, detail="Calendar not connected or error fetching events")

@app.post("/calendar/events")
async def create_calendar_event(event_request: CreateEventRequest):
    """Create a new calendar event directly (bypass agent)"""
    try:
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
async def get_reflection_prompt():
    """Get an autonomous daily reflection prompt"""
    try:
        prompt = await ai_agent.daily_reflection_prompt()
        return {"prompt": prompt}
    except Exception as e:
        return {"prompt": "How was your day today? What did you accomplish?", "error": str(e)}

# New endpoint for testing agent tools
@app.post("/test/agent-tools")
async def test_agent_tools():
    """Test the agent's autonomous capabilities"""
    try:
        test_messages = [
            "What's on my schedule today?",
            "Can you help me find a free hour tomorrow afternoon?",
            "I need to schedule a team meeting for 2 hours sometime next week"
        ]
        
        results = []
        for msg in test_messages:
            response = await ai_agent.chat(msg)
            results.append({
                "question": msg,
                "response": response.message,
                "has_pending_actions": response.requires_approval
            })
        
        return {"test_results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)