from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from sqlalchemy.orm import Session
from .calendar_service import GoogleCalendarService
from .database import User

class MessageAnalytics(BaseModel):
    sentiment_score: Optional[float] = None  # -5.0 to 5.0
    energy_level: Optional[int] = None       # 1 to 10
    stress_level: Optional[int] = None       # 1 to 10
    satisfaction_level: Optional[int] = None # 1 to 10

class AgentResponse(BaseModel):
    message: str
    pending_actions: Optional[List[Dict[str, Any]]] = None
    requires_approval: Optional[bool] = False
    analytics: Optional[MessageAnalytics] = None

class PendingAction(BaseModel):
    action_id: str
    action_type: str  # "create_event", "update_event", "delete_event"
    description: str
    details: Dict[str, Any]

@dataclass
class CalendarDependencies:
    calendar_service: GoogleCalendarService
    user_id: int
    user: User
    db: Session
    pending_actions: Optional[List[PendingAction]] = None
    
@dataclass
class ReflectionDependencies:
    calendar_service: GoogleCalendarService
    user_id: int
    user: User
    db: Session
    pending_actions: Optional[List[PendingAction]] = None