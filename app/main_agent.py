from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from .calendar_service import GoogleCalendarService
from .database import User
from .models import ChatResponse
from pydantic_ai import Agent
import logfire
from .config import (
    AZURE_AI_API_KEY, 
    AZURE_AI_O4_ENDPOINT, 
    AZURE_API_VERSION, 
    AZURE_MODEL_NAME, 
)
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.azure import AzureProvider

class MainAgent:
    """Main agent that routes user requests to appropriate sub-agents"""
    
    def __init__(self, calendar_service: GoogleCalendarService, user_id: int, user: User, db: Session):
        self.calendar_service = calendar_service
        self.user_id = user_id
        self.user = user
        self.db = db
        self.model = OpenAIModel(
            AZURE_MODEL_NAME,
            provider=AzureProvider(
                azure_endpoint=AZURE_AI_O4_ENDPOINT,
                api_version=AZURE_API_VERSION,
                api_key=AZURE_AI_API_KEY,
            ),
        )
        # Create the routing agent
        self.routing_agent = Agent(
            self.model,
            system_prompt="""You are a routing agent that decides which specialized agent should handle a user's request.
            
            Available agents:
            1. CALENDAR - Handles calendar operations, scheduling, event management, availability checking
            2. REFLECTION - Handles personal reflection, insights, journaling, goal tracking, and self-improvement
            
            Based on the user's message, determine which agent should handle the request.
            
            Rules:
            - If the user is asking about calendar events, scheduling, meetings, appointments, or time management -> CALENDAR
            - If the user is asking about reflection, insights, journaling, goals, personal growth, or self-improvement -> REFLECTION
            - If the message is ambiguous or could be either, prefer CALENDAR as the default
            - Respond with only the agent type: either "CALENDAR" or "REFLECTION"
            """,
            # deps_type=None
        )
    
    async def chat(self, message: str, user_id: str, conversation_id: Optional[int] = None) -> ChatResponse:
        """Route the message to the appropriate sub-agent"""
        try:
            # Import here to avoid circular import
            from .agent_factory import AgentFactory, AgentType
            
            # Use the routing agent to determine which sub-agent to use
            routing_result = await self.routing_agent.run(message)
            chosen_agent_type = routing_result.output.strip().upper()
            
            logfire.info(f"Main agent routing decision: {chosen_agent_type} for message: {message[:50]}...")
            
            # Map string to AgentType enum
            if chosen_agent_type == "CALENDAR":
                agent_type = AgentType.CALENDAR
            elif chosen_agent_type == "REFLECTION":
                agent_type = AgentType.REFLECTION
            else:
                # Default to calendar if unclear
                agent_type = AgentType.CALENDAR
                logfire.warning(f"Unknown agent type '{chosen_agent_type}', defaulting to CALENDAR")
            
            # Create the appropriate sub-agent
            sub_agent = AgentFactory.create_agent(
                agent_type,
                self.calendar_service,
                self.user_id,
                self.user,
                self.db
            )
            
            # Forward the message to the sub-agent
            return await sub_agent.chat(message, user_id, conversation_id)
            
        except Exception as e:
            logfire.error(f"Error in main agent routing: {e}")
            # Fallback to calendar agent on error
            from .agent_factory import AgentFactory, AgentType
            calendar_agent = AgentFactory.create_agent(
                AgentType.CALENDAR,
                self.calendar_service,
                self.user_id,
                self.user,
                self.db
            )
            return await calendar_agent.chat(message, user_id, conversation_id)
    
    async def approve_action(self, action_id: str) -> Dict[str, Any]:
        """Approve action - delegate to calendar agent since only it has pending actions"""
        from .agent_factory import AgentFactory, AgentType
        calendar_agent = AgentFactory.create_agent(
            AgentType.CALENDAR,
            self.calendar_service,
            self.user_id,
            self.user,
            self.db
        )
        return await calendar_agent.approve_action(action_id)
    
    async def reject_action(self, action_id: str) -> Dict[str, Any]:
        """Reject action - delegate to calendar agent since only it has pending actions"""
        from .agent_factory import AgentFactory, AgentType
        calendar_agent = AgentFactory.create_agent(
            AgentType.CALENDAR,
            self.calendar_service,
            self.user_id,
            self.user,
            self.db
        )
        return await calendar_agent.reject_action(action_id)
    
    async def generate_insights(self, days: int = 7) -> str:
        """Generate insights for a custom time period - delegate to reflection agent"""
        from .agent_factory import AgentFactory, AgentType
        reflection_agent = AgentFactory.create_agent(
            AgentType.REFLECTION,
            self.calendar_service,
            self.user_id,
            self.user,
            self.db
        )
        return await reflection_agent.generate_insights(days)
    