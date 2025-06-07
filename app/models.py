# app/models.py
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class ChatMessage(BaseModel):
    message: str
    user_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    suggested_actions: Optional[List[str]] = None
    pending_actions: Optional[List[Dict[str, Any]]] = None
    requires_approval: Optional[bool] = False

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

class ActionApprovalRequest(BaseModel):
    action_id: str
    approved: bool
    user_message: Optional[str] = None

class PendingActionResponse(BaseModel):
    action_id: str
    action_type: str
    description: str
    details: Dict[str, Any]
    created_at: datetime