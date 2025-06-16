from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import pytz
from typing import List, Optional
from .models import CalendarEvent

class GoogleCalendarService:
    def __init__(self, credentials: Optional[Credentials] = None):
        self.service = None
        self.credentials = credentials
        # Start with UTC, but will be updated based on calendar settings
        self.timezone = pytz.UTC
        self._timezone_detected = False
        
        # Initialize service if credentials provided
        if credentials:
            self._initialize_service()
    
    def _initialize_service(self):
        """Initialize the Google Calendar service with current credentials"""
        if not self.credentials:
            raise Exception("No credentials provided")
        
        # Refresh credentials if expired
        if self.credentials.expired and self.credentials.refresh_token:
            self.credentials.refresh(Request())
        
        self.service = build('calendar', 'v3', credentials=self.credentials)
        
        # Detect timezone on first service initialization
        if not self._timezone_detected:
            self._detect_calendar_timezone()
    
    def set_credentials(self, credentials: Credentials):
        """Set new credentials and reinitialize service"""
        self.credentials = credentials
        self._initialize_service()
    
    def _ensure_service_ready(self):
        """Ensure service is initialized and credentials are fresh"""
        if not self.credentials:
            raise Exception("No calendar credentials found")
        
        if not self.service:
            self._initialize_service()
        
        # Refresh credentials if expired
        if self.credentials.expired and self.credentials.refresh_token:
            self.credentials.refresh(Request())
            # Note: In a real implementation, you'd want to update the database here
            # with the refreshed credentials
    
    def _detect_calendar_timezone(self):
        """Detect and set timezone from calendar settings"""
        if not self.service or self._timezone_detected:
            return
        
        try:
            # Get calendar settings to determine timezone
            calendar_info = self.service.calendars().get(calendarId='primary').execute()
            timezone_id = calendar_info.get('timeZone', 'UTC')
            
            # Update service timezone
            self.timezone = pytz.timezone(timezone_id)
            self._timezone_detected = True
            print(f"Calendar timezone detected: {timezone_id}")
            
        except Exception as e:
            print(f"Could not detect calendar timezone, using UTC: {e}")
            self.timezone = pytz.UTC
            self._timezone_detected = True
    
    def _ensure_timezone_aware(self, dt: datetime) -> datetime:
        """Ensure datetime is timezone-aware, defaulting to service timezone"""
        if dt.tzinfo is None:
            return self.timezone.localize(dt)
        return dt.astimezone(self.timezone)
    
    def _parse_datetime_with_timezone(self, dt_string: str, fallback_timezone: str = None) -> datetime:
        """Parse datetime string and handle timezone information from Google Calendar"""
        try:
            # Handle ISO format with timezone
            if 'T' in dt_string:
                if dt_string.endswith('Z'):
                    # UTC timezone
                    dt = datetime.fromisoformat(dt_string.replace('Z', '+00:00'))
                else:
                    # Has timezone info
                    dt = datetime.fromisoformat(dt_string)
                
                # Convert to calendar's timezone
                return dt.astimezone(self.timezone)
            else:
                # Date-only format (all-day events)
                date_obj = datetime.fromisoformat(dt_string).date()
                dt = datetime.combine(date_obj, datetime.min.time())
                return self.timezone.localize(dt)
        except Exception:
            # Fallback parsing
            dt = datetime.fromisoformat(dt_string.replace('Z', '+00:00'))
            return self._ensure_timezone_aware(dt)
    
    def get_events(self, days_ahead: int = 7, days_back: int = 0) -> List[CalendarEvent]:
        """Get calendar events for the next N days and optionally previous M days"""
        self._ensure_service_ready()
        
        # Detect timezone from calendar settings
        self._detect_calendar_timezone()
        
        # Use timezone-aware datetime for API calls
        now = datetime.now(self.timezone)
        
        # Calculate time range - support both forward and backward
        if days_back > 0:
            time_min = now - timedelta(days=days_back)
        else:
            time_min = now
            
        time_max = now + timedelta(days=days_ahead)
        
        events_result = self.service.events().list(
            calendarId='primary',
            timeMin=time_min.isoformat(),
            timeMax=time_max.isoformat(),
            maxResults=50,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = []
        for event in events_result.get('items', []):
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))
            
            # Parse and ensure timezone consistency
            start_dt = self._parse_datetime_with_timezone(start)
            end_dt = self._parse_datetime_with_timezone(end)
            
            events.append(CalendarEvent(
                id=event['id'],
                title=event.get('summary', 'No Title'),
                start_time=self._ensure_timezone_aware(start_dt),
                end_time=self._ensure_timezone_aware(end_dt),
                description=event.get('description', ''),
                location=event.get('location', '')
            ))
        
        return events
    
    def create_event(self, event: CalendarEvent) -> str:
        """Create a new calendar event"""
        self._ensure_service_ready()
        
        # Ensure timezone consistency for event creation
        start_time = self._ensure_timezone_aware(event.start_time)
        end_time = self._ensure_timezone_aware(event.end_time)
        
        event_body = {
            'summary': event.title,
            'start': {'dateTime': start_time.isoformat()},
            'end': {'dateTime': end_time.isoformat()},
            'description': event.description or '',
            'location': event.location or ''
        }
        
        created_event = self.service.events().insert(
            calendarId='primary',
            body=event_body
        ).execute()
        
        return created_event['id']