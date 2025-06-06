# app/improved_agent.py
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.azure import AzureProvider
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import pytz
from dataclasses import dataclass
from .config import AZURE_AI_API_KEY, AZURE_AI_O4_ENDPOINT, AZURE_API_VERSION
from .models import CalendarEvent
from .calendar_service import GoogleCalendarService

class AgentResponse(BaseModel):
    message: str
    pending_actions: Optional[List[Dict[str, Any]]] = None
    requires_approval: Optional[bool] = False

class PendingAction(BaseModel):
    action_id: str
    action_type: str  # "create_event", "update_event", "delete_event"
    description: str
    details: Dict[str, Any]

@dataclass
class CalendarDependencies:
    calendar_service: GoogleCalendarService
    pending_actions: Dict[str, PendingAction]

class CalendarAIAgent:
    def __init__(self, calendar_service: GoogleCalendarService):
        self.calendar_service = calendar_service
        self.pending_actions: Dict[str, PendingAction] = {}
        # Initialize with calendar service timezone (will be updated when calendar is accessed)
        self.timezone = getattr(calendar_service, 'timezone', pytz.UTC)
        model = OpenAIModel(
            'o4-mini',
            provider=AzureProvider(
                azure_endpoint=AZURE_AI_O4_ENDPOINT,
                api_version=AZURE_API_VERSION,
                api_key=AZURE_AI_API_KEY,
            ),
        )
        
        self.agent = Agent(
            model,
            deps_type=CalendarDependencies,
            result_type=AgentResponse,
            system_prompt="""You are an autonomous calendar assistant with the following capabilities:

1. **Reading Calendar**: You can autonomously read the user's calendar to understand their schedule
2. **Writing Calendar**: You can propose calendar changes, but MUST get user approval first
3. **Daily Reflection**: Help users reflect on their completed activities
4. **Schedule Planning**: Proactively suggest schedule optimizations

IMPORTANT RULES:
- Always read the calendar first when discussing schedules
- For any calendar modifications, explain what you want to do and ask for approval
- Be proactive - suggest improvements and ask thoughtful questions
- When creating events, always confirm details like time, duration, and description
- Consider the user's existing schedule to avoid conflicts

Available tools:
- get_calendar_events: Read current calendar events
- get_events_for_date: Get events for a specific date
- propose_calendar_event: Propose creating a new event (requires approval)
- get_free_time_slots: Find available time slots
- analyze_schedule_patterns: Analyze user's scheduling patterns

Keep responses conversational and helpful. Always use tools when you need information."""
        )
        
        # Register tools
        self._register_tools()
    
    def _sync_timezone_with_calendar(self):
        """Sync agent timezone with calendar service timezone"""
        if hasattr(self.calendar_service, 'timezone'):
            current_tz = self.calendar_service.timezone
            if current_tz != self.timezone:
                self.timezone = current_tz
                print(f"Agent timezone synced to: {current_tz}")
    
    def _get_timezone_aware_datetime(self, dt: datetime) -> datetime:
        """Convert naive datetime to timezone-aware datetime using calendar timezone"""
        # Ensure we're using the latest calendar timezone
        self._sync_timezone_with_calendar()
        
        if dt.tzinfo is None:
            return self.timezone.localize(dt)
        return dt.astimezone(self.timezone)
    
    def _get_current_time(self) -> datetime:
        """Get current time as timezone-aware datetime using calendar timezone"""
        self._sync_timezone_with_calendar()
        return datetime.now(self.timezone)
    
    def _register_tools(self):
        """Register all available tools with the agent"""

        @self.agent.tool_plain
        async def get_current_date() -> str:
            """
            Get the current date and time.
            """
            now = self._get_current_time()
            return now.isoformat()
        
        @self.agent.tool
        async def get_calendar_events(ctx: RunContext[CalendarDependencies], days_ahead: int = 7) -> List[Dict[str, Any]]:
            """Get the user's calendar events for the next N days"""
            try:
                events = ctx.deps.calendar_service.get_events(days_ahead=days_ahead)
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
                # Parse date and make it timezone-aware
                target_date = datetime.fromisoformat(date)
                if target_date.tzinfo is None:
                    target_date = self.timezone.localize(target_date)
                
                all_events = ctx.deps.calendar_service.get_events(days_ahead=30)
                
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
        async def propose_calendar_event(
            ctx: RunContext[CalendarDependencies],
            title: str,
            start_time: str,  # ISO format
            end_time: str,    # ISO format
            description: str = "",
            location: str = ""
        ) -> Dict[str, Any]:
            """Propose creating a new calendar event - requires user approval"""
            try:
                # Generate unique action ID
                action_id = f"create_{len(ctx.deps.pending_actions) + 1}_{int(datetime.now().timestamp())}"
                
                # Check for conflicts - ensure timezone consistency
                start_dt = datetime.fromisoformat(start_time)
                end_dt = datetime.fromisoformat(end_time)
                
                # Make timezone-aware if needed
                start_dt = self._get_timezone_aware_datetime(start_dt)
                end_dt = self._get_timezone_aware_datetime(end_dt)
                
                existing_events = ctx.deps.calendar_service.get_events(days_ahead=30)
                conflicts = [
                    event for event in existing_events
                    if (start_dt < self._get_timezone_aware_datetime(event.end_time) and 
                        end_dt > self._get_timezone_aware_datetime(event.start_time))
                ]
                
                conflict_warning = ""
                if conflicts:
                    conflict_time = self._get_timezone_aware_datetime(conflicts[0].start_time)
                    conflict_warning = f" ⚠️ Warning: This conflicts with {conflicts[0].title} at {conflict_time.strftime('%H:%M')}"
                
                # Store pending action with timezone-aware times
                pending_action = PendingAction(
                    action_id=action_id,
                    action_type="create_event",
                    description=f"Create '{title}' from {start_dt.strftime('%Y-%m-%d %H:%M')} to {end_dt.strftime('%H:%M')}",
                    details={
                        "title": title,
                        "start_time": start_dt.isoformat(),
                        "end_time": end_dt.isoformat(),
                        "description": description,
                        "location": location
                    }
                )
                ctx.deps.pending_actions[action_id] = pending_action
                
                return {
                    "action_id": action_id,
                    "status": "pending_approval",
                    "message": f"I'd like to create '{title}' from {start_dt.strftime('%m/%d %H:%M')} to {end_dt.strftime('%H:%M')}.{conflict_warning}",
                    "requires_approval": True
                }
            except Exception as e:
                return {"error": f"Could not propose event: {str(e)}"}
        
        @self.agent.tool
        async def get_free_time_slots(
            ctx: RunContext[CalendarDependencies],
            date: str,           # YYYY-MM-DD
            duration_minutes: int = 60,
            business_hours_only: bool = True
        ) -> List[Dict[str, str]]:
            """Find available time slots on a given date"""
            try:
                # Parse date and make timezone-aware
                target_date = datetime.fromisoformat(date)
                if target_date.tzinfo is None:
                    target_date = self.timezone.localize(target_date)
                
                events = await get_events_for_date(ctx, date)
                
                # Define business hours
                start_hour = 9 if business_hours_only else 6
                end_hour = 18 if business_hours_only else 22
                
                # Create time slots with timezone awareness
                current_time = target_date.replace(hour=start_hour, minute=0, second=0, microsecond=0)
                end_time = target_date.replace(hour=end_hour, minute=0, second=0, microsecond=0)
                
                # Ensure timezone consistency
                if current_time.tzinfo is None:
                    current_time = self.timezone.localize(current_time)
                    end_time = self.timezone.localize(end_time)
                
                free_slots = []
                
                while current_time + timedelta(minutes=duration_minutes) <= end_time:
                    slot_end = current_time + timedelta(minutes=duration_minutes)
                    
                    # Check if this slot conflicts with any event
                    conflict = False
                    for event in events:
                        if "error" not in event:
                            # Parse event times with timezone awareness
                            event_start = datetime.combine(target_date.date(), 
                                                         datetime.strptime(event["start_time"], "%H:%M").time())
                            event_end = datetime.combine(target_date.date(), 
                                                       datetime.strptime(event["end_time"], "%H:%M").time())
                            
                            # Make timezone-aware
                            event_start = self.timezone.localize(event_start)
                            event_end = self.timezone.localize(event_end)
                            
                            if (current_time < event_end and slot_end > event_start):
                                conflict = True
                                break
                    
                    if not conflict:
                        free_slots.append({
                            "start_time": current_time.strftime("%H:%M"),
                            "end_time": slot_end.strftime("%H:%M"),
                            "duration_minutes": duration_minutes
                        })
                    
                    current_time += timedelta(minutes=30)  # Check every 30 minutes
                
                return free_slots[:10]  # Return max 10 slots
            except Exception as e:
                return [{"error": f"Could not find free slots: {str(e)}"}]
        
        @self.agent.tool
        async def analyze_schedule_patterns(ctx: RunContext[CalendarDependencies]) -> Dict[str, Any]:
            """Analyze the user's scheduling patterns and provide insights"""
            try:
                events = ctx.deps.calendar_service.get_events(days_ahead=30)
                
                if not events:
                    return {"message": "No recent events to analyze"}
                
                # Analyze patterns
                total_events = len(events)
                meeting_events = [e for e in events if 'meeting' in e.title.lower()]
                work_hours = []
                
                for event in events:
                    hour = event.start_time.hour
                    if 6 <= hour <= 22:  # Reasonable work hours
                        work_hours.append(hour)
                
                avg_start_hour = sum(work_hours) / len(work_hours) if work_hours else 9
                
                return {
                    "total_events": total_events,
                    "meeting_percentage": len(meeting_events) / total_events * 100 if total_events > 0 else 0,
                    "average_start_hour": round(avg_start_hour, 1),
                    "busiest_days": "Analysis shows your schedule patterns",
                    "suggestions": [
                        "Consider blocking focus time if you have many meetings",
                        "Try to batch similar activities together",
                        "Schedule breaks between long meetings"
                    ]
                }
            except Exception as e:
                return {"error": f"Could not analyze schedule: {str(e)}"}
    
    async def chat(self, message: str, user_id: Optional[str] = None) -> AgentResponse:
        """Chat with the autonomous AI agent"""
        try:
            deps = CalendarDependencies(
                calendar_service=self.calendar_service,
                pending_actions=self.pending_actions
            )
            result = await self.agent.run(message, deps=deps)
            
            # Check if there are pending actions that need approval
            has_pending = len(self.pending_actions) > 0
            pending_list = [
                {
                    "action_id": action.action_id,
                    "description": action.description,
                    "type": action.action_type
                }
                for action in self.pending_actions.values()
            ] if has_pending else None
            
            return AgentResponse(
                message=result.data.message,
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
        if action_id not in self.pending_actions:
            return {"error": "Action not found"}
        
        action = self.pending_actions[action_id]
        
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
                
                # Remove from pending
                del self.pending_actions[action_id]
                
                return {
                    "success": True,
                    "message": f"✅ Created '{details['title']}' successfully!",
                    "event_id": event_id
                }
            
            # Add more action types here (update, delete, etc.)
            
        except Exception as e:
            return {"error": f"Failed to execute action: {str(e)}"}
    
    async def reject_action(self, action_id: str) -> Dict[str, Any]:
        """Reject a pending action"""
        if action_id not in self.pending_actions:
            return {"error": "Action not found"}
        
        action = self.pending_actions[action_id]
        del self.pending_actions[action_id]
        
        return {
            "success": True,
            "message": f"❌ Cancelled: {action.description}"
        }
    
    async def daily_reflection_prompt(self) -> str:
        """Generate an autonomous daily reflection prompt"""
        try:
            # Get today's events with timezone awareness
            today = self._get_current_time().strftime("%Y-%m-%d")
            deps = CalendarDependencies(
                calendar_service=self.calendar_service,
                pending_actions=self.pending_actions
            )
            events = await self.agent.run(f"Get my events for today ({today}) and create a thoughtful reflection question about them", deps=deps)
            return events.data.message
        except:
            return "How was your day today? What did you accomplish and what did you learn?"