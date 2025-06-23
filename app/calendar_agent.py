from pydantic_ai import RunContext
from typing import List, Dict, Any
from datetime import datetime, timedelta

import pytz
from .base_agent import BaseAgent
from .database_utils import PendingActionService
from .agent_dataclasses import CalendarDependencies


class CalendarAgent(BaseAgent):
    """Calendar-focused AI agent with scheduling capabilities"""
    
    def __init__(self, calendar_service, user_id, user, db):
        self.calendar_service = calendar_service
        self.user_id = user_id
        self.user = user
        self.db = db
        self.timezone = getattr(calendar_service, 'timezone', pytz.UTC)
        system_prompt = f"""You are a calendar scheduling assistant. Current date/time: {self._get_current_time()}

## Core Functions
- **Read**: Access user's calendar autonomously (past and future events)
- **Write**: Propose calendar changes (requires user approval)
- **Plan**: Suggest schedule optimizations for meetings, work blocks, and personal time

## Rules
1. Always check existing calendar before discussing schedules
2. Get explicit approval before any modifications
3. Confirm event details: time, duration, description
4. Avoid scheduling conflicts
5. Be proactive with optimization suggestions

## Available Tools
- get_calendar_events: Read current/future events (supports days_back parameter for historical events)
- get_events_for_date: Get specific date events (past or future)
- search_calendar_events: Search for events by keyword (searches titles, descriptions, locations)
- propose_calendar_event: Create new event (needs approval)
- get_free_time_slots: Find available times
- analyze_schedule_patterns: Analyze scheduling patterns (supports historical analysis)
- create_reflection: Generate a reflection based on conversations and activities

Keep responses conversational. Use tools for all schedule information."""
        
        super().__init__(calendar_service, user_id, user, db, system_prompt)
        self._register_calendar_tools()
    
    def _register_calendar_tools(self):
        """Register calendar-specific tools"""
        
        @self.agent.tool
        async def propose_calendar_event(
            ctx: RunContext[CalendarDependencies],
            title: str,
            start_time: str,
            end_time: str,
            description: str = "",
            location: str = ""
        ) -> Dict[str, Any]:
            """Propose creating a new calendar event - requires user approval"""
            try:
                action_id = f"create_{len(ctx.deps.pending_actions) + 1}_{int(datetime.now().timestamp())}"
                
                start_dt = self._get_timezone_aware_datetime(datetime.fromisoformat(start_time))
                end_dt = self._get_timezone_aware_datetime(datetime.fromisoformat(end_time))
                
                existing_events = ctx.deps.calendar_service.get_events(days_ahead=30, days_back=7)
                conflicts = [
                    event for event in existing_events
                    if (start_dt < self._get_timezone_aware_datetime(event.end_time) and 
                        end_dt > self._get_timezone_aware_datetime(event.start_time))
                ]
                
                conflict_warning = ""
                if conflicts:
                    conflict_time = self._get_timezone_aware_datetime(conflicts[0].start_time)
                    conflict_warning = f" ⚠️ Warning: This conflicts with {conflicts[0].title} at {conflict_time.strftime('%H:%M')}"
                
                PendingActionService.create_pending_action(
                    ctx.deps.db,
                    ctx.deps.user_id,
                    action_id,
                    "create_event",
                    f"Create '{title}' from {start_dt.strftime('%Y-%m-%d %H:%M')} to {end_dt.strftime('%H:%M')}",
                    {
                        "title": title,
                        "start_time": start_dt.isoformat(),
                        "end_time": end_dt.isoformat(),
                        "description": description,
                        "location": location
                    }
                )
                
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
            date: str,
            duration_minutes: int = 60,
            business_hours_only: bool = True
        ) -> List[Dict[str, str]]:
            """Find available time slots on a given date"""
            try:
                target_date = datetime.fromisoformat(date)
                if target_date.tzinfo is None:
                    target_date = self.timezone.localize(target_date)
                
                events = await get_events_for_date(ctx, date)
                
                start_hour = 9 if business_hours_only else 6
                end_hour = 18 if business_hours_only else 22
                
                current_time = target_date.replace(hour=start_hour, minute=0, second=0, microsecond=0)
                end_time = target_date.replace(hour=end_hour, minute=0, second=0, microsecond=0)
                
                if current_time.tzinfo is None:
                    current_time = self.timezone.localize(current_time)
                    end_time = self.timezone.localize(end_time)
                
                free_slots = []
                
                while current_time + timedelta(minutes=duration_minutes) <= end_time:
                    slot_end = current_time + timedelta(minutes=duration_minutes)
                    
                    conflict = False
                    for event in events:
                        if "error" not in event:
                            event_start = datetime.combine(target_date.date(), 
                                                         datetime.strptime(event["start_time"], "%H:%M").time())
                            event_end = datetime.combine(target_date.date(), 
                                                       datetime.strptime(event["end_time"], "%H:%M").time())
                            
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
                    
                    current_time += timedelta(minutes=30)
                
                return free_slots[:10]
            except Exception as e:
                return [{"error": f"Could not find free slots: {str(e)}"}]
        
        @self.agent.tool
        async def analyze_schedule_patterns(ctx: RunContext[CalendarDependencies], days_ahead: int = 30, days_back: int = 30) -> Dict[str, Any]:
            """Analyze the user's scheduling patterns and provide insights"""
            try:
                events = ctx.deps.calendar_service.get_events(days_ahead=days_ahead, days_back=days_back)
                
                if not events:
                    return {"message": "No recent events to analyze"}
                
                total_events = len(events)
                meeting_events = [e for e in events if 'meeting' in e.title.lower()]
                work_hours = []
                
                for event in events:
                    hour = event.start_time.hour
                    if 6 <= hour <= 22:
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
        
        @self.agent.tool
        async def create_reflection(ctx: RunContext[CalendarDependencies], days: int = 7) -> Dict[str, Any]:
            """Create a reflection based on the user's conversations and activities for a custom period"""
            try:
                from .database_utils import ConversationService
                
                period_ago = self._get_current_time() - timedelta(days=days)
                conversations = ConversationService.get_user_conversations_since(ctx.deps.db, ctx.deps.user_id, period_ago)
                
                if not conversations:
                    return {"message": f"No conversations found in the past {days} days to reflect on"}
                
                past_events = ctx.deps.calendar_service.get_events(days_ahead=0, days_back=days)
                conversation_count = len(conversations)
                total_messages = sum(len(ConversationService.get_conversation_messages(ctx.deps.db, conv.id)) for conv in conversations)
                
                period_text = f"Past {days} day{'s' if days != 1 else ''}"
                
                return {
                    "period": period_text,
                    "conversation_count": conversation_count,
                    "total_messages": total_messages,
                    "events_attended": len(past_events),
                    "reflection": f"In the {period_text.lower()} you had {conversation_count} conversations with me and attended {len(past_events)} calendar events. Based on your activity, here are some insights.",
                    "suggestions": [
                        "Review your most productive conversation topics",
                        "Consider scheduling focused work blocks based on your patterns",
                        "Reflect on which activities brought you the most value",
                        "Summarize the topics you discussed and how they relate to your goals"
                    ]
                }
            except Exception as e:
                return {"error": f"Could not create reflection: {str(e)}"}
    
    async def daily_reflection_prompt(self) -> str:
        """Generate an autonomous daily reflection prompt"""
        try:
            today = self._get_current_time().strftime("%Y-%m-%d")
            current_pending_actions = PendingActionService.get_user_pending_actions(self.db, self.user_id)
            
            deps = CalendarDependencies(
                calendar_service=self.calendar_service,
                user_id=self.user_id,
                user=self.user,
                db=self.db,
                pending_actions=current_pending_actions
            )
            events = await self.agent.run(f"Get my events for today ({today}) and create a thoughtful reflection question about them", deps=deps)
            return events.output.message
        except:
            return "How was your day today? What did you accomplish and what did you learn?"