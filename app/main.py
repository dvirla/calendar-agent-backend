from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from .models import ChatMessage, ChatResponse, CreateEventRequest, CalendarEvent
from .calendar_service import GoogleCalendarService
from .ai_agent import CalendarAIAgent
from datetime import datetime, timedelta
import os

# Initialize FastAPI app
app = FastAPI(title="Calendar Agent API")

# Add CORS middleware - CORRECTED VERSION
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific URLs
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Initialize services
calendar_service = GoogleCalendarService()
ai_agent = CalendarAIAgent()

@app.get("/")
async def root():
    return {"message": "Calendar Agent API is running!"}

@app.get("/auth/google")
async def auth_google():
    """Initiate Google OAuth flow"""
    try:
        auth_url = calendar_service.get_auth_url()
        return {"auth_url": auth_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating auth URL: {str(e)}")

@app.get("/auth/callback")
async def auth_callback(code: str):
    """Handle Google OAuth callback"""
    try:
        result = calendar_service.handle_oauth_callback(code)
        return RedirectResponse(url="http://localhost:5173?auth=success")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/chat")
async def chat_with_agent(message: ChatMessage):
    """Chat with the AI agent"""
    try:
        # Get user's calendar events for context
        events = []
        try:
            events = calendar_service.get_events(days_ahead=7)
        except:
            pass  # Continue without calendar context if not authenticated
        
        # Chat with AI agent
        response = await ai_agent.chat(message.message, events)
        
        return {
            "response": response.message,
            "suggested_actions": response.suggested_actions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/calendar/events")
async def get_calendar_events():
    """Get user's calendar events"""
    try:
        events = calendar_service.get_events(days_ahead=7)
        return {"events": [event.dict() for event in events]}
    except Exception as e:
        raise HTTPException(status_code=400, detail="Calendar not connected or error fetching events")

@app.post("/calendar/events")
async def create_calendar_event(event_request: CreateEventRequest):
    """Create a new calendar event"""
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
    """Get a daily reflection prompt based on today's completed events"""
    try:
        # Get today's events
        all_events = calendar_service.get_events(days_ahead=1)
        now = datetime.now()
        
        # Filter completed events (events that ended before now)
        completed_events = [
            event for event in all_events 
            if event.end_time < now
        ]
        
        prompt = await ai_agent.daily_reflection_prompt(completed_events)
        return {"prompt": prompt, "completed_events": len(completed_events)}
    except Exception as e:
        return {"prompt": "How was your day today? What did you accomplish?", "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)