from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class ChatMessage(BaseModel):
    message: str
    user_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    suggested_actions: Optional[List[str]] = None

class CalendarEvent(BaseModel):
    id: Optional[str] = None
    title: str
    start_time: datetime
    end_time: datetime
    description: Optional[str] = None
    location: Optional[str] = None

class CreateEventRequest(BaseModel):
    title: str
    start_time: str  # ISO format
    end_time: str    # ISO format
    description: Optional[str] = None
    location: Optional[str] = None