from pydantic_ai import RunContext
from typing import Dict, Any
from datetime import datetime, timedelta
import pytz
from .base_agent import BaseAgent
from .agent_dataclasses import CalendarDependencies
import logfire
from .config import LOGFIRE_TOKEN

logfire.configure(token=LOGFIRE_TOKEN, scrubbing=False)  
logfire.instrument_pydantic_ai() 

class ReflectionAgent(BaseAgent):
    """Reflection-focused AI agent for insights and personal growth"""
    
    def __init__(self, calendar_service, user_id, user, db):
        self.calendar_service = calendar_service
        self.user_id = user_id
        self.user = user
        self.db = db
        self.timezone = getattr(calendar_service, 'timezone', pytz.UTC)
        system_prompt = f"""You are a reflection and insights assistant. Current date/time: {self._get_current_time()}

## Core Purpose
- **Analyze**: Review user's activities, conversations, and patterns
- **Reflect**: Generate thoughtful questions and insights about productivity and well-being
- **Guide**: Offer personalized suggestions for improvement and growth

## Rules
1. Focus on meaningful insights, not just data summaries
2. Ask thoughtful questions that promote self-reflection
3. Connect patterns across different time periods
4. Provide actionable suggestions for improvement
5. Be empathetic and encouraging in tone

## Available Tools
- get_calendar_events: Access historical and upcoming events
- get_events_for_date: Review specific day activities
- search_calendar_events: Find patterns in event types
- create_reflection: Generate custom period reflections
- analyze_patterns: Deep dive into behavioral patterns

Keep responses thoughtful and focused on personal growth."""
        
        super().__init__(calendar_service, user_id, user, db, system_prompt)
        self._register_reflection_tools()
    
    def _register_reflection_tools(self):
        """Register reflection-specific tools"""
        
        @self.agent.tool
        async def create_reflection(ctx: RunContext[CalendarDependencies], days: int = 7) -> Dict[str, Any]:
            """Create a detailed reflection based on activities and conversations"""
            try:
                from .database_utils import ConversationService
                
                period_ago = self._get_current_time() - timedelta(days=days)
                conversations = ConversationService.get_user_conversations_since(ctx.deps.db, ctx.deps.user_id, period_ago)
                
                if not conversations:
                    return {"message": f"No conversations found in the past {days} days to reflect on"}
                
                past_events = ctx.deps.calendar_service.get_events(days_ahead=0, days_back=days)
                conversation_count = len(conversations)
                total_messages = sum(len(ConversationService.get_conversation_messages(ctx.deps.db, conv.id)) for conv in conversations)
                for item in past_events:
                    logfire.info(f"Event: {item.title} at {item.start_time} - {item.end_time}")
                # Analyze event types and patterns
                work_events = [e for e in past_events if any(keyword in e.title.lower() for keyword in ['meeting', 'work', 'call', 'standup'])]
                personal_events = [e for e in past_events if any(keyword in e.title.lower() for keyword in ['personal', 'family', 'friend', 'gym', 'lunch'])]
                
                period_text = f"Past {days} day{'s' if days != 1 else ''}"
                
                return {
                    "period": period_text,
                    "conversation_count": conversation_count,
                    "total_messages": total_messages,
                    "events_attended": len(past_events),
                    "work_events": len(work_events),
                    "personal_events": len(personal_events),
                    "reflection": f"Reflecting on the {period_text.lower()}: You engaged in {conversation_count} conversations and attended {len(past_events)} events ({len(work_events)} work-related, {len(personal_events)} personal). This shows a {'balanced' if abs(len(work_events) - len(personal_events)) <= 2 else 'work-heavy' if len(work_events) > len(personal_events) else 'personal-focused'} schedule.",
                    "insights": [
                        f"Your conversation engagement was {'high' if total_messages > conversation_count * 10 else 'moderate' if total_messages > conversation_count * 5 else 'light'} with an average of {total_messages//conversation_count if conversation_count > 0 else 0} messages per conversation",
                        f"Event distribution suggests you're {'maintaining good work-life balance' if abs(len(work_events) - len(personal_events)) <= 2 else 'heavily focused on work - consider more personal time' if len(work_events) > len(personal_events) else 'prioritizing personal activities'}",
                        "Consider what activities brought you the most energy and fulfillment"
                    ],
                    "questions": [
                        "Which conversations or activities from this period do you feel most proud of?",
                        "What patterns do you notice in how you spend your time?",
                        "If you could change one thing about this period, what would it be?",
                        "What did you learn about yourself during these activities?"
                    ]
                }
            except Exception as e:
                return {"error": f"Could not create reflection: {str(e)}"}
        
        @self.agent.tool
        async def analyze_patterns(ctx: RunContext[CalendarDependencies], days_back: int = 30) -> Dict[str, Any]:
            """Deep analysis of behavioral and scheduling patterns"""
            try:
                events = ctx.deps.calendar_service.get_events(days_ahead=0, days_back=days_back)
                
                if not events:
                    return {"message": "No events found for pattern analysis"}
                
                # Time-based analysis
                morning_events = [e for e in events if e.start_time.hour < 12]
                afternoon_events = [e for e in events if 12 <= e.start_time.hour < 17]
                evening_events = [e for e in events if e.start_time.hour >= 17]
                
                # Duration analysis
                total_minutes = sum((e.end_time - e.start_time).total_seconds() / 60 for e in events)
                avg_duration = total_minutes / len(events) if events else 0
                
                # Weekly patterns
                weekday_events = [e for e in events if e.start_time.weekday() < 5]
                weekend_events = [e for e in events if e.start_time.weekday() >= 5]
                
                return {
                    "analysis_period": f"Past {days_back} days",
                    "total_events": len(events),
                    "time_preferences": {
                        "morning": len(morning_events),
                        "afternoon": len(afternoon_events),
                        "evening": len(evening_events)
                    },
                    "schedule_intensity": {
                        "average_event_duration": round(avg_duration, 1),
                        "weekday_events": len(weekday_events),
                        "weekend_events": len(weekend_events)
                    },
                    "insights": [
                        f"You're most active during {'morning' if len(morning_events) >= max(len(afternoon_events), len(evening_events)) else 'afternoon' if len(afternoon_events) >= len(evening_events) else 'evening'} hours",
                        f"Your events average {round(avg_duration, 0)} minutes - {'quite focused and efficient' if avg_duration < 60 else 'thorough and comprehensive' if avg_duration < 120 else 'intensive and deep-dive oriented'}",
                        f"Work-life separation is {'well-maintained' if len(weekend_events) < len(weekday_events) * 0.3 else 'blended - consider protecting weekend time'}"
                    ],
                    "recommendations": [
                        "Consider your natural energy patterns when scheduling important activities",
                        "Look for opportunities to optimize meeting lengths",
                        "Protect time blocks that align with your most productive hours",
                        "Regular reflection helps maintain awareness of these patterns"
                    ]
                }
            except Exception as e:
                return {"error": f"Could not analyze patterns: {str(e)}"}
    
    async def generate_weekly_insights(self) -> str:
        """Generate weekly insights and reflection prompts"""
        try:
            current_pending_actions = []
            deps = CalendarDependencies(
                calendar_service=self.calendar_service,
                user_id=self.user_id,
                user=self.user,
                db=self.db,
                pending_actions=current_pending_actions
            )
            
            result = await self.agent.run("Create a comprehensive 7-day reflection with deep insights and thoughtful questions", deps=deps)
            return result.output.message
        except Exception as e:
            return f"Error generating insights: {str(e)}"