from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.azure import AzureProvider
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from .config import AZURE_AI_API_KEY, AZURE_AI_O4_ENDPOINT, AZURE_API_VERSION
from .models import CalendarEvent

class AgentResponse(BaseModel):
    message: str
    suggested_actions: Optional[List[str]] = None
    calendar_action: Optional[str] = None

class CalendarAIAgent:
    def __init__(self):
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
            result_type=AgentResponse,
            system_prompt="""You are a helpful calendar assistant. You help users:
            1. Plan and organize their schedule
            2. Reflect on their daily activities
            3. Suggest improvements for productivity
            4. Create calendar events when requested
            
            When users ask about their schedule, provide context-aware responses.
            If they want to create an event, set calendar_action to "create_event".
            Always be encouraging and helpful with daily reflection questions.
            
            Keep responses conversational and friendly, around 1-2 sentences unless more detail is needed."""
        )
    
    async def chat(self, message: str, calendar_events: List[CalendarEvent] = None) -> AgentResponse:
        """Chat with the AI agent, providing calendar context"""
        
        # Prepare context about user's calendar
        calendar_context = ""
        if calendar_events:
            calendar_context = "User's upcoming events:\n"
            for event in calendar_events[:5]:  # Show next 5 events
                calendar_context += f"- {event.title} at {event.start_time.strftime('%Y-%m-%d %H:%M')}\n"
        
        # Combine user message with calendar context
        full_message = f"{calendar_context}\n\nUser message: {message}"
        
        try:
            result = await self.agent.run(full_message)
            return result.data
        except Exception as e:
            return AgentResponse(
                message=f"I'm having trouble processing that. Could you try rephrasing? (Error: {str(e)})",
                suggested_actions=["Try asking about your schedule", "Ask me to create an event"]
            )
    
    async def daily_reflection_prompt(self, completed_events: List[CalendarEvent]) -> str:
        """Generate a daily reflection prompt based on completed events"""
        if not completed_events:
            return "How was your day today? What did you accomplish?"
        
        events_text = "\n".join([f"- {event.title}" for event in completed_events])
        prompt = f"Generate a thoughtful reflection question about these completed activities:\n{events_text}"
        
        try:
            result = await self.agent.run(prompt)
            return result.data.message
        except:
            return f"I see you completed {len(completed_events)} activities today. How did they go? What did you learn?"