from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.azure import AzureProvider
import logfire
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import pytz
from sqlalchemy.orm import Session
from .config import (
    AZURE_AI_API_KEY, 
    AZURE_AI_O4_ENDPOINT, 
    AZURE_API_VERSION, 
    LOGFIRE_TOKEN, 
    AZURE_MODEL_NAME, 
    MODEL_TEMPRATURE
)
from .models import CalendarEvent
from .calendar_service import GoogleCalendarService
from .database import User
from .database_utils import PendingActionService
from .agent_dataclasses import AgentResponse, CalendarDependencies

logfire.configure(token=LOGFIRE_TOKEN, scrubbing=False)  
logfire.instrument_pydantic_ai()

class BaseAgent:
    """Base class for all AI agents with shared functionality"""
    
    def __init__(self, calendar_service: GoogleCalendarService, user_id: int, user: User, db: Session, system_prompt: str):
        self.calendar_service = calendar_service
        self.user_id = user_id
        self.user = user
        self.db = db
        self.timezone = getattr(calendar_service, 'timezone', pytz.UTC)
        
        model = OpenAIModel(
            AZURE_MODEL_NAME,
            provider=AzureProvider(
                azure_endpoint=AZURE_AI_O4_ENDPOINT,
                api_version=AZURE_API_VERSION,
                api_key=AZURE_AI_API_KEY,
            ),
        )
        
        self.agent = Agent(
            model,
            deps_type=CalendarDependencies,
            output_type=AgentResponse,
            model_settings={"temperature": MODEL_TEMPRATURE},
            system_prompt=system_prompt
        )
        
        self._register_shared_tools()
    
    def _sync_timezone_with_calendar(self):
        """Sync agent timezone with calendar service timezone"""
        if hasattr(self.calendar_service, 'timezone'):
            current_tz = self.calendar_service.timezone
            if current_tz != self.timezone:
                self.timezone = current_tz
    
    def _get_timezone_aware_datetime(self, dt: datetime) -> datetime:
        """Convert naive datetime to timezone-aware datetime using calendar timezone"""
        self._sync_timezone_with_calendar()
        if dt.tzinfo is None:
            return self.timezone.localize(dt)
        return dt.astimezone(self.timezone)
    
    def _get_current_time(self) -> datetime:
        """Get current time as timezone-aware datetime using calendar timezone"""
        self._sync_timezone_with_calendar()
        return datetime.now(self.timezone)
    
    def _register_shared_tools(self):
        """Register shared tools that all agents can use"""
        
        @self.agent.tool
        async def get_calendar_events(ctx: RunContext[CalendarDependencies], days_ahead: int = 7, days_back: int = 0) -> List[Dict[str, Any]]:
            """Get the user's calendar events for the next N days and optionally previous M days"""
            try:
                events = ctx.deps.calendar_service.get_events(days_ahead=days_ahead, days_back=days_back)
                current_time = self._get_current_time()
                return [
                    {
                        "id": event.id,
                        "title": event.title,
                        "start_time": event.start_time.isoformat(),
                        "end_time": event.end_time.isoformat(),
                        "description": event.description or "",
                        "location": event.location or "",
                        "status": "upcoming" if self._get_timezone_aware_datetime(event.start_time) > current_time else "completed"
                    }
                    for event in events
                ]
            except Exception as e:
                return [{"error": f"Could not fetch calendar events: {str(e)}"}]
        
        @self.agent.tool
        async def get_events_for_date(ctx: RunContext[CalendarDependencies], date: str) -> List[Dict[str, Any]]:
            """Get events for a specific date (format: YYYY-MM-DD)"""
            try:
                target_date = datetime.fromisoformat(date)
                if target_date.tzinfo is None:
                    target_date = self.timezone.localize(target_date)
                
                today = self._get_current_time().date()
                if target_date.date() < today:
                    days_back = (today - target_date.date()).days
                    days_ahead = 1
                else:
                    days_back = 0
                    days_ahead = (target_date.date() - today).days + 1
                
                all_events = ctx.deps.calendar_service.get_events(days_ahead=days_ahead, days_back=days_back)
                day_events = [
                    event for event in all_events
                    if self._get_timezone_aware_datetime(event.start_time).date() == target_date.date()
                ]
                
                return [
                    {
                        "title": event.title,
                        "start_time": self._get_timezone_aware_datetime(event.start_time).strftime("%H:%M"),
                        "end_time": self._get_timezone_aware_datetime(event.end_time).strftime("%H:%M"),
                        "description": event.description or "",
                        "duration_minutes": int((self._get_timezone_aware_datetime(event.end_time) - self._get_timezone_aware_datetime(event.start_time)).total_seconds() / 60)
                    }
                    for event in day_events
                ]
            except Exception as e:
                return [{"error": f"Could not fetch events for {date}: {str(e)}"}]
        
        @self.agent.tool
        async def search_calendar_events(
            ctx: RunContext[CalendarDependencies], 
            query: str, 
            max_results: int = 20,
            time_min: Optional[str] = None,
            time_max: Optional[str] = None
        ) -> List[Dict[str, Any]]:
            """Search for events by keyword in titles, descriptions, locations, and attendees"""
            try:
                time_min_dt = None
                time_max_dt = None
                
                if time_min:
                    time_min_dt = datetime.fromisoformat(time_min)
                    if time_min_dt.tzinfo is None:
                        time_min_dt = self.timezone.localize(time_min_dt)
                
                if time_max:
                    time_max_dt = datetime.fromisoformat(time_max)
                    if time_max_dt.tzinfo is None:
                        time_max_dt = self.timezone.localize(time_max_dt)
                
                events = ctx.deps.calendar_service.search_events(
                    query=query,
                    max_results=max_results,
                    time_min=time_min_dt,
                    time_max=time_max_dt
                )
                
                current_time = self._get_current_time()
                return [
                    {
                        "id": event.id,
                        "title": event.title,
                        "start_time": event.start_time.isoformat(),
                        "end_time": event.end_time.isoformat(),
                        "description": event.description or "",
                        "location": event.location or "",
                        "status": "upcoming" if self._get_timezone_aware_datetime(event.start_time) > current_time else "completed",
                        "date": event.start_time.strftime("%Y-%m-%d"),
                        "time": event.start_time.strftime("%H:%M")
                    }
                    for event in events
                ]
            except Exception as e:
                return [{"error": f"Could not search calendar events: {str(e)}"}]
    
    async def chat(self, message: str, user_id: Optional[str] = None, conversation_id: Optional[int] = None) -> AgentResponse:
        """Chat with the AI agent"""
        try:
            current_pending_actions = PendingActionService.get_user_pending_actions(self.db, self.user_id)
            
            deps = CalendarDependencies(
                calendar_service=self.calendar_service,
                user_id=self.user_id,
                user=self.user,
                db=self.db,
                pending_actions=current_pending_actions
            )
            
            message_history = None
            if conversation_id:
                from .database_utils import ConversationService
                from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart, TextPart
                
                messages = ConversationService.get_conversation_messages(self.db, conversation_id)
                message_history = []
                for msg in messages[:-1]:
                    if msg.role == 'user':
                        message_history.append(
                            ModelRequest(parts=[UserPromptPart(content=msg.content, timestamp=msg.timestamp)])
                        )
                    elif msg.role == 'assistant':
                        message_history.append(
                            ModelResponse(
                                parts=[TextPart(content=msg.content)],
                                timestamp=msg.timestamp
                            )
                        )
            
            result = await self.agent.run(message, deps=deps, message_history=message_history)
            
            pending_actions = PendingActionService.get_user_pending_actions(self.db, self.user_id)
            has_pending = len(pending_actions) > 0
            pending_list = [
                {
                    "action_id": action.action_id,
                    "description": action.description,
                    "type": action.action_type
                }
                for action in pending_actions
            ] if has_pending else None
            #TODO: make sure output==data
            return AgentResponse(
                message=result.output.message,
                pending_actions=pending_list,
                requires_approval=has_pending
            )
        except Exception as e:
            return AgentResponse(
                message=f"I encountered an error: {str(e)}. Let me try to help you differently.",
                pending_actions=None,
                requires_approval=False
            )
    
    async def approve_action(self, action_id: str) -> Dict[str, Any]:
        """Approve and execute a pending action"""
        action = PendingActionService.get_pending_action(self.db, action_id, self.user_id)
        if not action:
            return {"error": "Action not found or expired"}
        
        try:
            if action.action_type == "create_event":
                details = action.details
                event = CalendarEvent(
                    title=details["title"],
                    start_time=datetime.fromisoformat(details["start_time"]),
                    end_time=datetime.fromisoformat(details["end_time"]),
                    description=details.get("description", ""),
                    location=details.get("location", "")
                )
                
                event_id = self.calendar_service.create_event(event)
                PendingActionService.delete_pending_action(self.db, action_id, self.user_id)
                
                return {
                    "success": True,
                    "message": f"✅ Created '{details['title']}' successfully!",
                    "event_id": event_id
                }
            
        except Exception as e:
            return {"error": f"Failed to execute action: {str(e)}"}
    
    async def reject_action(self, action_id: str) -> Dict[str, Any]:
        """Reject a pending action"""
        action = PendingActionService.get_pending_action(self.db, action_id, self.user_id)
        if not action:
            return {"error": "Action not found or expired"}
        
        description = action.description
        PendingActionService.delete_pending_action(self.db, action_id, self.user_id)
        
        return {
            "success": True,
            "message": f"❌ Cancelled: {description}"
        }