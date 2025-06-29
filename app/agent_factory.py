from enum import Enum
from typing import Union
from .calendar_agent import CalendarAgent
from .reflection_agent import ReflectionAgent
from .calendar_service import GoogleCalendarService
from .database import User
from sqlalchemy.orm import Session
from .profile_agent import ProfileAgent

class AgentType(Enum):
    CALENDAR = "calendar"
    REFLECTION = "reflection"
    PROFILE = "profile"


class AgentFactory:
    """Factory for creating different types of AI agents"""
    
    @staticmethod
    def create_agent(
        agent_type: AgentType,
        calendar_service: GoogleCalendarService,
        user_id: int,
        user: User,
        db: Session
    ) -> Union[CalendarAgent, ReflectionAgent, ProfileAgent]:
        """Create an agent of the specified type"""
        
        if agent_type == AgentType.CALENDAR:
            return CalendarAgent(calendar_service, user_id, user, db)
        elif agent_type == AgentType.REFLECTION:
            return ReflectionAgent(calendar_service, user_id, user, db)
        elif agent_type == AgentType.PROFILE:
            return ProfileAgent(calendar_service, user_id, user, db)
        else:
            raise ValueError(f"Unknown agent type: {agent_type}")
    
    @staticmethod
    def get_available_agent_types() -> list[str]:
        """Get list of available agent types"""
        return [agent_type.value for agent_type in AgentType]