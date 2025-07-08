# app/models.py
from pydantic import BaseModel, EmailStr
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

# Waitinglist models
class WaitlistSignup(BaseModel):
    email: EmailStr
    name: str
    interestedFeatures: str  # "AI Scheduler", "Reflections", "Both", "other (explain)"
    primaryUsage: str  # "Work", "Private Life", "Work-Life Balance", "other (explain)"
    schedulingFrustration: str  # free text
    currentCalendarTool: str  # "Google Calendar", "Outlook", "Apple Calendar", "Notion", "Pen and Paper", "other (explain)"
    roleProfession: str  # "Entrepreneur/Founder", "Manager/Executive", "Consultant/Freelancer", "Developer/Designer", "Sales/Marketing", "Student", "Other (explain)"
    journalingExperience: str  # "Yes, but quit after a few days", "Yes, still do it sometimes", "No, seems too time-consuming", "No, don't know what to write"
    company: str = ""
    referralSource: str = ""
    utmSource: str = ""
    timestamp: Optional[str] = None
    timezone: Optional[str] = None

class WaitlistResponse(BaseModel):
    success: bool
    position: Optional[int] = None
    message: Optional[str] = None
    error: Optional[str] = None

class WaitlistStats(BaseModel):
    total: int
    roles: Dict[str, int]
    last_signup: Optional[str] = None
    error: Optional[str] = None

class EmailCheck(BaseModel):
    email: EmailStr

class EmailCheckResponse(BaseModel):
    exists: bool

class UserProfileUpdate(BaseModel):
    short_term_goals: Optional[List[str]] = None
    long_term_goals: Optional[List[str]] = None
    work_preferences: Optional[Dict[str, Any]] = None
    personal_interests: Optional[List[str]] = None
    reflection_frequency: Optional[str] = None  # daily, weekly, monthly
    reflection_focus_areas: Optional[List[str]] = None
    communication_tone: Optional[str] = None  # casual, professional, encouraging
    preferred_insights: Optional[List[str]] = None

class UserProfileResponse(BaseModel):
    id: int
    user_id: int
    short_term_goals: Optional[List[str]] = None
    long_term_goals: Optional[List[str]] = None
    work_preferences: Optional[Dict[str, Any]] = None
    personal_interests: Optional[List[str]] = None
    reflection_frequency: str = "weekly"
    reflection_focus_areas: Optional[List[str]] = None
    communication_tone: str = "professional"
    preferred_insights: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime

class ProfileUpdateRequest(BaseModel):
    message: str  # Natural language request to update profile

class InsightResponse(BaseModel):
    id: int
    user_id: int
    content: str
    analysis_period: int
    insights_type: str
    created_at: datetime
    from_cache: bool = False